from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.models import AnalysisResult, Blogger, Tweet, User, UserBloggerFollow
from app.services.analysis_job_service import (
    AnalysisJobForbidden,
    AnalysisJobNotFound,
    AnalysisJobTargetNotFound,
    create_analysis_job,
    get_analysis_job,
    list_analysis_jobs,
    mark_analysis_job_dispatch_failed,
    run_user_analysis_job,
)


def _user(db_session, name: str) -> User:
    value = User(
        email=f"{name}-{uuid4()}@example.test",
        username=f"{name}-{uuid4()}",
        password_hash="x",
        status="active",
    )
    db_session.add(value)
    db_session.flush()
    return value


def _tweet(db_session) -> Tweet:
    value = Tweet(
        tweet_id=str(uuid4()),
        author_handle="analyst",
        content="market update",
        published_at=datetime.now(timezone.utc),
    )
    db_session.add(value)
    db_session.flush()
    return value


def test_create_tweet_job_validates_target_status_and_payload(db_session):
    owner = _user(db_session, "owner")
    target = _tweet(db_session)

    job = create_analysis_job(
        db_session,
        owner.id,
        kind="tweet_analysis",
        target_id=target.id,
        pipeline_version="v1",
    )

    assert job.status == "queued"
    assert job.request_payload == {
        "target_id": str(target.id),
        "pipeline_version": "v1",
    }
    assert job.reused_result is False

    with pytest.raises(AnalysisJobTargetNotFound):
        create_analysis_job(
            db_session,
            owner.id,
            kind="tweet_analysis",
            target_id=uuid4(),
            pipeline_version="v1",
        )

    with pytest.raises(ValueError):
        create_analysis_job(
            db_session,
            owner.id,
            kind="other",
            target_id=target.id,
            pipeline_version="v1",
        )


def test_blogger_job_requires_existing_follow_for_same_user(db_session):
    owner = _user(db_session, "owner")
    other = _user(db_session, "other")
    blogger = Blogger(handle=f"analyst-{uuid4()}", name="Analyst")
    db_session.add(blogger)
    db_session.flush()

    with pytest.raises(AnalysisJobTargetNotFound):
        create_analysis_job(
            db_session,
            owner.id,
            kind="blogger_analysis",
            target_id=uuid4(),
            pipeline_version="v1",
        )

    db_session.add(UserBloggerFollow(user_id=other.id, blogger_id=blogger.id))
    db_session.flush()
    with pytest.raises(AnalysisJobForbidden):
        create_analysis_job(
            db_session,
            owner.id,
            kind="blogger_analysis",
            target_id=blogger.id,
            pipeline_version="v1",
        )

    db_session.add(UserBloggerFollow(user_id=owner.id, blogger_id=blogger.id))
    db_session.flush()
    job = create_analysis_job(
        db_session,
        owner.id,
        kind="blogger_analysis",
        target_id=blogger.id,
        pipeline_version="v1",
    )
    assert job.kind == "blogger_analysis"


def test_owner_scoped_get_list_and_safe_dispatch_failure(db_session):
    owner = _user(db_session, "owner")
    other = _user(db_session, "other")
    target = _tweet(db_session)
    own = create_analysis_job(
        db_session,
        owner.id,
        kind="tweet_analysis",
        target_id=target.id,
        pipeline_version="v1",
    )
    foreign = create_analysis_job(
        db_session,
        other.id,
        kind="tweet_analysis",
        target_id=target.id,
        pipeline_version="v1",
    )

    with pytest.raises(AnalysisJobNotFound):
        get_analysis_job(db_session, owner.id, foreign.id)

    items, total = list_analysis_jobs(db_session, owner.id, limit=10, offset=0)
    assert items == [own]
    assert total == 1

    failed = mark_analysis_job_dispatch_failed(db_session, own)
    assert failed.status == "failed"
    assert failed.error_code == "dispatch_failed"
    assert failed.error_summary == (
        "Analysis job could not be queued. Please retry later."
    )


def test_run_tweet_job_reuses_cached_analysis_without_llm(db_session):
    owner = _user(db_session, "owner")
    target = _tweet(db_session)
    cached = AnalysisResult(
        tweet_id=target.id,
        analysis_type="tweet_analysis",
        result={"signal": "cached"},
        model_used="test",
        confidence=0.9,
        pipeline_version="v1",
    )
    db_session.add(cached)
    db_session.flush()
    job = create_analysis_job(
        db_session,
        owner.id,
        kind="tweet_analysis",
        target_id=target.id,
        pipeline_version="v1",
    )
    db_session.commit()
    calls = []

    result = run_user_analysis_job(
        db_session,
        job.id,
        pipeline_version="v1",
        analyze_single_tweet=lambda *args: calls.append(args),
        analyze_by_blogger=lambda *args: calls.append(args),
    )

    db_session.refresh(job)
    db_session.refresh(cached)
    assert result["reused_result"] is True
    assert calls == []
    assert job.status == "completed"
    assert job.reused_result is True
    assert cached.cache_key is not None


def test_run_tweet_job_analyzes_cache_miss_and_completes(db_session):
    owner = _user(db_session, "owner")
    target = _tweet(db_session)
    job = create_analysis_job(
        db_session,
        owner.id,
        kind="tweet_analysis",
        target_id=target.id,
        pipeline_version="v1",
    )
    db_session.commit()

    def analyze_single_tweet(db, tweet_id):
        db.add(
            AnalysisResult(
                tweet_id=target.id,
                analysis_type="tweet_analysis",
                result={"signal": "fresh"},
                model_used="test",
                confidence=0.8,
                pipeline_version="v1",
            )
        )
        db.flush()
        return {"batch_id": str(uuid4()), "analyzed": 1}

    result = run_user_analysis_job(
        db_session,
        job.id,
        pipeline_version="v1",
        analyze_single_tweet=analyze_single_tweet,
        analyze_by_blogger=lambda *args: {"batch_id": str(uuid4())},
    )

    db_session.refresh(job)
    assert result["reused_result"] is False
    assert result["analyzed"] == 1
    assert job.status == "completed"
    assert job.reused_result is False
    assert job.batch_id is not None


def test_run_blogger_job_reuses_cache_when_no_pending_tweets(db_session):
    owner = _user(db_session, "owner")
    blogger = Blogger(handle=f"analyst-{uuid4()}", name="Analyst")
    db_session.add(blogger)
    db_session.flush()
    db_session.add(UserBloggerFollow(user_id=owner.id, blogger_id=blogger.id))
    target = Tweet(
        tweet_id=str(uuid4()),
        author_handle=blogger.handle,
        content="market update",
        published_at=datetime.now(timezone.utc),
        status="analyzed",
    )
    db_session.add(target)
    db_session.flush()
    db_session.add(
        AnalysisResult(
            tweet_id=target.id,
            analysis_type="tweet_analysis",
            result={"signal": "cached"},
            model_used="test",
            confidence=0.8,
            pipeline_version="v1",
        )
    )
    db_session.flush()
    job = create_analysis_job(
        db_session,
        owner.id,
        kind="blogger_analysis",
        target_id=blogger.id,
        pipeline_version="v1",
    )
    db_session.commit()
    calls = []

    result = run_user_analysis_job(
        db_session,
        job.id,
        pipeline_version="v1",
        analyze_single_tweet=lambda *args: calls.append(args),
        analyze_by_blogger=lambda *args: calls.append(args),
    )

    db_session.refresh(job)
    assert result["reused_result"] is True
    assert result["cached_count"] == 1
    assert calls == []
    assert job.status == "completed"
