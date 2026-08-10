"""extraction stages table

Records each stage of a document-extraction run so a long run is observable and
a retry is decidable rather than hopeful. PDF conversion alone takes roughly
three minutes before any model is called, so a pipeline that reports only a
final value leaves an operator with nothing when it fails partway.

Additive only: no existing table or column is touched, so this migration is
safe to apply to a populated database and safe to reverse.

Revision ID: a1b2c3d4e5f6
Revises: d2e3f4a5b6c7
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "d2e3f4a5b6c7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "extraction_stages",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "document_version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("document_versions.id"),
            nullable=False,
        ),
        # Nullable: the early stages run before an ExtractionRun exists, and
        # creating one first would record a run that may never survive
        # conversion.
        sa.Column(
            "extraction_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("extraction_runs.id"),
            nullable=True,
        ),
        sa.Column("idempotency_key", sa.String(length=64), nullable=False),
        sa.Column("stage_name", sa.String(length=80), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="ok"),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("input_hash", sa.String(length=64), nullable=True),
        sa.Column("output_hash", sa.String(length=64), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("diagnostics_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
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
    )

    # A retry must not silently record a second row for the same stage of the
    # same run. Keyed on attempt as well, so a *deliberate* re-attempt is
    # recordable while an accidental duplicate is refused by the database rather
    # than by application code that could be bypassed.
    op.create_unique_constraint(
        "uq_extraction_stages_key_stage_attempt",
        "extraction_stages",
        ["idempotency_key", "stage_name", "attempt"],
    )
    op.create_index(
        "ix_extraction_stages_idempotency_key", "extraction_stages", ["idempotency_key"]
    )
    op.create_index(
        "ix_extraction_stages_document_version_id",
        "extraction_stages",
        ["document_version_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_extraction_stages_document_version_id", table_name="extraction_stages")
    op.drop_index("ix_extraction_stages_idempotency_key", table_name="extraction_stages")
    op.drop_constraint(
        "uq_extraction_stages_key_stage_attempt", "extraction_stages", type_="unique"
    )
    op.drop_table("extraction_stages")
