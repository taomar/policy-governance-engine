"""two-track case decision receipts: schema_version and per-track columns

`case_decision_v2` answers a case as two independent tracks — what the retained
published policies *state*, and what the case *comes to* — because a single
question can ask for either or both. The stored envelope in `response_json`
carries all of that; this migration adds the five columns a database needs to be
able to *ask about* it without parsing JSON, plus the one column that says which
envelope a row holds.

WHY THIS IS ADDITIVE AND NOTHING IS REWRITTEN

Rows written before v2 are `case_decision_v1` receipts and stay readable exactly
as they are. A receipt exists to be citable months later, so re-projecting one
into a newer shape — inventing the two booleans nobody classified for it — would
destroy the thing it was written for. So:

  * every new column is nullable;
  * `schema_version` is backfilled to `case_decision_v1` for existing rows,
    because that is what they are, and left NULL for nothing;
  * the four semantic columns stay NULL on those rows, because no classifier
    ever ran for them and a false or invented value would read as fact.

`decision_status` is untouched and keeps being written. From v2 it is *derived*
from the two tracks by the application layer — the verdict track when there is
one, the information track otherwise — so the operational queries written
against the single-value shape keep working while the envelope stays the
authority.

Revision ID: b8f3d2a67c14
Revises: a4e2c7b18f36
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b8f3d2a67c14"
down_revision = "a4e2c7b18f36"
branch_labels = None
depends_on = None

TABLE = "policy_case_decisions"


def upgrade() -> None:
    op.add_column(TABLE, sa.Column("schema_version", sa.String(length=50), nullable=True))
    op.add_column(TABLE, sa.Column("information_requested", sa.Boolean(), nullable=True))
    op.add_column(TABLE, sa.Column("verdict_requested", sa.Boolean(), nullable=True))
    op.add_column(TABLE, sa.Column("information_status", sa.String(length=50), nullable=True))
    op.add_column(TABLE, sa.Column("verdict_status", sa.String(length=50), nullable=True))

    # Every row that already carries an envelope carries a v1 one: the field was
    # never optional in that shape and no other version has ever been written.
    # Naming it now is what lets the reader dispatch on the column instead of
    # falling back to "no version means the old one", which is a rule that stops
    # being true the moment a third version exists.
    #
    # Restricted to completed rows on purpose. A pending or failed row has no
    # envelope, so stamping it with a version would claim a receipt it does not
    # have.
    op.execute(
        sa.text(
            f"UPDATE {TABLE} SET schema_version = 'case_decision_v1' "
            "WHERE response_json IS NOT NULL AND schema_version IS NULL"
        )
    )


def downgrade() -> None:
    # Reverse order of creation. The backfill is not undone because the columns
    # it wrote into are being dropped.
    op.drop_column(TABLE, "verdict_status")
    op.drop_column(TABLE, "information_status")
    op.drop_column(TABLE, "verdict_requested")
    op.drop_column(TABLE, "information_requested")
    op.drop_column(TABLE, "schema_version")
