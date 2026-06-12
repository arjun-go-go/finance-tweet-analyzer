"""add user_profile table

Revision ID: 0004_user_profile
Revises: 0003_user_preferences
Create Date: 2026-05-29

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0004_user_profile"
down_revision: str | None = "0003_user_preferences"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_profile",
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
            comment="用户标识，唯一一行一用户",
        ),
        sa.Column("name", sa.String(128), nullable=True, comment="真实姓名"),
        sa.Column("nickname", sa.String(128), nullable=True, comment="昵称"),
        sa.Column(
            "occupation",
            sa.String(128),
            nullable=True,
            comment="职业/身份",
        ),
        sa.Column("birthday", sa.Date(), nullable=True, comment="生日"),
        sa.Column(
            "location", sa.String(256), nullable=True, comment="所在地"
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
            comment="最近更新时间",
        ),
        sa.UniqueConstraint("user_id", name="uq_user_profile_user_id"),
        comment="用户客观事实档案表",
    )
    op.create_index(
        "ix_user_profile_user_id", "user_profile", ["user_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_user_profile_user_id", table_name="user_profile")
    op.drop_table("user_profile")
