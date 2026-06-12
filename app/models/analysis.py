import uuid

from sqlalchemy import String, Float, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class AnalysisResult(Base, TimestampMixin):
    __tablename__ = "analysis_results"

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
