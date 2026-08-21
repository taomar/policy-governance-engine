"""viewer feedback on published policy versions

A viewer can submit comments/feedback on a published policy version without
changing the policy. The request has its own lifecycle (open → acknowledged →
actioned/dismissed, or open → withdrawn) entirely separate from the policy
version's lifecycle — no column here overlaps with anything that determines
policy currency.

Revision ID: f7a8b9c0d1e2
Revises: e9c8d7b6a5f4
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "f7a8b9c0d1e2"
down_revision = "e9c8d7b6a5f4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "policy_review_requests",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("policy_set_key", sa.String(length=200), nullable=False),
        sa.Column("approved_policy_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("submitted_by", sa.String(length=200), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("comment", sa.Text(), nullable=False),
        sa.Column("categories", postgresql.JSONB(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="open"),
        sa.Column("resolved_by", sa.String(length=200), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["approved_policy_version_id"], ["approved_policy_versions.id"]),
        sa.CheckConstraint(
            "status IN ('open', 'acknowledged', 'actioned', 'dismissed', 'withdrawn')",
            name="ck_policy_review_requests_status",
        ),
    )
    op.create_index(
        "ix_policy_review_requests_policy_set_key",
        "policy_review_requests",
        ["policy_set_key"],
    )
    op.create_index(
        "ix_policy_review_requests_approved_policy_version_id",
        "policy_review_requests",
        ["approved_policy_version_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_policy_review_requests_approved_policy_version_id", table_name="policy_review_requests")
    op.drop_index("ix_policy_review_requests_policy_set_key", table_name="policy_review_requests")
    op.drop_table("policy_review_requests")
