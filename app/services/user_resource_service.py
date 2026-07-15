"""User-scoped follows and tweet bookmarks over shared resources."""

from uuid import UUID, uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import (
    Blogger,
    Tweet,
    User,
    UserBloggerFollow,
    UserTweetBookmark,
)


class ResourceNotFound(Exception):
    """Raised when a requested shared resource does not exist."""


class ResourceLimitExceeded(Exception):
    """Raised when a user has reached a resource limit."""


def _follow_for(
    db: Session, user_id: UUID, blogger_id: UUID
) -> UserBloggerFollow | None:
    return db.execute(
        select(UserBloggerFollow).where(
            UserBloggerFollow.user_id == user_id,
            UserBloggerFollow.blogger_id == blogger_id,
        )
    ).scalar_one_or_none()


def follow_blogger(
    db: Session,
    user_id: UUID,
    blogger_id: UUID,
    *,
    max_follows: int,
) -> UserBloggerFollow:
    if db.execute(
        select(User.id).where(User.id == user_id).with_for_update()
    ).scalar_one_or_none() is None:
        raise ResourceNotFound("user")

    if db.execute(
        select(Blogger.id).where(Blogger.id == blogger_id).with_for_update()
    ).scalar_one_or_none() is None:
        raise ResourceNotFound("blogger")

    existing = _follow_for(db, user_id, blogger_id)
    if existing is None:
        current_count = db.execute(
            select(func.count())
            .select_from(UserBloggerFollow)
            .where(UserBloggerFollow.user_id == user_id)
        ).scalar_one()
        if current_count >= max_follows:
            raise ResourceLimitExceeded("Follow limit exceeded")

    db.execute(
        insert(UserBloggerFollow)
        .values(id=uuid4(), user_id=user_id, blogger_id=blogger_id)
        .on_conflict_do_nothing(constraint="uq_user_blogger_follow")
    )
    db.flush()
    relationship = _follow_for(db, user_id, blogger_id)
    if relationship is None:  # pragma: no cover - database invariant
        raise RuntimeError("Follow relationship was not persisted")
    return relationship


def unfollow_blogger(db: Session, user_id: UUID, blogger_id: UUID) -> bool:
    result = db.execute(
        delete(UserBloggerFollow).where(
            UserBloggerFollow.user_id == user_id,
            UserBloggerFollow.blogger_id == blogger_id,
        )
    )
    return result.rowcount > 0


def list_followed_bloggers(
    db: Session,
    user_id: UUID,
    *,
    limit: int,
    offset: int,
) -> tuple[list[Blogger], int]:
    total = db.execute(
        select(func.count())
        .select_from(UserBloggerFollow)
        .where(UserBloggerFollow.user_id == user_id)
    ).scalar_one()
    bloggers = db.execute(
        select(Blogger)
        .join(
            UserBloggerFollow,
            UserBloggerFollow.blogger_id == Blogger.id,
        )
        .where(UserBloggerFollow.user_id == user_id)
        .order_by(
            UserBloggerFollow.created_at.desc(),
            UserBloggerFollow.id.desc(),
        )
        .limit(limit)
        .offset(offset)
    ).scalars().all()
    return list(bloggers), total


def _bookmark_for(
    db: Session, user_id: UUID, tweet_id: UUID
) -> UserTweetBookmark | None:
    return db.execute(
        select(UserTweetBookmark).where(
            UserTweetBookmark.user_id == user_id,
            UserTweetBookmark.tweet_id == tweet_id,
        )
    ).scalar_one_or_none()


def bookmark_tweet(
    db: Session, user_id: UUID, tweet_id: UUID
) -> UserTweetBookmark:
    if db.execute(
        select(User.id).where(User.id == user_id).with_for_update()
    ).scalar_one_or_none() is None:
        raise ResourceNotFound("user")

    if db.execute(
        select(Tweet.id).where(Tweet.id == tweet_id).with_for_update()
    ).scalar_one_or_none() is None:
        raise ResourceNotFound("tweet")

    db.execute(
        insert(UserTweetBookmark)
        .values(id=uuid4(), user_id=user_id, tweet_id=tweet_id)
        .on_conflict_do_nothing(constraint="uq_user_tweet_bookmark")
    )
    db.flush()
    relationship = _bookmark_for(db, user_id, tweet_id)
    if relationship is None:  # pragma: no cover - database invariant
        raise RuntimeError("Bookmark relationship was not persisted")
    return relationship


def remove_tweet_bookmark(
    db: Session, user_id: UUID, tweet_id: UUID
) -> bool:
    result = db.execute(
        delete(UserTweetBookmark).where(
            UserTweetBookmark.user_id == user_id,
            UserTweetBookmark.tweet_id == tweet_id,
        )
    )
    return result.rowcount > 0


def list_bookmarked_tweets(
    db: Session,
    user_id: UUID,
    *,
    limit: int,
    offset: int,
) -> tuple[list[Tweet], int]:
    total = db.execute(
        select(func.count())
        .select_from(UserTweetBookmark)
        .where(UserTweetBookmark.user_id == user_id)
    ).scalar_one()
    tweets = db.execute(
        select(Tweet)
        .join(
            UserTweetBookmark,
            UserTweetBookmark.tweet_id == Tweet.id,
        )
        .where(UserTweetBookmark.user_id == user_id)
        .order_by(
            UserTweetBookmark.created_at.desc(),
            UserTweetBookmark.id.desc(),
        )
        .limit(limit)
        .offset(offset)
    ).scalars().all()
    return list(tweets), total
