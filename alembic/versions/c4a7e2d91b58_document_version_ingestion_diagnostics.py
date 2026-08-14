"""Persist ingestion diagnostics on the document version.

Revision ID: c4a7e2d91b58
Revises: b8d1e5f30a72
Create Date: 2025-01-01 00:00:00.000000

WHY

`upload_document` built a list of ingestion diagnostics, populated it, and
returned it in the HTTP response -- and nothing wrote it anywhere. A diagnostic
with severity "error" saying the source fragments do not resolve to the recorded
text was shown once, to whoever performed the upload, and was then unrecoverable.
No reviewer or auditor looking at the document afterwards could discover that its
source had not fully resolved.

The columns live on `document_versions` rather than in
`extraction_stages.diagnostics_json` because this is a property of one ingestion
of one version -- same cardinality, same lifetime, written once and never
revised. `extraction_stages` describes per-stage bookkeeping of an extraction
run, keyed by idempotency and input/output hashes; at upload time no run exists,
so those columns would all be NULL and the row would contradict its own schema.

Both columns are nullable with no backfill, and that is deliberate. Existing
versions were ingested before anything recorded this, so NULL means "unrecorded"
-- which the response layer reports as `unrecorded`, distinct from `ok`. Writing
a default of "clean" over rows nobody observed would manufacture exactly the
false assurance these columns exist to prevent.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "c4a7e2d91b58"
down_revision = "b8d1e5f30a72"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Safe to run against a live database. Adding a nullable column with no
    # default is catalogue-only in PostgreSQL 11+, but it still needs a brief
    # ACCESS EXCLUSIVE lock -- and if a long transaction is holding the table,
    # this statement would queue and every reader would queue behind it. The
    # timeout makes it fail fast and harmlessly instead of stalling traffic.
    op.execute("SET lock_timeout = '3s'")
    op.add_column(
        "document_versions",
        sa.Column("ingestion_diagnostics_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "document_versions",
        sa.Column("ingestion_error", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("document_versions", "ingestion_error")
    op.drop_column("document_versions", "ingestion_diagnostics_json")
