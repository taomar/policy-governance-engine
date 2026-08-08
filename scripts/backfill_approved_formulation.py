"""Recover AI formulation records lost from already-published rules.

Context
-------
`approved_rules` had no column for `CanonicalRule.formulation` until migration
e4c7a2b8d190, so every rule published before that migration was written with
the formulator agent's record silently discarded. The record still exists on
the candidate row the rule was published from; only the published copy was
lost.

Why this is a script and not part of the migration
--------------------------------------------------
`ApprovedRule` is immutable (Rule 5.3): a published rule is not rewritten in
place. Restoring these records is therefore a deliberate, reviewable act rather
than a silent side effect of running migrations.

The exception is narrow and worth stating plainly. `formulation` is never read
by the evaluator — it carries no scope, condition, effect, or priority — so
restoring it cannot change any decision any published rule makes. What it
changes is whether a reviewer can still see what the source actually said. The
alternative to restoring it is leaving audit data permanently destroyed and
leaving the UI asserting these rules were "hand-authored", which is false.

Rules that legitimately have no formulation (hand-authored, or drafted before
the formulator agent existed) are left as NULL, which is the correct value.

Usage
-----
    .\\.venv\\Scripts\\python.exe scripts/backfill_approved_formulation.py --dry-run
    .\\.venv\\Scripts\\python.exe scripts/backfill_approved_formulation.py --apply
"""
from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import text

from policy_platform.infrastructure.db import get_sessionmaker

# Matches a published rule to the candidate row it was published from.
# `published_version_id` is the exact link recorded at publish time; rule_id
# disambiguates within that version. Only rows still missing a formulation are
# touched, so the script is idempotent and re-runnable.
SELECT_RECOVERABLE = text(
    """
    SELECT ar.id AS approved_id,
           ar.rule_id,
           ar.title,
           cr.payload_json ->> 'formulation' AS formulation
    FROM approved_rules ar
    JOIN candidate_rules cr
      ON cr.published_version_id = ar.policy_version_id
     AND cr.payload_json ->> 'rule_id' = ar.rule_id
    WHERE ar.formulation_json IS NULL
      AND cr.payload_json -> 'formulation' IS NOT NULL
      AND cr.payload_json ->> 'formulation' <> 'null'
    """
)

UPDATE_ONE = text(
    # asyncpg does not adapt a Python dict for a JSONB parameter in raw SQL, so
    # the value is passed as JSON text and cast server-side.
    "UPDATE approved_rules SET formulation_json = CAST(:formulation AS jsonb) WHERE id = :approved_id"
)

COUNT_STATE = text(
    """
    SELECT count(*) AS total,
           count(*) FILTER (WHERE formulation_json IS NOT NULL) AS with_formulation
    FROM approved_rules
    """
)


async def main(apply: bool) -> None:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        before = (await session.execute(COUNT_STATE)).mappings().one()
        rows = (await session.execute(SELECT_RECOVERABLE)).mappings().all()

        print(
            f"published rules: {before['total']}  "
            f"already carrying a formulation: {before['with_formulation']}"
        )
        print(f"recoverable from the originating candidate row: {len(rows)}")

        if not rows:
            print("nothing to do.")
            return

        for row in rows:
            print(f"  {row['rule_id']}  {row['title'][:70]}")

        if not apply:
            print("\ndry run — nothing written. Re-run with --apply to restore these records.")
            return

        for row in rows:
            await session.execute(
                UPDATE_ONE,
                {"formulation": row["formulation"], "approved_id": row["approved_id"]},
            )
        await session.commit()

        after = (await session.execute(COUNT_STATE)).mappings().one()
        print(
            f"\nrestored {len(rows)} record(s). "
            f"published rules now carrying a formulation: "
            f"{after['with_formulation']} / {after['total']}"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="report what would change")
    group.add_argument("--apply", action="store_true", help="write the recovered records")
    args = parser.parse_args()
    asyncio.run(main(apply=args.apply))
