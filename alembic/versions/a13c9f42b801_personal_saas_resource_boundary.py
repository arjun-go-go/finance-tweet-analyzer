"""Add personal SaaS resource boundaries and analysis jobs.

Revision ID: a13c9f42b801
Revises: 3f3258d837fe
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "a13c9f42b801"
down_revision: Union[str, None] = "3f3258d837fe"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_blogger_follows",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("blogger_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["blogger_id"], ["bloggers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "blogger_id", name="uq_user_blogger_follow"
        ),
    )
    op.create_index(
        "ix_user_blogger_follow_created",
        "user_blogger_follows",
        ["user_id", "created_at"],
    )

    op.create_table(
        "user_tweet_bookmarks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tweet_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["tweet_id"], ["tweets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "tweet_id", name="uq_user_tweet_bookmark"
        ),
    )
    op.create_index(
        "ix_user_tweet_bookmark_created",
        "user_tweet_bookmarks",
        ["user_id", "created_at"],
    )

    op.create_table(
        "analysis_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "requested_by_user_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("celery_task_id", sa.String(length=64), nullable=True),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column(
            "request_payload",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "status",
            sa.String(length=24),
            nullable=False,
            server_default="queued",
        ),
        sa.Column("batch_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "reused_result",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_summary", sa.String(length=512), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("celery_task_id"),
    )
    op.create_index(
        "ix_analysis_jobs_user_created",
        "analysis_jobs",
        ["requested_by_user_id", "created_at"],
    )
    op.create_index(
        "ix_analysis_jobs_status_created",
        "analysis_jobs",
        ["status", "created_at"],
    )

    op.add_column(
        "analysis_results",
        sa.Column("cache_key", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "analysis_results",
        sa.Column(
            "pipeline_version",
            sa.String(length=32),
            nullable=False,
            server_default="v1",
        ),
    )
    op.create_index(
        "uq_analysis_results_cache_key",
        "analysis_results",
        ["cache_key"],
        unique=True,
        postgresql_where=sa.text("cache_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_analysis_results_cache_key", table_name="analysis_results")
    op.drop_column("analysis_results", "pipeline_version")
    op.drop_column("analysis_results", "cache_key")

    op.drop_index("ix_analysis_jobs_status_created", table_name="analysis_jobs")
    op.drop_index("ix_analysis_jobs_user_created", table_name="analysis_jobs")
    op.drop_table("analysis_jobs")

    op.drop_index(
        "ix_user_tweet_bookmark_created", table_name="user_tweet_bookmarks"
    )
    op.drop_table("user_tweet_bookmarks")

    op.drop_index(
        "ix_user_blogger_follow_created", table_name="user_blogger_follows"
    )
    op.drop_table("user_blogger_follows")
