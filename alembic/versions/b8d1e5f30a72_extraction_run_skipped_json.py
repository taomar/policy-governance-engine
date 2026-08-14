"""keep the record of what an extraction run skipped

A run that skips material records it in a list built in memory, returned in the
HTTP response of the extraction request, and then dropped. There is no column
for it. Ten sentences on RUN-83257A81 were classified as carrying no policy
rule, five of which no other record recovered — including:

    "GMU is fully committed to equal opportunity at all levels without
     discrimination on the basis of race, gender, religion, age, family status,
     or national origin."

That is what a compliance reviewer opens this tool to find. It was not flagged,
not low confidence, not marked uncertain. It was gone — and the phrase "into a
list nobody reads" understates it, because with nowhere to store the list,
nobody *can* read it. Anyone asking afterwards what a run passed over has no
place to look.

The run row already answers "did this finish" and, since
`RUN_COMPLETED_WITH_GAPS`, "did this read the whole document". It could not
answer "what did it decide not to extract", which is the question a coverage
review actually asks.

Schema change is purely additive: `extraction_runs` gains a nullable
`skipped_json` holding the list of `{item, reason, kind}` entries. NULL is
correct and meaningful for every run recorded before this column existed — it
means the record was never kept, which is not the same as a run that skipped
nothing, and an empty list would assert the stronger claim falsely.

Deliberately not backfilled. The skip lists of past runs were never written
anywhere; there is nothing to recover them from.

Revision ID: b8d1e5f30a72
Revises: e7f4a9c2b615
Create Date: 2026-08-11 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'b8d1e5f30a72'
down_revision: Union[str, Sequence[str], None] = 'e7f4a9c2b615'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'extraction_runs',
        sa.Column('skipped_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('extraction_runs', 'skipped_json')
