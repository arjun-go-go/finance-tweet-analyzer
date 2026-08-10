from langchain_core.runnables import RunnableConfig
from langgraph.prebuilt import ToolNode
from loguru import logger

from app.agents.chat.observability import (
    record_tool_call_route_link,
    record_tool_route_decision,
)
from app.agents.chat.routing import (
    classify_tool_route,
    latest_human_text,
    recent_context_text,
)
from app.agents.chat.tool_results import (
    attach_tool_evidence,
    parse_tool_envelope,
    tool_error,
    tool_ok,
)
from app.agents.chat.tools.registry import tools


tool_node = ToolNode(tools, handle_tool_errors=True)


def route_tools_node(state: dict, config: RunnableConfig) -> dict:
    """Expose only the tool subset needed for the current user intent."""
    message = latest_human_text(state)
    route, allowed = classify_tool_route(message, recent_context_text(state))
    metadata = (config or {}).get("metadata") or {}
    configurable = (config or {}).get("configurable") or {}
    record_tool_route_decision(
        route=route,
        allowed_tool_names=allowed,
        message=message,
        user_id=metadata.get("user_id"),
        thread_id=configurable.get("thread_id"),
    )
    logger.info("[ChatRouter] route={} tools={}", route, allowed)
    return {"tool_route": route, "allowed_tool_names": allowed}


def tools_node(state: dict, config: RunnableConfig | None = None) -> dict:
    """Execute tool calls, normalize results, and record route/tool linkage."""
    result = tool_node.invoke(state)
    consecutive = state.get("consecutive_tool_failures", 0)
    metadata = (config or {}).get("metadata") or {}
    configurable = (config or {}).get("configurable") or {}
    route = state.get("tool_route")
    allowed_tool_names = state.get("allowed_tool_names") or []

    standardized_messages = []
    has_error = False
    for message in result.get("messages", []):
        if not (
            hasattr(message, "content")
            and isinstance(message.content, str)
        ):
            standardized_messages.append(message)
            continue

        content = message.content
        envelope = parse_tool_envelope(content)
        tool_node_status = getattr(message, "status", None)
        if envelope is None:
            if tool_node_status == "error" or content.startswith("Error:"):
                content = tool_error(
                    "TOOL_EXECUTION_ERROR",
                    content,
                    retryable=True,
                )
            else:
                content = tool_ok(content)
            if hasattr(message, "model_copy"):
                message = message.model_copy(update={"content": content})
            else:
                message.content = content
            envelope = parse_tool_envelope(content)

        if envelope is not None and envelope.get("ok") is True:
            content = attach_tool_evidence(content, getattr(message, "name", None))
            if hasattr(message, "model_copy"):
                message = message.model_copy(update={"content": content})
            else:
                message.content = content
            envelope = parse_tool_envelope(content)

        failed = envelope is not None and envelope.get("ok") is False
        if failed:
            has_error = True
            logger.warning("[ToolNode] Tool failure detected: {}", content[:100])
        tool_status = "error" if failed else "success"
        record_tool_call_route_link(
            route=route,
            allowed_tool_names=allowed_tool_names,
            tool_name=getattr(message, "name", None),
            tool_status=tool_status,
            user_id=metadata.get("user_id"),
            thread_id=configurable.get("thread_id"),
            error_detail=content if failed else None,
        )
        standardized_messages.append(message)

    result["messages"] = standardized_messages
    result["consecutive_tool_failures"] = consecutive + 1 if has_error else 0
    return result
