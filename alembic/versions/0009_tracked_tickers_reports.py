"""add tracked_tickers and reports tables

Revision ID: 0009_tracked_tickers_reports
Revises: 0008_documents
Create Date: 2026-06-05

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0009_tracked_tickers_reports"
down_revision: str | None = "0008_documents"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Allow doc_chunks to store signal chunks (tweets/analyses) without a parent document
    op.alter_column("doc_chunks", "document_id", nullable=True)

    op.create_table(
        "tracked_tickers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("ticker", sa.String(20), nullable=False),
        sa.Column("frequency", sa.String(20), nullable=False),
        sa.Column("last_report_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status", sa.String(20), nullable=False, server_default="active"
        ),
        sa.Column(
            "config",
            postgresql.JSONB,
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_tracked_user_ticker",
        "tracked_tickers",
        ["user_id", "ticker"],
        unique=True,
        postgresql_where=sa.text("status != 'deleted'"),
    )
    op.create_index(
        "ix_tracked_next_run",
        "tracked_tickers",
        ["next_run_at"],
        postgresql_where=sa.text("status = 'active'"),
    )

    op.create_table(
        "reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("ticker", sa.String(20), nullable=False),
        sa.Column("title", sa.Text, nullable=True),
        sa.Column("trigger_type", sa.String(20), nullable=False),
        sa.Column(
            "tracked_ticker_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tracked_tickers.id"),
            nullable=True,
        ),
        sa.Column(
            "sections",
            postgresql.JSONB,
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "citations",
            postgresql.JSONB,
            nullable=False,
            server_default="[]",
        ),
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column("consensus", sa.String(20), nullable=True),
        sa.Column("token_usage", postgresql.JSONB, nullable=True),
        sa.Column("latency_ms", sa.Integer, nullable=True),
        sa.Column(
            "status", sa.String(20), nullable=False, server_default="generating"
        ),
        sa.Column("error_detail", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_reports_user_ticker",
        "reports",
        ["user_id", "ticker", "created_at"],
    )
    op.create_index(
        "ix_reports_tracked",
        "reports",
        ["tracked_ticker_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_reports_tracked", table_name="reports")
    op.drop_index("ix_reports_user_ticker", table_name="reports")
    op.drop_table("reports")
    op.drop_index("ix_tracked_next_run", table_name="tracked_tickers")
    op.drop_index("ix_tracked_user_ticker", table_name="tracked_tickers")
    op.drop_table("tracked_tickers")
    op.alter_column("doc_chunks", "document_id", nullable=False)
