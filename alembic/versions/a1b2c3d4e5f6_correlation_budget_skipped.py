"""correlation_runs.rules_budget_skipped

Splits the correlation coverage figure by cause.

`rules_uncompared` counted every rule the run never examined, but two very
different things land in that number: a rule that shares no comparison signal
with any other rule and so was never comparable, and a rule that *was*
comparable but whose groups fell outside the group budget. The UI attributed
the whole figure to the first cause, so a run that examined 20 of 171 rules
because of a tight budget read as a corpus where 151 rules simply stand alone —
the reviewer concludes the analysis was complete when it was truncated.

Nullable rather than defaulted to 0: runs recorded before this column existed
genuinely do not know how much of their uncompared total was the budget, and
claiming zero truncation for them would reintroduce the same false reassurance
this column exists to remove.

Purely additive and reversible.

Revision ID: a1b2c3d4e5f6
Revises: d5e6f7a8b9c0
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a1b2c3d4e5f6"
down_revision = "d5e6f7a8b9c0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "correlation_runs",
        sa.Column("rules_budget_skipped", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("correlation_runs", "rules_budget_skipped")
