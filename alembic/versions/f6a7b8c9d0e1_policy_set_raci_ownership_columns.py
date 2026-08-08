"""policy_sets RACI ownership columns

Adds individual-level ownership / RACI metadata (ADR-0013) on top of the
existing department-level `owner` string: `accountable_owner`,
`delegate_approver`, `escalation_contact` (plain strings) and
`consulted_parties_json` / `informed_parties_json` (JSONB string lists).

This closes the "Policy Ownership / RACI Metadata" P2 gap in
docs/known-limitations.md: ISO 37301 and standard GRC practice expect each
policy to have a named accountable owner, delegate approver, and
escalation path beyond just an owning department.

Purely additive: five new columns with non-null defaults ('' / '[]'), no
existing tables/columns/rows are touched or need a backfill.

Revision ID: f6a7b8c9d0e1
Revises: d1e2f3a4b5c6
Create Date: 2026-08-08 10:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, Sequence[str], None] = 'd1e2f3a4b5c6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'policy_sets',
        sa.Column('accountable_owner', sa.String(length=200), nullable=False, server_default=''),
    )
    op.add_column(
        'policy_sets',
        sa.Column('delegate_approver', sa.String(length=200), nullable=False, server_default=''),
    )
    op.add_column(
        'policy_sets',
        sa.Column('escalation_contact', sa.String(length=200), nullable=False, server_default=''),
    )
    op.add_column(
        'policy_sets',
        sa.Column(
            'consulted_parties_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='[]'
        ),
    )
    op.add_column(
        'policy_sets',
        sa.Column(
            'informed_parties_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='[]'
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('policy_sets', 'informed_parties_json')
    op.drop_column('policy_sets', 'consulted_parties_json')
    op.drop_column('policy_sets', 'escalation_contact')
    op.drop_column('policy_sets', 'delegate_approver')
    op.drop_column('policy_sets', 'accountable_owner')
