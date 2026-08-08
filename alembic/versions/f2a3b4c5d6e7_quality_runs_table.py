"""quality_runs table

Persists each quality evaluation so the Quality tab can show run history
instead of only the latest in-memory result. Purely additive: a new table with
no changes to existing ones, so it is safe to apply to a populated database and
trivially reversible.

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "f2a3b4c5d6e7"
down_revision = "e1f2a3b4c5d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "quality_runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("policy_set_id", UUID(as_uuid=True), sa.ForeignKey("policy_sets.id"), nullable=False),
        sa.Column("scope", sa.String(20), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=True),
        sa.Column("rule_count", sa.Integer(), nullable=False),
        sa.Column("high_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("medium_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("low_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ai_review_used", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("findings_json", JSONB(), nullable=False, server_default="[]"),
        sa.Column("triggered_by", sa.String(200), nullable=False, server_default=""),
        sa.Column("run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_quality_runs_policy_set_id", "quality_runs", ["policy_set_id"])


def downgrade() -> None:
    op.drop_index("ix_quality_runs_policy_set_id", table_name="quality_runs")
    op.drop_table("quality_runs")
