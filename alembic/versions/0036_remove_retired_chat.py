"""Remove the retired conversational assistant persistence.

Revision ID: 0036_remove_retired_chat
Revises: 0035_claim_sponsor
"""

from collections.abc import Sequence

from alembic import op


revision: str = "0036_remove_retired_chat"
down_revision: str | None = "0035_claim_sponsor"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # LangGraph checkpoint tables are created by its PostgreSQL saver rather
    # than Alembic, so every drop is conditional.
    op.execute("DROP TABLE IF EXISTS checkpoint_writes")
    op.execute("DROP TABLE IF EXISTS checkpoint_blobs")
    op.execute("DROP TABLE IF EXISTS checkpoints")
    op.execute("DROP TABLE IF EXISTS checkpoint_migrations")
    op.execute("DROP TABLE IF EXISTS mem0_messages")
    op.execute("DROP TABLE IF EXISTS mem0_history")
    op.execute("DROP TABLE IF EXISTS messages")
    op.execute("DROP TABLE IF EXISTS conversations")


def downgrade() -> None:
    raise RuntimeError(
        "0036 removes retired assistant data and is intentionally irreversible; "
        "restore a database backup to roll back."
    )
