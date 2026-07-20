from langchain_core.messages import HumanMessage

from app.agents import chat_agent
from app.agents.chat import observability


def test_route_tools_node_records_structured_route_decision(monkeypatch):
    captured = {}

    def fake_record(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(chat_agent, "_record_tool_route_decision", fake_record)

    result = chat_agent.route_tools_node(
        {"messages": [HumanMessage(content="生成一份 TSLA 日报")]},
        {
            "metadata": {"user_id": "user-1"},
            "configurable": {"thread_id": "conv-1"},
        },
    )

    assert result["tool_route"] == "report"
    assert captured == {
        "route": "report",
        "allowed_tool_names": result["allowed_tool_names"],
        "message": "生成一份 TSLA 日报",
        "user_id": "user-1",
        "thread_id": "conv-1",
    }


def test_record_tool_route_decision_reuses_agent_trace_for_uuid_thread(monkeypatch):
    captured = {}

    def fake_write_trace_immediate(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(observability, "write_trace_immediate", fake_write_trace_immediate)

    observability.record_tool_route_decision(
        route="report",
        allowed_tool_names=["query_database", "generate_tracking_report"],
        message="生成一份 TSLA 日报",
        user_id="user-1",
        thread_id="10000000-0000-0000-0000-000000000001",
    )

    assert str(captured["conversation_id"]) == "10000000-0000-0000-0000-000000000001"
    assert captured["node_name"] == "route_tools"
    assert captured["tool_name"] is None
    assert captured["status"] == "success"
    assert captured["input"] == {
        "message_preview": "生成一份 TSLA 日报",
        "user_id": "user-1",
        "thread_id": "10000000-0000-0000-0000-000000000001",
    }
    assert captured["output"] == {
        "route": "report",
        "allowed_tool_names": ["query_database", "generate_tracking_report"],
    }


def test_record_tool_route_decision_skips_agent_trace_for_non_uuid_thread(monkeypatch):
    calls = []

    monkeypatch.setattr(
        observability,
        "write_trace_immediate",
        lambda **kwargs: calls.append(kwargs),
    )

    observability.record_tool_route_decision(
        route="read_only",
        allowed_tool_names=["query_database"],
        message="查我的关注",
        user_id="user-1",
        thread_id="not-a-uuid",
    )

    assert calls == []
