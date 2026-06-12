"""Pydantic schemas for ticker tracking subscriptions."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class TrackingCreateRequest(BaseModel):
    ticker: str = Field(..., max_length=20, examples=["TSLA"])
    frequency: str = Field(..., pattern="^(daily|weekly|manual)$")


class TrackingUpdateRequest(BaseModel):
    frequency: str | None = Field(None, pattern="^(daily|weekly|manual)$")
    status: str | None = Field(None, pattern="^(active|paused)$")


class TrackingResponse(BaseModel):
    id: UUID
    user_id: UUID
    ticker: str
    frequency: str
    last_report_at: datetime | None = None
    next_run_at: datetime | None = None
    status: str
    config: dict = {}
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TrackingListResponse(BaseModel):
    items: list[TrackingResponse]
    total: int
