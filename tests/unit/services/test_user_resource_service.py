from uuid import uuid4

import pytest

from app.models import Blogger, User
from app.services.user_resource_service import (
    ResourceLimitExceeded,
    follow_blogger,
    list_followed_bloggers,
    unfollow_blogger,
)


def _user(alias: str) -> User:
    return User(
        id=uuid4(),
        email=f"{alias}-{uuid4()}@example.test",
        username=f"{alias}-{uuid4()}",
        password_hash="unused",
    )


def _blogger(alias: str) -> Blogger:
    return Blogger(handle=f"{alias}-{uuid4()}", name=alias)


def test_follow_is_idempotent_scoped_and_removable(db_session):
    user = _user("reader")
    blogger = _blogger("analyst")
    db_session.add_all([user, blogger])
    db_session.flush()

    first = follow_blogger(db_session, user.id, blogger.id, max_follows=3)
    second = follow_blogger(db_session, user.id, blogger.id, max_follows=3)
    items, total = list_followed_bloggers(
        db_session, user.id, limit=20, offset=0
    )

    assert first.id == second.id
    assert total == 1
    assert [item.id for item in items] == [blogger.id]
    assert unfollow_blogger(db_session, user.id, blogger.id) is True
    assert unfollow_blogger(db_session, user.id, blogger.id) is False


def test_follow_limit_applies_only_to_new_relationships(db_session):
    user = _user("reader")
    first = _blogger("first")
    second = _blogger("second")
    db_session.add_all([user, first, second])
    db_session.flush()

    existing = follow_blogger(db_session, user.id, first.id, max_follows=1)
    assert follow_blogger(db_session, user.id, first.id, max_follows=1).id == existing.id
    with pytest.raises(ResourceLimitExceeded):
        follow_blogger(db_session, user.id, second.id, max_follows=1)
