"""Add reusable human instrument correction rules.

Revision ID: 0023_instrument_rules
Revises: 0022_prediction_instrument
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0023_instrument_rules"
down_revision: Union[str, None] = "0022_prediction_instrument"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "instrument_correction_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_symbol", sa.String(length=64), nullable=False),
        sa.Column("context_terms", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("corrected_instrument", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_instrument_correction_rules_source_symbol",
        "instrument_correction_rules",
        ["source_symbol"],
    )
    op.create_index(
        "ix_instrument_correction_rules_source_active",
        "instrument_correction_rules",
        ["source_symbol", "active"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_instrument_correction_rules_source_active",
        table_name="instrument_correction_rules",
    )
    op.drop_index(
        "ix_instrument_correction_rules_source_symbol",
        table_name="instrument_correction_rules",
    )
    op.drop_table("instrument_correction_rules")
