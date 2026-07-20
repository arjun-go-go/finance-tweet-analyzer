import json
from unittest.mock import patch

from langchain_core.messages import ToolMessage

from app.agents import chat_agent


def test_tool_result_error_envelope_marks_failure():
    content = json.dumps(
        {
            "ok": False,
            "error_code": "VECTOR_STORE_UNAVAILABLE",
            "message": "公共信号检索暂时不可用",
        },
        ensure_ascii=False,
    )

    with patch.object(
        chat_agent._tool_node,
        "invoke",
        return_value={"messages": [ToolMessage(content=content, tool_call_id="t1")]},
    ):
        result = chat_agent.tools_node({"messages": [], "consecutive_tool_failures": 1})

    assert result["consecutive_tool_failures"] == 2


def test_plain_text_tool_result_with_error_words_is_not_failure():
    with patch.object(
        chat_agent._tool_node,
        "invoke",
        return_value={"messages": [ToolMessage(content="未找到相关记录，这是一条正常查询结果。", tool_call_id="t1")]},
    ):
        result = chat_agent.tools_node({"messages": [], "consecutive_tool_failures": 2})

    assert result["consecutive_tool_failures"] == 0
    content = result["messages"][0].content
    assert json.loads(content)["ok"] is True
    assert json.loads(content)["message"] == "未找到相关记录，这是一条正常查询结果。"


def test_tool_ok_returns_json_envelope():
    content = chat_agent._tool_ok("查询完成", data={"count": 1})

    assert json.loads(content) == {
        "ok": True,
        "message": "查询完成",
        "data": {"count": 1},
    }


def test_tool_error_returns_json_envelope():
    content = chat_agent._tool_error("INVALID_ARGUMENT", "参数错误")

    assert json.loads(content) == {
        "ok": False,
        "error_code": "INVALID_ARGUMENT",
        "message": "参数错误",
        "retryable": False,
    }
