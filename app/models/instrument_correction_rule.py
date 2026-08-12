import uuid

from sqlalchemy import Boolean, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class InstrumentCorrectionRule(Base, TimestampMixin):
    """A human-approved, context-scoped instrument identity correction."""

    __tablename__ = "instrument_correction_rules"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source_symbol: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    context_terms: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    corrected_instrument: Mapped[dict] = mapped_column(JSONB, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        Index(
            "ix_instrument_correction_rules_source_active",
            "source_symbol",
            "active",
        ),
    )
