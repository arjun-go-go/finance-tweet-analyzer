import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Integer, String, Text, DateTime
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Tweet(Base, TimestampMixin):
    __tablename__ = "tweets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tweet_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    author_handle: Mapped[str] = mapped_column(String(128), index=True)
    author_name: Mapped[str] = mapped_column(String(256), default="")
    content: Mapped[str] = mapped_column(Text)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    metrics: Mapped[dict | None] = mapped_column(JSONB, default=None)
    media_urls: Mapped[Any | None] = mapped_column(JSONB, default=None)
    raw_json: Mapped[dict | None] = mapped_column(JSONB, default=None)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    analysis_attempts: Mapped[int] = mapped_column(Integer, default=0)
    analysis_last_error: Mapped[str | None] = mapped_column(Text, default=None)
    analysis_next_retry_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None, index=True
    )
    analysis_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    analysis_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
