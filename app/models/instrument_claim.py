import uuid

from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class InstrumentClaim(Base, TimestampMixin):
    """One independently attributable view about one verified instrument."""

    __tablename__ = "instrument_claims"
    __table_args__ = (
        UniqueConstraint(
            "analysis_result_id",
            "claim_index",
            name="uq_instrument_claims_analysis_index",
        ),
        Index(
            "ix_instrument_claims_symbol_direction_horizon",
            "instrument_symbol",
            "direction",
            "horizon",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    analysis_result_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("analysis_results.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    claim_index: Mapped[int] = mapped_column(Integer, nullable=False)
    instrument_symbol: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    instrument_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    horizon: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    claim_type: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    opinion_source: Mapped[str] = mapped_column(String(16), nullable=False)
    thesis: Mapped[str] = mapped_column(Text, nullable=False, default="")
    evidence: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    media_evidence: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    catalysts: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    risk_factors: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    risk_details: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    risk_level: Mapped[str] = mapped_column(String(16), nullable=False, default="low")
    entry_conditions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    invalidation_conditions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    price_targets: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    forecast_spec: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    downstream_eligible: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, index=True
    )
    sponsor_relation: Mapped[str] = mapped_column(
        String(16), nullable=False, default="none", index=True
    )
    performance_eligible: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, index=True
    )
    performance_exclusion_reason: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    claim_schema_version: Mapped[str] = mapped_column(
        String(16), nullable=False, default="v4"
    )
