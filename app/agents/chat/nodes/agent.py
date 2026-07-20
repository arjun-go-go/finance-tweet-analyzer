from __future__ import annotations

from collections.abc import Callable, Mapping

from langchain_core.messages import AIMessage, SystemMessage, trim_messages
from langchain_core.runnables import RunnableConfig
from loguru import logger

from app.agents.llm import get_report_llm
from app.core.config import settings
from app.prompts import get_prompt


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
            "<memories>\n以下是用户的历史偏好和记忆，请结合这些信息回答：\n"
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
    llm_with_tools = get_llm().bind_tools(selected_tools)

    response = llm_with_tools.invoke(
        [SystemMessage(content=system_prompt)] + messages
    )
    return {"messages": [response]}
