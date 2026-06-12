"""Pydantic schemas for report generation and retrieval."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ReportGenerateRequest(BaseModel):
    ticker: str = Field(..., max_length=20, examples=["TSLA"])
    time_range: str = Field(default="1w", examples=["1w", "1d", "1m"])
    focus_aspects: list[str] | None = None


class ReportResponse(BaseModel):
    id: UUID
    user_id: UUID
    ticker: str
    title: str | None = None
    trigger_type: str
    tracked_ticker_id: UUID | None = None
    sections: dict = {}
    citations: list = []
    summary: str | None = None
    consensus: str | None = None
    token_usage: dict | None = None
    latency_ms: int | None = None
    status: str
    error_detail: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ReportListItem(BaseModel):
    id: UUID
    ticker: str
    title: str | None = None
    trigger_type: str
    summary: str | None = None
    consensus: str | None = None
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ReportListResponse(BaseModel):
    items: list[ReportListItem]
    total: int
