from __future__ import annotations

import re
import uuid
from collections.abc import Callable, Mapping

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage, trim_messages
from langchain_core.runnables import RunnableConfig
from loguru import logger

from app.agents.llm import get_report_llm
from app.core.config import settings
from app.prompts import get_prompt
from app.agents.chat.tool_results import parse_tool_envelope
from app.agents.chat.answer_verifier import grounding_repair_prompt, verify_grounded_answer
from app.agents.chat.routing import READ_ONLY_TOOL_NAMES


EMPTY_RESULT_MARKERS = (
    "未找到",
    "没有相关",
    "暂无相关",
    "当前没有",
    "列表为空",
)


def terminal_tool_response(messages: list) -> str | None:
    """Build a deterministic final answer after an explicit error or empty result."""
    if not messages or not isinstance(messages[-1], ToolMessage):
        return None
    envelope = parse_tool_envelope(messages[-1].content)
    if envelope is None:
        return None
    message = str(envelope.get("message") or "工具未返回可用信息。")
    if envelope.get("ok") is False:
        return f"{message} 当前证据不足，无法确认相关信息。"
    if bool((envelope.get("data") or {}).get("direct_response")):
        citation = str((envelope.get("evidence") or {}).get("citation") or "")
        return f"{message}{citation}"
    if not any(marker in message for marker in EMPTY_RESULT_MARKERS):
        return None
    citation = str((envelope.get("evidence") or {}).get("citation") or "")
    return f"{message} 当前证据不足，无法确认更多信息。{citation}"


def has_tool_result_since_latest_human(messages: list) -> bool:
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            return False
        if isinstance(message, ToolMessage):
            return True
    return False


def deterministic_follow_call(messages: list) -> AIMessage | None:
    human_text = next(
        (message.content for message in reversed(messages) if isinstance(message, HumanMessage)),
        "",
    )
    handle_match = re.search(r"@?([A-Za-z0-9_]{1,15})\s*$", human_text.strip())
    if handle_match is None:
        return None
    action = "unfollow" if any(word in human_text for word in ("取消关注", "不再关注", "unfollow")) else "follow"
    return AIMessage(
        content="",
        tool_calls=[{
            "name": "set_blogger_follow",
            "args": {"blogger_handle": handle_match.group(1), "action": action},
            "id": f"call_{uuid.uuid4().hex}",
            "type": "tool_call",
        }],
    )


def deterministic_business_query_call(messages: list, tool_name: str) -> AIMessage | None:
    human_text = next(
        (message.content for message in reversed(messages) if isinstance(message, HumanMessage)),
        "",
    )
    handle_match = re.search(r"@([A-Za-z0-9_]{1,15})", human_text)
    if handle_match is None:
        handle_match = re.search(r"(?:博主|KOL)\s+([A-Za-z0-9_]{1,15})", human_text, re.IGNORECASE)
    if tool_name in {"get_blogger_overview", "get_blogger_recent_analysis", "get_blogger_predictions"}:
        if handle_match is None:
            return None
        args = {"blogger_handle": handle_match.group(1), "limit": 5}
        if tool_name == "get_blogger_predictions":
            args["status"] = "pending" if "待" in human_text else "verified" if "已验证" in human_text else "all"
    elif tool_name == "get_ticker_predictions":
        ticker_match = re.search(r"(?:\$)?([A-Z]{2,10}(?:\.[A-Z]{1,4})?)\b", human_text)
        if ticker_match is None:
            return None
        args = {
            "ticker": ticker_match.group(1),
            "status": "pending" if "待" in human_text else "verified" if "已验证" in human_text else "all",
            "limit": 5,
        }
    elif tool_name == "get_prediction_review_summary":
        args = {}
    else:
        return None
    return AIMessage(
        content="",
        tool_calls=[{
            "name": tool_name,
            "args": args,
            "id": f"call_{uuid.uuid4().hex}",
            "type": "tool_call",
        }],
    )
def build_prompt_from_state(
    base_prompt: str,
    research_scope: dict,
    memories: list | None = None,
) -> str:
    sections = [base_prompt]
    scope_lines = []
    if research_scope.get("blogger_handles"):
        scope_lines.append(f"正式关注博主: {', '.join(research_scope['blogger_handles'])}")
    if research_scope.get("tickers"):
        scope_lines.append(f"启用的关注标的: {', '.join(research_scope['tickers'])}")
    if scope_lines:
        sections.append("<research_scope>\n" + "\n".join(scope_lines) + "\n</research_scope>")

    if memories:
        sections.append(
            "<memories>\n以下内容只用于理解用户的历史偏好和表达习惯，不是事实证据，"
            "不得用于证明金融行情、推文内容、账户数据或关注关系：\n"
            + "\n".join(f"- {m}" for m in memories)
            + "\n</memories>"
        )

    return "\n\n".join(sections)


