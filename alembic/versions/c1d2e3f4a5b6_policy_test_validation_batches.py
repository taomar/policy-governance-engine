"""policy test validation batches and blind expectation snapshots

Revision ID: c1d2e3f4a5b6
Revises: b8f2c6a41d73
Create Date: 2026-08-09 02:35:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "c1d2e3f4a5b6"
down_revision: Union[str, Sequence[str], None] = "b8f2c6a41d73"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "policy_test_batches",
        sa.Column("policy_set_id", sa.UUID(), nullable=False),
        sa.Column("policy_version_id", sa.UUID(), nullable=False),
        sa.Column("grounding_mode", sa.String(length=30), nullable=False),
        sa.Column("selected_rule_ids_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("grounding_context_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("scenario_count", sa.Integer(), nullable=False),
        sa.Column("reasoning_effort", sa.String(length=20), nullable=False),
        sa.Column("guidance", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="generated"),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["policy_set_id"], ["policy_sets.id"]),
        sa.ForeignKeyConstraint(["policy_version_id"], ["approved_policy_versions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_policy_test_batches_policy_set_id"),
        "policy_test_batches",
        ["policy_set_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_policy_test_batches_policy_version_id"),
        "policy_test_batches",
        ["policy_version_id"],
        unique=False,
    )

    op.add_column("policy_tests", sa.Column("generation_batch_id", sa.UUID(), nullable=True))
    op.add_column("policy_tests", sa.Column("scenario_text", sa.Text(), nullable=False, server_default=""))
    op.add_column("policy_tests", sa.Column("expectation_hash", sa.String(length=64), nullable=True))
    op.create_foreign_key(
        "fk_policy_tests_generation_batch_id",
        "policy_tests",
        "policy_test_batches",
        ["generation_batch_id"],
        ["id"],
    )
    op.create_index(
        op.f("ix_policy_tests_generation_batch_id"),
        "policy_tests",
        ["generation_batch_id"],
        unique=False,
    )

    op.add_column(
        "policy_test_runs",
        sa.Column("expected_assertions_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column("policy_test_runs", sa.Column("expectation_hash", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("policy_test_runs", "expectation_hash")
    op.drop_column("policy_test_runs", "expected_assertions_json")
    op.drop_index(op.f("ix_policy_tests_generation_batch_id"), table_name="policy_tests")
    op.drop_constraint("fk_policy_tests_generation_batch_id", "policy_tests", type_="foreignkey")
    op.drop_column("policy_tests", "expectation_hash")
    op.drop_column("policy_tests", "scenario_text")
    op.drop_column("policy_tests", "generation_batch_id")
    op.drop_index(op.f("ix_policy_test_batches_policy_version_id"), table_name="policy_test_batches")
    op.drop_index(op.f("ix_policy_test_batches_policy_set_id"), table_name="policy_test_batches")
    op.drop_table("policy_test_batches")
