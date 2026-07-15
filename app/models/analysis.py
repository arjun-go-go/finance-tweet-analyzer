import uuid

from sqlalchemy import Float, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class AnalysisResult(Base, TimestampMixin):
    __tablename__ = "analysis_results"
    __table_args__ = (
        Index(
            "uq_analysis_results_cache_key",
            "cache_key",
            unique=True,
            postgresql_where=text("cache_key IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tweet_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tweets.id"), index=True
    )
    analysis_type: Mapped[str] = mapped_column(String(32), index=True)
    result: Mapped[dict] = mapped_column(JSONB)
    model_used: Mapped[str] = mapped_column(String(64))
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    batch_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), default=None)
    prediction_status: Mapped[str] = mapped_column(
        String(16), default="pending", index=True
    )
    cache_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pipeline_version: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="v1"
    )
