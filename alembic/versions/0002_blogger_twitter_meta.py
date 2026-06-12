"""extend bloggers with twitter metadata fields

Revision ID: 0002_blogger_twitter_meta
Revises: 0001_initial
Create Date: 2026-05-26

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0002_blogger_twitter_meta"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "bloggers",
        sa.Column("twitter_user_id", sa.String(64), nullable=True),
    )
    op.add_column("bloggers", sa.Column("location", sa.String(256), nullable=True))
    op.add_column(
        "bloggers",
        sa.Column("tweets_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "bloggers",
        sa.Column("following_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "bloggers",
        sa.Column("favorites_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "bloggers",
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "bloggers",
        sa.Column(
            "verified", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
    )
    op.add_column(
        "bloggers",
        sa.Column(
            "protected", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
    )
    op.add_column("bloggers", sa.Column("profile_url", sa.String(512), nullable=True))

    op.create_index(
        "ix_bloggers_twitter_user_id",
        "bloggers",
        ["twitter_user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_bloggers_twitter_user_id", table_name="bloggers")
    op.drop_column("bloggers", "profile_url")
    op.drop_column("bloggers", "protected")
    op.drop_column("bloggers", "verified")
    op.drop_column("bloggers", "joined_at")
    op.drop_column("bloggers", "favorites_count")
    op.drop_column("bloggers", "following_count")
    op.drop_column("bloggers", "tweets_count")
    op.drop_column("bloggers", "location")
    op.drop_column("bloggers", "twitter_user_id")
