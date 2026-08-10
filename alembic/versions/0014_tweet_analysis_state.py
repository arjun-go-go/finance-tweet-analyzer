"""Add durable tweet analysis state fields.

Revision ID: 0014_tweet_analysis_state
Revises: 0013_outbox_events
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0014_tweet_analysis_state"
down_revision: Union[str, None] = "0013_outbox_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tweets",
        sa.Column(
            "analysis_attempts",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "tweets",
        sa.Column("analysis_last_error", sa.Text(), nullable=True),
    )
    op.add_column(
        "tweets",
        sa.Column("analysis_next_retry_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "tweets",
        sa.Column("analysis_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "tweets",
        sa.Column("analysis_completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        """
        UPDATE tweets
        SET analysis_attempts = CASE WHEN status = 'analyzed' THEN 1 ELSE 0 END,
            analysis_completed_at = CASE
                WHEN status = 'analyzed' THEN COALESCE(created_at, now())
                ELSE NULL
            END
        """
    )
    op.create_index(
        "ix_tweets_analysis_next_retry_at",
        "tweets",
        ["analysis_next_retry_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_tweets_analysis_next_retry_at", table_name="tweets")
    op.drop_column("tweets", "analysis_completed_at")
    op.drop_column("tweets", "analysis_started_at")
    op.drop_column("tweets", "analysis_next_retry_at")
    op.drop_column("tweets", "analysis_last_error")
    op.drop_column("tweets", "analysis_attempts")
