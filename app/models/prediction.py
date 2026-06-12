import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Prediction(Base, TimestampMixin):
    __tablename__ = "predictions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    analysis_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("analysis_results.id"), index=True
    )
    tweet_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tweets.id"), index=True
    )
    blogger_handle: Mapped[str] = mapped_column(String(128), index=True)
    ticker: Mapped[str] = mapped_column(String(64), index=True)
    sentiment: Mapped[str] = mapped_column(String(16))
    investment_horizon: Mapped[str] = mapped_column(String(16), default="unknown")
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    verifiable_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    verdict: Mapped[str | None] = mapped_column(String(16), default=None)
    score: Mapped[float | None] = mapped_column(Float, default=None)
    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    verified_by: Mapped[str | None] = mapped_column(String(64), default=None)
    note: Mapped[str | None] = mapped_column(Text, default=None)

    __table_args__ = (
        Index("ix_predictions_handle_verdict", "blogger_handle", "verdict"),
        Index("ix_predictions_handle_ticker", "blogger_handle", "ticker"),
        Index(
            "ix_predictions_dedup",
            "blogger_handle",
            "ticker",
            "sentiment",
            "published_at",
        ),
    )
