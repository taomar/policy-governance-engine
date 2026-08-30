"""policy index states: the projection profile an index was built under

An index is stale on two axes, and until now the record could only report one.

The first is the version: the documents were built for an approved version that
is no longer active. The second is the **projection profile** — the versioned
rendering contract the documents' retrieval text was produced under. A query is
rendered under one contract before it retrieves, and text rendered under another
is not comparable with it; an index that is perfectly current for the active
version can still be un-matchable because it was built under a superseded
rendering.

Reporting that as `current` would send an operator looking for a problem the
record can already prove, so `policy_index_freshness` now treats a profile
mismatch as stale. This column is what it reads.

WHY IT IS NULLABLE AND NOT BACKFILLED

A row written before projections existed records a build that really did happen
and really did index documents — it simply did not render them. NULL is that
fact. Backfilling the current profile onto those rows would claim a rendering
that never ran, and the retrieval gate would then trust an index it must refuse;
backfilling some placeholder would invent a profile no code can act on. The
honest value is the absent one, and the repair is a rebuild.

Revision ID: c1d4e8a92b73
Revises: b8f3d2a67c14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c1d4e8a92b73"
down_revision = "b8f3d2a67c14"
branch_labels = None
depends_on = None

TABLE = "policy_index_states"


def upgrade() -> None:
    op.add_column(TABLE, sa.Column("projection_profile", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column(TABLE, "projection_profile")
