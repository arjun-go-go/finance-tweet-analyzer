"""Focus persistence on the Twitter intelligence product core.

Revision ID: 0030_twitter_intelligence_core
Revises: 0029_intelligence_corrections
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0030_twitter_intelligence_core"
down_revision: str | None = "0029_intelligence_corrections"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # RAG ledger: make source identity first-class and remove the retired
    # private-document relationship while preserving all tweet/analysis chunks.
    op.rename_table("doc_chunks", "content_chunks")
    op.alter_column(
        "index_jobs",
        "doc_chunk_id",
        new_column_name="content_chunk_id",
        existing_type=postgresql.UUID(as_uuid=True),
        existing_nullable=False,
    )
    op.drop_constraint(
        "es_index_jobs_doc_chunk_id_fkey", "index_jobs", type_="foreignkey"
    )
    op.create_foreign_key(
        "fk_index_jobs_content_chunk_id",
        "index_jobs",
        "content_chunks",
        ["content_chunk_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.add_column(
        "content_chunks", sa.Column("source_type", sa.String(32), nullable=True)
    )
    op.add_column(
        "content_chunks", sa.Column("source_id", sa.String(128), nullable=True)
    )
    op.add_column(
        "content_chunks", sa.Column("index_stage", sa.String(32), nullable=True)
    )
    op.execute(
        """
        UPDATE content_chunks
        SET source_type = metadata->>'source_type',
            source_id = metadata->>'source_id',
            index_stage = COALESCE(metadata->>'index_stage', metadata->>'source_type')
        """
    )
    op.alter_column("content_chunks", "source_type", nullable=False)
    op.alter_column("content_chunks", "source_id", nullable=False)
    op.alter_column("content_chunks", "index_stage", nullable=False)

    op.drop_constraint(
        "doc_chunks_document_id_fkey", "content_chunks", type_="foreignkey"
    )
    op.drop_index("ix_doc_chunks_document", table_name="content_chunks")
    op.drop_index("ix_doc_chunks_hash", table_name="content_chunks")
    op.drop_column("content_chunks", "document_id")
    op.execute(
        """
        UPDATE content_chunks
        SET metadata = metadata - 'source_type' - 'source_id' - 'index_stage'
        """
    )
    op.create_unique_constraint(
        "uq_content_chunks_source_part",
        "content_chunks",
        ["source_type", "source_id", "chunk_index"],
    )
    op.create_index(
        "ix_content_chunks_source",
        "content_chunks",
        ["source_type", "source_id"],
    )
    op.create_index(
        "ix_content_chunks_stage",
        "content_chunks",
        ["index_stage", "created_at"],
    )
    op.create_index(
        "ix_content_chunks_hash", "content_chunks", ["content_hash"]
    )

    # Intelligence evidence is already reachable through
    # event -> analysis_result -> tweet; keep one canonical copy.
    op.drop_table("intelligence_evidence")
    op.drop_index("ix_intelligence_events_tweet_id", table_name="intelligence_events")
    op.drop_index(
        "ix_intelligence_events_fingerprint", table_name="intelligence_events"
    )
    op.drop_constraint(
        "intelligence_events_tweet_id_fkey",
        "intelligence_events",
        type_="foreignkey",
    )
    op.drop_column("intelligence_events", "tweet_id")
    op.drop_column("intelligence_events", "fingerprint")
    op.drop_column("intelligence_events", "model_used")
    op.drop_column("intelligence_events", "pipeline_version")
    op.drop_column("intelligence_topics", "evidence_count")

    # Watch is a user scope, not a scheduled-report system.
    op.drop_index("ix_tracked_next_run", table_name="tracked_tickers")
    op.execute(
        """
        UPDATE tracked_tickers
        SET config = jsonb_set(
            config
              - 'report_status'
              - 'current_report_id'
              - 'report_queued_at'
              - 'last_report_error'
              - 'report_completed_at'
              - 'report_started_at',
            '{alerts}',
            COALESCE(config->'alerts', '{}'::jsonb) - 'report_failure',
            true
        )
        """
    )
    op.drop_column("tracked_tickers", "frequency")
    op.drop_column("tracked_tickers", "last_report_at")
    op.drop_column("tracked_tickers", "next_run_at")

    # Conversation ownership belongs to users; message/user counters are derived.
    op.alter_column(
        "conversations",
        "user_id",
        existing_type=sa.String(128),
        type_=postgresql.UUID(as_uuid=True),
        existing_nullable=False,
        postgresql_using="user_id::uuid",
    )
    op.create_foreign_key(
        "fk_conversations_user_id_users",
        "conversations",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_column("conversations", "message_count")
    op.drop_column("conversations", "total_tokens")
    op.drop_column("conversations", "last_message_at")
    op.drop_index("ix_messages_user_id", table_name="messages")
    op.drop_column("messages", "user_id")
    op.drop_column("messages", "tool_result")
    op.drop_column("messages", "token_count")
    op.drop_column("messages", "parent_id")

    # Retired products and empty/obsolete personal-memory mirrors.
    op.drop_table("research_conclusions")
    op.drop_table("research_evidence")
    op.drop_table("research_topics")
    op.drop_table("reports")
    op.drop_table("analysis_jobs")
    op.drop_table("user_tweet_bookmarks")
    op.drop_table("user_preferences")
    op.drop_table("user_profile")
    op.drop_table("documents")


def downgrade() -> None:
    raise RuntimeError(
        "0030 removes retired product tables and is intentionally irreversible; "
        "restore a database backup to roll back."
    )
