"""Carry a table row's own identity and column labels onto the clause that stores it.

The parser that actually runs already computes both. `document_ingestion`
assigns every grid a `table_id`, and where a row of that grid evidenced itself
as stating column labels it records those labels as `table_headers` — and where
no row did, it records `None` and says why in a diagnostic. `CanonicalElement`
has carried both fields for as long as there have been two parsers.

They were lost at exactly one place: the projection into `clauses`. A document
is read back from its stored clauses rather than re-parsed, so every consumer
downstream of storage saw `table_id=None` and `table_headers=None` on every row
of every table, whichever converter produced it. The row survived; the fact that
it was a row of anything did not.

What this restores, concretely
------------------------------

`structural_graph._add_table_continuations` groups elements by `table_id` and
reads `table_headers` to tell a grid continued from the previous page (headers
above, none below) from a new grid that happens to follow one. Both of its
inputs were `None` after storage, so on a rebuilt document it could never fire —
and a rebuilt document is what `/structure` serves. That path needs no cell
coordinates, only these two fields.

What this does not restore
--------------------------

Cell coordinates. `structural_graph._add_table_edges` requires
`table_cell is not None`, so `table_cell_of`, `header_for` and `merged_with`
remain unavailable after storage, and `reading_plan._add_table_context` — which
reads those edges — still cannot frame an individual cell. This migration
carries a row's column labels, not a table's geometry, and nothing here should
be read as making the second available.

Absent is not empty
-------------------

`table_headers` is nullable with no server default and no backfill. `NULL` means
no row of that grid stated column labels, which is a fact ingestion established
and warned about; `[]` would be this system asserting a grid has zero columns.
Existing rows get `NULL` for both columns because that is what is true of them:
they were stored before the projection carried either value, and no SQL here can
discover what their tables were called without re-parsing the source.

Revision ID: c4b1e83f0a57
Revises: d1f6b3c07e45
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "c4b1e83f0a57"
down_revision = "d1f6b3c07e45"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "clauses",
        sa.Column("table_id", sa.String(length=200), nullable=True),
    )
    op.add_column(
        "clauses",
        sa.Column("table_headers", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    # Rows of one table are always read together — "which grid is this a row
    # of" is the only question either column is asked. Partial, because the
    # column is NULL on every element that is not a table row, and those are the
    # majority of any document.
    op.create_index(
        "ix_clauses_table_id",
        "clauses",
        ["document_version_id", "table_id"],
        postgresql_where=sa.text("table_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_clauses_table_id", table_name="clauses")
    op.drop_column("clauses", "table_headers")
    op.drop_column("clauses", "table_id")
