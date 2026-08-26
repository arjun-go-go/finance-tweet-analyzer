"""Align ORM metadata and remove redundant indexes.

Revision ID: 0031_schema_metadata_alignment
Revises: 0030_twitter_intelligence_core
"""

from collections.abc import Sequence

from alembic import op


revision: str = "0031_schema_metadata_alignment"
down_revision: str | None = "0030_twitter_intelligence_core"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "UPDATE agent_traces SET retry_count = 0 WHERE retry_count IS NULL"
    )
    op.execute(
        "UPDATE agent_traces SET latency_ms = 0 WHERE latency_ms IS NULL"
    )
    op.alter_column("agent_traces", "retry_count", nullable=False)
    op.alter_column("agent_traces", "latency_ms", nullable=False)

    op.execute(
        "UPDATE instrument_correction_rules SET created_at = now() "
        "WHERE created_at IS NULL"
    )
    op.alter_column("instrument_correction_rules", "created_at", nullable=False)

    op.execute(
        "UPDATE tracked_tickers SET created_at = now() WHERE created_at IS NULL"
    )
    op.execute(
        "UPDATE tracked_tickers SET updated_at = created_at WHERE updated_at IS NULL"
    )
    op.alter_column("tracked_tickers", "created_at", nullable=False)
    op.alter_column("tracked_tickers", "updated_at", nullable=False)

    # The unique constraints already provide equivalent btree indexes.
    op.drop_index("ix_bloggers_handle", table_name="bloggers")
    op.drop_index("ix_tweets_tweet_id", table_name="tweets")
    op.drop_index("ix_messages_conv_seq", table_name="messages")


def downgrade() -> None:
    op.create_index("ix_messages_conv_seq", "messages", ["conversation_id", "sequence"])
    op.create_index("ix_tweets_tweet_id", "tweets", ["tweet_id"])
    op.create_index("ix_bloggers_handle", "bloggers", ["handle"])
    op.alter_column("tracked_tickers", "updated_at", nullable=True)
    op.alter_column("tracked_tickers", "created_at", nullable=True)
    op.alter_column("instrument_correction_rules", "created_at", nullable=True)
    op.alter_column("agent_traces", "latency_ms", nullable=True)
    op.alter_column("agent_traces", "retry_count", nullable=True)
