import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
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
    claim_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("instrument_claims.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    tweet_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tweets.id"), index=True
    )
    blogger_handle: Mapped[str] = mapped_column(String(128), index=True)
    ticker: Mapped[str] = mapped_column(String(64), index=True)
    sentiment: Mapped[str] = mapped_column(String(16))
    prediction_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="price_direction", index=True
    )
    target_spec: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    temporal_expression: Mapped[str | None] = mapped_column(Text, default=None)
    investment_horizon: Mapped[str] = mapped_column(String(16), default="unknown")
    horizon_source: Mapped[str] = mapped_column(
        String(32), nullable=False, default="missing"
    )
    time_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    verifiable_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    verifier_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="unsupported", index=True
    )
    scoring_eligible: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, index=True
    )
    verification_policy_version: Mapped[str] = mapped_column(
        String(32), nullable=False, default="prediction_contract_v1"
    )
    verdict: Mapped[str | None] = mapped_column(String(16), default=None)
    score: Mapped[float | None] = mapped_column(Float, default=None)
    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    verified_by: Mapped[str | None] = mapped_column(String(64), default=None)
    note: Mapped[str | None] = mapped_column(Text, default=None)
    instrument_snapshot: Mapped[dict | None] = mapped_column(JSONB, default=None)
    creation_rule_version: Mapped[str | None] = mapped_column(String(32), default=None)
    creation_evidence: Mapped[dict | None] = mapped_column(JSONB, default=None)

    __table_args__ = (
        Index("ix_predictions_handle_verdict", "blogger_handle", "verdict"),
        Index("ix_predictions_handle_ticker", "blogger_handle", "ticker"),
        Index(
            "ix_predictions_dedup",
            "blogger_handle",
            "ticker",
            "prediction_type",
            "sentiment",
            "investment_horizon",
            "published_at",
        ),
        Index(
            "ix_predictions_scoring_due",
            "scoring_eligible",
            "verifiable_at",
            "verdict",
        ),
    )
