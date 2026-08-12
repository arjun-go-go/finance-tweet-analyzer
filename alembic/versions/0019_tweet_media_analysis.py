"""Add multimodal tweet media analysis.

Revision ID: 0019_tweet_media_analysis
Revises: 0018_tweet_media_assets
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0019_tweet_media_analysis"
down_revision: Union[str, None] = "0018_tweet_media_assets"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tweet_media_analyses",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tweet_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("media_set_hash", sa.String(length=64), nullable=False),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("model_used", sa.String(length=128), nullable=False),
        sa.Column("prompt_version", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("analyzed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tweet_id"], ["tweets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tweet_id"),
    )
    op.create_index("ix_tweet_media_analyses_status", "tweet_media_analyses", ["status", "created_at"])
    op.create_index("ix_tweet_media_analyses_media_set_hash", "tweet_media_analyses", ["media_set_hash"])


def downgrade() -> None:
    op.drop_index("ix_tweet_media_analyses_media_set_hash", table_name="tweet_media_analyses")
    op.drop_index("ix_tweet_media_analyses_status", table_name="tweet_media_analyses")
    op.drop_table("tweet_media_analyses")
