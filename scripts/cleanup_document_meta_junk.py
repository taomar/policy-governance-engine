"""One-off cleanup: reject candidate rules that are pure document-lifecycle
metadata, not substantive policy content.

## Root cause

Stage 2 extraction (policy_formulator) occasionally turns a document's
self-referential *meta* statements — about the document's own citation,
promulgation, publication, supersession of a prior version, or entry into
force — into a candidate rule, when these statements have **zero
operational content for any party or process** and should have been
classified `non_normative` (which the pipeline already silently drops via
`_SKIPPED_RULE_TYPES` in `formulation_mapping.py`).

This is a *general* intake-quality defect, not one specific to legal
statutes: the same pattern shows up in corporate policy documents as things
like "Approved by: ...", "This SOP supersedes v3.2", "Document Control"
tables, or a policy's own "last reviewed" date. In the current
`saudi-labor-law` dataset it happens to manifest with legal-statute
vocabulary (Royal Decree, entry into force, repeal) because that is the
source document's genre — but the underlying defect and this cleanup's
selection criteria are genre-agnostic: "would ANY enterprise policy engine
ever need to evaluate/enforce this statement against a fact pattern?" If
the honest answer is no, it is meta, not policy.

## What this script does NOT touch

An initial broad keyword search (title ILIKE '%this law%' OR '%royal
decree%' OR ...) returned 49 rows, but manual read-through showed the large
majority are genuine substantive rules that merely *cite* "this Law" as
their legal basis — e.g. scope/applicability rules ("Provisions of this Law
shall apply to Workers of charitable institutions"), exemption rules
("Agricultural workers ... shall be exempted from the implementation of the
provisions of this Law"), and real obligations/permissions/prohibitions.
Those are correctly-formed policy rules and must NOT be rejected merely for
mentioning the source law by name. This script therefore does not use any
keyword filter at query time — it acts ONLY on the exact, individually
human-vetted candidate_rule IDs hardcoded below, each with its own
recorded rationale.

## Safety

- Uses the existing `CandidateRuleRepository.set_review_status()` path —
  the same mechanism a human reviewer's "reject" click uses. Nothing is
  deleted; the rows remain in the table with `review_status="rejected"`,
  `reviewed_by="ai-intake-cleanup"`, and a `review_notes` string quoting
  the specific reason, so the action is fully auditable and reversible
  (a human can re-open/re-classify from the rejected list at any time).
- `--dry-run` (default) prints what would change without writing.
- Pass `--apply` to actually write.
- Idempotent: rows already in a non-"candidate" state are reported and
  skipped, never overwritten.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from policy_platform.infrastructure.db import get_sessionmaker  # noqa: E402
from policy_platform.infrastructure.repositories import (  # noqa: E402
    CandidateRuleRepository,
    PolicySetRepository,
)

POLICY_SET_KEY = "saudi-labor-law"
REVIEWED_BY = "ai-intake-cleanup"

# Each entry: (candidate_rule id, short rationale). IDs were individually
# vetted by reading the full candidate title and confirming it carries no
# operational content — see module docstring for the general test applied.
TARGETS: list[tuple[str, str]] = [
    (
        "f8f2eb7b-b734-46fd-895e-c59062e3e88f",
        "Pure supersession/citation metadata about the source law replacing a prior "
        "law by Royal Decree number and Hijri date — no rule for any party to follow.",
    ),
    (
        "c87c01f7-ff77-42cd-a0e4-06ad250dc3c7",
        "Pure repeal boilerplate ('this Law shall repeal all provisions inconsistent "
        "therewith') — a legislative-housekeeping statement, not an operational rule.",
    ),
    (
        "f62b0f43-0b35-4624-b570-3c5182f03c63",
        "Pure promulgation/publication statement about the document itself "
        "('This Law shall be published') — no operational content.",
    ),
    (
        "7871024f-1861-4c64-8208-230164f3183d",
        "Pure entry-into-force/effective-date-of-this-document statement — "
        "document lifecycle metadata, not a rule any party evaluates against.",
    ),
    (
        "9b2f9188-060d-4306-ba5a-d9aa2504f96f",
        "Pure promulgation of secondary regulations ('The Implementing Regulations "
        "shall be published') — regulatory-apparatus housekeeping, not an "
        "operational rule for any employer/employee.",
    ),
    (
        "67174f64-ab06-4aea-ae9f-a85ec21b5187",
        "Transitional/continuity meta about prior regulations remaining in effect "
        "pending replacement — describes the regulatory apparatus's own continuity, "
        "not a new operational obligation on any party.",
    ),
]

REASON_PREFIX = "[Automated intake-quality cleanup] Document-lifecycle/self-referential meta-text, not a substantive policy rule: "


async def run(*, apply: bool) -> None:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:  # type: AsyncSession
        policy_set_repo = PolicySetRepository(session)
        candidate_repo = CandidateRuleRepository(session)

        policy_set = await policy_set_repo.get_by_key(POLICY_SET_KEY)
        if policy_set is None:
            raise SystemExit(f"policy set '{POLICY_SET_KEY}' not found")

        changed = 0
        skipped = 0
        for raw_id, rationale in TARGETS:
            candidate_id = uuid.UUID(raw_id)
            candidate = await candidate_repo.get_by_id(candidate_id)
            if candidate is None:
                print(f"  ! {raw_id} — NOT FOUND, skipping")
                skipped += 1
                continue
            if candidate.policy_set_id != policy_set.id:
                print(f"  ! {raw_id} — belongs to a different policy set, skipping")
                skipped += 1
                continue
            title = (candidate.payload_json or {}).get("title", "<no title>")
            if candidate.review_status != "candidate":
                print(f"  = {raw_id} already '{candidate.review_status}', leaving as-is: {title!r}")
                skipped += 1
                continue

            print(f"  -> {raw_id} [{candidate.rule_type}] {title!r}")
            print(f"     reason: {rationale}")
            if apply:
                await candidate_repo.set_review_status(
                    candidate,
                    review_status="rejected",
                    reviewed_by=REVIEWED_BY,
                    review_notes=REASON_PREFIX + rationale,
                )
            changed += 1

        if apply:
            await session.commit()

        print()
        print(
            f"{'Applied' if apply else 'Would apply'}: {changed} rejected, {skipped} skipped "
            f"(not found / wrong policy set / already reviewed), {len(TARGETS)} total targets."
        )
        if not apply:
            print("Dry run only — re-run with --apply to write.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Actually write changes (default: dry-run)")
    args = parser.parse_args()
    asyncio.run(run(apply=args.apply))


if __name__ == "__main__":
    main()
