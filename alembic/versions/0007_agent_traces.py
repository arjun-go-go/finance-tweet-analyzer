"""add agent_traces table

Revision ID: 0007_agent_traces
Revises: 0006_users
Create Date: 2026-06-01

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0007_agent_traces"
down_revision: str | None = "0006_users"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_traces",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("node_name", sa.String(64), nullable=False),
        sa.Column("tool_name", sa.String(128), nullable=True),
        sa.Column("input", postgresql.JSONB, nullable=True),
        sa.Column("output", postgresql.JSONB, nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="success"),
        sa.Column("retry_count", sa.Integer, server_default="0"),
        sa.Column("latency_ms", sa.Integer, server_default="0"),
        sa.Column("error_detail", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        comment="Agent execution traces - immutable audit log, not cascade-deleted",
    )
    op.create_index(
        "ix_agent_traces_conv_created",
        "agent_traces",
        ["conversation_id", "created_at"],
    )
    op.create_index(
        "ix_agent_traces_tool_status_created",
        "agent_traces",
        ["tool_name", "status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_agent_traces_tool_status_created", table_name="agent_traces")
    op.drop_index("ix_agent_traces_conv_created", table_name="agent_traces")
    op.drop_table("agent_traces")
