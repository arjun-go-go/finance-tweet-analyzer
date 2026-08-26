"""Add user intelligence correction records.

Revision ID: 0029_intelligence_corrections
Revises: 0028_user_alerts
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0029_intelligence_corrections"
down_revision: Union[str, None] = "0028_user_alerts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "intelligence_corrections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "topic_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("intelligence_topics.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("snapshot", postgresql.JSONB(), nullable=False, server_default="{}"),
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
    )
    op.create_index(
        "ix_intelligence_corrections_review",
        "intelligence_corrections",
        ["status", "created_at"],
    )
    op.create_index(
        "ix_intelligence_corrections_topic",
        "intelligence_corrections",
        ["topic_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_intelligence_corrections_topic",
        table_name="intelligence_corrections",
    )
    op.drop_index(
        "ix_intelligence_corrections_review",
        table_name="intelligence_corrections",
    )
    op.drop_table("intelligence_corrections")
