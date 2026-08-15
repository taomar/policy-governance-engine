"""A policy is a persisted entity, not a rearrangement performed on read.

The system already knew which rules a document stated together. `_provisions`
built the structural graph, asked it for each element's chain of governing
headings, used that chain to decide where an extraction *batch* should break,
and threw it away. The only consumer that ever saw a policy was
`GET /policy-sets/{key}/policies`, which rebuilt the grouping from
`lineage.source_elements` at request time. Every other consumer — approve,
publish, export, quality, search, the cross-run delta, relationships — still saw
a flat list of rules, because that is all the store held.

This migration gives the grouping a row.

What is added
-------------

* `document_provisions` — one passage of a document version, identified
  deterministically by (source release, normalised heading chain, occurrence).
  It holds no prose beyond the heading path copied verbatim from the source.
* `candidate_rules.provision_id` — nullable, `ON DELETE SET NULL`.
* `approved_rules.provision_key` / `provision_heading_json` — a snapshot, not a
  reference, so a published version cannot be re-described by a later
  extraction.

Why there is no SQL backfill
----------------------------

The provision key is computed by building a canonical document from the stored
clauses and walking its structural graph. That is Python; there is no honest way
to express it in `op.execute`. Writing an approximation in SQL would fork the
grouping into a second implementation that agrees today and drifts tomorrow,
while both claim to describe the same document.

Existing rows therefore keep `provision_id IS NULL` and render exactly as they
do now: the assembling read falls back to the element-anchored grouping it has
always used for any rule with no provision. Nothing regresses and nothing is
lost. `scripts/backfill_provisions.py` populates them, is re-runnable, and calls
the same function the pipeline calls.

Nullability is permanent
------------------------

`provision_id` is not a column that becomes `NOT NULL` in a later migration. A
document whose structure defeats grouping still extracts, and its rules still
have to appear in the review queue.

Revision ID: b8e1c5f70a92
Revises: c4a7e2d91b58
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "b8e1c5f70a92"
down_revision = "c4a7e2d91b58"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document_provisions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("policy_set_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provision_key", sa.String(length=64), nullable=False),
        sa.Column("heading_path_json", postgresql.JSONB(), nullable=False),
        sa.Column("heading_element_ids_json", postgresql.JSONB(), nullable=False),
        sa.Column("first_page", sa.Integer(), nullable=True),
        sa.Column("last_page", sa.Integer(), nullable=True),
        sa.Column("first_sequence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("merged_run_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["policy_set_id"], ["policy_sets.id"]),
        sa.ForeignKeyConstraint(["document_version_id"], ["document_versions.id"]),
        # The idempotence primitive. Two runs over the same version compute the
        # same keys, and this is what makes the second run's write a no-op
        # instead of a duplicate.
        sa.UniqueConstraint(
            "document_version_id",
            "provision_key",
            name="uq_document_provisions_version_key",
        ),
    )
    op.create_index(
        "ix_document_provisions_policy_set_id", "document_provisions", ["policy_set_id"]
    )
    op.create_index(
        "ix_document_provisions_document_version_id",
        "document_provisions",
        ["document_version_id"],
    )

    op.add_column(
        "candidate_rules",
        sa.Column("provision_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_candidate_rules_provision",
        "candidate_rules",
        "document_provisions",
        ["provision_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_candidate_rules_provision_id", "candidate_rules", ["provision_id"]
    )

    op.add_column(
        "approved_rules",
        sa.Column("provision_key", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "approved_rules",
        sa.Column("provision_heading_json", postgresql.JSONB(), nullable=True),
    )
    op.create_index(
        "ix_approved_rules_provision_key", "approved_rules", ["provision_key"]
    )


def downgrade() -> None:
    op.drop_index("ix_approved_rules_provision_key", table_name="approved_rules")
    op.drop_column("approved_rules", "provision_heading_json")
    op.drop_column("approved_rules", "provision_key")

    op.drop_index("ix_candidate_rules_provision_id", table_name="candidate_rules")
    op.drop_constraint("fk_candidate_rules_provision", "candidate_rules", type_="foreignkey")
    op.drop_column("candidate_rules", "provision_id")

    op.drop_index(
        "ix_document_provisions_document_version_id", table_name="document_provisions"
    )
    op.drop_index(
        "ix_document_provisions_policy_set_id", table_name="document_provisions"
    )
    op.drop_table("document_provisions")
