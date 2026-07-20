from __future__ import annotations

import uuid

from loguru import logger

from app.services.trace_service import write_trace_immediate


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
    message_preview = _truncate_message(message)
    logger.bind(
        event="chat_tool_route_decision",
        user_id=user_id or "",
        thread_id=thread_id or "",
        route=route,
        allowed_tool_names=allowed_tool_names,
        message_preview=message_preview,
    ).info(
        "[ChatRouter] route={} tools={} user={} thread={}",
        route,
        allowed_tool_names,
        user_id or "",
        thread_id or "",
    )

    try:
        conversation_id = uuid.UUID(str(thread_id))
    except (TypeError, ValueError, AttributeError):
        return

    write_trace_immediate(
        conversation_id=conversation_id,
        node_name="route_tools",
        tool_name=None,
        input={
            "message_preview": message_preview,
            "user_id": user_id or "",
            "thread_id": str(thread_id),
        },
        output={
            "route": route,
            "allowed_tool_names": allowed_tool_names,
        },
        status="success",
    )
