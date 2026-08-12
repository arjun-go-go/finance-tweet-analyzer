"""Add auditable prediction market verification records.

Revision ID: 0021_market_verifications
Revises: 0020_tweet_media_usage
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0021_market_verifications"
down_revision: Union[str, None] = "0020_tweet_media_usage"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "prediction_market_verifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("prediction_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("provider", sa.String(length=128), nullable=True),
        sa.Column("provider_symbol", sa.String(length=64), nullable=True),
        sa.Column("market", sa.String(length=16), nullable=True),
        sa.Column("start_observed_at", sa.String(length=64), nullable=True),
        sa.Column("start_price", sa.Float(), nullable=True),
        sa.Column("end_observed_at", sa.String(length=64), nullable=True),
        sa.Column("end_price", sa.Float(), nullable=True),
        sa.Column("raw_return", sa.Float(), nullable=True),
        sa.Column("directional_return", sa.Float(), nullable=True),
        sa.Column("threshold", sa.Float(), nullable=True),
        sa.Column("proposed_verdict", sa.String(length=16), nullable=True),
        sa.Column("proposed_score", sa.Float(), nullable=True),
        sa.Column(
            "rule_version",
            sa.String(length=32),
            nullable=False,
            server_default="market_auto_v1",
        ),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("applied", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["prediction_id"], ["predictions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_prediction_market_verifications_prediction_id",
        "prediction_market_verifications",
        ["prediction_id"],
    )
    op.create_index(
        "ix_prediction_market_verifications_status",
        "prediction_market_verifications",
        ["status"],
    )
    op.create_index(
        "ix_prediction_market_verifications_prediction_created",
        "prediction_market_verifications",
        ["prediction_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_prediction_market_verifications_prediction_created",
        table_name="prediction_market_verifications",
    )
    op.drop_index(
        "ix_prediction_market_verifications_status",
        table_name="prediction_market_verifications",
    )
    op.drop_index(
        "ix_prediction_market_verifications_prediction_id",
        table_name="prediction_market_verifications",
    )
    op.drop_table("prediction_market_verifications")
