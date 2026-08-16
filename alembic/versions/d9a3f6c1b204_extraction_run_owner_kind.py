"""mark which runtime owns an extraction run's in-process lifecycle

The API server, at startup, closes out extraction runs a previous incarnation
left `running` or `pending`: nothing can resume an in-process task whose process
is gone, so it is failed and the UI stops reporting a run that will never end.
That sweep had no ownership predicate. It updated every `running`/`pending` row
in `extraction_runs`, table-wide — including a run a *different* process (a
headless or CLI extraction) was still working. Such a run is legitimately
`running`; the sweep stamped it `failed` on nothing but the API's own restart.

The damage is not only a wrong label. `failed` is an unusable baseline status,
so a healthy run flipped to `failed` is silently dropped from baseline
selection — the same wrong-baseline mechanism the handover records as the source
of a large, confidently-wrong stability measurement. A still-working run and an
interrupted run are different states, and folding the first into the second is a
collapse the domain is careful elsewhere not to make.

This adds `owner_kind` so a run records which runtime's liveness it is bound to.
`"api"` marks a run the FastAPI server drives; the startup reconciler now scopes
its sweep to `owner_kind == 'api'` and leaves foreign runs alone. It is a role,
stable across API restarts, not a per-process token — a fresh API process still
owns the runs the previous one started on its behalf, which is exactly what the
startup sweep must reconcile.

Schema change is additive and safe to backfill. Every row written before this
column existed was created by the API path (or is a terminal `manual_entry` row
the sweep never touched), so `server_default='api'` gives existing rows the
value that preserves the reconciler's prior, correct behaviour for the runs that
genuinely were API-owned. NOT NULL with a server default: no row is left without
an owner, and no data is lost. Fully reversible — downgrade drops the column.

Revision ID: d9a3f6c1b204
Revises: f2a7c14d9e83
Create Date: 2026-08-12 00:00:00.000000

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "d9a3f6c1b204"
down_revision = "f2a7c14d9e83"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "extraction_runs",
        sa.Column("owner_kind", sa.String(length=50), nullable=False, server_default="api"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("extraction_runs", "owner_kind")
