"""append-only receipts for externally requested project-case decisions

One row per call to `POST /api/policy-decisions/{project_key}/case`. The row is
written `pending` and committed *before* the model runs, so a crash mid-call
leaves evidence the call was made; it then becomes `completed` (full envelope
plus its integrity seal) or `failed` (a reason, and no verdict).

This is deliberately not a widening of `evaluations`. That table records the
deterministic evaluator and requires a policy version, structured request facts
and an XACML status — none of which a prose case can honestly supply. Sharing
the table would misfile a model-mediated answer as a deterministic one.

`policy_version_id` is nullable because a case put to a project that has
published nothing is a legitimate, answerable outcome with no version to name.

Revision ID: a4e2c7b18f36
Revises: f7a8b9c0d1e2
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "a4e2c7b18f36"
down_revision = "f7a8b9c0d1e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "policy_case_decisions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("policy_set_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("policy_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("version_number", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("decision_status", sa.String(length=50), nullable=True),
        sa.Column("scenario_text", sa.Text(), nullable=False),
        sa.Column("scenario_hash", sa.String(length=128), nullable=False),
        sa.Column("request_hash", sa.String(length=128), nullable=False),
        sa.Column("correlation_id", sa.String(length=200), nullable=False),
        sa.Column("idempotency_key", sa.String(length=200), nullable=True),
        sa.Column("authenticated_principal_identity", sa.String(length=200), nullable=False),
        sa.Column("authenticated_principal_role", sa.String(length=50), nullable=False),
        sa.Column("authentication_source", sa.String(length=50), nullable=False),
        sa.Column("calling_system_identity", sa.String(length=200), nullable=True),
        sa.Column("channel", sa.String(length=20), nullable=False, server_default="api"),
        sa.Column("scope", sa.String(length=20), nullable=False),
        sa.Column("requested_provision_id", sa.String(length=200), nullable=True),
        sa.Column(
            "reasoning_effort_requested",
            sa.String(length=20),
            nullable=False,
            server_default="medium",
        ),
        sa.Column("request_metadata_json", postgresql.JSONB(), nullable=False),
        sa.Column("retrieval_json", postgresql.JSONB(), nullable=True),
        sa.Column("decision_summary_json", postgresql.JSONB(), nullable=True),
        sa.Column("citation_ids_json", postgresql.JSONB(), nullable=True),
        sa.Column("trace_json", postgresql.JSONB(), nullable=True),
        sa.Column("response_json", postgresql.JSONB(), nullable=True),
        sa.Column("decision_hash", sa.String(length=128), nullable=True),
        sa.Column("hash_basis", sa.String(length=50), nullable=True),
        sa.Column("failure_code", sa.String(length=50), nullable=True),
        sa.Column("failure_message", sa.Text(), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.ForeignKeyConstraint(["policy_set_id"], ["policy_sets.id"]),
        sa.ForeignKeyConstraint(["policy_version_id"], ["approved_policy_versions.id"]),
        # Load-bearing, not decoration: the application's race handling catches
        # the IntegrityError this raises when two calls share one key. Without
        # it, that handling is unreachable and one key yields two decisions.
        # NULL keys stay distinct under a Postgres unique constraint, so a call
        # made without a key is always a new decision.
        sa.UniqueConstraint(
            "policy_set_id",
            "authenticated_principal_identity",
            "idempotency_key",
            name="uq_policy_case_decisions_idempotency",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'completed', 'failed')",
            name="ck_policy_case_decisions_status",
        ),
    )
    op.create_index(
        "ix_policy_case_decisions_set_received",
        "policy_case_decisions",
        ["policy_set_id", "received_at"],
    )
    op.create_index(
        "ix_policy_case_decisions_correlation_id",
        "policy_case_decisions",
        ["correlation_id"],
    )


def downgrade() -> None:
    # Indexes first: dropping the table first happens to work on Postgres and
    # not on every backend, and an ordering that happens to work is the kind
    # that stops working during a rollback.
    op.drop_index("ix_policy_case_decisions_correlation_id", table_name="policy_case_decisions")
    op.drop_index("ix_policy_case_decisions_set_received", table_name="policy_case_decisions")
    op.drop_table("policy_case_decisions")
