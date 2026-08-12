"""Add provider usage metadata to tweet media analyses.

Revision ID: 0020_tweet_media_usage
Revises: 0019_tweet_media_analysis
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0020_tweet_media_usage"
down_revision: Union[str, None] = "0019_tweet_media_analysis"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tweet_media_analyses",
        sa.Column("usage", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tweet_media_analyses", "usage")
