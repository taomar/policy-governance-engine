"""Add canonical-document provenance to clauses.

Revision ID: a7b8c9d0e1f2
Revises: f2a3b4c5d6e7
Create Date: 2024-01-01 00:00:00.000000

Additive only. Existing clauses were produced by the previous page-scoped
parser and have no element identity, so all three columns are nullable; a NULL
`element_id` means "extracted before canonical ingestion existed" and callers
must treat provenance as unavailable rather than assuming offset zero.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "a7b8c9d0e1f2"
down_revision = "f2a3b4c5d6e7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("clauses", sa.Column("element_id", sa.String(length=20), nullable=True))
    op.add_column("clauses", sa.Column("element_type", sa.String(length=30), nullable=True))
    op.add_column("clauses", sa.Column("source_fragments", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("clauses", "source_fragments")
    op.drop_column("clauses", "element_type")
    op.drop_column("clauses", "element_id")
