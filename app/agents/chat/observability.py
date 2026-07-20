from __future__ import annotations

from loguru import logger


def _truncate_message(message: str, max_chars: int = 300) -> str:
    if len(message) <= max_chars:
        return message
    return message[:max_chars] + "..."


def record_tool_route_decision(
    *,
    route: str,
    allowed_tool_names: list[str],
    message: str,
    user_id: str | None = None,
    thread_id: str | None = None,
) -> None:
    """Emit a structured audit log for Chat Agent tool routing decisions."""
    logger.bind(
        event="chat_tool_route_decision",
        user_id=user_id or "",
        thread_id=thread_id or "",
        route=route,
        allowed_tool_names=allowed_tool_names,
        message_preview=_truncate_message(message),
    ).info(
        "[ChatRouter] route={} tools={} user={} thread={}",
        route,
        allowed_tool_names,
        user_id or "",
        thread_id or "",
    )
