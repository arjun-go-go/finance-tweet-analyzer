"""add user_preferences table

Revision ID: 0003_user_preferences
Revises: 0002_blogger_twitter_meta
Create Date: 2026-05-29

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0003_user_preferences"
down_revision: str | None = "0002_blogger_twitter_meta"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_preferences",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            comment="主键 UUID",
        ),
        sa.Column(
            "user_id",
            sa.String(128),
            nullable=False,
            server_default="default",
            comment="用户标识，单用户模式固定为 default",
        ),
        sa.Column(
            "preference_type",
            sa.String(64),
            nullable=False,
            comment="偏好类型：watched_bloggers/interested_tickers/reply_style/identity/investment_style",
        ),
        sa.Column(
            "value",
            postgresql.JSONB(),
            nullable=False,
            comment="偏好内容，JSON 结构由 preference_type 决定",
        ),
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
            comment="最近更新时间，upsert 时自动刷新",
        ),
        sa.UniqueConstraint("user_id", "preference_type", name="uq_user_pref_type"),
        comment="用户长期偏好记忆表，跨对话生效",
    )
    op.create_index(
        "ix_user_preferences_user_id", "user_preferences", ["user_id"], unique=False
    )
    op.create_index(
        "ix_user_preferences_preference_type",
        "user_preferences",
        ["preference_type"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_user_preferences_preference_type", table_name="user_preferences"
    )
    op.drop_index("ix_user_preferences_user_id", table_name="user_preferences")
    op.drop_table("user_preferences")
