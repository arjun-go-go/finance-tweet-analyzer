"""Store mem0 history and recent messages in shared PostgreSQL.

Revision ID: 0032_mem0_shared_history
Revises: 0031_schema_metadata_alignment
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0032_mem0_shared_history"
down_revision: str | None = "0031_schema_metadata_alignment"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "mem0_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("memory_id", sa.String(128), nullable=False),
        sa.Column("old_memory", sa.Text(), nullable=True),
        sa.Column("new_memory", sa.Text(), nullable=True),
        sa.Column("event", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("actor_id", sa.String(128), nullable=True),
        sa.Column("role", sa.String(32), nullable=True),
    )
    op.create_index("ix_mem0_history_memory_id", "mem0_history", ["memory_id", "created_at"])

    op.create_table(
        "mem0_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("session_scope", sa.Text(), nullable=False),
        sa.Column("role", sa.String(32), nullable=True),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("name", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_mem0_messages_scope", "mem0_messages", ["session_scope", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_mem0_messages_scope", table_name="mem0_messages")
    op.drop_table("mem0_messages")
    op.drop_index("ix_mem0_history_memory_id", table_name="mem0_history")
    op.drop_table("mem0_history")
