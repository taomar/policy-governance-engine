"""Governed Search projections: review versus runtime.

WHY TWO PROJECTIONS
-------------------
The existing indexer writes one kind of document: every clause of every uploaded
version, with `status` hardcoded to `"draft"`. That is fine for helping a
reviewer find things, and it is exactly wrong as the thing a runtime question is
answered from — it contains drafts, rejected candidates, and superseded
versions, none of which state current policy.

Rather than filter at query time, the two are separated at build time:

* **review** — candidate evidence and graph context, deliberately containing
  uncertainty. It must never be queried as approved policy.
* **runtime** — approved, effective rules only, one document per atomic rule.

Build-time separation is the stronger guarantee. A filter is a line of code that
can be forgotten in one caller; a document that was never built cannot be
returned by any caller, including one written later by someone who did not know
the rule.

WHY ONE DOCUMENT PER RULE
-------------------------
Not per file, which forces a reader to search inside a result for the part that
answers them, and not per parser chunk, which is an artifact of tokenisation and
frequently splits a rule from its threshold. One approved atomic rule with its
exact evidence is the smallest unit that is independently true.

EXACT TEXT VERSUS RETRIEVAL TEXT
---------------------------------
`exact_text` is copied from evidence and never rewritten. `retrieval_text` may
add headings and approved linked definitions to improve recall. They are
separate fields because collapsing them is how a heading ends up quoted back to
a user as though the policy said it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from policy_platform.contracts.canonical import canonical_hash

#: Statuses whose content may enter the runtime projection. Anything else --
#: draft, candidate, needs_changes, rejected, superseded -- states what the
#: policy *might* become, not what it is.
RUNTIME_ELIGIBLE_STATUSES = frozenset({"approved", "published", "active"})

ProjectionKind = Literal["review", "runtime"]


class ProjectionRefused(RuntimeError):
    """Raised when content is ineligible for the projection it was offered to."""


@dataclass
class ProjectionVerification:
    """Pre-activation check of a built projection.

    Activation is the moment a projection starts answering questions, so the
    checks happen before it rather than after: a projection found wrong
    afterwards has already been used.
    """

    expected_count: int = 0
    actual_count: int = 0
    missing_ids: list[str] = field(default_factory=list)
    unexpected_ids: list[str] = field(default_factory=list)
    hash_mismatches: list[str] = field(default_factory=list)
    ineligible_documents: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return (
            self.expected_count == self.actual_count
            and not self.missing_ids
            and not self.unexpected_ids
            and not self.hash_mismatches
            and not self.ineligible_documents
        )

    def failure_summary(self) -> str:
        parts: list[str] = []
        if self.expected_count != self.actual_count:
            parts.append(f"expected {self.expected_count} documents, found {self.actual_count}")
        for label, values in (
            ("missing", self.missing_ids),
            ("unexpected", self.unexpected_ids),
            ("hash mismatch", self.hash_mismatches),
            ("ineligible", self.ineligible_documents),
        ):
            if values:
                parts.append(f"{label}: {sorted(values)[:5]}")
        return " | ".join(parts)


def projection_document_id(*, release_id: str, rule_id: str) -> str:
    """Stable key for one projected rule.

    Derived from the release and rule rather than generated, so republishing the
    same release overwrites its own documents instead of accumulating a second
    copy beside them.
    """

    return f"{release_id}_{rule_id}"


def build_runtime_document(
    *,
    release_id: str,
    rule_id: str,
    status: str,
    policy_title: str,
    section_path: list[str],
    exact_text: str,
    evidence_locators: list[dict],
    modality: str | None = None,
    actor: str | None = None,
    action: str | None = None,
    outcome: str | None = None,
    scope: str | None = None,
    effective_from: str | None = None,
    effective_until: str | None = None,
    jurisdiction: str | None = None,
    organization: str | None = None,
    definition_ids: list[str] | None = None,
    exception_ids: list[str] | None = None,
    neighbour_rule_ids: list[str] | None = None,
    projection_version: str = "v1",
    embedding_deployment: str | None = None,
) -> dict:
    """Build one runtime document for an approved rule.

    Refuses anything not approved. The refusal is here, at build time, rather
    than in the publisher: a check in the publisher protects one code path,
    while a document that cannot be constructed protects every path that will
    ever exist.
    """

    if status.strip().casefold() not in RUNTIME_ELIGIBLE_STATUSES:
        raise ProjectionRefused(
            f"rule {rule_id} has status {status!r}; only approved content may enter the "
            "runtime projection"
        )
    if not exact_text.strip():
        raise ProjectionRefused(f"rule {rule_id} has no exact evidence text")
    if not evidence_locators:
        raise ProjectionRefused(f"rule {rule_id} has no evidence locator")

    document = {
        "id": projection_document_id(release_id=release_id, rule_id=rule_id),
        "projection_kind": "runtime",
        "projection_version": projection_version,
        "policy_release_id": release_id,
        "rule_id": rule_id,
        "status": status,
        "heading": policy_title,
        "section_heading": " > ".join(section_path),
        # The source's own characters. Never rewritten, never regenerated.
        "exact_text": exact_text,
        # Derived context to improve recall. Kept separate so a heading is never
        # quoted back to a user as though the policy said it.
        "retrieval_text": _retrieval_text(policy_title, section_path, exact_text),
        "modality": modality,
        "actor": actor,
        "action": action,
        "outcome": outcome,
        "scope": scope,
        "jurisdiction": jurisdiction,
        "organization": organization,
        "effective_from": effective_from,
        "effective_until": effective_until,
        "definition_rule_ids": list(definition_ids or []),
        "exception_rule_ids": list(exception_ids or []),
        "neighbour_rule_ids": list(neighbour_rule_ids or []),
        "evidence_locators": list(evidence_locators),
        "embedding_deployment": embedding_deployment,
    }
    document["content_hash"] = document_hash(document)
    return document


def build_review_document(
    *,
    document_version_id: str,
    candidate_key: str,
    policy_title: str,
    section_path: list[str],
    exact_text: str,
    evidence_locators: list[dict],
    review_status: str = "candidate",
    findings: list[str] | None = None,
    provenance_strength: str | None = None,
    projection_version: str = "v1",
) -> dict:
    """Build one review document for a candidate.

    Carries its uncertainty explicitly — review status, findings, provenance
    strength — because the review surface exists to show exactly what the
    runtime projection must not.
    """

    document = {
        "id": f"review_{document_version_id}_{candidate_key}",
        "projection_kind": "review",
        "projection_version": projection_version,
        "document_version_id": document_version_id,
        "candidate_key": candidate_key,
        "status": review_status,
        "heading": policy_title,
        "section_heading": " > ".join(section_path),
        "exact_text": exact_text,
        "retrieval_text": _retrieval_text(policy_title, section_path, exact_text),
        "findings": list(findings or []),
        "provenance_strength": provenance_strength,
        "evidence_locators": list(evidence_locators),
    }
    document["content_hash"] = document_hash(document)
    return document


def _retrieval_text(policy_title: str, section_path: list[str], exact_text: str) -> str:
    """Exact text plus the headings that scope it.

    Only headings and the text itself: everything here came from the document,
    so a match can always be explained by pointing at the source. Adding a
    summary or an expansion would make a hit unexplainable.
    """

    parts = [part for part in ([policy_title] + list(section_path)) if part]
    return " \n".join([*parts, exact_text]) if parts else exact_text


def document_hash(document: dict) -> str:
    """Content hash over everything but the hash field itself.

    Used to prove that what landed in the index is what was built, so a
    truncated or partially-applied upload is detectable rather than silent.
    """

    return canonical_hash({k: v for k, v in document.items() if k != "content_hash"})


def verify_projection(
    built: list[dict], indexed: list[dict], *, kind: ProjectionKind = "runtime"
) -> ProjectionVerification:
    """Compare what was built against what the index actually holds.

    Runs before activation. Checks counts, IDs and per-document hashes, and for
    the runtime projection re-checks eligibility — because the value of the
    build-time refusal depends on nothing having been inserted around it.
    """

    built_by_id = {doc["id"]: doc for doc in built}
    indexed_by_id = {doc["id"]: doc for doc in indexed}

    report = ProjectionVerification(
        expected_count=len(built_by_id),
        actual_count=len(indexed_by_id),
        missing_ids=sorted(set(built_by_id) - set(indexed_by_id)),
        unexpected_ids=sorted(set(indexed_by_id) - set(built_by_id)),
    )

    for document_id, expected in built_by_id.items():
        actual = indexed_by_id.get(document_id)
        if actual is None:
            continue
        # Recomputed from the indexed document's own content rather than read
        # from its `content_hash` field. Comparing the stored hashes would trust
        # the index to report its own corruption: content altered while the hash
        # field was preserved -- the exact shape of a partially-applied upload --
        # would compare equal and pass.
        if document_hash(actual) != expected.get("content_hash"):
            report.hash_mismatches.append(document_id)

    if kind == "runtime":
        for document_id, document in indexed_by_id.items():
            status = str(document.get("status", "")).strip().casefold()
            if status not in RUNTIME_ELIGIBLE_STATUSES:
                report.ineligible_documents.append(document_id)

    return report


def runtime_query_filter(
    *,
    organization: str | None = None,
    jurisdiction: str | None = None,
    as_of: str | None = None,
) -> str:
    """OData filter applied before relevance ranking.

    Status is always constrained, and not as a caller option. Relevance ranks
    what matches; it cannot exclude a rejected rule that happens to be the best
    textual match for a question, so the filter has to be unconditional.
    """

    clauses = [
        "(" + " or ".join(f"status eq '{s}'" for s in sorted(RUNTIME_ELIGIBLE_STATUSES)) + ")"
    ]
    if organization:
        clauses.append(f"(organization eq '{organization}' or organization eq null)")
    if jurisdiction:
        clauses.append(f"(jurisdiction eq '{jurisdiction}' or jurisdiction eq null)")
    if as_of:
        clauses.append(f"(effective_from eq null or effective_from le {as_of})")
        clauses.append(f"(effective_until eq null or effective_until ge {as_of})")
    return " and ".join(clauses)
