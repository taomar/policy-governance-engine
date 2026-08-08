"""document policy_set_id link

Revision ID: 7f3b9c2e1a44
Revises: da1d8876d496
Create Date: 2026-08-14 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7f3b9c2e1a44'
down_revision: Union[str, Sequence[str], None] = 'da1d8876d496'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Adds a nullable policy_set_id FK to source_documents so a document can
    belong to a project (policy set). Nullable + no backfill: pre-existing
    documents remain unassigned ("Document Inbox") and can be filed into a
    project afterwards via the UI/API — this is a non-breaking addition.
    """
    op.add_column('source_documents', sa.Column('policy_set_id', sa.UUID(), nullable=True))
    op.create_index(
        op.f('ix_source_documents_policy_set_id'), 'source_documents', ['policy_set_id'], unique=False
    )
    op.create_foreign_key(
        'fk_source_documents_policy_set_id', 'source_documents', 'policy_sets', ['policy_set_id'], ['id']
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('fk_source_documents_policy_set_id', 'source_documents', type_='foreignkey')
    op.drop_index(op.f('ix_source_documents_policy_set_id'), table_name='source_documents')
    op.drop_column('source_documents', 'policy_set_id')