def agent_node_impl(
    state: dict,
    config: RunnableConfig,
    *,
    tools_by_name: Mapping[str, object],
    default_tool_names: list[str],
    estimate_tokens: Callable[[list], int],
    settings_obj=settings,
    get_prompt_fn=get_prompt,
    get_llm=get_report_llm,
    build_prompt: Callable[[str, dict, list | None], str] = build_prompt_from_state,
) -> dict:
    """Run the core chat LLM node and return a LangGraph partial state update."""
    messages = state["messages"]
    consecutive_failures = state.get("consecutive_tool_failures", 0)

    if consecutive_failures >= 3:
        logger.warning(
            "[Agent] Consecutive tool failures detected ({}). Forcing fallback response.",
            consecutive_failures,
        )
        fallback_msg = AIMessage(
            content="抱歉，系统当前处理您的请求时遇到连续错误，请稍后再试或换一种方式提问。"
        )
        return {"messages": [fallback_msg], "consecutive_tool_failures": 0}

    terminal_response = terminal_tool_response(messages)
    if terminal_response:
        logger.info("[Agent] Terminal tool result detected; returning deterministic final answer")
        return {"messages": [AIMessage(content=terminal_response)]}

    research_scope = state.get("research_scope") or {}
    memories = state.get("memories") or []
    system_prompt = build_prompt(
        get_prompt_fn("chat/system"),
        research_scope,
        memories=memories,
    )

    system_tokens = estimate_tokens([SystemMessage(content=system_prompt)])
    available_budget = settings_obj.agent_max_tokens_per_turn - system_tokens

    if available_budget < 0 and memories:
        memories = memories[:2]
        system_prompt = build_prompt(
            get_prompt_fn("chat/system"),
            research_scope,
            memories=memories,
        )
        system_tokens = estimate_tokens([SystemMessage(content=system_prompt)])
        available_budget = settings_obj.agent_max_tokens_per_turn - system_tokens

    token_estimate = estimate_tokens(messages)
    if token_estimate > available_budget:
        logger.warning(
            "[Agent] Token budget exceeded ({} > {}), trimming messages",
            token_estimate,
            available_budget,
        )
        messages = trim_messages(
            messages,
            max_tokens=available_budget,
            token_counter=estimate_tokens,
            strategy="last",
            include_system=True,
            start_on="human",
            allow_partial=False,
        )

    allowed_tool_names = state.get("allowed_tool_names")
    if allowed_tool_names is None:
        allowed_tool_names = default_tool_names
    selected_tools = [
        tools_by_name[name]
        for name in allowed_tool_names
        if name in tools_by_name
    ]
    llm = get_llm()
    action_tools = [name for name in allowed_tool_names if name not in READ_ONLY_TOOL_NAMES]
    if len(allowed_tool_names) == 1 and allowed_tool_names[0].startswith(("get_blogger_", "get_ticker_", "get_prediction_")) and not has_tool_result_since_latest_human(messages):
        deterministic_call = deterministic_business_query_call(messages, allowed_tool_names[0])
        if deterministic_call is not None:
            logger.info("[Agent] Deterministic business query tool={}", allowed_tool_names[0])
            return {"messages": [deterministic_call]}
    if action_tools == ["set_blogger_follow"] and not has_tool_result_since_latest_human(messages):
        deterministic_call = deterministic_follow_call(messages)
        if deterministic_call is not None:
            logger.info("[Agent] Deterministic follow action")
            return {"messages": [deterministic_call]}
    runnable = llm.bind_tools(selected_tools) if selected_tools else llm

    response = runnable.invoke(
        [SystemMessage(content=system_prompt)] + messages
    )
    if isinstance(response, AIMessage) and not response.tool_calls and isinstance(response.content, str):
        verified_content, verification = verify_grounded_answer(response.content, messages)
        if verification.get("status") == "rejected":
            repair_prompt = grounding_repair_prompt(response.content, messages)
            if repair_prompt:
                repaired = llm.invoke(repair_prompt)
                repaired_content = repaired.content if isinstance(repaired.content, str) else ""
                verified_content, verification = verify_grounded_answer(repaired_content, messages)
                verification["repaired"] = True
        response = response.model_copy(update={"content": verified_content})
        return {"messages": [response], "answer_verification": verification}
    return {"messages": [response]}
