"""Unify index jobs and drop PG search vector.

Revision ID: 0012_index_jobs
Revises: 0011_es_index_jobs
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0012_index_jobs"
down_revision: Union[str, None] = "0011_es_index_jobs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.rename_table("es_index_jobs", "index_jobs")
    op.drop_constraint("es_index_jobs_pkey", "index_jobs", type_="primary")
    op.create_primary_key("index_jobs_pkey", "index_jobs", ["doc_chunk_id", "target"])
    op.drop_index("ix_es_index_jobs_status", table_name="index_jobs")
    op.create_index("ix_index_jobs_status", "index_jobs", ["status"])
    op.drop_column("doc_chunks", "search_vector")


def downgrade() -> None:
    op.add_column("doc_chunks", sa.Column("search_vector", postgresql.TSVECTOR(), nullable=True))
    op.drop_index("ix_index_jobs_status", table_name="index_jobs")
    op.create_index("ix_es_index_jobs_status", "index_jobs", ["status"])
    op.drop_constraint("index_jobs_pkey", "index_jobs", type_="primary")
    op.create_primary_key("es_index_jobs_pkey", "index_jobs", ["doc_chunk_id"])
    op.rename_table("index_jobs", "es_index_jobs")
