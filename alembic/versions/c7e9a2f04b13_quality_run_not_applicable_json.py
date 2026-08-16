"""keep the record of which checks did not apply to a quality run

A quality run computes which route-specific checks did not apply to the records
in scope -- a check scoped to one route is never asked of a record on the other,
so the run has nothing to say about that pairing. That disclosure was returned
in the HTTP response of a fresh run and then dropped: `quality_runs` stores the
findings and the severity counts, but had no column for it. A stored run -- the
one the Quality page reads back -- therefore showed its findings and nothing
about which checks did not apply, and the absence of a check reads as a check
that ran and found nothing. That is the overclaim: assurance the run never
established, inferred from a silence.

The run row already answers "what did this find" (`findings_json`) and "how
severe" (the denormalised counts). It could not answer "which checks did not
apply, and to how many records", which is the question a reviewer needs in order
to read the findings for what they are.

Schema change is purely additive: `quality_runs` gains a nullable
`not_applicable_json` holding the list of
`{check, route, applicability, records_in_scope, applies_to_routes}` entries.
NULL is correct and meaningful for every run recorded before this column
existed -- it means the disclosure was never kept, which is not the same as a
run against a single-route corpus where nothing was set aside, and an empty
list would assert that stronger, positive claim falsely.

Deliberately not backfilled. The disclosures of past runs were never written
anywhere; there is nothing to recover them from, and inventing an empty list for
them would be the very collapse this column exists to prevent.

Revision ID: c7e9a2f04b13
Revises: d9a3f6c1b204
Create Date: 2026-08-12 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "c7e9a2f04b13"
down_revision: Union[str, Sequence[str], None] = "d9a3f6c1b204"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "quality_runs",
        sa.Column("not_applicable_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("quality_runs", "not_applicable_json")
