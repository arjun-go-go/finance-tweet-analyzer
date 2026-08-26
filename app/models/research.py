import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ResearchTopic(Base):
    __tablename__ = "research_topics"
    __table_args__ = (
        Index("ix_research_topics_user_status", "user_id", "status", "updated_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    research_question: Mapped[str] = mapped_column(Text, nullable=False)
    mode: Mapped[str] = mapped_column(String(16), nullable=False, default="quick", server_default="quick")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active", server_default="active")
    tickers: Mapped[list[str]] = mapped_column(ARRAY(String(32)), nullable=False, default=list)
    source_scope: Mapped[list[str]] = mapped_column(ARRAY(String(32)), nullable=False, default=list)
    time_range: Mapped[str] = mapped_column(String(16), nullable=False, default="1w", server_default="1w")
    current_conclusion: Mapped[str | None] = mapped_column(Text)
    monitor_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    monitor_frequency: Mapped[str] = mapped_column(String(16), nullable=False, default="weekly", server_default="weekly")
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class ResearchEvidence(Base):
    __tablename__ = "research_evidence"
    __table_args__ = (
        Index("ix_research_evidence_topic", "topic_id", "created_at"),
        UniqueConstraint("topic_id", "evidence_key", name="uq_research_evidence_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    topic_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("research_topics.id", ondelete="CASCADE"), nullable=False)
    evidence_key: Mapped[str] = mapped_column(String(32), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_id: Mapped[str] = mapped_column(String(128), nullable=False)
    tickers: Mapped[list[str]] = mapped_column(ARRAY(String(32)), nullable=False, default=list)
    author: Mapped[str] = mapped_column(String(128), nullable=False, default="", server_default="")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    sentiment: Mapped[str] = mapped_column(String(16), nullable=False, default="", server_default="")
    verification_status: Mapped[str] = mapped_column(String(24), nullable=False, default="indexed", server_default="indexed")
    relevance_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, server_default="0")
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ResearchConclusion(Base):
    __tablename__ = "research_conclusions"
    __table_args__ = (
        Index("ix_research_conclusions_topic_version", "topic_id", "version"),
        UniqueConstraint("topic_id", "version", name="uq_research_conclusion_version"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    topic_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("research_topics.id", ondelete="CASCADE"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    conclusion: Mapped[str] = mapped_column(Text, nullable=False)
    thesis: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    counter_evidence: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    risks: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    evidence_keys: Mapped[list[str]] = mapped_column(ARRAY(String(32)), nullable=False, default=list)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
