"""rule-level advice column (XACML Obligations/Advice gap)

Adds `CanonicalRule.advice` (ADR-0011): non-blocking supplementary guidance
attached to a rule's decision, distinct from the existing mandatory
`effect`/`require_action` Obligation-equivalent. Grounded in the
standards-research gap analysis (docs/policy-standards-research.md, P1 item
"Obligations / Advice as post-decision actions") — XACML 3.0 defines both a
mandatory Obligations channel (already modeled here as `require_action`) and
a separate, non-blocking Advice channel that this platform had no equivalent
for.

Purely additive, following the same safe-default backfill pattern as
c9a1d4e0f2b3: `approved_rules` gains `advice_json` (JSONB list, default
`[]`). No existing rows are affected.

Revision ID: e1f2a3b4c5d6
Revises: d4f8a1c2e6b9
Create Date: 2026-08-08 01:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'e1f2a3b4c5d6'
down_revision: Union[str, Sequence[str], None] = 'd4f8a1c2e6b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'approved_rules',
        sa.Column('advice_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='[]'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('approved_rules', 'advice_json')
