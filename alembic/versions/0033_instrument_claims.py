"""Make per-instrument claims the canonical analysis business object.

Revision ID: 0033_instrument_claims
Revises: 0032_mem0_shared_history
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0033_instrument_claims"
down_revision: str | None = "0032_mem0_shared_history"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    empty_json = sa.text("'[]'::jsonb")
    op.create_table(
        "instrument_claims",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("analysis_result_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("claim_index", sa.Integer(), nullable=False),
        sa.Column("instrument_symbol", sa.String(64), nullable=False),
        sa.Column("instrument_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("direction", sa.String(16), nullable=False),
        sa.Column("horizon", sa.String(16), nullable=False),
        sa.Column("claim_type", sa.String(24), nullable=False),
        sa.Column("opinion_source", sa.String(16), nullable=False),
        sa.Column("thesis", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("evidence", postgresql.JSONB(), nullable=False, server_default=empty_json),
        sa.Column("media_evidence", postgresql.JSONB(), nullable=False, server_default=empty_json),
        sa.Column("catalysts", postgresql.JSONB(), nullable=False, server_default=empty_json),
        sa.Column("risk_factors", postgresql.JSONB(), nullable=False, server_default=empty_json),
        sa.Column("risk_details", postgresql.JSONB(), nullable=False, server_default=empty_json),
        sa.Column("risk_level", sa.String(16), nullable=False, server_default="low"),
        sa.Column("entry_conditions", postgresql.JSONB(), nullable=False, server_default=empty_json),
        sa.Column("invalidation_conditions", postgresql.JSONB(), nullable=False, server_default=empty_json),
        sa.Column("price_targets", postgresql.JSONB(), nullable=False, server_default=empty_json),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("downstream_eligible", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("claim_schema_version", sa.String(16), nullable=False, server_default="v3"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["analysis_result_id"], ["analysis_results.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "analysis_result_id",
            "claim_index",
            name="uq_instrument_claims_analysis_index",
        ),
    )
    op.create_index(
        "ix_instrument_claims_analysis_result_id",
        "instrument_claims",
        ["analysis_result_id"],
    )
    op.create_index(
        "ix_instrument_claims_instrument_symbol",
        "instrument_claims",
        ["instrument_symbol"],
    )
    op.create_index("ix_instrument_claims_direction", "instrument_claims", ["direction"])
    op.create_index("ix_instrument_claims_horizon", "instrument_claims", ["horizon"])
    op.create_index("ix_instrument_claims_claim_type", "instrument_claims", ["claim_type"])
    op.create_index(
        "ix_instrument_claims_downstream_eligible",
        "instrument_claims",
        ["downstream_eligible"],
    )
    op.create_index(
        "ix_instrument_claims_symbol_direction_horizon",
        "instrument_claims",
        ["instrument_symbol", "direction", "horizon"],
    )

    op.add_column(
        "predictions",
        sa.Column("claim_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_predictions_claim_id",
        "predictions",
        "instrument_claims",
        ["claim_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_predictions_claim_id", "predictions", ["claim_id"])
    op.drop_index("ix_predictions_dedup", table_name="predictions")
    op.create_index(
        "ix_predictions_dedup",
        "predictions",
        [
            "blogger_handle",
            "ticker",
            "sentiment",
            "investment_horizon",
            "published_at",
        ],
    )

    op.drop_constraint(
        "intelligence_events_analysis_result_id_key",
        "intelligence_events",
        type_="unique",
    )
    op.create_index(
        "ix_intelligence_events_analysis_result_id",
        "intelligence_events",
        ["analysis_result_id"],
    )
    op.add_column(
        "intelligence_events",
        sa.Column("claim_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "intelligence_events",
        sa.Column("horizon", sa.String(16), nullable=False, server_default="unknown"),
    )
    op.create_foreign_key(
        "fk_intelligence_events_claim_id",
        "intelligence_events",
        "instrument_claims",
        ["claim_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_unique_constraint(
        "uq_intelligence_events_claim_id", "intelligence_events", ["claim_id"]
    )

    op.add_column(
        "intelligence_topics",
        sa.Column("horizon", sa.String(16), nullable=False, server_default="unknown"),
    )
    op.drop_index("ix_intelligence_topics_match", table_name="intelligence_topics")
    op.create_index(
        "ix_intelligence_topics_match",
        "intelligence_topics",
        ["primary_ticker", "kind", "horizon", "last_seen_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_intelligence_topics_match", table_name="intelligence_topics")
    op.create_index(
        "ix_intelligence_topics_match",
        "intelligence_topics",
        ["primary_ticker", "kind", "last_seen_at"],
    )
    op.drop_column("intelligence_topics", "horizon")

    op.execute("DELETE FROM intelligence_events WHERE claim_id IS NOT NULL")
    op.drop_constraint(
        "uq_intelligence_events_claim_id", "intelligence_events", type_="unique"
    )
    op.drop_constraint(
        "fk_intelligence_events_claim_id", "intelligence_events", type_="foreignkey"
    )
    op.drop_column("intelligence_events", "horizon")
    op.drop_column("intelligence_events", "claim_id")
    op.drop_index(
        "ix_intelligence_events_analysis_result_id", table_name="intelligence_events"
    )
    op.create_unique_constraint(
        "intelligence_events_analysis_result_id_key",
        "intelligence_events",
        ["analysis_result_id"],
    )

    op.drop_index("ix_predictions_dedup", table_name="predictions")
    op.create_index(
        "ix_predictions_dedup",
        "predictions",
        ["blogger_handle", "ticker", "sentiment", "published_at"],
    )
    op.drop_index("ix_predictions_claim_id", table_name="predictions")
    op.drop_constraint("fk_predictions_claim_id", "predictions", type_="foreignkey")
    op.drop_column("predictions", "claim_id")

    op.drop_index(
        "ix_instrument_claims_symbol_direction_horizon",
        table_name="instrument_claims",
    )
    op.drop_index(
        "ix_instrument_claims_downstream_eligible", table_name="instrument_claims"
    )
    op.drop_index("ix_instrument_claims_claim_type", table_name="instrument_claims")
    op.drop_index("ix_instrument_claims_horizon", table_name="instrument_claims")
    op.drop_index("ix_instrument_claims_direction", table_name="instrument_claims")
    op.drop_index(
        "ix_instrument_claims_instrument_symbol", table_name="instrument_claims"
    )
    op.drop_index(
        "ix_instrument_claims_analysis_result_id", table_name="instrument_claims"
    )
    op.drop_table("instrument_claims")
