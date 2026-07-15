from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import HTTPException

from app.api import me
from app.core.config import settings
from app.models import AnalysisJob, Blogger, Tweet, User, UserBloggerFollow
from app.services.analysis_job_service import create_analysis_job


def _user_and_tweet(db_session, auth, alias: str):
    user = User(
        id=UUID(auth.user_id(alias)),
        email=f"{alias}-{uuid4()}@example.test",
        username=f"{alias}-{uuid4()}",
        password_hash="x",
        status="active",
    )
    target = Tweet(
        tweet_id=str(uuid4()),
        author_handle="analyst",
        content="market update",
        published_at=datetime.now(timezone.utc),
    )
    db_session.add_all([user, target])
    db_session.flush()
    return user, target


def test_disabled_and_limited_requests_never_dispatch(
    client, db_session, auth, monkeypatch
):
    _, target = _user_and_tweet(db_session, auth, "limited")
    calls = []
    monkeypatch.setattr(me.celery, "send_task", lambda *a, **k: calls.append(1))

    monkeypatch.setattr(settings, "user_analysis_requests_enabled", False)
    response = client.post(
        "/api/me/analysis-jobs",
        json={"kind": "tweet_analysis", "target_id": str(target.id)},
        headers=auth.headers("limited"),
    )
    assert response.status_code == 404

    monkeypatch.setattr(settings, "user_analysis_requests_enabled", True)

    def deny_limit(*args, **kwargs):
        raise HTTPException(status_code=429, detail="analysis limit exceeded")

    monkeypatch.setattr(me, "enforce_user_limit", deny_limit)
    response = client.post(
        "/api/me/analysis-jobs",
        json={"kind": "tweet_analysis", "target_id": str(target.id)},
        headers=auth.headers("limited"),
    )

    assert response.status_code == 429
    assert calls == []


def test_create_get_list_and_dispatch_failure(
    client, db_session, auth, monkeypatch
):
    user, target = _user_and_tweet(db_session, auth, "owner")
    monkeypatch.setattr(settings, "user_analysis_requests_enabled", True)
    monkeypatch.setattr(me, "enforce_user_limit", lambda *a, **k: None)
    sent = []

    def send_task(name, *, args, task_id, queue):
        sent.append((name, args, task_id, queue))

    monkeypatch.setattr(me.celery, "send_task", send_task)
    response = client.post(
        "/api/me/analysis-jobs",
        json={"kind": "tweet_analysis", "target_id": str(target.id)},
        headers=auth.headers("owner"),
    )

    assert response.status_code == 202
    body = response.json()
    assert "celery_task_id" not in body
    job_id = body["id"]
    assert sent == [
        (
            "app.scheduler.tasks.user_analysis_job_task",
            [job_id],
            job_id,
            "analysis",
        )
    ]
    assert db_session.get(AnalysisJob, UUID(job_id)).celery_task_id == job_id
    assert (
        client.get(
            f"/api/me/analysis-jobs/{job_id}", headers=auth.headers("owner")
        ).status_code
        == 200
    )
    assert (
        client.get(
            "/api/me/analysis-jobs", headers=auth.headers("owner")
        ).json()["total"]
        == 1
    )

    def fail_dispatch(*args, **kwargs):
        raise RuntimeError("secret broker details")

    monkeypatch.setattr(me.celery, "send_task", fail_dispatch)
    response = client.post(
        "/api/me/analysis-jobs",
        json={"kind": "tweet_analysis", "target_id": str(target.id)},
        headers=auth.headers("owner"),
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Analysis queue unavailable"
    assert (
        db_session.query(AnalysisJob)
        .filter_by(requested_by_user_id=user.id, status="failed")
        .count()
        == 1
    )


def test_blogger_job_requires_current_user_follow(
    client, db_session, auth, monkeypatch
):
    owner, _ = _user_and_tweet(db_session, auth, "blogger-owner")
    other = User(
        id=UUID(auth.user_id("other-blogger-owner")),
        email=f"other-{uuid4()}@example.test",
        username=f"other-{uuid4()}",
        password_hash="x",
        status="active",
    )
    blogger = Blogger(handle=f"analyst-{uuid4()}", name="Analyst")
    db_session.add_all([other, blogger])
    db_session.flush()
    db_session.add(UserBloggerFollow(user_id=other.id, blogger_id=blogger.id))
    db_session.flush()
    monkeypatch.setattr(settings, "user_analysis_requests_enabled", True)
    monkeypatch.setattr(me, "enforce_user_limit", lambda *a, **k: None)
    monkeypatch.setattr(me.celery, "send_task", lambda *a, **k: None)

    response = client.post(
        "/api/me/analysis-jobs",
        json={"kind": "blogger_analysis", "target_id": str(blogger.id)},
        headers=auth.headers("blogger-owner"),
    )
    assert response.status_code == 403

    db_session.add(UserBloggerFollow(user_id=owner.id, blogger_id=blogger.id))
    db_session.flush()
    response = client.post(
        "/api/me/analysis-jobs",
        json={"kind": "blogger_analysis", "target_id": str(blogger.id)},
        headers=auth.headers("blogger-owner"),
    )
    assert response.status_code == 202


def test_confirm_analysis_jobs_dispatches_only_current_user_jobs(
    client, db_session, auth, monkeypatch
):
    owner, target = _user_and_tweet(db_session, auth, "confirm-owner")
    other = User(
        id=UUID(auth.user_id("confirm-other")),
        email=f"confirm-other-{uuid4()}@example.test",
        username=f"confirm-other-{uuid4()}",
        password_hash="x",
        status="active",
    )
    db_session.add(other)
    db_session.flush()
    own_job = create_analysis_job(
        db_session,
        owner.id,
        kind="tweet_analysis",
        target_id=target.id,
        pipeline_version="v1",
        status="awaiting_confirmation",
    )
    other_job = create_analysis_job(
        db_session,
        other.id,
        kind="tweet_analysis",
        target_id=target.id,
        pipeline_version="v1",
        status="awaiting_confirmation",
    )
    db_session.commit()
    sent = []
    monkeypatch.setattr(settings, "user_analysis_requests_enabled", True)
    monkeypatch.setattr(me, "enforce_user_limit", lambda *a, **k: None)
    monkeypatch.setattr(
        me.celery,
        "send_task",
        lambda name, *, args, task_id, queue: sent.append(
            (name, args, task_id, queue)
        ),
    )

    response = client.post(
        "/api/me/analysis-jobs/confirm",
        json={"job_ids": [str(own_job.id), str(other_job.id)]},
        headers=auth.headers("confirm-owner"),
    )

    assert response.status_code == 200
    assert response.json()["confirmed"] == [str(own_job.id)]
    db_session.refresh(own_job)
    db_session.refresh(other_job)
    assert own_job.status == "queued"
    assert own_job.celery_task_id == str(own_job.id)
    assert other_job.status == "awaiting_confirmation"
    assert sent == [
        (
            "app.scheduler.tasks.user_analysis_job_task",
            [str(own_job.id)],
            str(own_job.id),
            "analysis",
        )
    ]
