"""policy_exceptions table

Adds the `PolicyException` entity (ADR-0009): an ad hoc, human-requested,
time-bounded waiver of a rule (or an entire policy set) for one particular
case, decided by a human reviewer. Distinct from the pre-existing
`rule_exceptions` table, which is a standing, automatically-evaluated
carve-out baked into a specific approved rule's own definition — see
domain/models.py::PolicyException docstring for the full contrast.

Purely additive: no existing tables or columns are touched.

Revision ID: c3d4e5f6a7b8
Revises: b8c9d0e1f2a3
Create Date: 2026-08-08 08:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'b8c9d0e1f2a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'policy_exceptions',
        sa.Column('policy_set_id', sa.UUID(), nullable=False),
        sa.Column('rule_id', sa.String(length=200), nullable=True),
        sa.Column('requester', sa.String(length=200), nullable=False),
        sa.Column('justification', sa.Text(), nullable=False),
        sa.Column('decision', sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column('expiry_date', sa.Date(), nullable=True),
        sa.Column('decided_by', sa.String(length=200), nullable=True),
        sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('decision_notes', sa.Text(), nullable=True),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['policy_set_id'], ['policy_sets.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_policy_exceptions_policy_set_id'), 'policy_exceptions', ['policy_set_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_policy_exceptions_policy_set_id'), table_name='policy_exceptions')
    op.drop_table('policy_exceptions')
