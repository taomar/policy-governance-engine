"""explicit clause sequence ordering

Adds an explicit `sequence` integer column to `clauses`, populated at
extraction time from the already-in-order Python list `extract_clauses()`
produces. This replaces implicit ordering by `created_at`, which is not a
reliable total order: `bulk_create()` inserts every clause for a document in
a single flush, and depending on OS clock resolution multiple rows can share
an identical timestamp, making `ORDER BY created_at` non-deterministic for
ties. This matters now that a "read the original document body top to
bottom" view is being built (Policies review journey) — such a view is only
useful if it reproduces true document order.

Existing rows are backfilled with a best-effort order (partitioned by
document_version_id, ordered by created_at then id) since their true
original position is no longer available; the important guarantee this
migration establishes is for every document uploaded from now on, where
`sequence` is always set correctly at insert time by `ClauseRepository.bulk_create`.

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-08-09 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c2d3e4f5a6b7'
down_revision: Union[str, Sequence[str], None] = 'b1c2d3e4f5a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'clauses',
        sa.Column('sequence', sa.Integer(), nullable=False, server_default='0'),
    )
    # Best-effort backfill for pre-existing rows: assign a stable per-document
    # ordinal using the best surrogate order available (created_at, then id).
    op.execute(
        """
        WITH ordered AS (
            SELECT id, ROW_NUMBER() OVER (
                PARTITION BY document_version_id ORDER BY created_at, id
            ) - 1 AS rn
            FROM clauses
        )
        UPDATE clauses
        SET sequence = ordered.rn
        FROM ordered
        WHERE clauses.id = ordered.id
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('clauses', 'sequence')
