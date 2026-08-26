"""Pydantic schemas for ticker tracking subscriptions."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class TrackingCreateRequest(BaseModel):
    ticker: str = Field(..., max_length=20, examples=["TSLA"])


class TrackingValidateRequest(BaseModel):
    ticker: str = Field(..., max_length=20, examples=["TSLA", "600519", "XAU"])


class TrackingUpdateRequest(BaseModel):
    status: str | None = Field(None, pattern="^(active|paused)$")


class TrackingResponse(BaseModel):
    id: UUID
    user_id: UUID
    ticker: str
    status: str
    config: dict = {}
    created_at: datetime
    updated_at: datetime
    instrument: dict | None = None
    monitor: dict = {}

    model_config = {"from_attributes": True}


class TrackingListResponse(BaseModel):
    items: list[TrackingResponse]
    total: int
    summary: dict = {}
