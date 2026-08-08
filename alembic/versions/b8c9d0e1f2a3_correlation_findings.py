"""correlation runs and findings

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2024-01-01 00:00:00.000000

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "b8c9d0e1f2a3"
down_revision = "a7b8c9d0e1f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "correlation_runs",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("policy_set_id", sa.UUID(as_uuid=True), sa.ForeignKey("policy_sets.id"), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("deployment_name", sa.String(200), nullable=True),
        sa.Column("prompt_version", sa.String(50), nullable=True),
        sa.Column("rules_analyzed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("groups_analyzed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rules_uncompared", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_correlation_runs_policy_set_id", "correlation_runs", ["policy_set_id"])

    op.create_table(
        "correlation_findings",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "run_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("correlation_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("policy_set_id", sa.UUID(as_uuid=True), sa.ForeignKey("policy_sets.id"), nullable=False),
        sa.Column("classification", sa.String(50), nullable=False),
        sa.Column("analysis_status", sa.String(30), nullable=False),
        sa.Column("severity", sa.String(30), nullable=False),
        sa.Column("rule_ids", JSONB(), nullable=False, server_default="[]"),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("payload_json", JSONB(), nullable=False),
        sa.Column("disposition", sa.String(30), nullable=False, server_default="open"),
        sa.Column("disposition_by", sa.String(200), nullable=True),
        sa.Column("disposition_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("disposition_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_correlation_findings_run_id", "correlation_findings", ["run_id"])
    op.create_index("ix_correlation_findings_policy_set_id", "correlation_findings", ["policy_set_id"])
    op.create_index("ix_correlation_findings_classification", "correlation_findings", ["classification"])


def downgrade() -> None:
    op.drop_table("correlation_findings")
    op.drop_index("ix_correlation_runs_policy_set_id", table_name="correlation_runs")
    op.drop_table("correlation_runs")
