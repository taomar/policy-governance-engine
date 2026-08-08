"""Record how many comparison groups a corpus yields.

`groups_analyzed` alone cannot say whether a run was complete, because the
budget that capped it is not stored on the run. Recording the available total
lets the UI report "60 of 213 groups" instead of an unqualified "truncated",
which is the difference between a warning an operator can act on and one they
can only re-run blind against.

Nullable: runs recorded before this column existed genuinely do not know their
total, and defaulting them to `groups_analyzed` would assert they were complete.

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "correlation_runs",
        sa.Column("groups_available", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("correlation_runs", "groups_available")
