"""record per-project policy index freshness

The per-project policy index is rebuilt best-effort after publish. If that
network call fails, Azure Search can later report that an index exists and has
documents, but it cannot say which approved version those documents represent.
That would make a stale index indistinguishable from a fresh one with no
matches.

This table records the latest rebuild attempt and the latest version that was
actually indexed. The two are separate on purpose: a failed attempt against v7
must not overwrite the fact that the index still contains v6.

Revision ID: e9c8d7b6a5f4
Revises: c7e9a2f04b13
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "e9c8d7b6a5f4"
down_revision = "c7e9a2f04b13"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "policy_index_states",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("policy_set_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("index_name", sa.String(length=128), nullable=False),
        sa.Column("indexed_version_number", sa.Integer(), nullable=True),
        sa.Column("document_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("built_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("attempted_version_number", sa.Integer(), nullable=True),
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["policy_set_id"], ["policy_sets.id"]),
        sa.UniqueConstraint("policy_set_id", name="uq_policy_index_states_policy_set"),
        sa.CheckConstraint(
            "status IN ('built', 'skipped', 'failed')",
            name="ck_policy_index_states_status",
        ),
    )
    op.create_index("ix_policy_index_states_policy_set_id", "policy_index_states", ["policy_set_id"])


def downgrade() -> None:
    op.drop_index("ix_policy_index_states_policy_set_id", table_name="policy_index_states")
    op.drop_table("policy_index_states")
