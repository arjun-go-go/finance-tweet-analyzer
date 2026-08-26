"""Add durable research workspace entities.

Revision ID: 0024_research_workspace
Revises: 0023_instrument_rules
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0024_research_workspace"
down_revision: Union[str, None] = "0023_instrument_rules"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "research_topics",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("conversations.id", ondelete="SET NULL")),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("research_question", sa.Text(), nullable=False),
        sa.Column("mode", sa.String(16), nullable=False, server_default="quick"),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("tickers", postgresql.ARRAY(sa.String(32)), nullable=False, server_default="{}"),
        sa.Column("source_scope", postgresql.ARRAY(sa.String(32)), nullable=False, server_default="{}"),
        sa.Column("time_range", sa.String(16), nullable=False, server_default="1w"),
        sa.Column("current_conclusion", sa.Text()),
        sa.Column("monitor_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("monitor_frequency", sa.String(16), nullable=False, server_default="weekly"),
        sa.Column("next_run_at", sa.DateTime(timezone=True)),
        sa.Column("last_run_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_research_topics_user_status", "research_topics", ["user_id", "status", "updated_at"])
    op.create_table(
        "research_evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("topic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("research_topics.id", ondelete="CASCADE"), nullable=False),
        sa.Column("evidence_key", sa.String(32), nullable=False),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("source_id", sa.String(128), nullable=False),
        sa.Column("tickers", postgresql.ARRAY(sa.String(32)), nullable=False, server_default="{}"),
        sa.Column("author", sa.String(128), nullable=False, server_default=""),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("excerpt", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False, server_default=""),
        sa.Column("sentiment", sa.String(16), nullable=False, server_default=""),
        sa.Column("verification_status", sa.String(24), nullable=False, server_default="indexed"),
        sa.Column("relevance_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("topic_id", "evidence_key", name="uq_research_evidence_key"),
    )
    op.create_index("ix_research_evidence_topic", "research_evidence", ["topic_id", "created_at"])
    op.create_table(
        "research_conclusions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("topic_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("research_topics.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("conclusion", sa.Text(), nullable=False),
        sa.Column("thesis", sa.Text(), nullable=False, server_default=""),
        sa.Column("counter_evidence", sa.Text(), nullable=False, server_default=""),
        sa.Column("risks", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("evidence_keys", postgresql.ARRAY(sa.String(32)), nullable=False, server_default="{}"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("topic_id", "version", name="uq_research_conclusion_version"),
    )
    op.create_index("ix_research_conclusions_topic_version", "research_conclusions", ["topic_id", "version"])


def downgrade() -> None:
    op.drop_table("research_conclusions")
    op.drop_table("research_evidence")
    op.drop_table("research_topics")
