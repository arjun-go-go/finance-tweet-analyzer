from datetime import datetime

from pydantic import BaseModel


class AlertItem(BaseModel):
    id: str
    kind: str
    severity: str
    title: str
    message: str
    target_url: str
    ticker: str | None = None
    blogger_handle: str | None = None
    status: str
    occurred_at: datetime
    read_at: datetime | None = None


class AlertListResponse(BaseModel):
    items: list[AlertItem]
    total: int
    unread: int
    high_priority: int


class AlertUpdateRequest(BaseModel):
    action: str
