"""initial schema with predictions and blogger profile

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-26

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tweets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tweet_id", sa.String(64), nullable=False),
        sa.Column("author_handle", sa.String(128), nullable=False),
        sa.Column("author_name", sa.String(256), nullable=False, server_default=""),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metrics", postgresql.JSONB, nullable=True),
        sa.Column("media_urls", postgresql.JSONB, nullable=True),
        sa.Column("raw_json", postgresql.JSONB, nullable=True),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("tweet_id", name="uq_tweets_tweet_id"),
    )
    op.create_index("ix_tweets_tweet_id", "tweets", ["tweet_id"])
    op.create_index("ix_tweets_author_handle", "tweets", ["author_handle"])
    op.create_index("ix_tweets_status", "tweets", ["status"])

    op.create_table(
        "bloggers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("handle", sa.String(128), nullable=False),
        sa.Column("name", sa.String(256), nullable=False, server_default=""),
        sa.Column("bio", sa.Text, nullable=True),
        sa.Column("avatar_url", sa.String(512), nullable=True),
        sa.Column(
            "followers_count", sa.Integer, nullable=False, server_default="0"
        ),
        sa.Column("market_focus", postgresql.ARRAY(sa.String), nullable=True),
        sa.Column(
            "credibility_score",
            sa.Float,
            nullable=False,
            server_default="50.0",
        ),
        sa.Column(
            "total_predictions", sa.Integer, nullable=False, server_default="0"
        ),
        sa.Column(
            "correct_predictions",
            sa.Float,
            nullable=False,
            server_default="0.0",
        ),
        sa.Column("profile_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("handle", name="uq_bloggers_handle"),
    )
    op.create_index("ix_bloggers_handle", "bloggers", ["handle"])

    op.create_table(
        "analysis_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tweet_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tweets.id"),
            nullable=False,
        ),
        sa.Column("analysis_type", sa.String(32), nullable=False),
        sa.Column("result", postgresql.JSONB, nullable=False),
        sa.Column("model_used", sa.String(64), nullable=False),
        sa.Column("confidence", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("batch_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_analysis_results_tweet_id", "analysis_results", ["tweet_id"]
    )
    op.create_index(
        "ix_analysis_results_analysis_type",
        "analysis_results",
        ["analysis_type"],
    )

    op.create_table(
        "predictions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "analysis_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("analysis_results.id"),
            nullable=False,
        ),
        sa.Column(
            "tweet_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tweets.id"),
            nullable=False,
        ),
        sa.Column("blogger_handle", sa.String(128), nullable=False),
        sa.Column("ticker", sa.String(64), nullable=False),
        sa.Column("sentiment", sa.String(16), nullable=False),
        sa.Column(
            "investment_horizon",
            sa.String(16),
            nullable=False,
            server_default="unknown",
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("verifiable_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("verdict", sa.String(16), nullable=True),
        sa.Column("score", sa.Float, nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_by", sa.String(64), nullable=True),
        sa.Column("note", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_predictions_analysis_id", "predictions", ["analysis_id"])
    op.create_index("ix_predictions_tweet_id", "predictions", ["tweet_id"])
    op.create_index("ix_predictions_blogger_handle", "predictions", ["blogger_handle"])
    op.create_index("ix_predictions_ticker", "predictions", ["ticker"])
    op.create_index("ix_predictions_verifiable_at", "predictions", ["verifiable_at"])
    op.create_index(
        "ix_predictions_handle_verdict", "predictions", ["blogger_handle", "verdict"]
    )
    op.create_index(
        "ix_predictions_handle_ticker", "predictions", ["blogger_handle", "ticker"]
    )
    op.create_index(
        "ix_predictions_dedup",
        "predictions",
        ["blogger_handle", "ticker", "sentiment", "published_at"],
    )


def downgrade() -> None:
    op.drop_table("predictions")
    op.drop_table("analysis_results")
    op.drop_table("bloggers")
    op.drop_table("tweets")
