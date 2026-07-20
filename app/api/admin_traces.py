import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.auth import get_current_admin
from app.core.deps import get_db
from app.models.user import User
from app.schemas.admin_traces import ToolRouteTraceItem, ToolRouteTraceListResponse
from app.services.admin_trace_service import list_tool_route_traces as list_tool_route_traces_service

router = APIRouter(prefix="/api/admin/agent-traces", tags=["admin-agent-traces"])


def _to_tool_route_trace_item(trace) -> ToolRouteTraceItem:
    trace_input = trace.input or {}
    trace_output = trace.output or {}
    return ToolRouteTraceItem(
        id=trace.id,
        conversation_id=trace.conversation_id,
        user_id=trace_input.get("user_id"),
        message_preview=trace_input.get("message_preview"),
        route=trace_output.get("route"),
        allowed_tool_names=trace_output.get("allowed_tool_names") or [],
        status=trace.status,
        created_at=trace.created_at,
    )


@router.get("/tool-routes", response_model=ToolRouteTraceListResponse)
def list_tool_route_traces(
    route: str | None = Query(default=None),
    user_id: str | None = Query(default=None),
    conversation_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> ToolRouteTraceListResponse:
    items, total = list_tool_route_traces_service(
        db,
        route=route,
        user_id=user_id,
        conversation_id=conversation_id,
        limit=limit,
        offset=offset,
    )
    return ToolRouteTraceListResponse(
        items=[_to_tool_route_trace_item(item) for item in items],
        total=total,
    )
