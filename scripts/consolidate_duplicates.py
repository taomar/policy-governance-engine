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
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from policy_platform.domain.models import CandidateRule, PolicySet
from policy_platform.infrastructure.consolidation.duplicate_records import (
    RepeatedRecord,
    repeated_records,
)
from policy_platform.infrastructure.persistence.db import get_sessionmaker

#: Written into `review_notes` so a reviewer meeting a missing record can find
#: out what happened to it without reading this file, and so `--undo` can find
#: exactly the rows this script superseded and no others.
NOTE = "Superseded by consolidation: an exact repetition of another record cut from the same source span."


@dataclass(frozen=True)
class Outcome:
    """What the pass found, and what it did about it.

    `superseded` is empty on a dry run, which is what lets one code path serve
    both modes: the decision is taken identically either way, and only the
    write is conditional. A dry run that took its decision by a different route
    would be a preview of something other than what `--apply` does.
    """

    considered: int
    repeats: tuple[RepeatedRecord, ...]
    redundant: tuple[str, ...]
    skipped: tuple[str, ...]
    superseded: tuple[str, ...]


async def supersede_repetitions(
    session: AsyncSession, *, policy_set_id: uuid.UUID, apply: bool
) -> Outcome:
    """Mark every redundant copy in one policy set as superseded.

    Only current rows are considered, which is what makes a second run a no-op:
    the copies this pass removed are no longer current, so each group it acted
    on has one member left and stops being a repetition. Nothing about a
    payload is written, so identity -- which is computed from the payload --
    cannot be moved by having run.
    """
    rows = (
        (
            await session.execute(
                select(CandidateRule).where(
                    CandidateRule.policy_set_id == policy_set_id,
                    CandidateRule.superseded_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    repeats = repeated_records([(str(row.id), row.payload_json) for row in rows])
    redundant = [key for repeat in repeats for key in repeat.redundant]
    by_id = {str(row.id): row for row in rows}

    # `--undo` finds its rows by the note, so a copy that already carries a
    # reviewer's own note cannot be superseded without either destroying that
    # note or becoming unrecoverable. Neither is acceptable for the sake of
    # removing a duplicate, so those are reported and left alone.
    skipped = tuple(key for key in redundant if by_id[key].review_notes)
    removable = tuple(key for key in redundant if not by_id[key].review_notes)

    if apply and removable:
        # The pure layer's keys are opaque strings, deliberately, so that it
        # knows nothing about storage. The column is a UUID, and a string bound
        # against it raises rather than matching nothing -- so the conversion
        # belongs here, at the one place that knows both.
        await session.execute(
            update(CandidateRule)
            .where(CandidateRule.id.in_([uuid.UUID(key) for key in removable]))
            .values(superseded_at=datetime.now(timezone.utc), review_notes=NOTE)
        )
        await session.commit()

    return Outcome(
        considered=len(rows),
        repeats=tuple(repeats),
        redundant=tuple(redundant),
        skipped=skipped,
        superseded=removable if apply else (),
    )


async def restore(session: AsyncSession, *, policy_set_id: uuid.UUID) -> int:
    """Undo this pass, and only this pass.

    Matching on the note as well as on supersession is what keeps a row
    superseded by anything else -- a failed run, a later extraction, a
    reviewer -- exactly where it was. An undo that restored every superseded
    row would be a second way to lose the reviewer's intent, which is the
    failure this mechanism exists to avoid rather than to repeat.
    """
    restored = await session.execute(
        update(CandidateRule)
        .where(
            CandidateRule.policy_set_id == policy_set_id,
            CandidateRule.review_notes == NOTE,
            CandidateRule.superseded_at.is_not(None),
        )
        .values(superseded_at=None, review_notes=None)
    )
    await session.commit()
    return restored.rowcount


async def run(policy_set_key: str, apply: bool, undo: bool) -> int:
    async with get_sessionmaker()() as session:
        policy_set = (
            await session.execute(select(PolicySet).where(PolicySet.key == policy_set_key))
        ).scalar_one_or_none()
        if policy_set is None:
            print(f"no policy set with key {policy_set_key!r}")
            return 2

        if undo:
            print(f"restored {await restore(session, policy_set_id=policy_set.id)} record(s)")
            return 0

        outcome = await supersede_repetitions(
            session, policy_set_id=policy_set.id, apply=apply
        )

        rows = (
            (
                await session.execute(
                    select(CandidateRule).where(
                        CandidateRule.policy_set_id == policy_set.id,
                    )
                )
            )
            .scalars()
            .all()
        )
        by_id = {str(row.id): row for row in rows}
        print(f"{outcome.considered} current record(s) in {policy_set_key!r}")
        print(
            f"{len(outcome.repeats)} repetition(s), "
            f"{len(outcome.redundant)} redundant copy/copies"
        )
        for repeat in outcome.repeats:
            kept = by_id[repeat.keep].payload_json or {}
            print(f"  {repeat.copies}x  {repeat.span}  {(kept.get('title') or '')[:60]!r}")
            print(f"       keep {repeat.keep}")
            for key in repeat.redundant:
                print(f"       drop {key}")
        for key in outcome.skipped:
            print(f"  skipped {key}: already carries a reviewer's note")

        if not apply:
            print("\ndry run; nothing written. Pass --apply to supersede the copies.")
        elif outcome.superseded:
            print(f"\nsuperseded {len(outcome.superseded)} record(s); --undo restores them")
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
