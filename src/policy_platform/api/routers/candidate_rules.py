"""Candidate-rule drafting, human review, and publish workflow.

This is the human-in-the-loop governance path described in Section 5 of the
spec: a candidate rule is drafted (manually today; by the MAF extraction
pipeline in a later phase — see docs/known-limitations.md), a reviewer
approves or rejects it, and approved candidates are bundled into a brand-new
immutable `ApprovedPolicyVersion` via the existing
`import_approved_policy_version` service. Nothing here mutates an
already-approved version; only the mutable `CandidateRule` rows are updated
in place during review, which is explicitly allowed (see domain/models.py).
"""
from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from policy_platform.api.schemas import (
    ApprovedPolicyVersionResponse,
    BulkCandidateRuleReviewRequest,
    BulkReviewResult,
    CandidateRuleDraftRequest,
    CandidateRuleEditRequest,
    CandidateRuleResponse,
    CandidateRuleReviewRequest,
    OverrideReviewRequest,
    PublishCandidatesRequest,
    RequestChangesRequest,
)
from policy_platform.contracts.policy import AggregateLimit, AggregateLimitContribution, CanonicalRule
from policy_platform.infrastructure.persistence.db import get_session
from policy_platform.infrastructure.extraction.formulation_mapping import (
    _decision_readiness_for,
    condition_provenance_for,
)
from policy_platform.contracts.policy import attributes_for, evaluation_mode_for
from policy_platform.infrastructure.extraction.policy_facts import published_facts
from policy_platform.infrastructure.projection.xacml_projection import build_xacml_view, xacml_effect_for
from policy_platform.infrastructure.projection.export import (
    ExportFormat,
    content_disposition,
    extension_for,
    media_type_for,
    rows_to_export,
)
from policy_platform.infrastructure.persistence.audit import (
    CANDIDATE_REVIEW_OVERRIDDEN,
    CANDIDATE_REVIEWED,
    CANDIDATES_BULK_REVIEWED,
    CANDIDATES_PUBLISHED,
    record_audit_event,
)
from policy_platform.infrastructure.ingestion.manual_extraction import get_or_create_manual_extraction_run
from policy_platform.infrastructure.persistence.mappers import approved_policy_version_to_package
from policy_platform.infrastructure.policy_tests.policy_test_execution import run_active_tests_for_version
from policy_platform.infrastructure.persistence.policy_version_import import import_approved_policy_version
from policy_platform.infrastructure.persistence.review_facets import build_review_facets
from policy_platform.infrastructure.persistence.repositories import (
    ApprovedPolicyVersionRepository,
    CandidateRuleRepository,
    NoteRepository,
    PolicyAggregateLimitRepository,
    PolicySetRepository,
)

router = APIRouter(prefix="/api/policy-sets", tags=["candidate-rules"])
logger = logging.getLogger(__name__)

# Statuses a candidate can be edited / re-submitted for review from. A
# candidate sent back to changes_requested by a manager is exactly as
# editable as a freshly-drafted or rejected one — the whole point of sending
# it back is to let the composer fix it and resubmit.
_EDITABLE_STATUSES = ("candidate", "rejected", "changes_requested")


def _require_manager(actor_role: str) -> None:
    if actor_role != "policy_manager":
        raise HTTPException(
            status_code=403,
            detail="Only a Policy Manager can perform this action. Switch your acting role in the header.",
        )


def _to_response(candidate) -> CandidateRuleResponse:
    return CandidateRuleResponse(
        id=str(candidate.id),
        policy_set_id=str(candidate.policy_set_id),
        extraction_run_id=str(candidate.extraction_run_id),
        rule_type=candidate.rule_type,
        revision=candidate.revision,
        review_status=candidate.review_status,
        reviewed_by=candidate.reviewed_by,
        reviewed_at=candidate.reviewed_at,
        review_notes=candidate.review_notes,
        published_version_id=str(candidate.published_version_id) if candidate.published_version_id else None,
        created_at=candidate.created_at,
        delta_status=candidate.delta_status,
        reworded=bool(candidate.reworded),
        baseline_candidate_id=(
            str(candidate.baseline_candidate_id) if candidate.baseline_candidate_id else None
        ),
        superseded_at=candidate.superseded_at,
        rule=_with_decision_readiness(CanonicalRule.model_validate(candidate.payload_json)),
    )


