import json

from langchain_core.messages import HumanMessage

from app.agents import chat_agent
from app.agents.chat import routing, tool_results


def test_tool_result_helpers_live_in_dedicated_module_and_are_reexported():
    assert chat_agent._tool_ok is tool_results.tool_ok
    assert chat_agent._tool_error is tool_results.tool_error
    assert chat_agent._parse_tool_envelope is tool_results.parse_tool_envelope

    content = tool_results.tool_ok("ok", data={"x": 1})
    assert json.loads(content) == {"ok": True, "message": "ok", "data": {"x": 1}}


def test_routing_helpers_live_in_dedicated_module_and_are_reexported():
    assert chat_agent._classify_tool_route is routing.classify_tool_route
    assert chat_agent._latest_human_text is routing.latest_human_text
    assert chat_agent._has_explicit_report_confirmation is routing.has_explicit_report_confirmation
    assert chat_agent._has_explicit_ingest_confirmation is routing.has_explicit_ingest_confirmation

    route, tools = routing.classify_tool_route("生成 BTC 本周报告")
    assert route == "report"
    assert "generate_tracking_report" in tools


def test_latest_human_text_ignores_non_human_messages():
    state = {"messages": [HumanMessage(content="第一句"), HumanMessage(content="最后一句")]}

    assert routing.latest_human_text(state) == "最后一句"
