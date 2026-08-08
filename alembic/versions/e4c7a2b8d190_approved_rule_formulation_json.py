"""retain the AI formulation record on published rules

Fixes a recurrence of the silent publish-time data-loss bug that migration
c9a1d4e0f2b3 already fixed once for a different set of fields.

`policy_platform.contracts.policy.CanonicalRule` carries `formulation` — the
policy-formulator agent's canonical subject/predicate/object decomposition plus
its OMG DMN 1.5 projection. The contract is explicit that this is retained
deliberately, because the executable fields alongside it are a *lossy*
projection of it:

    "Keeping the formulation means a reviewer can always see what the source
     actually said, and a future DMN compiler can work from the projection
     rather than re-extracting."

`approved_rules` never had a column for it. So `policy_version_import` dropped
it at publish and `mappers._rule_to_contract` rebuilt every published rule with
`formulation=None`. The record survived on the candidate row and was destroyed
the moment the rule was approved and published.

The user-visible symptom was that the two extraction JSON views (Canonical and
DMN) were present on the Review tab and vanished on the Policies tab, replaced
by "No AI extraction record — this rule was hand-authored or drafted before the
formulator agent existed." For AI-extracted rules that message was not merely
unhelpful, it was false.

Schema change is purely additive: `approved_rules` gains a nullable
`formulation_json`. NULL remains correct and meaningful for genuinely
hand-authored rules and for rules drafted before the formulator agent existed.

This migration deliberately does NOT backfill. `ApprovedRule` is immutable
(Rule 5.3), so restoring the lost records on already-published rows is a
separate, explicit act rather than a side effect of running migrations. Use
`scripts/backfill_approved_formulation.py`, which recovers each record from the
originating candidate row via `published_version_id` + `rule_id`.

Revision ID: e4c7a2b8d190
Revises: a7d3f1b9c204
Create Date: 2026-08-09 21:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'e4c7a2b8d190'
down_revision: Union[str, Sequence[str], None] = 'a7d3f1b9c204'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'approved_rules',
        sa.Column('formulation_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('approved_rules', 'formulation_json')
