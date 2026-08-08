"""One-off backfill: restore `EvidenceReference` rows for already-published
`ApprovedRule`s whose originating `CandidateRule.payload_json` carried
evidence that was never persisted at publish time.

Root cause: the demo/sample policy sets in this local database were
published before evidence persistence was fully wired into
`policy_version_import.import_approved_policy_version` (see
`EvidenceReferenceRepository.bulk_create`, which today runs correctly for
every *new* publish). Those earlier publishes carried the rule's other
fields into `approved_rules` but the `evidence` list was silently dropped,
so `evidence_references` ended up empty even though the source clause
linkage still exists verbatim in `candidate_rules.payload_json`. This script
repairs the data gap without touching any application code path — it is
safe to re-run (idempotent: skips any `ApprovedRule` that already has
evidence rows).

Some candidate payloads reference a `clause_id` from a `clauses` row that no
longer exists (e.g. the source document was re-processed after the
candidate was drafted, regenerating clause ids). Rather than aborting the
whole rule when this happens, the evidence item is still backfilled with
`clause_id=None` — page/section/offsets/source_hash/document reference are
independently useful citation info and are not lost just because the
fine-grained clause anchor went stale. If `document_version_id` itself is
missing (harder FK, non-nullable) that single evidence item is skipped and
reported, since there is nothing safe to insert.

Each rule is committed independently so one bad row never rolls back
already-backfilled rules.

Usage (from repo root, with the venv active):
    python scripts/backfill_evidence_references.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy import Integer, select  # noqa: E402

from policy_platform.contracts.policy import EvidenceReference as ContractEvidenceReference  # noqa: E402
from policy_platform.domain.models import (  # noqa: E402
    ApprovedRule,
    CandidateRule,
    Clause,
    DocumentVersion,
    EvidenceReference,
)
from policy_platform.infrastructure.db import get_sessionmaker  # noqa: E402
from policy_platform.infrastructure.repositories import EvidenceReferenceRepository  # noqa: E402


async def main() -> None:
    session_factory = get_sessionmaker()
    async with session_factory() as session:
        rules = list((await session.execute(select(ApprovedRule))).scalars().all())
        rules_with_evidence = {
            row[0] for row in (await session.execute(select(EvidenceReference.rule_id).distinct())).all()
        }
        valid_document_version_ids = {
            row[0] for row in (await session.execute(select(DocumentVersion.id))).all()
        }
        valid_clause_ids = {row[0] for row in (await session.execute(select(Clause.id))).all()}

        print(f"scanning {len(rules)} approved rule(s)…")

        backfilled_rules = 0
        backfilled_items = 0
        dropped_stale_clause_id = 0
        skipped_missing_document_version = 0
        already_had = 0
        no_candidate_match = 0
        candidate_had_no_evidence = 0
        failed_rules: list[str] = []

        for rule in rules:
            if rule.id in rules_with_evidence:
                already_had += 1
                continue

            candidate_result = await session.execute(
                select(CandidateRule).where(
                    CandidateRule.published_version_id == rule.policy_version_id,
                    CandidateRule.payload_json["rule_id"].astext == rule.rule_id,
                    CandidateRule.payload_json["rule_revision"].astext.cast(Integer) == rule.revision,
                )
            )
            candidate = candidate_result.scalars().first()
            if candidate is None:
                no_candidate_match += 1
                continue

            evidence_payload = candidate.payload_json.get("evidence") or []
            if not evidence_payload:
                candidate_had_no_evidence += 1
                continue

            # Validate through the same contract the live publish path uses,
            # so a malformed payload fails loudly instead of writing bad rows.
            validated = [ContractEvidenceReference.model_validate(ev) for ev in evidence_payload]

            usable: list[dict] = []
            for ev in validated:
                if uuid_str_to_valid_member(ev.document_version_id, valid_document_version_ids) is False:
                    skipped_missing_document_version += 1
                    print(f"  SKIP evidence item for {rule.rule_id}: document_version {ev.document_version_id} no longer exists")
                    continue
                dumped = ev.model_dump(mode="json")
                if ev.clause_id and uuid_str_to_valid_member(ev.clause_id, valid_clause_ids) is False:
                    dropped_stale_clause_id += 1
                    dumped["clause_id"] = None
                usable.append(dumped)

            if not usable:
                continue

            try:
                await EvidenceReferenceRepository(session).bulk_create(rule_id=rule.id, evidence=usable)
                await session.commit()
            except Exception as exc:  # noqa: BLE001
                await session.rollback()
                failed_rules.append(f"{rule.rule_id} rev {rule.revision}: {exc}")
                print(f"  FAILED {rule.rule_id} rev {rule.revision}: {exc}")
                continue

            backfilled_rules += 1
            backfilled_items += len(usable)
            print(f"  backfilled {len(usable)} evidence item(s) for {rule.rule_id} rev {rule.revision}")

        print()
        print("done.")
        print(f"  rules backfilled:                 {backfilled_rules} ({backfilled_items} evidence items)")
        print(f"  already had evidence (skipped):    {already_had}")
        print(f"  no matching candidate found:       {no_candidate_match}")
        print(f"  candidate had no evidence:         {candidate_had_no_evidence}")
        print(f"  evidence items with stale clause_id (kept, clause_id nulled): {dropped_stale_clause_id}")
        print(f"  evidence items skipped (missing document_version): {skipped_missing_document_version}")
        if failed_rules:
            print(f"  rules that failed to insert ({len(failed_rules)}):")
            for line in failed_rules:
                print(f"    - {line}")


def uuid_str_to_valid_member(value: str, valid_ids: set) -> bool:
    import uuid

    try:
        return uuid.UUID(value) in valid_ids
    except (ValueError, TypeError):
        return False


if __name__ == "__main__":
    asyncio.run(main())
