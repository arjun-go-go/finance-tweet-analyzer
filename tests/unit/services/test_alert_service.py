from datetime import datetime, timezone
from uuid import uuid4

from app.models import Blogger, TrackedTicker, User, UserBloggerFollow
from app.services.alert_service import _create_alert, _interested_user_ids, list_alerts, update_alert


def _user(alias: str) -> User:
    return User(
        id=uuid4(),
        email=f"{alias}-{uuid4()}@example.test",
        username=f"{alias}-{uuid4()}",
        password_hash="unused",
    )


def test_alert_recipients_come_from_formal_follow_or_active_ticker(db_session):
    follower = _user("follower")
    tracker = _user("tracker")
    unrelated = _user("unrelated")
    blogger = Blogger(handle="alert_author", name="Alert Author")
    db_session.add_all([follower, tracker, unrelated, blogger])
    db_session.flush()
    db_session.add_all([
        UserBloggerFollow(user_id=follower.id, blogger_id=blogger.id),
        TrackedTicker(user_id=tracker.id, ticker="BTC", status="active", config={}),
        TrackedTicker(user_id=unrelated.id, ticker="ETH", status="paused", config={}),
    ])
    db_session.flush()

    recipients = _interested_user_ids(
        db_session,
        blogger_handle="ALERT_AUTHOR",
        tickers=["BTC"],
    )

    assert recipients == {follower.id, tracker.id}


def test_alert_is_deduplicated_and_user_can_mark_it_read(db_session):
    user = _user("reader")
    db_session.add(user)
    db_session.flush()
    payload = {
        "user_id": user.id,
        "alert_key": "prediction:one:created",
        "kind": "new_prediction",
        "severity": "info",
        "title": "New BTC prediction",
        "message": "Evidence-backed prediction",
        "source_type": "prediction",
        "source_id": "one",
        "target_url": "/bloggers/author",
        "ticker": "BTC",
        "blogger_handle": "author",
        "occurred_at": datetime.now(timezone.utc),
    }

    assert _create_alert(db_session, **payload) is True
    db_session.flush()
    assert _create_alert(db_session, **payload) is False
    alerts = list_alerts(db_session, user.id, status="unread", limit=10, offset=0)
    assert alerts["total"] == alerts["unread"] == 1

    updated = update_alert(db_session, user.id, uuid4(), action="read")
    assert updated is None
    alert_id = alerts["items"][0]["id"]
    from uuid import UUID

    updated = update_alert(db_session, user.id, UUID(alert_id), action="read")
    assert updated["status"] == "read"
    assert list_alerts(db_session, user.id, status="unread", limit=10, offset=0)["total"] == 0
