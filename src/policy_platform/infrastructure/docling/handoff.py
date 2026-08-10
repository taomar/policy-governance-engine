"""Idempotent handoff of an extraction package into the existing application.

WHERE THE BOUNDARY IS
---------------------
This module converts a verified package into the shapes the existing
application already speaks — `ExtractionRun` and `CandidateRule` — and submits
them through that application's repositories. It does not create review work,
decide authority, approve anything, publish, or write to Search. Those remain
the application's, and the directive is explicit that a second such subsystem
must not appear alongside it.

WHY MAPPING IS A PURE FUNCTION
------------------------------
`build_candidate_payloads` takes a package and returns dictionaries. No session,
no I/O. That is what makes the interesting part — whether a rule's evidence,
identity and provenance survive the crossing intact — testable without a
database, which matters because the mapping is where silent corruption would
occur and the database is the least available part of the stack.

IDEMPOTENCY
-----------
Extraction is re-run for many legitimate reasons: a restart, a transient model
failure, an operator retry. Each must resolve to the same intake rather than a
second set of candidates in the review queue. The package's `idempotency_key` is
derived from the source bytes, canonical artifact, template and run
configuration, so a genuine re-extraction produces a different key while a retry
produces the same one. `submit_package` checks for that key before writing
anything.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from policy_platform.contracts.extraction_package import PolicyExtractionPackage

#: Marks a candidate as produced by this pipeline, and records which package
#: produced it. Persisted inside `payload_json` rather than as a column so the
#: handoff needs no migration and no change to a table the application owns.
PROVENANCE_KEY = "extraction_provenance"


class HandoffRefused(RuntimeError):
    """Raised when a package must not be submitted.

    Distinct from a write failure: refusing is a *correct* outcome for an
    unverified package, and treating it as an error to be retried would
    eventually push unverified rules into the review queue.
    """


@dataclass
class HandoffResult:
    """What a submission did, or would have done."""

    idempotency_key: str
    candidates_created: int = 0
    already_submitted: bool = False
    extraction_run_id: str | None = None
    payloads: list[dict] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


def build_candidate_payloads(package: PolicyExtractionPackage) -> tuple[list[dict], list[str]]:
    """Map a package's rules onto candidate payloads, returning skips too.

    Every rule carries its own evidence spans rather than a reference into a
    shared list, because the payload crosses into a table this pipeline does not
    own: a reference that resolves only inside the package would become a
    dangling pointer the moment the row is read on its own.

    Rules whose evidence cannot be resolved are skipped with a reason rather
    than submitted without evidence. A candidate with no evidence is not a
    weaker candidate — it is an assertion a reviewer cannot check against the
    source, which is precisely what the pointer-only design exists to prevent.
    """

    payloads: list[dict] = []
    skipped: list[str] = []
    spans_by_hash = {span.evidence_hash: span for span in package.evidence_spans}

    for rule in package.canonical_rules:
        spans = [spans_by_hash[h] for h in rule.evidence_hashes if h in spans_by_hash]
        if not spans:
            skipped.append(f"{rule.rule_key}: no resolvable evidence, not submitted")
            continue

        payloads.append(
            {
                "rule_id": rule.rule_key,
                "title": rule.title,
                "modality": rule.modality,
                "actor": rule.actor,
                "action": rule.action,
                "outcome": rule.outcome,
                "scope": rule.scope,
                "conditions": list(rule.conditions),
                "exceptions": list(rule.exceptions),
                "approvals": list(rule.approvals),
                "unresolved_facts": list(rule.unresolved_facts),
                "status": rule.status,
                "evidence": [
                    {
                        "element_id": span.element_id,
                        "role": span.role,
                        # The source's own characters. Carried verbatim so a
                        # reviewer sees what the document says, not a summary of
                        # it, and never regenerated on read.
                        "exact_text": span.exact_text,
                        "page": span.page,
                        "page_start_offset": span.page_start_offset,
                        "page_end_offset": span.page_end_offset,
                        "evidence_hash": span.evidence_hash,
                    }
                    for span in spans
                ],
                PROVENANCE_KEY: {
                    "package_version": package.package_version,
                    "source_hash": package.source_release.source_hash,
                    "canonical_hash": package.canonical_document.canonical_hash,
                    "idempotency_key": package.application_handoff.idempotency_key,
                    "parser": package.canonical_document.parser,
                    "converter_version": package.canonical_document.converter_version,
                },
            }
        )

    return payloads, skipped


def rule_type_for(payload: dict) -> str:
    """Map a candidate onto the platform's existing rule-type vocabulary.

    Deliberately coarse. The modality the document states is the only thing
    known at this point, and inferring a finer type from prose would put a guess
    into a field the review workbench treats as classified fact.
    """

    modality = (payload.get("modality") or "").strip().casefold()
    if modality in ("must", "shall", "required"):
        return "obligation"
    if modality in ("must_not", "shall_not", "prohibited"):
        return "prohibition"
    if modality in ("may", "permitted"):
        return "permission"
    if modality in ("entitlement", "eligibility"):
        return "eligibility"
    if modality == "authority":
        return "authority"
    return "unclassified"


def preview_handoff(package: PolicyExtractionPackage) -> HandoffResult:
    """Compute what submission would do, without touching a database.

    Exists because the expensive, slow, unreviewable part of a handoff is the
    write, and everything worth checking happens before it.
    """

    _require_submittable(package)
    payloads, skipped = build_candidate_payloads(package)
    return HandoffResult(
        idempotency_key=package.application_handoff.idempotency_key,
        candidates_created=len(payloads),
        payloads=payloads,
        skipped=skipped,
    )


def _require_submittable(package: PolicyExtractionPackage) -> None:
    if not package.verification.ok:
        raise HandoffRefused(
            "package has verification blockers: "
            + "; ".join(package.verification.blockers[:3])
        )
    if not package.coverage.is_complete:
        raise HandoffRefused(
            f"coverage is incomplete: {len(package.coverage.unaccounted_element_ids)} "
            "element(s) unaccounted"
        )
    if not package.application_handoff.idempotency_key:
        raise HandoffRefused("package carries no idempotency key; a retry could duplicate intake")


async def submit_package(
    package: PolicyExtractionPackage,
    *,
    session,
    policy_set_id: uuid.UUID,
    document_version_id: uuid.UUID,
    deployment_name: str = "docling-graph",
    parser_version: str = "docling",
) -> HandoffResult:
    """Submit a verified package through the application's own repositories.

    Never writes directly to the database or to Search: everything goes through
    `ExtractionRunRepository` and `CandidateRuleRepository`, which is what keeps
    the application's own invariants — supersession, delta status, review
    lifecycle — in force.

    Re-submitting the same package is a no-op. The check is a query for the
    idempotency key rather than a caught unique-constraint violation, because
    the latter needs a constraint on a table this pipeline does not own.
    """

    from policy_platform.infrastructure.repositories import (
        CandidateRuleRepository,
        ExtractionRunRepository,
    )

    _require_submittable(package)
    key = package.application_handoff.idempotency_key

    candidate_repo = CandidateRuleRepository(session)
    existing = await candidate_repo.list_by_policy_set(policy_set_id, include_superseded=True)
    for candidate in existing:
        provenance = (candidate.payload_json or {}).get(PROVENANCE_KEY) or {}
        if provenance.get("idempotency_key") == key:
            return HandoffResult(
                idempotency_key=key,
                already_submitted=True,
                extraction_run_id=str(candidate.extraction_run_id),
            )

    payloads, skipped = build_candidate_payloads(package)

    run_repo = ExtractionRunRepository(session)
    run = await run_repo.create(
        document_version_id=document_version_id,
        deployment_name=deployment_name,
        prompt_version=package.package_version,
        parser_version=parser_version,
    )

    for payload in payloads:
        await candidate_repo.create(
            policy_set_id=policy_set_id,
            extraction_run_id=run.id,
            rule_type=rule_type_for(payload),
            payload_json=payload,
        )

    return HandoffResult(
        idempotency_key=key,
        candidates_created=len(payloads),
        extraction_run_id=str(run.id),
        payloads=payloads,
        skipped=skipped,
    )
