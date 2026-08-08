"""store the Section 83 trusted config on the policy set

The policy-formulator agent may not invent FEEL fact paths. Its only sanctioned
source of technical detail absent from the source text is the specification's
Section 83 trusted configuration (`fact_model`, `output_model`,
`value_normalization`, ...). Without one it returns `enrichment_required` with
`FACT_MODEL_REQUIRED`, and `formulation_mapping` then produces a rule with
`machine_executable=False`.

That is documented, intended behaviour. What was missing is the other half: a
place to *put* a trusted config. It could only ever be passed per-extraction
request, and no caller ever passed one — the web client's `extractWithAi` posts
no body at all. So every extraction this platform has ever run took the
empty-config path, and every rule it produced was non-executable.

The downstream consequences were not obviously related to each other:

  * `evaluator.engine` skips non-executable rules, so evaluations returned
    NOT_APPLICABLE with an empty `rule_results`, and every policy test that
    pinned an `expected_rule_id` failed with "expected rule ... to appear in
    the evaluation's applicable rules, but it was not found" — a message that
    sent reviewers looking for a wrong rule id rather than a non-executable one.
  * No rule could contribute to an aggregate limit, so the Aggregate Limits tab
    correctly but unhelpfully reported "0 can contribute / N cannot" for every
    published version, closing authoring entirely.

One cause, several unrelated-looking symptoms.

The config is stored on `policy_sets` rather than on a document, an extraction
run, or a request because it is the *domain's* vocabulary: the same terms recur
across every document in the set and every re-run, and a reviewer needs to see
the mapping that made a rule executable. Per-request supply remains available
and still wins when given, so a caller can override for a one-off run.

Schema change is purely additive and defaulted, so existing policy sets keep
today's behaviour (empty config -> honest, non-executable projections) until
someone deliberately supplies a fact model.

Revision ID: b8f2c6a41d73
Revises: e4c7a2b8d190
Create Date: 2026-08-09 22:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'b8f2c6a41d73'
down_revision: Union[str, Sequence[str], None] = 'e4c7a2b8d190'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'policy_sets',
        sa.Column(
            'trusted_config_json',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('policy_sets', 'trusted_config_json')