def _with_decision_readiness(rule: CanonicalRule) -> CanonicalRule:
    """Derive the readiness assessment and XACML view from the canonical record.

    Always recomputed, never read from the stored payload. Both are pure
    functions of `formulation.canonical`, which is persisted, so deriving them
    costs nothing and keeps one source of truth.

    An earlier version preferred a stored copy when present, on the reasoning
    that a shipped value should not change underneath a reviewer. That was
    wrong in the direction that matters: when the assessment was corrected — a
    `classification` carrying a 5% threshold had been reported as stating no
    decision — every rule extracted before the fix kept the stale verdict,
    because the stored copy shadowed it. A derivation that cannot be improved
    without re-running extraction over the whole corpus is not a derivation.
    """

    if rule.formulation is None or rule.formulation.canonical is None:
        return rule
    canonical = rule.formulation.canonical
    # Reconciled against the rule's own `required_facts`, exactly as extraction
    # does. Without it the two paths disagreed about the same name: a fact
    # whose type the compiled comparison establishes came back blank here.
    facts = published_facts(canonical.rule, rule.required_facts)
    return rule.model_copy(
        update={
            "decision_readiness": _decision_readiness_for(canonical),
            "xacml_view": build_xacml_view(
                canonical, record_effect=xacml_effect_for(rule.effect.type)
            ),
            # Re-derived for the same reason as the two above. A candidate
            # stores it at extraction time, so reading it back would work — but
            # then a corrected message would reach published rules (which
            # derive it) and not candidates, and the two views of the same rule
            # would disagree about why its condition is empty.
            "condition_provenance": condition_provenance_for(rule.formulation, rule.condition),
            "evaluation_mode": evaluation_mode_for(rule),
            "fact_model": facts,
            # Derived alongside the facts it references, from the same list, so
            # a row can never name an identifier the fact model does not carry.
            "attributes": attributes_for(canonical.rule, facts),
        }
    )


@router.post(
    "/{key}/candidate-rules",
    response_model=CandidateRuleResponse,
    status_code=201,
)
async def draft_candidate_rule(
    key: str, body: CandidateRuleDraftRequest, session: AsyncSession = Depends(get_session)
) -> CandidateRuleResponse:
    policy_set_repo = PolicySetRepository(session)
    policy_set = await policy_set_repo.get_by_key(key)
    if policy_set is None:
        raise HTTPException(status_code=404, detail=f"policy set '{key}' not found")

    # Overwrite server-owned identity fields; the client only supplies these
    # because CanonicalRule requires them, not because they're meaningful yet.
    rule = body.rule.model_copy(
        update={
            "policy_set_id": str(policy_set.id),
            "policy_version_id": "draft",
        }
    )

    extraction_run = await get_or_create_manual_extraction_run(session)
    candidate_repo = CandidateRuleRepository(session)
    candidate = await candidate_repo.create(
        policy_set_id=policy_set.id,
        extraction_run_id=extraction_run.id,
        rule_type=rule.rule_type.value if hasattr(rule.rule_type, "value") else str(rule.rule_type),
        payload_json=rule.model_dump(mode="json"),
    )
    await session.commit()
    return _to_response(candidate)


