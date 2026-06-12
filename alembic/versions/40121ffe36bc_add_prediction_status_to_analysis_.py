"""add prediction_status to analysis_results

Revision ID: 40121ffe36bc
Revises: 0007_agent_traces
Create Date: 2026-06-02 13:35:20.149265

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '40121ffe36bc'
down_revision: Union[str, None] = '0007_agent_traces'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'analysis_results',
        sa.Column('prediction_status', sa.String(length=16), nullable=False, server_default='pending'),
    )
    op.create_index(
        op.f('ix_analysis_results_prediction_status'),
        'analysis_results',
        ['prediction_status'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_analysis_results_prediction_status'), table_name='analysis_results')
    op.drop_column('analysis_results', 'prediction_status')
