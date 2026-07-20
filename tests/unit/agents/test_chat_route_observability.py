from langchain_core.messages import HumanMessage

from app.agents import chat_agent


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
