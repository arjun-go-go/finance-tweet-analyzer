"""partial_unique_index_documents_user_hash

Revision ID: 955d8bfe0d9e
Revises: 0010_search_vector
Create Date: 2026-06-12 14:15:31.186691

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '955d8bfe0d9e'
down_revision: Union[str, None] = '0010_search_vector'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("uq_documents_user_hash", "documents", type_="unique")
    op.execute(
        """
        CREATE UNIQUE INDEX uq_documents_user_hash
        ON documents (user_id, content_hash)
        WHERE status != 'deleted'
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_documents_user_hash")
    op.create_unique_constraint(
        "uq_documents_user_hash", "documents", ["user_id", "content_hash"]
    )