@router.get("/{key}/candidate-rules", response_model=list[CandidateRuleResponse])
async def list_candidate_rules(
    key: str,
    status: str | None = None,
    document_id: uuid.UUID | None = None,
    document_version_id: uuid.UUID | None = None,
    extraction_run_id: uuid.UUID | None = None,
    delta_status: str | None = None,
    include_superseded: bool = False,
    session: AsyncSession = Depends(get_session),
) -> list[CandidateRuleResponse]:
    """The review queue, narrowed to whatever the reviewer is looking at.

    `include_superseded` is opt-in and only meaningful alongside
    `extraction_run_id`: it is how a reviewer opens a historical run to see what
    it produced. Left off, this returns the current generation of rules, which
    is what every other view means.
    """

    policy_set_repo = PolicySetRepository(session)
    policy_set = await policy_set_repo.get_by_key(key)
    if policy_set is None:
        raise HTTPException(status_code=404, detail=f"policy set '{key}' not found")

    candidate_repo = CandidateRuleRepository(session)
    candidates = await candidate_repo.list_by_policy_set(
        policy_set.id,
        review_status=status,
        document_id=document_id,
        document_version_id=document_version_id,
        extraction_run_id=extraction_run_id,
        delta_status=delta_status,
        include_superseded=include_superseded,
    )
    return _with_successors([_to_response(c) for c in candidates])


def _with_successors(responses: list[CandidateRuleResponse]) -> list[CandidateRuleResponse]:
    """Say which record replaced which, over the set being returned.

    A later run records the reading it replaces as its `baseline_candidate_id`,
    so the successor relation is already in the data — just held by the wrong
    end of the pair. A reader looking at one record cannot tell whether
    something newer exists; a reader looking at the queue sees both and has no
    way to order them.

    Derived here rather than stored because it depends on the set in view. A
    record is the latest *among what was asked for*, and asking for one run's
    output should not make its rules look superseded by a run nobody requested.

    Baselines pointing outside the set are left alone: 30 of 41 do, because
    their predecessors belong to runs already retired from the queue.
    """

    successor: dict[str, str] = {}
    present = {response.id for response in responses}
    for response in responses:
        baseline = response.baseline_candidate_id
        if baseline and baseline in present:
            successor[baseline] = response.id
    return [
        response.model_copy(update={"superseded_by_candidate_id": successor.get(response.id)})
        for response in responses
    ]


@router.get("/{key}/review-facets")
async def review_facets(key: str, session: AsyncSession = Depends(get_session)) -> dict:
    """Everything the review queue needs to offer filters, in one round-trip.

    A reviewer facing hundreds of candidates needs to narrow by the things that
    actually organise the work — which document, which extraction run, and what
    changed — and each of those lists has to be derived from the data rather
    than hardcoded. Returned together because they are always needed together;
    four separate calls would only make the filter bar render in stages.

    Also returns `removed`: rules the previous extraction produced that the
    latest one did not. Those generate no row in the queue, so without this they
    would be invisible — and a clause disappearing from a re-uploaded document
    is precisely the kind of change a reviewer must not miss.
    """

    policy_set_repo = PolicySetRepository(session)
    policy_set = await policy_set_repo.get_by_key(key)
    if policy_set is None:
        raise HTTPException(status_code=404, detail=f"policy set '{key}' not found")

    return await build_review_facets(session, policy_set)


