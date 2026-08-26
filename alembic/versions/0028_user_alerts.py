"""Add persistent user alerts.

Revision ID: 0028_user_alerts
Revises: 0027_prediction_eligibility
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0028_user_alerts"
down_revision: Union[str, None] = "0027_prediction_eligibility"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("alert_key", sa.String(160), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False, server_default="info"),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("source_id", sa.String(64), nullable=False),
        sa.Column("target_url", sa.Text(), nullable=False),
        sa.Column("ticker", sa.String(32)),
        sa.Column("blogger_handle", sa.String(128)),
        sa.Column("status", sa.String(16), nullable=False, server_default="unread"),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "alert_key", name="uq_user_alert_key"),
    )
    op.create_index("ix_user_alert_feed", "user_alerts", ["user_id", "status", "occurred_at"])


def downgrade() -> None:
    op.drop_index("ix_user_alert_feed", table_name="user_alerts")
    op.drop_table("user_alerts")
