from __future__ import annotations

from langchain_core.runnables import RunnableConfig
from sqlalchemy import select

from app.core.deps import SessionLocal
from app.memory.identity import normalize_user_id
from app.models.blogger import Blogger
from app.models.tracked_ticker import TrackedTicker
from app.models.user_blogger_follow import UserBloggerFollow


def get_authenticated_user_id(config: RunnableConfig | None) -> str:
    metadata = (config or {}).get("metadata") or {}
    return normalize_user_id(metadata.get("user_id"))


def init_context_node_impl(state: dict, config: RunnableConfig) -> dict:
    """Load the canonical followed-blogger and tracked-ticker scope."""
    user_id = get_authenticated_user_id(config)
    db = SessionLocal()
    try:
        handles = list(db.execute(
            select(Blogger.handle)
            .join(UserBloggerFollow, UserBloggerFollow.blogger_id == Blogger.id)
            .where(UserBloggerFollow.user_id == user_id)
            .order_by(UserBloggerFollow.created_at.desc())
        ).scalars())
        tickers = list(db.execute(
            select(TrackedTicker.ticker)
            .where(
                TrackedTicker.user_id == user_id,
                TrackedTicker.status == "active",
            )
            .order_by(TrackedTicker.created_at.desc())
        ).scalars())
    finally:
        db.close()
    return {"research_scope": {"blogger_handles": handles, "tickers": tickers}}
