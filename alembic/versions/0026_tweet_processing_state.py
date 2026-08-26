"""Add observable tweet processing state metadata.

Revision ID: 0026_tweet_processing_state
Revises: 0025_tweet_context
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0026_tweet_processing_state"
down_revision: Union[str, None] = "0025_tweet_context"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tweets", sa.Column("failure_stage", sa.String(32)))
    op.add_column(
        "tweets",
        sa.Column("processing_updated_at", sa.DateTime(timezone=True)),
    )
    op.execute("UPDATE tweets SET processing_updated_at = created_at")
    op.create_index(
        "ix_tweets_processing_updated_at", "tweets", ["processing_updated_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_tweets_processing_updated_at", table_name="tweets")
    op.drop_column("tweets", "processing_updated_at")
    op.drop_column("tweets", "failure_stage")
