from __future__ import annotations

from langchain_core.runnables import RunnableConfig

from app.core.deps import SessionLocal
from app.memory.identity import normalize_user_id


def get_authenticated_user_id(config: RunnableConfig | None) -> str:
    metadata = (config or {}).get("metadata") or {}
    return normalize_user_id(metadata.get("user_id"))


def init_context_node_impl(state: dict, config: RunnableConfig) -> dict:
    """Load per-user profile/preferences once at graph entry."""
    from app.memory.preferences import get_preferences
    from app.memory.profile import get_profile

    user_id = get_authenticated_user_id(config)
    db = SessionLocal()
    try:
        profile = get_profile(db, user_id) or {}
        prefs = get_preferences(db, user_id) or {}
    finally:
        db.close()
    return {"user_profile": profile, "user_prefs": prefs}
