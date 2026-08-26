"""Add auditable prediction eligibility decisions.

Revision ID: 0027_prediction_eligibility
Revises: 0026_tweet_processing_state
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0027_prediction_eligibility"
down_revision: Union[str, None] = "0026_tweet_processing_state"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "analysis_results",
        sa.Column("prediction_decision", postgresql.JSONB()),
    )
    op.add_column("predictions", sa.Column("creation_rule_version", sa.String(32)))
    op.add_column(
        "predictions",
        sa.Column("creation_evidence", postgresql.JSONB()),
    )


def downgrade() -> None:
    op.drop_column("predictions", "creation_evidence")
    op.drop_column("predictions", "creation_rule_version")
    op.drop_column("analysis_results", "prediction_decision")
