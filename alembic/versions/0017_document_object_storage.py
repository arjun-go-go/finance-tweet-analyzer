"""Add document object storage metadata.

Revision ID: 0017_document_object_storage
Revises: 0016_intelligence_topics
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0017_document_object_storage"
down_revision: Union[str, None] = "0016_intelligence_topics"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("storage_key", sa.Text(), nullable=True))
    op.add_column(
        "documents",
        sa.Column("storage_backend", sa.String(length=20), server_default="local", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("documents", "storage_backend")
    op.drop_column("documents", "storage_key")
