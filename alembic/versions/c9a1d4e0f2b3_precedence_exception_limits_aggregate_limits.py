"""precedence fields, exception limits, and aggregate limit persistence

Fixes a silent data-loss bug (ADR-0009 "related discovery"): the canonical
contract layer (`policy_platform.contracts.policy`) gained
`CanonicalRule.is_explicit_override`, `CanonicalRule.supersedes_rule_ids`,
`RuleException.limit_value`/`limit_unit`, and the entire `AggregateLimit`
construct across prior segments, but the corresponding relational
persistence was never added — so every one of these fields was silently
dropped when a candidate rule was published into an `ApprovedRule`/
`RuleException` row, and `AggregateLimit` had no table at all.

This migration is purely additive:
- `approved_rules` gains `is_explicit_override` (bool, default False) and
  `supersedes_rule_ids_json` (JSONB list, default []).
- `rule_exceptions` gains `limit_value` (nullable float) and `limit_unit`
  (nullable string) for structured magnitudes ("15 days/year").
- Two new tables model aggregate limits (e.g. "combined family-care leave
  capped at 70 days/year across rules R1+R2"):
  - `policy_aggregate_limits` — mutable draft, scoped to `policy_set_id`,
    edited directly by a Policy Manager like `PolicySet.tags_json`.
  - `approved_aggregate_limits` — immutable snapshot, scoped to
    `policy_version_id`, written once at publish time (Rule 5.3).

No existing rows are affected; existing rules simply get the safe defaults
(no override, no supersession, no numeric exception limit, no aggregate
limits) until re-published with the now-fixed pipeline.

Revision ID: c9a1d4e0f2b3
Revises: c2d3e4f5a6b7
Create Date: 2026-08-09 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'c9a1d4e0f2b3'
down_revision: Union[str, Sequence[str], None] = 'c2d3e4f5a6b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'approved_rules',
        sa.Column('is_explicit_override', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        'approved_rules',
        sa.Column(
            'supersedes_rule_ids_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='[]'
        ),
    )
    op.add_column(
        'rule_exceptions',
        sa.Column('limit_value', sa.Float(), nullable=True),
    )
    op.add_column(
        'rule_exceptions',
        sa.Column('limit_unit', sa.String(length=50), nullable=True),
    )
    op.create_table(
        'policy_aggregate_limits',
        sa.Column('policy_set_id', sa.UUID(), nullable=False),
        sa.Column('aggregate_key', sa.String(length=200), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('contributing_rules_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('aggregator', sa.String(length=20), nullable=False),
        sa.Column('max_value', sa.Float(), nullable=False),
        sa.Column('period', sa.String(length=50), nullable=True),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['policy_set_id'], ['policy_sets.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('policy_set_id', 'aggregate_key', name='uq_policy_aggregate_limits_set_key'),
    )
    op.create_table(
        'approved_aggregate_limits',
        sa.Column('policy_version_id', sa.UUID(), nullable=False),
        sa.Column('aggregate_key', sa.String(length=200), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('contributing_rules_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('aggregator', sa.String(length=20), nullable=False),
        sa.Column('max_value', sa.Float(), nullable=False),
        sa.Column('period', sa.String(length=50), nullable=True),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['policy_version_id'], ['approved_policy_versions.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('policy_version_id', 'aggregate_key', name='uq_approved_aggregate_limits_version_key'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('approved_aggregate_limits')
    op.drop_table('policy_aggregate_limits')
    op.drop_column('rule_exceptions', 'limit_unit')
    op.drop_column('rule_exceptions', 'limit_value')
    op.drop_column('approved_rules', 'supersedes_rule_ids_json')
    op.drop_column('approved_rules', 'is_explicit_override')
