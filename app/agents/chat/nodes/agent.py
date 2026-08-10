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


def deterministic_analysis_call(messages: list, tool_name: str) -> AIMessage | None:
    """Build the two-stage analysis tool call without relying on model sampling."""
    human_text = next(
        (message.content for message in reversed(messages) if isinstance(message, HumanMessage)),
        "",
    )
    if tool_name == "preview_tweet_analysis":
        handle_match = re.search(r"@([A-Za-z0-9_]{1,15})", human_text)
        since_match = re.search(r"\b(\d+[hdw])\b", human_text.lower())
        args = {
            "blogger_handle": handle_match.group(1) if handle_match else "",
            "reanalyze": "重新分析" in human_text,
            "since": since_match.group(1) if since_match else "",
        }
    elif tool_name == "confirm_tweet_analysis":
        context = "\n".join(
            message.content
            for message in messages
            if isinstance(message, (AIMessage, ToolMessage)) and isinstance(message.content, str)
        )
        confirmation_match = re.search(
            r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
            context,
        )
        if confirmation_match is None:
            return None
        args = {"task_id": confirmation_match.group(0)}
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
    profile: dict,
    prefs: dict,
    memories: list | None = None,
) -> str:
    sections = [base_prompt]

    profile_lines = []
    if profile.get("name"):
        profile_lines.append(f"姓名: {profile['name']}")
    if profile.get("nickname"):
        profile_lines.append(f"昵称: {profile['nickname']}")
    if profile.get("occupation"):
        profile_lines.append(f"职业: {profile['occupation']}")
    if profile.get("location"):
        profile_lines.append(f"所在地: {profile['location']}")
    if profile.get("birthday"):
        profile_lines.append(f"生日: {profile['birthday']}")
    if profile_lines:
        sections.append("用户档案：\n" + "\n".join(profile_lines))

    pref_lines = []
    if prefs.get("investment_style"):
        pref_lines.append(f"投资偏好: {prefs['investment_style']}")
    if prefs.get("watched_bloggers"):
        pref_lines.append(f"关注博主: {', '.join(prefs['watched_bloggers'])}")
    if prefs.get("interested_tickers"):
        pref_lines.append(f"关注标的: {', '.join(prefs['interested_tickers'])}")
    if prefs.get("reply_style"):
        style_label = "简洁" if prefs["reply_style"] == "concise" else "详细"
        pref_lines.append(f"回复风格: {style_label}")
    if pref_lines:
        sections.append("用户偏好：\n" + "\n".join(pref_lines))

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
    build_prompt: Callable[[str, dict, dict, list | None], str] = build_prompt_from_state,
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

    profile = state.get("user_profile") or {}
    prefs = state.get("user_prefs") or {}
    memories = state.get("memories") or []
    system_prompt = build_prompt(
        get_prompt_fn("chat/system"),
        profile,
        prefs,
        memories=memories,
    )

    system_tokens = estimate_tokens([SystemMessage(content=system_prompt)])
    available_budget = settings_obj.agent_max_tokens_per_turn - system_tokens

    if available_budget < 0 and memories:
        memories = memories[:2]
        system_prompt = build_prompt(
            get_prompt_fn("chat/system"),
            profile,
            prefs,
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

    allowed_tool_names = state.get("allowed_tool_names") or default_tool_names
    selected_tools = [
        tools_by_name[name]
        for name in allowed_tool_names
        if name in tools_by_name
    ]
    llm = get_llm()
    action_tools = [name for name in allowed_tool_names if name not in READ_ONLY_TOOL_NAMES]
    if (
        len(action_tools) == 1
        and action_tools[0] in ("preview_tweet_analysis", "confirm_tweet_analysis")
        and not has_tool_result_since_latest_human(messages)
    ):
        deterministic_call = deterministic_analysis_call(messages, action_tools[0])
        if deterministic_call is not None:
            logger.info("[Agent] Deterministic analysis action tool={}", action_tools[0])
            return {"messages": [deterministic_call]}
    runnable = llm.bind_tools(selected_tools)

    response = runnable.invoke(
        [SystemMessage(content=system_prompt)] + messages
    )
    return {"messages": [response]}
