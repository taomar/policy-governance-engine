"""policy index states: whether the built projection was checked, and how it scored

WHAT THIS ADDS AND WHY THE PREVIOUS COLUMN WAS NOT ENOUGH

`projection_profile` (revision c1d4e8a92b73) records the versioned contract an
index's retrieval text was *produced* under. It is a real fact and it is not the
fact a reader needs before trusting a corpus: producing text under a contract
says the rendering call returned, the embedding call returned and the upload was
acknowledged. All three are properties of **transport**. None of them is evidence
that what the index holds is a rendering of the record it names.

Until this revision, that transport evidence was the entire basis on which an
index became a load-bearing `ready` corpus. These columns carry the separate
verdict — a deterministic coverage and link check over the whole build, plus a
per-document embedding comparison between the authoritative text and the
projection derived from it — together with the scores it was reached on.

WHY THE PROFILE IS VERSIONED SEPARATELY FROM THE RENDERING ONE

They move for different reasons. The rendering contract moves when the text in
the index would change; this moves when what counts as *acceptable* changes. A
corpus rendered under one contract can be re-validated under a stricter statement
of quality and fail without a single document changing, and one name for both
would make that impossible to say — and would force a full re-render of every
corpus to restate a threshold.

WHY EVERY COLUMN IS NULLABLE, AND WHY NOTHING IS BACKFILLED

Every existing row describes a build that really happened and really indexed
documents. None of them was validated, because there was nothing to validate
with. NULL is exactly that fact.

Backfilling `passed` would claim a check that never ran, and the readiness gate
would then admit a corpus nobody has looked at — which is precisely the condition
this whole revision exists to end. Backfilling `failed` would be equally
inaccurate in the other direction and would take working projects offline on no
evidence. The honest value is the absent one, and the repair is one validation
run per project, which re-renders nothing.

WHAT THESE COLUMNS MAY NEVER HOLD

Counts, scores, profile names and a timestamp. No finding text, no document text,
no source text, no service reply. There is deliberately no column here that could
hold prose: a column that could would hold a policy sentence the first time
somebody wanted the record to be more helpful.

WHAT DOWNGRADE COSTS

Exactly the validation verdicts, and nothing else. No index document is touched,
no corpus is rebuilt, and the built projections themselves are unaffected —
a downgraded database simply cannot say whether they were checked. The live
readiness gate reads the *manifest document in the search index*, not this table,
so a downgrade does not open the gate on anything; it only makes the app's own
record of the verdict unreadable until an upgrade restores the columns.

Revision ID: e3a7c9d15b82
Revises: c1d4e8a92b73
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e3a7c9d15b82"
down_revision = "c1d4e8a92b73"
branch_labels = None
depends_on = None

TABLE = "policy_index_states"

#: Every column is independently nullable and additive, so a partially applied
#: upgrade is still a coherent schema and every reader tolerates each one being
#: absent.
#:
#: Written out one call at a time rather than looped, deliberately: a migration
#: is read far more often than it is run, and a literal `add_column` beside a
#: literal `drop_column` is a pair anyone — or any static check — can see
#: matches. A loop over a table of names hides exactly the asymmetry a rollback
#: would discover.


def upgrade() -> None:
    op.add_column(TABLE, sa.Column("quality_state", sa.String(length=20), nullable=True))
    op.add_column(TABLE, sa.Column("quality_profile", sa.String(length=64), nullable=True))
    op.add_column(TABLE, sa.Column("quality_checked_documents", sa.Integer(), nullable=True))
    op.add_column(TABLE, sa.Column("quality_structural_findings", sa.Integer(), nullable=True))
    op.add_column(TABLE, sa.Column("quality_min_similarity", sa.Float(), nullable=True))
    op.add_column(TABLE, sa.Column("quality_mean_similarity", sa.Float(), nullable=True))
    op.add_column(
        TABLE, sa.Column("quality_validated_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column(TABLE, "quality_validated_at")
    op.drop_column(TABLE, "quality_mean_similarity")
    op.drop_column(TABLE, "quality_min_similarity")
    op.drop_column(TABLE, "quality_structural_findings")
    op.drop_column(TABLE, "quality_checked_documents")
    op.drop_column(TABLE, "quality_profile")
    op.drop_column(TABLE, "quality_state")
