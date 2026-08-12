import re
import uuid
from datetime import datetime, timezone

from app.agents import chat_agent
from app.agents.chat.tools import definitions
from app.core.config import settings
from app.models import AnalysisJob, Blogger, OutboxEvent, Tweet, User, UserBloggerFollow


class _SessionProxy:
    def __init__(self, session):
        self._session = session

    def __getattr__(self, name):
        return getattr(self._session, name)

    def close(self):
        pass


def test_chat_analysis_confirmation_creates_and_dispatches_durable_jobs(
    db_session, monkeypatch
):
    user = User(
        id=uuid.uuid4(),
        email=f"user-{uuid.uuid4()}@example.test",
        username=f"user-{uuid.uuid4()}",
        password_hash="x",
        status="active",
    )
    blogger = Blogger(handle=f"analyst{uuid.uuid4().hex[:7]}", name="Analyst")
    db_session.add_all([user, blogger])
    db_session.flush()
    db_session.add(UserBloggerFollow(user_id=user.id, blogger_id=blogger.id))
    db_session.add(
        Tweet(
            tweet_id=str(uuid.uuid4()),
            author_handle=blogger.handle,
            content="market update",
            published_at=datetime.now(timezone.utc),
            status="pending",
        )
    )
    db_session.flush()

    monkeypatch.setattr(settings, "user_analysis_requests_enabled", True)
    monkeypatch.setattr(definitions, "SessionLocal", lambda: _SessionProxy(db_session))

    preview = chat_agent.preview_tweet_analysis.invoke(
        {"blogger_handle": blogger.handle},
        config={"metadata": {"user_id": str(user.id)}},
    )
    confirmation_id = re.search(r"确认ID: ([0-9a-f-]+)", preview).group(1)
    awaiting = (
        db_session.query(AnalysisJob)
        .filter_by(
            requested_by_user_id=user.id,
            status="awaiting_confirmation",
        )
        .one()
    )

    result = chat_agent.confirm_tweet_analysis.invoke(
        {"task_id": confirmation_id},
        config={"metadata": {"user_id": str(user.id)}},
    )

    db_session.refresh(awaiting)
    assert "已提交分析任务" in result
    assert awaiting.status == "queued"
    assert awaiting.celery_task_id == str(awaiting.id)
    event = (
        db_session.query(OutboxEvent)
        .filter_by(event_type="analysis.job_requested")
        .one()
    )
    assert event.payload["job_id"] == str(awaiting.id)
    assert event.payload["task_id"] == str(awaiting.id)
