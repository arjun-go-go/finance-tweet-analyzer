"""Remove shared default identities from memory tables.

Revision ID: c7b6e2d9f104
Revises: a13c9f42b801
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c7b6e2d9f104"
down_revision: Union[str, None] = "a13c9f42b801"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "user_preferences",
        "user_id",
        existing_type=sa.String(length=128),
        existing_nullable=False,
        server_default=None,
    )
    op.alter_column(
        "user_profile",
        "user_id",
        existing_type=sa.String(length=128),
        existing_nullable=False,
        server_default=None,
    )


def downgrade() -> None:
    op.alter_column(
        "user_profile",
        "user_id",
        existing_type=sa.String(length=128),
        existing_nullable=False,
        server_default=sa.text("'default'"),
    )
    op.alter_column(
        "user_preferences",
        "user_id",
        existing_type=sa.String(length=128),
        existing_nullable=False,
        server_default=sa.text("'default'"),
    )
