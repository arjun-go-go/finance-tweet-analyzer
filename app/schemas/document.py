from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl


# ============================================================
# Request schemas
# ============================================================

class DocumentPasteRequest(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    content: str = Field(min_length=1, max_length=2_000_000)
    tickers: list[str] = Field(default_factory=list, max_length=20)
    publish_date: date | None = None


class DocumentUrlRequest(BaseModel):
    url: HttpUrl
    title: str | None = Field(default=None, max_length=500)
    tickers: list[str] = Field(default_factory=list, max_length=20)


# ============================================================
# Response schemas
# ============================================================

class DocumentResponse(BaseModel):
    id: UUID
    title: str
    source_type: str
    status: str
    char_count: int
    chunk_count: int
    tickers: list[str]
    publish_date: date | None
    error_detail: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DocumentListResponse(BaseModel):
    items: list[DocumentResponse]
    total: int
    page: int
    page_size: int


class DocumentStatusResponse(BaseModel):
    id: UUID
    status: str
    chunk_count: int
    error_detail: str | None
