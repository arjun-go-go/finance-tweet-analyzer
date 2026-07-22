"""Add Elasticsearch index job ledger.

Revision ID: 0011_es_index_jobs
Revises: c7b6e2d9f104
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0011_es_index_jobs"
down_revision: Union[str, None] = "c7b6e2d9f104"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "es_index_jobs",
        sa.Column("doc_chunk_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "target",
            sa.String(length=32),
            server_default="elasticsearch",
            nullable=False,
        ),
        sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["doc_chunk_id"], ["doc_chunks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("doc_chunk_id"),
    )
    op.create_index("ix_es_index_jobs_status", "es_index_jobs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_es_index_jobs_status", table_name="es_index_jobs")
    op.drop_table("es_index_jobs")
