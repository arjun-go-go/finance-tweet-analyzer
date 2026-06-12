"""add documents and doc_chunks tables

Revision ID: 0008_documents
Revises: 40121ffe36bc
Create Date: 2026-06-05

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0008_documents"
down_revision: str | None = "40121ffe36bc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("source_type", sa.String(20), nullable=False),
        sa.Column("source_uri", sa.Text, nullable=True),
        sa.Column("content_hash", sa.CHAR(64), nullable=False),
        sa.Column("char_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("chunk_count", sa.Integer, server_default="0"),
        sa.Column("file_size_bytes", sa.Integer, server_default="0"),
        sa.Column(
            "tickers",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("publish_date", sa.Date, nullable=True),
        sa.Column(
            "status", sa.String(20), nullable=False, server_default="pending"
        ),
        sa.Column("error_detail", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "user_id", "content_hash", name="uq_documents_user_hash"
        ),
    )
    op.create_index(
        "ix_documents_user_status", "documents", ["user_id", "status"]
    )
    op.create_index(
        "ix_documents_tickers",
        "documents",
        ["tickers"],
        postgresql_using="gin",
    )

    op.create_table(
        "doc_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("chunk_index", sa.Integer, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("content_hash", sa.CHAR(64), nullable=False),
        sa.Column("char_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "metadata",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("vector_id", sa.String(64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_doc_chunks_document", "doc_chunks", ["document_id"]
    )
    op.create_index(
        "ix_doc_chunks_hash", "doc_chunks", ["content_hash"]
    )


def downgrade() -> None:
    op.drop_index("ix_doc_chunks_hash", table_name="doc_chunks")
    op.drop_index("ix_doc_chunks_document", table_name="doc_chunks")
    op.drop_table("doc_chunks")

    op.drop_index("ix_documents_tickers", table_name="documents")
    op.drop_index("ix_documents_user_status", table_name="documents")
    op.drop_table("documents")
