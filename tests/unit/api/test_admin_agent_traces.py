import uuid

from app.models.agent_trace import AgentTrace


def _route_trace(conversation_id, *, route, user_id="user-1", message="生成 TSLA 日报"):
    return AgentTrace(
        id=uuid.uuid4(),
        conversation_id=conversation_id,
        node_name="route_tools",
        tool_name=None,
        input={
            "message_preview": message,
            "user_id": user_id,
            "thread_id": str(conversation_id),
        },
        output={
            "route": route,
            "allowed_tool_names": ["query_database", "generate_tracking_report"],
        },
        status="success",
    )


def test_admin_tool_route_trace_endpoint_lists_route_decisions(client, db_session):
    conversation_id = uuid.uuid4()
    db_session.add(_route_trace(conversation_id, route="report"))
    db_session.add(
        AgentTrace(
            id=uuid.uuid4(),
            conversation_id=conversation_id,
            node_name="tools",
            tool_name="query_database",
            input={},
            output={},
            status="success",
        )
    )
    db_session.commit()

    response = client.get("/api/admin/agent-traces/tool-routes")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["conversation_id"] == str(conversation_id)
    assert item["route"] == "report"
    assert item["allowed_tool_names"] == ["query_database", "generate_tracking_report"]
    assert item["message_preview"] == "生成 TSLA 日报"
    assert item["user_id"] == "user-1"


def test_admin_tool_route_trace_endpoint_filters_by_route_and_user(client, db_session):
    first_conversation_id = uuid.uuid4()
    second_conversation_id = uuid.uuid4()
    db_session.add(_route_trace(first_conversation_id, route="report", user_id="user-1"))
    db_session.add(_route_trace(second_conversation_id, route="read_only", user_id="user-2"))
    db_session.commit()

    response = client.get("/api/admin/agent-traces/tool-routes?route=read_only&user_id=user-2")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["conversation_id"] == str(second_conversation_id)
    assert body["items"][0]["route"] == "read_only"
