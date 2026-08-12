"""Add archived tweet media assets.

Revision ID: 0018_tweet_media_assets
Revises: 0017_document_object_storage
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0018_tweet_media_assets"
down_revision: Union[str, None] = "0017_document_object_storage"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tweet_media_assets",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tweet_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("media_status_id", sa.String(length=64), nullable=True),
        sa.Column("media_type", sa.String(length=20), server_default="image", nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("object_key", sa.Text(), nullable=True),
        sa.Column("storage_backend", sa.String(length=20), server_default="minio", nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("content_type", sa.String(length=100), nullable=True),
        sa.Column("file_size_bytes", sa.Integer(), server_default="0", nullable=False),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tweet_id"], ["tweets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tweet_id", "source_url", name="uq_tweet_media_asset_source"),
    )
    op.create_index("ix_tweet_media_assets_tweet_id", "tweet_media_assets", ["tweet_id"])
    op.create_index("ix_tweet_media_assets_status", "tweet_media_assets", ["status", "created_at"])
    op.create_index("ix_tweet_media_assets_hash", "tweet_media_assets", ["content_hash"])


def downgrade() -> None:
    op.drop_index("ix_tweet_media_assets_hash", table_name="tweet_media_assets")
    op.drop_index("ix_tweet_media_assets_status", table_name="tweet_media_assets")
    op.drop_index("ix_tweet_media_assets_tweet_id", table_name="tweet_media_assets")
    op.drop_table("tweet_media_assets")
