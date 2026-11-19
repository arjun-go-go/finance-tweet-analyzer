"""Remember the cutoff for new-only paid analysis.

Revision ID: 0038_analysis_ingest_scope
Revises: 0037_runtime_controls
"""

import sqlalchemy as sa
from alembic import op


revision = "0038_analysis_ingest_scope"
down_revision = "0037_runtime_controls"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "runtime_controls",
        sa.Column("analysis_ingested_after", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("runtime_controls", "analysis_ingested_after")
