"""add search_vector tsvector column to doc_chunks

Revision ID: 0010_search_vector
Revises: 0009_tracked_tickers_reports
Create Date: 2026-06-08

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import TSVECTOR


revision: str = "0010_search_vector"
down_revision: str | None = "0009_tracked_tickers_reports"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("doc_chunks", sa.Column("search_vector", TSVECTOR, nullable=True))
    op.create_index(
        "ix_doc_chunks_search_vector",
        "doc_chunks",
        ["search_vector"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index("ix_doc_chunks_search_vector", table_name="doc_chunks")
    op.drop_column("doc_chunks", "search_vector")
