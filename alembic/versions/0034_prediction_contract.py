"""Add auditable prediction contracts and generic verification metadata.

Revision ID: 0034_prediction_contract
Revises: 0033_instrument_claims
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0034_prediction_contract"
down_revision: str | None = "0033_instrument_claims"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    empty_object = sa.text("'{}'::jsonb")

    op.add_column(
        "instrument_claims",
        sa.Column(
            "forecast_spec",
            postgresql.JSONB(),
            nullable=False,
            server_default=empty_object,
        ),
    )
    op.alter_column(
        "instrument_claims",
        "claim_schema_version",
        server_default="v4",
    )

    op.add_column(
        "predictions",
        sa.Column(
            "prediction_type",
            sa.String(32),
            nullable=False,
            server_default="price_direction",
        ),
    )
    op.add_column(
        "predictions",
        sa.Column(
            "target_spec",
            postgresql.JSONB(),
            nullable=False,
            server_default=empty_object,
        ),
    )
    op.add_column("predictions", sa.Column("temporal_expression", sa.Text(), nullable=True))
    op.add_column(
        "predictions",
        sa.Column(
            "horizon_source",
            sa.String(32),
            nullable=False,
            server_default="legacy_fixed_window",
        ),
    )
    op.add_column(
        "predictions",
        sa.Column("time_confidence", sa.Float(), nullable=False, server_default="0.4"),
    )
    op.add_column(
        "predictions",
        sa.Column(
            "verifier_type",
            sa.String(32),
            nullable=False,
            server_default="market_price_direction",
        ),
    )
    op.add_column(
        "predictions",
        sa.Column(
            "scoring_eligible",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.add_column(
        "predictions",
        sa.Column(
            "verification_policy_version",
            sa.String(32),
            nullable=False,
            server_default="market_auto_v1",
        ),
    )
    op.execute(
        """
        UPDATE predictions
        SET target_spec = jsonb_build_object(
            'prediction_type', 'price_direction',
            'direction', sentiment
        ),
            scoring_eligible = sentiment IN ('bullish', 'bearish')
        """
    )
    op.alter_column("predictions", "verifiable_at", nullable=True)
    op.create_index("ix_predictions_prediction_type", "predictions", ["prediction_type"])
    op.create_index("ix_predictions_verifier_type", "predictions", ["verifier_type"])
    op.create_index("ix_predictions_scoring_eligible", "predictions", ["scoring_eligible"])
    op.create_index(
        "ix_predictions_scoring_due",
        "predictions",
        ["scoring_eligible", "verifiable_at", "verdict"],
    )
    op.drop_index("ix_predictions_dedup", table_name="predictions")
    op.create_index(
        "ix_predictions_dedup",
        "predictions",
        [
            "blogger_handle",
            "ticker",
            "prediction_type",
            "sentiment",
            "investment_horizon",
            "published_at",
        ],
    )

    op.add_column(
        "prediction_market_verifications",
        sa.Column(
            "verification_type",
            sa.String(32),
            nullable=False,
            server_default="market_price_direction",
        ),
    )
    op.add_column(
        "prediction_market_verifications",
        sa.Column(
            "observation",
            postgresql.JSONB(),
            nullable=False,
            server_default=empty_object,
        ),
    )
    op.create_index(
        "ix_prediction_market_verifications_verification_type",
        "prediction_market_verifications",
        ["verification_type"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_prediction_market_verifications_verification_type",
        table_name="prediction_market_verifications",
    )
    op.drop_column("prediction_market_verifications", "observation")
    op.drop_column("prediction_market_verifications", "verification_type")

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
    op.drop_index("ix_predictions_scoring_due", table_name="predictions")
    op.drop_index("ix_predictions_scoring_eligible", table_name="predictions")
    op.drop_index("ix_predictions_verifier_type", table_name="predictions")
    op.drop_index("ix_predictions_prediction_type", table_name="predictions")
    op.alter_column("predictions", "verifiable_at", nullable=False)
    op.drop_column("predictions", "verification_policy_version")
    op.drop_column("predictions", "scoring_eligible")
    op.drop_column("predictions", "verifier_type")
    op.drop_column("predictions", "time_confidence")
    op.drop_column("predictions", "horizon_source")
    op.drop_column("predictions", "temporal_expression")
    op.drop_column("predictions", "target_spec")
    op.drop_column("predictions", "prediction_type")

    op.alter_column(
        "instrument_claims",
        "claim_schema_version",
        server_default="v3",
    )
    op.drop_column("instrument_claims", "forecast_spec")
