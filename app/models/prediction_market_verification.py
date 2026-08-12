import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class PredictionMarketVerification(Base):
    """Immutable evidence from one market-price verification attempt."""

    __tablename__ = "prediction_market_verifications"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    prediction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("predictions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    provider: Mapped[str | None] = mapped_column(String(128))
    provider_symbol: Mapped[str | None] = mapped_column(String(64))
    market: Mapped[str | None] = mapped_column(String(16))
    start_observed_at: Mapped[str | None] = mapped_column(String(64))
    start_price: Mapped[float | None] = mapped_column(Float)
    end_observed_at: Mapped[str | None] = mapped_column(String(64))
    end_price: Mapped[float | None] = mapped_column(Float)
    raw_return: Mapped[float | None] = mapped_column(Float)
    directional_return: Mapped[float | None] = mapped_column(Float)
    threshold: Mapped[float | None] = mapped_column(Float)
    proposed_verdict: Mapped[str | None] = mapped_column(String(16))
    proposed_score: Mapped[float | None] = mapped_column(Float)
    rule_version: Mapped[str] = mapped_column(
        String(32), nullable=False, default="market_auto_v1"
    )
    evidence: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text)
    applied: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index(
            "ix_prediction_market_verifications_prediction_created",
            "prediction_id",
            "created_at",
        ),
    )
