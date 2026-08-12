"""Add persistent intelligence events and evidence.

Revision ID: 0015_intelligence_events
Revises: 0014_tweet_analysis_state
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0015_intelligence_events"
down_revision: Union[str, None] = "0014_tweet_analysis_state"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "intelligence_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("analysis_result_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tweet_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("direction", sa.String(length=16), nullable=False),
        sa.Column("primary_ticker", sa.String(length=32), nullable=False),
        sa.Column("tickers", postgresql.ARRAY(sa.String(length=32)), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("source_credibility", sa.Float(), nullable=False),
        sa.Column("risk_level", sa.String(length=16), nullable=False),
        sa.Column("risk_factors", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("key_points", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("model_used", sa.String(length=64), nullable=False),
        sa.Column("pipeline_version", sa.String(length=32), nullable=False),
        sa.Column("projection_version", sa.String(length=16), server_default="v1", nullable=False),
        sa.Column("status", sa.String(length=16), server_default="active", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["analysis_result_id"], ["analysis_results.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tweet_id"], ["tweets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("analysis_result_id"),
    )
    op.create_index("ix_intelligence_events_feed", "intelligence_events", ["status", "published_at"])
    op.create_index("ix_intelligence_events_primary_ticker", "intelligence_events", ["primary_ticker"])
    op.create_index("ix_intelligence_events_fingerprint", "intelligence_events", ["fingerprint"])
    op.create_index("ix_intelligence_events_tweet_id", "intelligence_events", ["tweet_id"])

    op.create_table(
        "intelligence_evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("source_id", sa.String(length=64), nullable=False),
        sa.Column("author", sa.String(length=128), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("excerpt", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["intelligence_events.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", "source_type", "source_id", name="uq_intelligence_evidence_source"),
    )
    op.create_index("ix_intelligence_evidence_event", "intelligence_evidence", ["event_id"])


def downgrade() -> None:
    op.drop_index("ix_intelligence_evidence_event", table_name="intelligence_evidence")
    op.drop_table("intelligence_evidence")
    op.drop_index("ix_intelligence_events_tweet_id", table_name="intelligence_events")
    op.drop_index("ix_intelligence_events_fingerprint", table_name="intelligence_events")
    op.drop_index("ix_intelligence_events_primary_ticker", table_name="intelligence_events")
    op.drop_index("ix_intelligence_events_feed", table_name="intelligence_events")
    op.drop_table("intelligence_events")
