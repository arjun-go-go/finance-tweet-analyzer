from unittest.mock import MagicMock

from langchain_core.messages import AIMessage, HumanMessage

from app.agents import chat_agent
from app.agents.chat import graph


def _state(message: str, **extra):
    state = {
        "messages": [HumanMessage(content=message)],
        "research_scope": {},
        "consecutive_tool_failures": 0,
        "memories": [],
    }
    state.update(extra)
    return state


def test_route_tools_uses_formal_follow_scope_tool():
    result = chat_agent.route_tools_node(_state("我关注了哪些博主？"), {})
    assert result["tool_route"] == "followed_bloggers"
    assert result["allowed_tool_names"] == ["list_my_followed_bloggers"]


def test_route_tools_exposes_no_tools_for_greeting():
    result = chat_agent.route_tools_node(_state("你好"), {})
    assert result["tool_route"] == "conversation"
    assert result["allowed_tool_names"] == []


def test_route_tools_uses_public_signal_search_for_market_question():
    result = chat_agent.route_tools_node(_state("市场怎么看 BTC？"), {})
    assert result["tool_route"] == "public_signals"
    assert result["allowed_tool_names"] == ["search_public_signals"]


def test_agent_node_binds_only_route_allowed_tools(monkeypatch):
    bound_tool_names = []

    class LLM:
        def bind_tools(self, selected_tools):
            bound_tool_names.extend(tool.name for tool in selected_tools)
            return self

        def invoke(self, messages):
            return AIMessage(content="ok")

    monkeypatch.setattr(graph, "get_report_llm", lambda: LLM())
    monkeypatch.setattr(graph, "get_prompt", lambda name: "system")
    monkeypatch.setattr(graph.settings, "agent_max_tokens_per_turn", 100000)

    result = chat_agent.agent_node(
        _state(
            "查询我的关注",
            allowed_tool_names=["query_database", "list_my_followed_bloggers"],
        ),
        {"metadata": {"user_id": "10000000-0000-0000-0000-000000000001"}},
    )

    assert result["messages"][0].content == "ok"
    assert bound_tool_names == ["query_database", "list_my_followed_bloggers"]


def test_agent_node_builds_deterministic_follow_call(monkeypatch):
    monkeypatch.setattr(graph, "get_report_llm", MagicMock())
    monkeypatch.setattr(graph, "get_prompt", lambda name: "system")
    monkeypatch.setattr(graph.settings, "agent_max_tokens_per_turn", 100000)

    result = chat_agent.agent_node(
        _state(
            "关注博主 @qinbafrank",
            allowed_tool_names=["set_blogger_follow"],
        ),
        {"metadata": {"user_id": "10000000-0000-0000-0000-000000000001"}},
    )

    call = result["messages"][0].tool_calls[0]
    assert call["name"] == "set_blogger_follow"
    assert call["args"] == {"blogger_handle": "qinbafrank", "action": "follow"}
