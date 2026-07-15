from datetime import datetime, timedelta, timezone
from threading import Event, Thread
from time import monotonic
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import sessionmaker

from app.models import (
    Blogger,
    Tweet,
    User,
    UserBloggerFollow,
)
from app.services.user_resource_service import (
    ResourceLimitExceeded,
    ResourceNotFound,
    bookmark_tweet,
    follow_blogger,
    list_bookmarked_tweets,
    list_followed_bloggers,
    remove_tweet_bookmark,
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


def _tweet(alias: str) -> Tweet:
    return Tweet(
        tweet_id=str(uuid4()),
        author_handle=alias,
        content=f"tweet from {alias}",
        published_at=datetime.now(timezone.utc),
    )


def _persist(db_session, *objects) -> None:
    db_session.add_all(objects)
    db_session.flush()


def test_follow_blogger_is_idempotent_and_returns_same_relationship(db_session):
    user = _user("reader")
    blogger = _blogger("analyst")
    _persist(db_session, user, blogger)

    first = follow_blogger(db_session, user.id, blogger.id, max_follows=3)
    second = follow_blogger(db_session, user.id, blogger.id, max_follows=3)

    assert second.id == first.id
    assert second.user_id == user.id
    assert second.blogger_id == blogger.id


def test_bookmark_tweet_is_idempotent(db_session):
    user = _user("reader")
    tweet = _tweet("analyst")
    _persist(db_session, user, tweet)

    first = bookmark_tweet(db_session, user.id, tweet.id)
    second = bookmark_tweet(db_session, user.id, tweet.id)

    assert second.id == first.id
    assert second.user_id == user.id
    assert second.tweet_id == tweet.id


def test_follow_limit_is_per_user_and_existing_follow_remains_idempotent(db_session):
    first_user = _user("first")
    second_user = _user("second")
    first_blogger = _blogger("first-blogger")
    second_blogger = _blogger("second-blogger")
    _persist(db_session, first_user, second_user, first_blogger, second_blogger)

    existing = follow_blogger(
        db_session, first_user.id, first_blogger.id, max_follows=1
    )

    with pytest.raises(ResourceLimitExceeded):
        follow_blogger(
            db_session, first_user.id, second_blogger.id, max_follows=1
        )

    repeated = follow_blogger(
        db_session, first_user.id, first_blogger.id, max_follows=1
    )
    other_user_follow = follow_blogger(
        db_session, second_user.id, second_blogger.id, max_follows=1
    )

    assert repeated.id == existing.id
    assert other_user_follow.user_id == second_user.id


def test_lists_are_user_scoped_counted_and_ordered_by_relationship_time(db_session):
    first_user = _user("first")
    second_user = _user("second")
    old_blogger = _blogger("old")
    new_blogger = _blogger("new")
    other_blogger = _blogger("other")
    old_tweet = _tweet("old")
    new_tweet = _tweet("new")
    other_tweet = _tweet("other")
    _persist(
        db_session,
        first_user,
        second_user,
        old_blogger,
        new_blogger,
        other_blogger,
        old_tweet,
        new_tweet,
        other_tweet,
    )

    old_follow = follow_blogger(
        db_session, first_user.id, old_blogger.id, max_follows=5
    )
    new_follow = follow_blogger(
        db_session, first_user.id, new_blogger.id, max_follows=5
    )
    follow_blogger(db_session, second_user.id, other_blogger.id, max_follows=5)
    old_bookmark = bookmark_tweet(db_session, first_user.id, old_tweet.id)
    new_bookmark = bookmark_tweet(db_session, first_user.id, new_tweet.id)
    bookmark_tweet(db_session, second_user.id, other_tweet.id)

    now = datetime.now(timezone.utc)
    old_follow.created_at = now - timedelta(hours=1)
    new_follow.created_at = now
    old_bookmark.created_at = now - timedelta(hours=1)
    new_bookmark.created_at = now
    db_session.flush()

    bloggers, blogger_total = list_followed_bloggers(
        db_session, first_user.id, limit=1, offset=0
    )
    tweets, tweet_total = list_bookmarked_tweets(
        db_session, first_user.id, limit=1, offset=0
    )
    other_bloggers, other_blogger_total = list_followed_bloggers(
        db_session, second_user.id, limit=10, offset=0
    )
    other_tweets, other_tweet_total = list_bookmarked_tweets(
        db_session, second_user.id, limit=10, offset=0
    )

    assert [item.id for item in bloggers] == [new_blogger.id]
    assert blogger_total == 2
    assert [item.id for item in tweets] == [new_tweet.id]
    assert tweet_total == 2
    assert [item.id for item in other_bloggers] == [other_blogger.id]
    assert other_blogger_total == 1
    assert [item.id for item in other_tweets] == [other_tweet.id]
    assert other_tweet_total == 1


def test_delete_operations_are_user_scoped_and_report_whether_deleted(db_session):
    owner = _user("owner")
    other_user = _user("other")
    blogger = _blogger("analyst")
    tweet = _tweet("analyst")
    _persist(db_session, owner, other_user, blogger, tweet)
    follow_blogger(db_session, owner.id, blogger.id, max_follows=3)
    bookmark_tweet(db_session, owner.id, tweet.id)

    assert unfollow_blogger(db_session, other_user.id, blogger.id) is False
    assert remove_tweet_bookmark(db_session, other_user.id, tweet.id) is False
    assert unfollow_blogger(db_session, owner.id, blogger.id) is True
    assert remove_tweet_bookmark(db_session, owner.id, tweet.id) is True
    assert unfollow_blogger(db_session, owner.id, blogger.id) is False
    assert remove_tweet_bookmark(db_session, owner.id, tweet.id) is False


@pytest.mark.parametrize("resource_kind", ["blogger", "tweet"])
def test_missing_shared_target_raises_safe_not_found(db_session, resource_kind):
    user = _user("reader")
    _persist(db_session, user)
    missing_id = uuid4()

    with pytest.raises(ResourceNotFound) as exc_info:
        if resource_kind == "blogger":
            follow_blogger(db_session, user.id, missing_id, max_follows=3)
        else:
            bookmark_tweet(db_session, user.id, missing_id)

    assert str(missing_id) not in str(exc_info.value)


@pytest.mark.parametrize("resource_kind", ["blogger", "tweet"])
def test_missing_user_raises_not_found_without_breaking_transaction(
    db_session, resource_kind
):
    target = _blogger("analyst") if resource_kind == "blogger" else _tweet("analyst")
    _persist(db_session, target)

    with pytest.raises(ResourceNotFound, match="^user$"):
        if resource_kind == "blogger":
            follow_blogger(db_session, uuid4(), target.id, max_follows=3)
        else:
            bookmark_tweet(db_session, uuid4(), target.id)

    assert db_session.scalar(select(func.count()).select_from(User)) >= 0


def test_same_created_at_uses_relationship_id_as_stable_tiebreaker(db_session):
    user = _user("reader")
    first_blogger = _blogger("first")
    second_blogger = _blogger("second")
    first_tweet = _tweet("first")
    second_tweet = _tweet("second")
    _persist(
        db_session,
        user,
        first_blogger,
        second_blogger,
        first_tweet,
        second_tweet,
    )

    first_follow = follow_blogger(
        db_session, user.id, first_blogger.id, max_follows=5
    )
    second_follow = follow_blogger(
        db_session, user.id, second_blogger.id, max_follows=5
    )
    first_bookmark = bookmark_tweet(db_session, user.id, first_tweet.id)
    second_bookmark = bookmark_tweet(db_session, user.id, second_tweet.id)
    tied_at = datetime.now(timezone.utc)
    first_follow.id = UUID(int=1)
    second_follow.id = UUID(int=2)
    first_bookmark.id = UUID(int=3)
    second_bookmark.id = UUID(int=4)
    first_follow.created_at = tied_at
    second_follow.created_at = tied_at
    first_bookmark.created_at = tied_at
    second_bookmark.created_at = tied_at
    db_session.flush()

    bloggers, _ = list_followed_bloggers(
        db_session, user.id, limit=10, offset=0
    )
    tweets, _ = list_bookmarked_tweets(db_session, user.id, limit=10, offset=0)

    assert [item.id for item in bloggers] == [
        second_blogger.id,
        first_blogger.id,
    ]
    assert [item.id for item in tweets] == [second_tweet.id, first_tweet.id]


def test_concurrent_follows_competing_for_last_slot_enforce_hard_limit(engine):
    user = _user("concurrent")
    first_blogger = _blogger("first-concurrent")
    second_blogger = _blogger("second-concurrent")
    SessionFactory = sessionmaker(bind=engine, expire_on_commit=False)
    setup = SessionFactory()
    setup.add_all([user, first_blogger, second_blogger])
    setup.commit()
    setup.close()

    session_a = SessionFactory()
    b_started = Event()
    b_done = Event()
    b_state = {}

    def attempt_second_follow():
        session_b = SessionFactory()
        try:
            b_state["pid"] = session_b.scalar(text("select pg_backend_pid()"))
            b_started.set()
            follow_blogger(
                session_b, user.id, second_blogger.id, max_follows=1
            )
            session_b.commit()
            b_state["outcome"] = "success"
        except ResourceLimitExceeded:
            session_b.rollback()
            b_state["outcome"] = "limited"
        except BaseException as exc:
            session_b.rollback()
            b_state["error"] = exc
        finally:
            session_b.close()
            b_done.set()

    worker = Thread(target=attempt_second_follow)
    try:
        follow_blogger(
            session_a, user.id, first_blogger.id, max_follows=1
        )
        worker.start()
        assert b_started.wait(timeout=10), "session B did not start"

        lock_observed = False
        deadline = monotonic() + 10
        with engine.connect() as observer:
            while monotonic() < deadline and not b_done.is_set():
                wait_event_type = observer.scalar(
                    text(
                        "select wait_event_type from pg_stat_activity "
                        "where pid = :pid"
                    ),
                    {"pid": b_state["pid"]},
                )
                if wait_event_type == "Lock":
                    lock_observed = True
                    break
                b_done.wait(timeout=0.05)

        assert lock_observed, "session B never waited on the user row lock"
        assert not b_done.is_set()

        session_a.commit()
        assert b_done.wait(timeout=10), "session B stayed blocked after commit"
        assert "error" not in b_state
        assert b_state["outcome"] == "limited"

        verification = SessionFactory()
        final_count = verification.scalar(
            select(func.count())
            .select_from(UserBloggerFollow)
            .where(UserBloggerFollow.user_id == user.id)
        )
        verification.close()

        assert final_count == 1
    finally:
        session_a.rollback()
        session_a.close()
        if worker.ident is not None:
            worker.join(timeout=10)
        assert not worker.is_alive(), "session B thread did not terminate"

        cleanup = SessionFactory()
        cleanup.execute(
            delete(UserBloggerFollow).where(
                UserBloggerFollow.user_id == user.id
            )
        )
        cleanup.execute(
            delete(Blogger).where(
                Blogger.id.in_([first_blogger.id, second_blogger.id])
            )
        )
        cleanup.execute(delete(User).where(User.id == user.id))
        cleanup.commit()
        cleanup.close()


def test_service_does_not_commit_caller_transaction(db_session, monkeypatch):
    user = _user("reader")
    blogger = _blogger("analyst")
    tweet = _tweet("analyst")
    _persist(db_session, user, blogger, tweet)

    def fail_if_committed():
        pytest.fail("service must not commit the caller-owned transaction")

    monkeypatch.setattr(db_session, "commit", fail_if_committed)

    follow_blogger(db_session, user.id, blogger.id, max_follows=3)
    bookmark_tweet(db_session, user.id, tweet.id)
    list_followed_bloggers(db_session, user.id, limit=10, offset=0)
    list_bookmarked_tweets(db_session, user.id, limit=10, offset=0)
    unfollow_blogger(db_session, user.id, blogger.id)
    remove_tweet_bookmark(db_session, user.id, tweet.id)
