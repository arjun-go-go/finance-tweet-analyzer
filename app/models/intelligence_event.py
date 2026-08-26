import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class IntelligenceTopic(Base):
    __tablename__ = "intelligence_topics"
    __table_args__ = (
        Index("ix_intelligence_topics_feed", "status", "last_seen_at"),
        Index("ix_intelligence_topics_match", "primary_ticker", "kind", "last_seen_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    primary_ticker: Mapped[str] = mapped_column(String(32), nullable=False)
    tickers: Mapped[list[str]] = mapped_column(ARRAY(String(32)), nullable=False, default=list)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    source_credibility: Mapped[float] = mapped_column(Float, nullable=False, default=50.0)
    risk_level: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    risk_factors: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    key_points: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    lifecycle: Mapped[str] = mapped_column(String(16), nullable=False, default="new", server_default="new")
    event_count: Mapped[int] = mapped_column(nullable=False, default=1, server_default="1")
    source_count: Mapped[int] = mapped_column(nullable=False, default=1, server_default="1")
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active", server_default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class IntelligenceEvent(Base):
    __tablename__ = "intelligence_events"
    __table_args__ = (
        Index("ix_intelligence_events_feed", "status", "published_at"),
        Index("ix_intelligence_events_primary_ticker", "primary_ticker"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    topic_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("intelligence_topics.id", ondelete="SET NULL"), nullable=True, index=True
    )
    analysis_result_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("analysis_results.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    primary_ticker: Mapped[str] = mapped_column(String(32), nullable=False)
    tickers: Mapped[list[str]] = mapped_column(ARRAY(String(32)), nullable=False, default=list)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    source_credibility: Mapped[float] = mapped_column(Float, nullable=False, default=50.0)
    risk_level: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    risk_factors: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    key_points: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    projection_version: Mapped[str] = mapped_column(String(16), nullable=False, default="v1", server_default="v1")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active", server_default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
