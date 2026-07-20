import uuid
from datetime import datetime

from pydantic import BaseModel


class ToolRouteTraceItem(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    user_id: str | None = None
    message_preview: str | None = None
    route: str | None = None
    allowed_tool_names: list[str] = []
    status: str
    created_at: datetime


class ToolRouteTraceListResponse(BaseModel):
    items: list[ToolRouteTraceItem]
    total: int
