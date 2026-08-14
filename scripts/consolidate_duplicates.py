"""Apply Tier 1 consolidation to a policy set, and undo it.

The decision is made in `infrastructure/consolidation/duplicate_records.py`,
which is pure. This script is only the part that touches the database, kept
separate so the rule about what counts as a repetition can be tested without a
session and cannot drift into being defined by how it is stored.

Three properties this script exists to guarantee, none of which are optional:

- **Nothing happens unless asked.** The default is a dry run that prints what it
  would do. `--apply` is the only thing that writes.
- **Removal is reversible.** A redundant copy is marked superseded, which is the
  mechanism the schema already uses for "no longer current, still here". The row
  survives; `--undo` restores it. Supersession has already fired during a run
  that then failed and left a reviewer with fewer records than they started
  with, and a pass that removes rows has no business being less recoverable than
  the mechanism it borrows.
- **Identity comes from the payload, never from a stored fingerprint.** Those
  columns are written by a pass that runs after every batch, so they are empty
  for exactly the runs most likely to contain repetitions — the ones that
  stalled partway.

Usage:
    python scripts/consolidate_duplicates.py <policy-set-key> [--apply] [--undo]
"""

from __future__ import annotations

import asyncio
import os
import sys

from sqlalchemy import select, update

from policy_platform.domain.models import CandidateRule, PolicySet
from policy_platform.infrastructure.consolidation.duplicate_records import (
    repeated_records,
)
from policy_platform.infrastructure.persistence.db import get_sessionmaker

#: Written into `review_notes` so a reviewer meeting a missing record can find
#: out what happened to it without reading this file, and so `--undo` can find
#: exactly the rows this script superseded and no others.
NOTE = "Superseded by consolidation: an exact repetition of another record cut from the same source span."


async def run(policy_set_key: str, apply: bool, undo: bool) -> int:
    async with get_sessionmaker()() as session:
        policy_set = (
            await session.execute(select(PolicySet).where(PolicySet.key == policy_set_key))
        ).scalar_one_or_none()
        if policy_set is None:
            print(f"no policy set with key {policy_set_key!r}")
            return 2

        if undo:
            restored = await session.execute(
                update(CandidateRule)
                .where(
                    CandidateRule.policy_set_id == policy_set.id,
                    CandidateRule.review_notes == NOTE,
                    CandidateRule.superseded_at.is_not(None),
                )
                .values(superseded_at=None, review_notes=None)
            )
            await session.commit()
            print(f"restored {restored.rowcount} record(s)")
            return 0

        rows = (
            (
                await session.execute(
                    select(CandidateRule).where(
                        CandidateRule.policy_set_id == policy_set.id,
                        CandidateRule.superseded_at.is_(None),
                    )
                )
            )
            .scalars()
            .all()
        )
        records = [(str(row.id), row.payload_json) for row in rows]
        repeats = repeated_records(records)

        redundant = [key for repeat in repeats for key in repeat.redundant]
        print(f"{len(rows)} current record(s) in {policy_set_key!r}")
        print(f"{len(repeats)} repetition(s), {len(redundant)} redundant copy/copies")
        by_id = {str(row.id): row for row in rows}
        for repeat in repeats:
            kept = by_id[repeat.keep].payload_json
            print(f"  {repeat.copies}x  {repeat.span}  {(kept.get('title') or '')[:60]!r}")
            print(f"       keep {repeat.keep}")
            for key in repeat.redundant:
                print(f"       drop {key}")

        if not apply:
            print("\ndry run; nothing written. Pass --apply to supersede the copies.")
            return 0
        if not redundant:
            return 0

        # `--undo` finds its rows by the note, so a copy that already carries a
        # reviewer's own note cannot be superseded without either destroying that
        # note or becoming unrecoverable. Neither is acceptable for the sake of
        # removing a duplicate, so those are reported and left alone.
        annotated = [key for key in redundant if by_id[key].review_notes]
        removable = [key for key in redundant if not by_id[key].review_notes]
        for key in annotated:
            print(f"  skipped {key}: already carries a reviewer's note")

        if not removable:
            return 0

        from datetime import datetime, timezone

        await session.execute(
            update(CandidateRule)
            .where(CandidateRule.id.in_(removable))
            .values(superseded_at=datetime.now(timezone.utc), review_notes=NOTE)
        )
        await session.commit()
        print(f"\nsuperseded {len(removable)} record(s); --undo restores them")
        return 0


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    if len(args) != 1:
        print(__doc__)
        return 2
    return asyncio.run(run(args[0], apply="--apply" in flags, undo="--undo" in flags))


if __name__ == "__main__":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    sys.exit(main())
