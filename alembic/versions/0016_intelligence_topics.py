"""Add persistent intelligence topics and event membership.

Revision ID: 0016_intelligence_topics
Revises: 0015_intelligence_events
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0016_intelligence_topics"
down_revision: Union[str, None] = "0015_intelligence_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "intelligence_topics",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
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
        sa.Column("lifecycle", sa.String(length=16), server_default="new", nullable=False),
        sa.Column("event_count", sa.Integer(), server_default="1", nullable=False),
        sa.Column("evidence_count", sa.Integer(), server_default="1", nullable=False),
        sa.Column("source_count", sa.Integer(), server_default="1", nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="active", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_intelligence_topics_feed", "intelligence_topics", ["status", "last_seen_at"])
    op.create_index(
        "ix_intelligence_topics_match",
        "intelligence_topics",
        ["primary_ticker", "kind", "last_seen_at"],
    )
    op.add_column("intelligence_events", sa.Column("topic_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_intelligence_events_topic_id",
        "intelligence_events",
        "intelligence_topics",
        ["topic_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_intelligence_events_topic_id", "intelligence_events", ["topic_id"])


def downgrade() -> None:
    op.drop_index("ix_intelligence_events_topic_id", table_name="intelligence_events")
    op.drop_constraint("fk_intelligence_events_topic_id", "intelligence_events", type_="foreignkey")
    op.drop_column("intelligence_events", "topic_id")
    op.drop_index("ix_intelligence_topics_match", table_name="intelligence_topics")
    op.drop_index("ix_intelligence_topics_feed", table_name="intelligence_topics")
    op.drop_table("intelligence_topics")
