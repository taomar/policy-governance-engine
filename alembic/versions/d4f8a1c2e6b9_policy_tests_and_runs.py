"""policy_tests and policy_test_runs tables

Adds the `PolicyTest`/`PolicyTestRun` entities required by Section 23's data
model but not previously present. `PolicyTest` is a named, saved test case
scoped to `policy_set_id` (never to one specific version, so it can be
re-run against every future published version per Section 9.11 step 6).
`PolicyTestRun` is an append-only record of one execution of a test against
one specific `approved_policy_versions` row (mirrors the immutability
convention already used by `evaluations`/`approved_rules`).

Purely additive: no existing tables or columns are touched.

Revision ID: d4f8a1c2e6b9
Revises: c9a1d4e0f2b3
Create Date: 2026-08-16 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'd4f8a1c2e6b9'
down_revision: Union[str, Sequence[str], None] = 'c9a1d4e0f2b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'policy_tests',
        sa.Column('policy_set_id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=300), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('test_kind', sa.String(length=50), nullable=False),
        sa.Column('input_facts_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('evaluation_timestamp_override', sa.DateTime(timezone=True), nullable=True),
        sa.Column('expected_overall_status', sa.String(length=50), nullable=False),
        sa.Column('expected_rule_id', sa.String(length=200), nullable=True),
        sa.Column('expected_rule_status', sa.String(length=50), nullable=True),
        sa.Column('expected_missing_facts_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('proposed_by', sa.String(length=20), nullable=False, server_default='human'),
        sa.Column('review_status', sa.String(length=50), nullable=False, server_default='active'),
        sa.Column('reviewed_by', sa.String(length=200), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('review_notes', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['policy_set_id'], ['policy_sets.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_policy_tests_policy_set_id'), 'policy_tests', ['policy_set_id'], unique=False)
    op.create_table(
        'policy_test_runs',
        sa.Column('policy_test_id', sa.UUID(), nullable=False),
        sa.Column('policy_version_id', sa.UUID(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('explanation', sa.Text(), nullable=False),
        sa.Column('actual_response_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('run_trigger', sa.String(length=20), nullable=False),
        sa.Column('triggered_by', sa.String(length=200), nullable=False),
        sa.Column('run_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['policy_test_id'], ['policy_tests.id'], ),
        sa.ForeignKeyConstraint(['policy_version_id'], ['approved_policy_versions.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_policy_test_runs_policy_test_id'), 'policy_test_runs', ['policy_test_id'], unique=False)
    op.create_index(
        op.f('ix_policy_test_runs_policy_version_id'), 'policy_test_runs', ['policy_version_id'], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_policy_test_runs_policy_version_id'), table_name='policy_test_runs')
    op.drop_index(op.f('ix_policy_test_runs_policy_test_id'), table_name='policy_test_runs')
    op.drop_table('policy_test_runs')
    op.drop_index(op.f('ix_policy_tests_policy_set_id'), table_name='policy_tests')
    op.drop_table('policy_tests')
