import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.agent_trace import AgentTrace


def list_tool_route_traces(
    db: Session,
    *,
    route: str | None = None,
    user_id: str | None = None,
    conversation_id: uuid.UUID | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[AgentTrace], int]:
    query = select(AgentTrace).where(AgentTrace.node_name == "route_tools")
    count_query = select(func.count(AgentTrace.id)).where(AgentTrace.node_name == "route_tools")

    if route:
        query = query.where(AgentTrace.output["route"].astext == route)
        count_query = count_query.where(AgentTrace.output["route"].astext == route)
    if user_id:
        query = query.where(AgentTrace.input["user_id"].astext == user_id)
        count_query = count_query.where(AgentTrace.input["user_id"].astext == user_id)
    if conversation_id:
        query = query.where(AgentTrace.conversation_id == conversation_id)
        count_query = count_query.where(AgentTrace.conversation_id == conversation_id)

    query = query.order_by(AgentTrace.created_at.desc(), AgentTrace.id.desc()).limit(limit).offset(offset)
    items = list(db.execute(query).scalars().all())
    total = int(db.execute(count_query).scalar_one())
    return items, total
