"""Store the manually corrected instrument on a prediction.

Revision ID: 0022_prediction_instrument
Revises: 0021_market_verifications
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0022_prediction_instrument"
down_revision: Union[str, None] = "0021_market_verifications"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "predictions",
        sa.Column(
            "instrument_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("predictions", "instrument_snapshot")
