"""category, tags, and variation-group columns

Adds business-domain classification (category/tags) to policy_sets and
approved_rules, and variation-group clustering (group_label/related_rule_ids)
to approved_rules. All columns are additive with safe defaults, so existing
rows and the evaluator's evaluation of them are unaffected.

Revision ID: b1c2d3e4f5a6
Revises: da1d8876d496
Create Date: 2026-08-08 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'b1c2d3e4f5a6'
down_revision: Union[str, Sequence[str], None] = '7f3b9c2e1a44'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'policy_sets',
        sa.Column('category', sa.String(length=100), nullable=False, server_default=''),
    )
    op.add_column(
        'policy_sets',
        sa.Column('tags_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='[]'),
    )
    op.add_column(
        'approved_rules',
        sa.Column('category', sa.String(length=100), nullable=False, server_default=''),
    )
    op.add_column(
        'approved_rules',
        sa.Column('tags_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='[]'),
    )
    op.add_column(
        'approved_rules',
        sa.Column('group_label', sa.String(length=200), nullable=False, server_default=''),
    )
    op.add_column(
        'approved_rules',
        sa.Column('related_rule_ids_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='[]'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('approved_rules', 'related_rule_ids_json')
    op.drop_column('approved_rules', 'group_label')
    op.drop_column('approved_rules', 'tags_json')
    op.drop_column('approved_rules', 'category')
    op.drop_column('policy_sets', 'tags_json')
    op.drop_column('policy_sets', 'category')
