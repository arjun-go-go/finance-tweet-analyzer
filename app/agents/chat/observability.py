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


def record_tool_call_route_link(
    *,
    route: str | None,
    allowed_tool_names: list[str] | None,
    tool_name: str | None,
    tool_status: str,
    user_id: str | None = None,
    thread_id: str | None = None,
    error_detail: str | None = None,
) -> None:
    """Emit an audit trace linking route selection to the concrete tool call."""
    normalized_route = route or "unknown"
    normalized_allowed = allowed_tool_names or []
    normalized_tool_name = tool_name or "unknown"
    route_allowed = normalized_tool_name in normalized_allowed

    logger.bind(
        event="chat_tool_call_route_link",
        user_id=user_id or "",
        thread_id=thread_id or "",
        route=normalized_route,
        allowed_tool_names=normalized_allowed,
        tool_name=normalized_tool_name,
        tool_status=tool_status,
        route_allowed=route_allowed,
    ).info(
        "[ChatRouter] route={} actual_tool={} allowed={} status={} user={} thread={}",
        normalized_route,
        normalized_tool_name,
        route_allowed,
        tool_status,
        user_id or "",
        thread_id or "",
    )

    try:
        conversation_id = uuid.UUID(str(thread_id))
    except (TypeError, ValueError, AttributeError):
        return

    write_trace_immediate(
        conversation_id=conversation_id,
        node_name="tool_route_link",
        tool_name=normalized_tool_name,
        input={
            "route": normalized_route,
            "allowed_tool_names": normalized_allowed,
            "tool_name": normalized_tool_name,
            "user_id": user_id or "",
            "thread_id": str(thread_id),
        },
        output={
            "tool_status": tool_status,
            "route_allowed": route_allowed,
        },
        status="error" if tool_status == "error" else "success",
        error_detail=_truncate_message(error_detail or "", 500) if error_detail else None,
    )
