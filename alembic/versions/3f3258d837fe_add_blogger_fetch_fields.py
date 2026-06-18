"""add blogger fetch fields

Revision ID: 3f3258d837fe
Revises: 955d8bfe0d9e
Create Date: 2026-06-18 17:32:41.705809

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '3f3258d837fe'
down_revision: Union[str, None] = '955d8bfe0d9e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('bloggers', sa.Column('last_fetched_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('bloggers', sa.Column('fetch_enabled', sa.Boolean(), nullable=False, server_default=sa.text('false')))


def downgrade() -> None:
    op.drop_column('bloggers', 'fetch_enabled')
    op.drop_column('bloggers', 'last_fetched_at')
