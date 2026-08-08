"""Cross-run rule identity and soft supersession on candidate_rules.

Re-extracting a document previously deleted the prior run's unreviewed
candidates outright. That made a delta impossible to compute (there was nothing
left to compare against), made "this rule is no longer being extracted"
inexpressible, and made filtering the review queue by extraction run meaningless
because only one run's rows ever survived.

This migration keeps every run's output and marks the older rows superseded
instead. Existing reads that mean "the current set" become
`superseded_at IS NULL`.

Backfill: all pre-existing rows are the current set of their document by
definition (everything else was already deleted), so they are left
un-superseded and marked `baseline` — they are the reference the next run will
be compared against, not a delta against anything.

Revision ID: a7d3f1b9c204
Revises: f6a7b8c9d0e1
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "a7d3f1b9c204"
down_revision = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("candidate_rules", sa.Column("content_fingerprint", sa.String(length=64), nullable=True))
    op.add_column("candidate_rules", sa.Column("anchor_fingerprint", sa.String(length=64), nullable=True))
    op.add_column("candidate_rules", sa.Column("delta_status", sa.String(length=20), nullable=True))
    op.add_column(
        "candidate_rules",
        sa.Column("baseline_candidate_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "candidate_rules",
        sa.Column("reworded", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "candidate_rules",
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "candidate_rules",
        sa.Column("superseded_by_run_id", postgresql.UUID(as_uuid=True), nullable=True),
    )

    op.create_foreign_key(
        "fk_candidate_rules_baseline_candidate",
        "candidate_rules",
        "candidate_rules",
        ["baseline_candidate_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_candidate_rules_superseded_by_run",
        "candidate_rules",
        "extraction_runs",
        ["superseded_by_run_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_index("ix_candidate_rules_content_fingerprint", "candidate_rules", ["content_fingerprint"])
    op.create_index("ix_candidate_rules_anchor_fingerprint", "candidate_rules", ["anchor_fingerprint"])
    op.create_index("ix_candidate_rules_delta_status", "candidate_rules", ["delta_status"])
    # The review queue's hot path is "current rules for this policy set", which
    # is now a two-column predicate on every read.
    op.create_index(
        "ix_candidate_rules_policy_set_current",
        "candidate_rules",
        ["policy_set_id", "superseded_at"],
    )

    op.execute("UPDATE candidate_rules SET delta_status = 'baseline' WHERE delta_status IS NULL")


def downgrade() -> None:
    op.drop_index("ix_candidate_rules_policy_set_current", table_name="candidate_rules")
    op.drop_index("ix_candidate_rules_delta_status", table_name="candidate_rules")
    op.drop_index("ix_candidate_rules_anchor_fingerprint", table_name="candidate_rules")
    op.drop_index("ix_candidate_rules_content_fingerprint", table_name="candidate_rules")
    op.drop_constraint("fk_candidate_rules_superseded_by_run", "candidate_rules", type_="foreignkey")
    op.drop_constraint("fk_candidate_rules_baseline_candidate", "candidate_rules", type_="foreignkey")
    op.drop_column("candidate_rules", "superseded_by_run_id")
    op.drop_column("candidate_rules", "superseded_at")
    op.drop_column("candidate_rules", "reworded")
    op.drop_column("candidate_rules", "baseline_candidate_id")
    op.drop_column("candidate_rules", "delta_status")
    op.drop_column("candidate_rules", "anchor_fingerprint")
    op.drop_column("candidate_rules", "content_fingerprint")
