"""One-off maintenance script: fix `Clause.sequence` for document versions that
already had clauses extracted *before* the `sequence` column existed.

Background (see alembic/versions/c2d3e4f5a6b7_clause_sequence_ordering.py):
`Clause.created_at` is a Python-side default evaluated per-row at flush time,
not a DB `server_default`. The original `bulk_create()` added an entire
document's clauses in one `add_all()` + `flush()`, so many rows could get an
identical `created_at` timestamp (clock resolution). That migration backfilled
`sequence` using `ROW_NUMBER() OVER (ORDER BY created_at, id)` as a best
effort — but wherever timestamps tied, the tiebreak fell to `id` (a random
UUID), silently scrambling document order. Live verification against this
repo's own seeded documents confirmed it: page numbers came back as
3, 23, 24, 2, 14, 20, 21, 19, ... instead of increasing.

This script does better: for every document version that already has clauses,
it re-runs the *same, deterministic* `extract_clauses()` used at upload time
against the file still on disk (`storage_path`) to recover the true original
order, then updates each existing `Clause` row's `sequence` to match — keyed
by `clause_ref`, which `extract_clauses()` derives deterministically from
position in the source file. Row identity (`Clause.id`) is never touched, so
any existing evidence/clause_id references made by candidate or canonical
rules stay valid.

Usage (from repo root, with the venv active):
    python scripts/fix_legacy_clause_sequence.py [--dry-run]
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy import select  # noqa: E402

from policy_platform.domain.models import Clause, DocumentVersion, SourceDocument  # noqa: E402
from policy_platform.infrastructure import document_extraction  # noqa: E402
from policy_platform.infrastructure.db import get_sessionmaker  # noqa: E402


async def main() -> None:
    dry_run = "--dry-run" in sys.argv
    session_factory = get_sessionmaker()
    async with session_factory() as session:
        result = await session.execute(select(DocumentVersion).where(DocumentVersion.storage_path != ""))
        versions = list(result.scalars().all())

        for version in versions:
            existing = list(
                (
                    await session.execute(
                        select(Clause).where(Clause.document_version_id == version.id)
                    )
                ).scalars()
            )
            if not existing:
                continue

            doc = (
                await session.execute(select(SourceDocument).where(SourceDocument.id == version.document_id))
            ).scalar_one()
            label = f"{doc.title} v{version.version_number}"

            try:
                extracted = document_extraction.extract_clauses(version.storage_path, version.mime_type)
            except Exception as exc:  # noqa: BLE001
                print(f"SKIP {label}: re-extraction failed ({exc})")
                continue

            true_order = {c.clause_ref: idx for idx, c in enumerate(extracted)}
            if len(true_order) != len(extracted):
                print(f"WARN {label}: duplicate clause_ref values in fresh extraction, skipping")
                continue

            by_ref: dict[str, list[Clause]] = {}
            for row in existing:
                by_ref.setdefault(row.clause_ref, []).append(row)
            ambiguous = {ref for ref, rows in by_ref.items() if len(rows) > 1}
            if ambiguous:
                print(f"WARN {label}: {len(ambiguous)} duplicate clause_ref(s) in DB rows, skipping those")

            changed = 0
            unmatched = 0
            for row in existing:
                if row.clause_ref in ambiguous:
                    continue
                new_seq = true_order.get(row.clause_ref)
                if new_seq is None:
                    unmatched += 1
                    continue
                if row.sequence != new_seq:
                    row.sequence = new_seq
                    changed += 1

            status = "DRY-RUN" if dry_run else "FIXED"
            print(
                f"{status} {label}: {changed}/{len(existing)} rows re-sequenced"
                f"{f', {unmatched} unmatched (left as-is)' if unmatched else ''}"
            )

        if dry_run:
            await session.rollback()
            print("Dry run — no changes committed.")
        else:
            await session.commit()
            print("Committed.")


if __name__ == "__main__":
    asyncio.run(main())
