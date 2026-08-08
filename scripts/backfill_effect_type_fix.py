"""One-off backfill: re-derive `rule.title` / `rule.effect` for existing
candidate rules using the now-fixed deterministic mapping functions in
`formulation_mapping.py`, without calling the LLM again.

Context (see AGENT_PROGRESS.md / session history): `definition` and
`classification` rule types used to be forced into `EffectType.ALLOW` (no
neutral effect type existed), and a stray `predicate=":"` term-separator
idiom leaked into `effect.action`/`title` as a literal leading colon. Both
bugs are now fixed at the source (`contracts/policy.py`'s new
`EffectType.INFORMATIONAL`, `formulation_mapping.py`'s `_is_separator_predicate`
guard). This script re-applies the corrected, purely-deterministic derivation
functions to each row's *already-stored* `formulation.canonical` payload and
updates only `title`/`effect` in place.

Explicitly NOT touched: `review_status`, `condition`, `ambiguity_status`,
`evidence`, `lineage`, `group_label`, `related_rule_ids`, `rule_id`,
`rule_revision`, or any other field. No new rows are created. No LLM calls
are made. This does not advance any candidate rule through review -- it only
corrects two derived display/effect fields on rows that are still sitting in
the (already-populated) review queue.

Usage:
    .venv\\Scripts\\python.exe scripts\\backfill_effect_type_fix.py <policy-set-key> [--dry-run]

Example:
    .venv\\Scripts\\python.exe scripts\\backfill_effect_type_fix.py saudi-labor-law --dry-run
    .venv\\Scripts\\python.exe scripts\\backfill_effect_type_fix.py saudi-labor-law
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy import select  # noqa: E402

from policy_platform.contracts.policy import CanonicalRule, Effect  # noqa: E402
from policy_platform.domain.models import CandidateRule, PolicySet  # noqa: E402
from policy_platform.infrastructure.db import get_sessionmaker  # noqa: E402
from policy_platform.infrastructure.formulation_mapping import (  # noqa: E402
    _RULE_TYPE_MAP,
    _effect_action,
    _title_for,
)
from policy_platform.infrastructure.repositories import CandidateRuleRepository  # noqa: E402


async def backfill(policy_set_key: str, *, dry_run: bool) -> None:
    session_factory = get_sessionmaker()
    async with session_factory() as session:
        policy_set = (
            await session.execute(select(PolicySet).where(PolicySet.key == policy_set_key))
        ).scalar_one_or_none()
        if policy_set is None:
            print(f"No policy set found with key={policy_set_key!r}")
            return

        candidates = list(
            (
                await session.execute(
                    select(CandidateRule).where(CandidateRule.policy_set_id == policy_set.id)
                )
            )
            .scalars()
            .all()
        )
        print(f"Loaded {len(candidates)} candidate rule(s) for policy set {policy_set_key!r}.")

        repo = CandidateRuleRepository(session)
        changed = 0
        unchanged = 0
        skipped_no_formulation = 0
        changes_by_rule_type: Counter[str] = Counter()

        for candidate in candidates:
            rule = CanonicalRule.model_validate(candidate.payload_json)
            policy = rule.formulation.canonical if rule.formulation else None
            if policy is None or policy.rule is None:
                skipped_no_formulation += 1
                continue

            mapped = _RULE_TYPE_MAP.get(policy.rule.rule_type)
            if mapped is None:
                skipped_no_formulation += 1
                continue
            _, effect_type = mapped

            new_title = _title_for(policy)
            new_action = _effect_action(policy)

            if new_title == rule.title and effect_type == rule.effect.type and new_action == rule.effect.action:
                unchanged += 1
                continue

            changed += 1
            changes_by_rule_type[rule.rule_type.value] += 1
            if dry_run:
                print(f"[DRY RUN] {candidate.id} ({rule.rule_type.value}):")
                print(f"    title:  {rule.title!r} -> {new_title!r}")
                print(f"    effect: {rule.effect.type.value}:{rule.effect.action!r} -> {effect_type.value}:{new_action!r}")
                continue

            updated = rule.model_copy(update={"title": new_title, "effect": Effect(type=effect_type, action=new_action)})
            await repo.update_payload(candidate, payload_json=updated.model_dump(mode="json"))

        if not dry_run:
            await session.commit()

        print("\n--- Summary ---")
        print(f"Changed:   {changed}")
        print(f"Unchanged: {unchanged}")
        print(f"Skipped (no formulation/no mapping): {skipped_no_formulation}")
        if changes_by_rule_type:
            print("Changed by rule_type:")
            for rule_type, count in changes_by_rule_type.most_common():
                print(f"  {rule_type}: {count}")
        if dry_run:
            print("\n(dry run -- no changes were written)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("policy_set_key", help="e.g. saudi-labor-law")
    parser.add_argument("--dry-run", action="store_true", help="Print planned changes without writing them")
    args = parser.parse_args()
    asyncio.run(backfill(args.policy_set_key, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
