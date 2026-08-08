"""policy_attestations table

Adds the `PolicyAttestation` entity (ADR-0012): tracks one employee's
obligation to acknowledge one published policy version (ISO 37301 §7.3
personnel attestation/awareness requirement). Bound to a specific
`approved_policy_versions` row, mirroring `policy_test_runs`'
version-binding, so the audit trail of who acknowledged what stays
meaningful even after the policy set republishes.

Purely additive: no existing tables or columns are touched.

Revision ID: d1e2f3a4b5c6
Revises: 222abe350967
Create Date: 2026-08-08 11:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd1e2f3a4b5c6'
down_revision: Union[str, Sequence[str], None] = '222abe350967'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'policy_attestations',
        sa.Column('policy_set_id', sa.UUID(), nullable=False),
        sa.Column('policy_version_id', sa.UUID(), nullable=False),
        sa.Column('employee_name', sa.String(length=200), nullable=False),
        sa.Column('employee_identifier', sa.String(length=200), nullable=True),
        sa.Column('due_date', sa.Date(), nullable=False),
        sa.Column('assigned_by', sa.String(length=200), nullable=False),
        sa.Column('acknowledged_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('acknowledgment_notes', sa.Text(), nullable=True),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['policy_set_id'], ['policy_sets.id'], ),
        sa.ForeignKeyConstraint(['policy_version_id'], ['approved_policy_versions.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_policy_attestations_policy_set_id'), 'policy_attestations', ['policy_set_id'], unique=False
    )
    op.create_index(
        op.f('ix_policy_attestations_policy_version_id'), 'policy_attestations', ['policy_version_id'], unique=False
    )
    op.create_index(
        op.f('ix_policy_attestations_employee_identifier'),
        'policy_attestations',
        ['employee_identifier'],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_policy_attestations_employee_identifier'), table_name='policy_attestations')
    op.drop_index(op.f('ix_policy_attestations_policy_version_id'), table_name='policy_attestations')
    op.drop_index(op.f('ix_policy_attestations_policy_set_id'), table_name='policy_attestations')
    op.drop_table('policy_attestations')