@router.get("/{key}/candidate-rules/export")
async def export_candidate_rules(
    key: str,
    format: ExportFormat = "json",
    status: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Download candidate rules (optionally filtered by review_status) as
    JSON, JSONL, or CSV — including review metadata (status/reviewer/notes)
    alongside the rule payload, so a policy manager can audit the review
    trail offline, not just the rule content.
    """
    policy_set_repo = PolicySetRepository(session)
    policy_set = await policy_set_repo.get_by_key(key)
    if policy_set is None:
        raise HTTPException(status_code=404, detail=f"policy set '{key}' not found")

    candidate_repo = CandidateRuleRepository(session)
    candidates = await candidate_repo.list_by_policy_set(policy_set.id, review_status=status)

    rows: list[dict] = []
    for candidate in candidates:
        response = _to_response(candidate)
        row = response.model_dump(mode="json")
        rule = row.pop("rule")
        # Flatten the nested rule payload with a `rule_` prefix so both the
        # review metadata and the rule content sit in one flat record —
        # important for the CSV path, where nesting isn't representable.
        row.update({f"rule_{field}": value for field, value in rule.items()})
        rows.append(row)

    content = rows_to_export(rows, format)
    suffix = f"-{status}" if status else ""
    filename = f"{key}-candidate-rules{suffix}.{extension_for(format)}"
    return Response(
        content=content, media_type=media_type_for(format), headers=content_disposition(filename)
    )


@router.post(
    "/{key}/candidate-rules/{candidate_id}/review",
    response_model=CandidateRuleResponse,
)
async def review_candidate_rule(
    key: str,
    candidate_id: uuid.UUID,
    body: CandidateRuleReviewRequest,
    session: AsyncSession = Depends(get_session),
) -> CandidateRuleResponse:
    policy_set_repo = PolicySetRepository(session)
    policy_set = await policy_set_repo.get_by_key(key)
    if policy_set is None:
        raise HTTPException(status_code=404, detail=f"policy set '{key}' not found")

    candidate_repo = CandidateRuleRepository(session)
    candidate = await candidate_repo.get_by_id(candidate_id)
    if candidate is None or candidate.policy_set_id != policy_set.id:
        raise HTTPException(status_code=404, detail=f"candidate rule '{candidate_id}' not found")
    if candidate.review_status not in _EDITABLE_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=f"candidate rule '{candidate_id}' is '{candidate.review_status}' and cannot be re-reviewed",
        )

    new_status = "approved" if body.decision == "approve" else "rejected"
    previous_status = candidate.review_status
    candidate = await candidate_repo.set_review_status(
        candidate, review_status=new_status, reviewed_by=body.reviewer, review_notes=body.notes
    )
    record_audit_event(
        session,
        event_type=CANDIDATE_REVIEWED,
        entity_type="candidate_rule",
        entity_id=candidate.id,
        actor=body.reviewer,
        policy_set_key=key,
        details={
            "decision": body.decision,
            "from_status": previous_status,
            "to_status": new_status,
            "notes": body.notes or "",
        },
    )
    await session.commit()
    return _to_response(candidate)


@router.put(
    "/{key}/candidate-rules/{candidate_id}",
    response_model=CandidateRuleResponse,
)
async def edit_candidate_rule(
    key: str,
    candidate_id: uuid.UUID,
    body: CandidateRuleEditRequest,
    session: AsyncSession = Depends(get_session),
) -> CandidateRuleResponse:
    """Manual, human-typed correction to a candidate's content — the direct-edit
    counterpart to the AI "suggest rewrite" flow. Only valid pre-approval (or
    after being explicitly sent back for changes); an approved-but-unpublished
    candidate must first go through `/request-changes` before it can be edited
    again, so there is always an explicit, auditable reason on record for why
    an already-reviewed rule changed.
    """
    policy_set_repo = PolicySetRepository(session)
    policy_set = await policy_set_repo.get_by_key(key)
    if policy_set is None:
        raise HTTPException(status_code=404, detail=f"policy set '{key}' not found")

    candidate_repo = CandidateRuleRepository(session)
    candidate = await candidate_repo.get_by_id(candidate_id)
    if candidate is None or candidate.policy_set_id != policy_set.id:
        raise HTTPException(status_code=404, detail=f"candidate rule '{candidate_id}' not found")
    if candidate.review_status not in _EDITABLE_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=(
                f"candidate rule '{candidate_id}' is '{candidate.review_status}' and cannot be edited "
                "directly — approved candidates must be sent back for changes first."
            ),
        )

    # Identity fields are server-owned; never trust the client to keep them stable.
    validated = body.rule.model_copy(
        update={
            "policy_set_id": str(policy_set.id),
            "policy_version_id": "draft",
            "rule_id": candidate.payload_json.get("rule_id", body.rule.rule_id),
        }
    )
    candidate = await candidate_repo.update_payload(candidate, payload_json=validated.model_dump(mode="json"))

    note_repo = NoteRepository(session)
    await note_repo.create(
        entity_type="candidate_rule",
        entity_id=str(candidate.id),
        author=body.editor,
        author_role="editor",
        body=f"Manually edited rule content (now revision {candidate.revision}).",
    )
    await session.commit()
    return _to_response(candidate)


@router.post(
    "/{key}/candidate-rules/{candidate_id}/request-changes",
    response_model=CandidateRuleResponse,
)
async def request_changes(
    key: str,
    candidate_id: uuid.UUID,
    body: RequestChangesRequest,
    session: AsyncSession = Depends(get_session),
) -> CandidateRuleResponse:
    """A Policy Manager sends an approved-but-unpublished candidate back to the
    composer/reviewer pool for rework, with a mandatory reason. This is the
    "send it back to review" action — it reopens the candidate for editing and
    re-review; it does not touch anything already published.
    """
    policy_set_repo = PolicySetRepository(session)
    policy_set = await policy_set_repo.get_by_key(key)
    if policy_set is None:
        raise HTTPException(status_code=404, detail=f"policy set '{key}' not found")

    _require_manager(body.actor_role)

    candidate_repo = CandidateRuleRepository(session)
    candidate = await candidate_repo.get_by_id(candidate_id)
    if candidate is None or candidate.policy_set_id != policy_set.id:
        raise HTTPException(status_code=404, detail=f"candidate rule '{candidate_id}' not found")
    if candidate.review_status != "approved":
        raise HTTPException(
            status_code=409,
            detail=f"candidate rule '{candidate_id}' is '{candidate.review_status}', not 'approved' — nothing to send back",
        )

    note_text = f"[{body.reason}] {body.notes}".strip() if body.notes else f"[{body.reason}]"
    candidate = await candidate_repo.set_review_status(
        candidate, review_status="changes_requested", reviewed_by=body.manager, review_notes=note_text
    )
    note_repo = NoteRepository(session)
    await note_repo.create(
        entity_type="candidate_rule",
        entity_id=str(candidate.id),
        author=body.manager,
        author_role="Policy Manager",
        body=f"Sent back for changes — {note_text}",
    )
    await session.commit()
    return _to_response(candidate)


@router.post(
    "/{key}/candidate-rules/{candidate_id}/override",
    response_model=CandidateRuleResponse,
)
async def override_review(
    key: str,
    candidate_id: uuid.UUID,
    body: OverrideReviewRequest,
    session: AsyncSession = Depends(get_session),
) -> CandidateRuleResponse:
    """A Policy Manager directly forces a decision, bypassing the normal
    composer/reviewer step (e.g. approving something a reviewer rejected, or
    rejecting something a reviewer already approved) with mandatory
    justification recorded on the audit trail. Never usable once published —
    publishing is a one-way door; a correction after that point must be a new
    candidate that supersedes the rule in a future version.
    """
    policy_set_repo = PolicySetRepository(session)
    policy_set = await policy_set_repo.get_by_key(key)
    if policy_set is None:
        raise HTTPException(status_code=404, detail=f"policy set '{key}' not found")

    _require_manager(body.actor_role)

    candidate_repo = CandidateRuleRepository(session)
    candidate = await candidate_repo.get_by_id(candidate_id)
    if candidate is None or candidate.policy_set_id != policy_set.id:
        raise HTTPException(status_code=404, detail=f"candidate rule '{candidate_id}' not found")
    if candidate.review_status == "published":
        raise HTTPException(
            status_code=409,
            detail="Published candidates cannot be overridden — draft a new candidate to supersede this rule instead.",
        )

    new_status = "approved" if body.decision == "approve" else "rejected"
    note_text = f"[Manager override — {body.reason}] {body.notes}".strip() if body.notes else f"[Manager override — {body.reason}]"
    candidate = await candidate_repo.set_review_status(
        candidate, review_status=new_status, reviewed_by=body.manager, review_notes=note_text
    )
    note_repo = NoteRepository(session)
    await note_repo.create(
        entity_type="candidate_rule",
        entity_id=str(candidate.id),
        author=body.manager,
        author_role="Policy Manager",
        body=f"Overrode review decision to '{new_status}' — {note_text}",
    )
    record_audit_event(
        session,
        event_type=CANDIDATE_REVIEW_OVERRIDDEN,
        entity_type="candidate_rule",
        entity_id=candidate.id,
        actor=body.manager,
        policy_set_key=key,
        details={
            "decision": body.decision,
            "to_status": new_status,
            "actor_role": body.actor_role,
            "reason": body.reason,
        },
    )
    await session.commit()
    return _to_response(candidate)


@router.post(
    "/{key}/candidate-rules/bulk-review",
    response_model=BulkReviewResult,
)
async def bulk_review_candidate_rules(
    key: str,
    body: BulkCandidateRuleReviewRequest,
    session: AsyncSession = Depends(get_session),
) -> BulkReviewResult:
    policy_set_repo = PolicySetRepository(session)
    policy_set = await policy_set_repo.get_by_key(key)
    if policy_set is None:
        raise HTTPException(status_code=404, detail=f"policy set '{key}' not found")

    candidate_repo = CandidateRuleRepository(session)
    if body.candidate_ids:
        targets = []
        for raw_id in body.candidate_ids:
            candidate = await candidate_repo.get_by_id(uuid.UUID(raw_id))
            if candidate is not None and candidate.policy_set_id == policy_set.id:
                targets.append(candidate)
    else:
        targets = await candidate_repo.list_by_policy_set(policy_set.id, review_status="candidate")

    new_status = "approved" if body.decision == "approve" else "rejected"
    reviewed = 0
    skipped: list[str] = []
    for candidate in targets:
        if candidate.review_status not in _EDITABLE_STATUSES:
            skipped.append(str(candidate.id))
            continue
        await candidate_repo.set_review_status(
            candidate, review_status=new_status, reviewed_by=body.reviewer, review_notes=body.notes
        )
        reviewed += 1

    # One event for the batch, not one per rule: a bulk approval is a single
    # human decision, and expanding it into hundreds of identical rows would
    # bury the individually-reviewed ones an auditor actually cares about. The
    # affected ids are kept in the detail payload so nothing is lost.
    if reviewed:
        record_audit_event(
            session,
            event_type=CANDIDATES_BULK_REVIEWED,
            entity_type="policy_set",
            entity_id=policy_set.id,
            actor=body.reviewer,
            policy_set_key=key,
            details={
                "decision": body.decision,
                "to_status": new_status,
                "reviewed_count": reviewed,
                "skipped_count": len(skipped),
                "candidate_ids": [str(c.id) for c in targets if str(c.id) not in skipped],
            },
        )

    await session.commit()
    return BulkReviewResult(reviewed=reviewed, skipped=skipped)


@router.post(
    "/{key}/publish",
    response_model=ApprovedPolicyVersionResponse,
    status_code=201,
)
async def publish_approved_candidates(
    key: str, body: PublishCandidatesRequest, session: AsyncSession = Depends(get_session)
) -> ApprovedPolicyVersionResponse:
    policy_set_repo = PolicySetRepository(session)
    policy_set = await policy_set_repo.get_by_key(key)
    if policy_set is None:
        raise HTTPException(status_code=404, detail=f"policy set '{key}' not found")

    candidate_repo = CandidateRuleRepository(session)
    approved = [
        c for c in await candidate_repo.list_by_policy_set(policy_set.id, review_status="approved")
        if c.published_version_id is None
    ]
    if not approved:
        raise HTTPException(
            status_code=409,
            detail=f"no approved, unpublished candidate rules for policy set '{key}'",
        )

    version_repo = ApprovedPolicyVersionRepository(session)
    version_number = body.version_number
    if version_number is None:
        version_number = await version_repo.get_max_version_number(policy_set.id) + 1

    # ApprovedPolicyVersion rows are full immutable snapshots (Rule 5.3 /
    # docs/data-model.md), not deltas. Publishing must therefore carry
    # forward every rule from the current active version, with newly
    # approved candidates added or, if they share a rule_id, superseding the
    # prior revision of that rule — never silently dropping the rest of the
    # rule set.
    merged_rules: dict[str, CanonicalRule] = {}
    current_active = await version_repo.get_active_version(policy_set.id)
    if current_active is not None:
        baseline_package = approved_policy_version_to_package(current_active)
        for rule in baseline_package.rules:
            merged_rules[rule.rule_id] = rule

    for candidate in approved:
        rule = CanonicalRule.model_validate(candidate.payload_json).model_copy(
            update={
                "policy_set_id": str(policy_set.id),
                "policy_version_id": "pending",  # overwritten implicitly; not persisted by the import service
            }
        )
        merged_rules[rule.rule_id] = rule

    rules: list[CanonicalRule] = list(merged_rules.values())

    # Aggregate limits (e.g. "60+15 days capped at 70/year combined") have no
    # per-candidate review step — they're structural policy-set config a
    # Policy Manager maintains directly via the aggregate-limits CRUD
    # endpoints. Publishing snapshots the *current full draft list* into this
    # version, exactly as `rules` above represents the full carried-forward
    # rule set rather than only this batch's changes.
    draft_limits = await PolicyAggregateLimitRepository(session).list_by_policy_set(policy_set.id)
    aggregate_limits = [
        AggregateLimit(
            aggregate_id=row.aggregate_key,
            description=row.description,
            contributing_rules=[
                AggregateLimitContribution(**c) for c in (row.contributing_rules_json or [])
            ],
            aggregator=row.aggregator,
            max_value=row.max_value,
            period=row.period,
        )
        for row in draft_limits
    ]

    version = await import_approved_policy_version(
        session,
        policy_set_id=policy_set.id,
        version_number=version_number,
        effective_from=body.effective_from,
        effective_to=body.effective_to,
        approved_by=body.approved_by,
        is_active=body.is_active,
        rules=rules,
        aggregate_limits=aggregate_limits,
    )

    for candidate in approved:
        await candidate_repo.mark_published(candidate, published_version_id=version.id)

    record_audit_event(
        session,
        event_type=CANDIDATES_PUBLISHED,
        entity_type="approved_policy_version",
        entity_id=version.id,
        actor=body.approved_by,
        policy_set_key=key,
        details={
            "version_number": version_number,
            "effective_from": body.effective_from.isoformat(),
            "effective_to": body.effective_to.isoformat() if body.effective_to else None,
            "is_active": body.is_active,
            "rules_in_version": len(rules),
            "candidates_published": len(approved),
            "aggregate_limits": len(aggregate_limits),
        },
    )

    await session.commit()

    # Section 9.11 step 6: publishing a new version must re-run every active
    # PolicyTest for this policy set against it. Additive and best-effort —
    # the publish itself is already committed above, so a problem re-running
    # tests must never turn an otherwise-successful publish into a failed
    # request; it's logged and surfaced only through the tests' own run
    # history / Findings view instead.
    try:
        await run_active_tests_for_version(
            session,
            policy_set_id=policy_set.id,
            policy_version_id=version.id,
            run_trigger="on_publish",
            triggered_by=body.approved_by,
        )
        await session.commit()
    except Exception as exc:  # noqa: BLE001 - publish already succeeded; never fail the request because of this
        logger.warning("on-publish PolicyTest re-run failed for policy set '%s': %s", key, exc)

    return ApprovedPolicyVersionResponse(
        id=str(version.id),
        policy_set_id=str(version.policy_set_id),
        version_number=version.version_number,
        effective_from=version.effective_from,
        effective_to=version.effective_to,
        is_active=version.is_active,
        approved_by=version.approved_by,
        approved_at=version.approved_at,
        rule_count=len(rules),
    )
