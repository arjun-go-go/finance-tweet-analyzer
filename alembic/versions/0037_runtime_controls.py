"""Add persistent runtime controls for paid model analysis.

Revision ID: 0037_runtime_controls
Revises: 0036_remove_retired_chat
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0037_runtime_controls"
down_revision: str | None = "0036_remove_retired_chat"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "runtime_controls",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column(
            "mode",
            sa.String(length=32),
            nullable=False,
            server_default="enabled",
        ),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("provider", sa.String(length=64), nullable=True),
        sa.Column("model", sa.String(length=160), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "consecutive_failures",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("last_failure_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resume_after", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_by", sa.String(length=64), nullable=True),
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
        sa.PrimaryKeyConstraint("key"),
    )
    op.execute(
        "INSERT INTO runtime_controls (key, mode, updated_by) "
        "VALUES ('llm_analysis', 'enabled', 'migration')"
    )


def downgrade() -> None:
    op.drop_table("runtime_controls")
