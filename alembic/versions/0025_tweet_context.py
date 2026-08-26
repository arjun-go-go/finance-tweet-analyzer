"""Add Twitter conversation and reference context.

Revision ID: 0025_tweet_context
Revises: 0024_research_workspace
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0025_tweet_context"
down_revision: Union[str, None] = "0024_research_workspace"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tweets",
        sa.Column("tweet_type", sa.String(20), nullable=False, server_default="original"),
    )
    op.add_column("tweets", sa.Column("conversation_tweet_id", sa.String(64)))
    op.add_column("tweets", sa.Column("in_reply_to_tweet_id", sa.String(64)))
    op.add_column("tweets", sa.Column("quoted_tweet_id", sa.String(64)))
    op.add_column("tweets", sa.Column("reposted_tweet_id", sa.String(64)))
    op.add_column(
        "tweets",
        sa.Column(
            "referenced_tweets",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.create_index("ix_tweets_tweet_type", "tweets", ["tweet_type"])
    op.create_index(
        "ix_tweets_conversation_tweet_id", "tweets", ["conversation_tweet_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_tweets_conversation_tweet_id", table_name="tweets")
    op.drop_index("ix_tweets_tweet_type", table_name="tweets")
    op.drop_column("tweets", "referenced_tweets")
    op.drop_column("tweets", "reposted_tweet_id")
    op.drop_column("tweets", "quoted_tweet_id")
    op.drop_column("tweets", "in_reply_to_tweet_id")
    op.drop_column("tweets", "conversation_tweet_id")
    op.drop_column("tweets", "tweet_type")
