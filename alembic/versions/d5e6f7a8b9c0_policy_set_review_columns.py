"""policy_sets review_due_date/last_reviewed_at columns

Adds periodic review / recertification tracking (ISO 37301 §9.3, ISO 27001)
to `PolicySet` (ADR-0009). `review_due_date` is a plain nullable date set by
a Policy Manager; "overdue" is computed at API-response time
(`is_review_overdue` in `PolicySetResponse`), not stored, matching the
`PolicyException.is_expired` pattern already used elsewhere in this codebase
since there is no background scheduler to flip a stored status.
`last_reviewed_at` is a pure audit timestamp of when a human last attested
the policy set was reviewed (via `POST /{key}/review`).

Purely additive: two new nullable columns, no existing tables/columns/rows
are touched or need a backfill.

Revision ID: d5e6f7a8b9c0
Revises: c3d4e5f6a7b8
Create Date: 2026-08-08 09:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd5e6f7a8b9c0'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('policy_sets', sa.Column('review_due_date', sa.Date(), nullable=True))
    op.add_column(
        'policy_sets', sa.Column('last_reviewed_at', sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('policy_sets', 'last_reviewed_at')
    op.drop_column('policy_sets', 'review_due_date')
