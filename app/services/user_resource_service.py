"""User-scoped follows over shared Twitter blogger resources."""

from uuid import UUID, uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import Blogger, Prediction, User, UserBloggerFollow


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
        .join(UserBloggerFollow, UserBloggerFollow.blogger_id == Blogger.id)
        .where(UserBloggerFollow.user_id == user_id)
        .order_by(UserBloggerFollow.created_at.desc(), UserBloggerFollow.id.desc())
        .limit(limit)
        .offset(offset)
    ).scalars().all()
    return list(bloggers), total


def count_pending_predictions_by_blogger(
    db: Session, blogger_handles: list[str]
) -> dict[str, int]:
    if not blogger_handles:
        return {}
    rows = db.execute(
        select(Prediction.blogger_handle, func.count())
        .where(
            Prediction.blogger_handle.in_(blogger_handles),
            Prediction.verdict.is_(None),
        )
        .group_by(Prediction.blogger_handle)
    ).all()
    return {handle: int(count) for handle, count in rows}
