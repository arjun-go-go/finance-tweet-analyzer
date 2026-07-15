import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError

import app.models as models


def test_personal_resource_models_are_registered() -> None:
    expected_tables = {
        "user_blogger_follows",
        "user_tweet_bookmarks",
        "analysis_jobs",
    }

    assert expected_tables <= set(models.Base.metadata.tables)
    assert models.UserBloggerFollow.__table__.name == "user_blogger_follows"
    assert models.UserTweetBookmark.__table__.name == "user_tweet_bookmarks"
    assert models.AnalysisJob.__table__.name == "analysis_jobs"


def test_analysis_result_exposes_cache_identity_fields() -> None:
    columns = models.AnalysisResult.__table__.columns

    assert columns["cache_key"].type.length == 64
    assert columns["cache_key"].nullable is True
    assert columns["pipeline_version"].type.length == 32
    assert columns["pipeline_version"].nullable is False
    assert columns["pipeline_version"].server_default.arg == "v1"


def _user(alias: str) -> models.User:
    return models.User(
        email=f"{alias}@example.test",
        username=alias,
        password_hash="unused",
    )


def _blogger(handle: str) -> models.Blogger:
    return models.Blogger(handle=handle)


def _tweet(tweet_id: str) -> models.Tweet:
    return models.Tweet(
        tweet_id=tweet_id,
        author_handle="boundary-test",
        content="A test tweet",
        published_at=datetime.now(UTC),
    )


def test_follow_pair_is_unique_in_postgresql(db_session) -> None:
    user = _user(f"follow-{uuid.uuid4().hex}")
    blogger = _blogger(f"follow-{uuid.uuid4().hex}")
    db_session.add_all([user, blogger])
    db_session.flush()
    db_session.add_all(
        [
            models.UserBloggerFollow(user_id=user.id, blogger_id=blogger.id),
            models.UserBloggerFollow(user_id=user.id, blogger_id=blogger.id),
        ]
    )

    with pytest.raises(IntegrityError) as exc_info:
        db_session.flush()

    assert exc_info.value.orig.diag.constraint_name == "uq_user_blogger_follow"


def test_bookmark_pair_is_unique_in_postgresql(db_session) -> None:
    user = _user(f"bookmark-{uuid.uuid4().hex}")
    tweet = _tweet(f"bookmark-{uuid.uuid4().hex}")
    db_session.add_all([user, tweet])
    db_session.flush()
    db_session.add_all(
        [
            models.UserTweetBookmark(user_id=user.id, tweet_id=tweet.id),
            models.UserTweetBookmark(user_id=user.id, tweet_id=tweet.id),
        ]
    )

    with pytest.raises(IntegrityError) as exc_info:
        db_session.flush()

    assert exc_info.value.orig.diag.constraint_name == "uq_user_tweet_bookmark"


def test_analysis_job_requires_requesting_user_in_postgresql(db_session) -> None:
    db_session.add(models.AnalysisJob(kind="tweet_analysis"))

    with pytest.raises(IntegrityError) as exc_info:
        db_session.flush()

    assert exc_info.value.orig.diag.column_name == "requested_by_user_id"
