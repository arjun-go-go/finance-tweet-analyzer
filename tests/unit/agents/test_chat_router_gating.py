from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage, HumanMessage

from app.agents import chat_agent
from app.agents.chat import graph


def _state(message: str, **extra):
    base = {
        "messages": [HumanMessage(content=message)],
        "user_profile": {},
        "user_prefs": {},
        "consecutive_tool_failures": 0,
        "memories": [],
    }
    base.update(extra)
    return base


def test_route_tools_defaults_to_read_only_for_status_queries():
    result = chat_agent.route_tools_node(_state("我关注了哪些博主？"), {})

    assert result["tool_route"] == "followed_bloggers"
    assert result["allowed_tool_names"] == ["list_my_followed_bloggers"]


def test_route_tools_exposes_no_tools_for_conversation():
    result = chat_agent.route_tools_node(_state("你好"), {})

    assert result["tool_route"] == "conversation"
    assert result["allowed_tool_names"] == []


def test_route_tools_opens_report_tools_for_report_intent():
    result = chat_agent.route_tools_node(_state("生成 BTC 本周跟踪报告"), {})

    assert result["tool_route"] == "report"
    assert "generate_tracking_report" in result["allowed_tool_names"]
    assert "fetch_and_save_tweets" not in result["allowed_tool_names"]


def test_route_tools_opens_analysis_tools_for_explicit_analysis_intent():
    result = chat_agent.route_tools_node(_state("预览并确认分析我关注博主的待分析推文"), {})

    assert result["tool_route"] == "analysis"
    assert "preview_tweet_analysis" not in result["allowed_tool_names"]
    assert "confirm_tweet_analysis" in result["allowed_tool_names"]
    assert "generate_tracking_report" not in result["allowed_tool_names"]


def test_agent_node_binds_only_route_allowed_tools(monkeypatch):
    bound_tool_names = []

    class _LLM:
        def bind_tools(self, selected_tools):
            bound_tool_names.extend(tool.name for tool in selected_tools)
            return self

        def invoke(self, messages):
            return AIMessage(content="ok")

    monkeypatch.setattr(graph, "get_report_llm", lambda: _LLM())
    monkeypatch.setattr(graph, "get_prompt", lambda name: "system")
    monkeypatch.setattr(graph.settings, "agent_max_tokens_per_turn", 100000)

    result = chat_agent.agent_node(
        _state("查我的关注", allowed_tool_names=["query_database", "list_my_followed_bloggers"]),
        {"metadata": {"user_id": "10000000-0000-0000-0000-000000000001"}},
    )

    assert result["messages"][0].content == "ok"
    assert bound_tool_names == ["query_database", "list_my_followed_bloggers"]


def test_agent_node_does_not_bind_tools_for_conversation(monkeypatch):
    bound = False

    class _LLM:
        def bind_tools(self, selected_tools):
            nonlocal bound
            bound = True
            return self

        def invoke(self, messages):
            return AIMessage(content="你好，我可以帮你研究 Twitter 博主观点。")

    monkeypatch.setattr(graph, "get_report_llm", lambda: _LLM())
    monkeypatch.setattr(graph, "get_prompt", lambda name: "system")
    monkeypatch.setattr(graph.settings, "agent_max_tokens_per_turn", 100000)

    result = chat_agent.agent_node(
        _state("你好", allowed_tool_names=[]),
        {"metadata": {"user_id": "10000000-0000-0000-0000-000000000001"}},
    )

    assert result["messages"][0].content
    assert bound is False


def test_agent_node_builds_deterministic_follow_call(monkeypatch):
    monkeypatch.setattr(graph, "get_report_llm", MagicMock())
    monkeypatch.setattr(graph, "get_prompt", lambda name: "system")
    monkeypatch.setattr(graph.settings, "agent_max_tokens_per_turn", 100000)

    result = chat_agent.agent_node(
        _state("关注博主 @qinbafrank", allowed_tool_names=["set_blogger_follow"]),
        {"metadata": {"user_id": "10000000-0000-0000-0000-000000000001"}},
    )

    call = result["messages"][0].tool_calls[0]
    assert call["name"] == "set_blogger_follow"
    assert call["args"] == {"blogger_handle": "qinbafrank", "action": "follow"}
