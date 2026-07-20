from langchain_core.messages import HumanMessage
from langchain_core.messages import ToolMessage

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


def test_tools_node_records_route_link_for_actual_tool_call(monkeypatch):
    captured = {}

    def fake_record(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(chat_agent, "_record_tool_call_route_link", fake_record)
    monkeypatch.setattr(
        chat_agent._tool_node,
        "invoke",
        lambda state: {
            "messages": [
                ToolMessage(
                    content='{"ok": true, "message": "report ready"}',
                    name="generate_tracking_report",
                    tool_call_id="t1",
                )
            ]
        },
    )

    result = chat_agent.tools_node(
        {
            "messages": [],
            "tool_route": "report",
            "allowed_tool_names": ["query_database", "generate_tracking_report"],
            "consecutive_tool_failures": 0,
        },
        {
            "metadata": {"user_id": "user-1"},
            "configurable": {"thread_id": "10000000-0000-0000-0000-000000000001"},
        },
    )

    assert result["consecutive_tool_failures"] == 0
    assert captured == {
        "route": "report",
        "allowed_tool_names": ["query_database", "generate_tracking_report"],
        "tool_name": "generate_tracking_report",
        "tool_status": "success",
        "user_id": "user-1",
        "thread_id": "10000000-0000-0000-0000-000000000001",
        "error_detail": None,
    }


def test_record_tool_call_route_link_reuses_agent_trace_for_uuid_thread(monkeypatch):
    captured = {}

    def fake_write_trace_immediate(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(observability, "write_trace_immediate", fake_write_trace_immediate)

    observability.record_tool_call_route_link(
        route="report",
        allowed_tool_names=["query_database", "generate_tracking_report"],
        tool_name="generate_tracking_report",
        tool_status="success",
        user_id="user-1",
        thread_id="10000000-0000-0000-0000-000000000001",
    )

    assert str(captured["conversation_id"]) == "10000000-0000-0000-0000-000000000001"
    assert captured["node_name"] == "tool_route_link"
    assert captured["tool_name"] == "generate_tracking_report"
    assert captured["status"] == "success"
    assert captured["input"] == {
        "route": "report",
        "allowed_tool_names": ["query_database", "generate_tracking_report"],
        "tool_name": "generate_tracking_report",
        "user_id": "user-1",
        "thread_id": "10000000-0000-0000-0000-000000000001",
    }
    assert captured["output"] == {
        "tool_status": "success",
        "route_allowed": True,
    }
