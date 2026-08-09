"""AI feature endpoints: Ask-AI chat, AI rule extraction, AI rewrite
suggestions, version compare, and quality evaluation.

All AI calls in this router go through `infrastructure/ai_*.py` service
modules, which in turn only use the thin httpx-based clients in
`infrastructure/ai/openai_client.py` and `infrastructure/search/search_client.py`
— never the raw Azure REST APIs directly, and never client-supplied
credentials. If Azure OpenAI isn't configured, these endpoints return 503
rather than silently no-op'ing, so the frontend can show a clear
"AI features unavailable" state instead of a confusing empty response.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from policy_platform.infrastructure import (
    ai_chat,
    ai_compare,
    ai_draft,
    ai_extraction,
    ai_quality,
    ai_rewrite,
    ai_scenario_eval,
    ai_scenario_engine,
    ai_summary,
    correlation_service,
    extraction_progress,
    rule_change_explainer,
)
from policy_platform.domain.models import (
    CandidateRule,
    CorrelationFindingRow,
    CorrelationRun,
    ExtractionRun,
    PolicySet,
)
from policy_platform.infrastructure.audit import FINDING_DISPOSED, record_audit_event
from policy_platform.infrastructure.db import get_session
from policy_platform.infrastructure.repositories import (
    PolicySetRepository,
    QualityRunRepository,
)
from policy_platform.infrastructure.settings import get_settings

router = APIRouter(prefix="/api/ai", tags=["ai"])


def _require_ai_configured() -> None:
    if not get_settings().ai_enabled:
        raise HTTPException(status_code=503, detail="Azure OpenAI is not configured on this server")


class ChatTurn(BaseModel):
    role: str
    content: str


class AskRequest(BaseModel):
    question: str
    policy_set_key: str | None = None
    history: list[ChatTurn] = []
    focus_candidate_rule_id: str | None = None


@router.get("/status")
async def ai_status() -> dict:
    settings = get_settings()
    return {
        "ai_enabled": settings.ai_enabled,
        "search_enabled": settings.search_enabled,
        "chat_deployment": settings.azure_openai_deployment if settings.ai_enabled else None,
        "fast_deployment": settings.azure_openai_fast_deployment if settings.ai_enabled else None,
    }


@router.post("/ask")
async def ask(body: AskRequest, session: AsyncSession = Depends(get_session)) -> dict:
    try:
        return await ai_chat.ask(
            session,
            question=body.question,
            policy_set_key=body.policy_set_key,
            history=[t.model_dump() for t in body.history],
            focus_candidate_rule_id=body.focus_candidate_rule_id,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


class ExtractRequest(BaseModel):
    """Optional body for AI extraction.

    `trusted_config` is the specification's Section 83 configuration
    (`fact_model`, `output_model`, `value_normalization`, …) — see
    `PolicyFormulatorAgent`'s own docstring for the full grounding. It is the
    *only* sanctioned source of technical detail not present in the source
    text. Until now there was no way to supply one through this endpoint at
    all (the router never threaded it through), so every extraction — past
    and future — was structurally forced into the empty-config path: honest
    but non-executable DMN projections, and (as a direct consequence) no
    `group_label` ever derived, since `_group_labels()` only fires when a DMN
    decision covers 2+ canonical policies, which itself requires enough
    trusted configuration for the agent to build that decision instead of
    returning `enrichment_required`. This body is entirely optional and
    defaults to today's behavior — omitting it changes nothing.
    """

    trusted_config: dict[str, Any] | None = None
    max_clauses: int | None = None
    """Cap on how many of the document's clauses (in document order) to
    extract this run, for a small-batch validation pass before committing to
    a full-document run. `None` (the default) processes every clause, as
    before this field existed."""


@router.post("/policy-sets/{key}/documents/{document_version_id}/extract")
async def extract_with_ai(
    key: str,
    document_version_id: uuid.UUID,
    body: ExtractRequest | None = None,
    session: AsyncSession = Depends(get_session),
) -> dict:
    _require_ai_configured()
    try:
        return await ai_extraction.extract_candidate_rules(
            session,
            policy_set_key=key,
            document_version_id=document_version_id,
            trusted_config=body.trusted_config if body else None,
            max_clauses=body.max_clauses if body else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/candidate-rules/{candidate_id}/explain-change")
async def explain_candidate_change(
    candidate_id: uuid.UUID,
    narrative: bool = True,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """What changed between this candidate and the rule it continues.

    Answers the question the `Changed` badge creates. The field-level diff is
    computed from the two persisted payloads and is exact; the narrative is an
    optional plain-English reading of that diff and is omitted rather than
    guessed if the model is unavailable. Pass `narrative=false` to skip the
    model call entirely.

    A candidate with no predecessor is a normal state, not an error, so this
    returns `comparable: false` with an explanation instead of a 404.
    """
    try:
        return await rule_change_explainer.explain_candidate_change(
            session, candidate_id=candidate_id, use_ai_narrative=narrative
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/documents/{document_version_id}/extraction-progress")
async def extraction_progress_status(document_version_id: uuid.UUID) -> dict:
    """Live counters for an in-flight (or just-finished) extraction.

    Deliberately keyed on the document version rather than the run id: the
    client cannot learn a run id until the extract POST returns, which is after
    the run it wanted to watch has already ended.

    Returns `{"active": false}` when nothing is tracked — a poll for a document
    that was never extracted, or whose progress record has since been pruned, is
    a normal state and not an error.
    """
    record = extraction_progress.get(str(document_version_id))
    if record is None:
        return {"active": False}
    return {"active": True, **record}


@router.get("/documents/{document_version_id}/extraction-runs")
async def list_extraction_runs(
    document_version_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> list[dict]:
    """Every extraction attempt against a document version, newest first.

    A reviewer looking at 363 candidates needs to know which run produced them
    and what re-running would do. Counts are derived from `candidate_rules`
    rather than stored on the run, so they stay true as rules are reviewed —
    a stored count would drift the moment somebody approved something.
    """
    runs = (
        await session.execute(
            select(ExtractionRun)
            .where(ExtractionRun.document_version_id == document_version_id)
            .order_by(desc(ExtractionRun.started_at))
        )
    ).scalars().all()
    if not runs:
        return []

    counts = dict(
        (
            await session.execute(
                select(CandidateRule.extraction_run_id, func.count())
                .where(CandidateRule.extraction_run_id.in_([r.id for r in runs]))
                .group_by(CandidateRule.extraction_run_id)
            )
        ).all()
    )
    reviewed = dict(
        (
            await session.execute(
                select(CandidateRule.extraction_run_id, func.count())
                .where(
                    CandidateRule.extraction_run_id.in_([r.id for r in runs]),
                    CandidateRule.review_status != "candidate",
                )
                .group_by(CandidateRule.extraction_run_id)
            )
        ).all()
    )

    return [
        {
            "id": str(run.id),
            "reference": run.reference,
            "status": run.status,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
            "error_message": run.error_message,
            "prompt_version": run.prompt_version,
            "deployment_name": run.deployment_name,
            "rules_total": counts.get(run.id, 0),
            "rules_reviewed": reviewed.get(run.id, 0),
            # The newest run that produced anything is the one whose rules are
            # actually in the queue; older runs' unreviewed rules were cleared.
            "is_current": run.id == next((r.id for r in runs if counts.get(r.id, 0) > 0), None),
        }
        for run in runs
    ]


class RewriteRequest(BaseModel):
    instruction: str


@router.post("/candidate-rules/{candidate_id}/rewrite")
async def rewrite_candidate(
    candidate_id: uuid.UUID, body: RewriteRequest, session: AsyncSession = Depends(get_session)
) -> dict:
    _require_ai_configured()
    try:
        return await ai_rewrite.suggest_rewrite(session, candidate_id=candidate_id, instruction=body.instruction)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


class ApplyRewriteRequest(BaseModel):
    suggested_payload: dict


@router.post("/candidate-rules/{candidate_id}/rewrite/apply")
async def apply_rewrite(
    candidate_id: uuid.UUID, body: ApplyRewriteRequest, session: AsyncSession = Depends(get_session)
) -> dict:
    try:
        return await ai_rewrite.apply_rewrite(
            session, candidate_id=candidate_id, suggested_payload=body.suggested_payload
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


class RewritePreviewRequest(BaseModel):
    rule: dict
    instruction: str


@router.post("/rules/rewrite-preview")
async def rewrite_preview(body: RewritePreviewRequest) -> dict:
    """Same AI rewrite as `/candidate-rules/{id}/rewrite`, but for a rule that
    has no `CandidateRule` row yet — used by the "Revise this rule" form,
    which pre-fills from a *published* rule and only creates the candidate
    once the user submits."""
    _require_ai_configured()
    try:
        return await ai_rewrite.suggest_rewrite_for_payload(body.rule, instruction=body.instruction)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


class DraftFromTextRequest(BaseModel):
    """Authored policy text to formulate into draft rules."""

    text: str
    trusted_config: dict[str, Any] | None = None


@router.post("/policy-sets/{key}/rules/draft-from-text")
async def draft_from_text(
    key: str, body: DraftFromTextRequest, session: AsyncSession = Depends(get_session)
) -> dict:
    """Turn a policy statement a human typed into draft `CanonicalRule`s.

    The document-extraction counterpart of this endpoint reads clauses out of
    an ingested file; this one takes the author's own words. Both hand the text
    to the same policy formulator agent and the same deterministic mapper, so a
    rule drafted here is structurally identical to one extracted from a
    document — it simply cites no clause, because none exists.

    Returns unsaved drafts plus a `trace` of what the pipeline did. Nothing is
    persisted: the caller reviews and edits the result, then submits it through
    `POST /api/policy-sets/{key}/candidate-rules` like any other draft, which
    keeps a single, human-operated door into the review queue.
    """

    _require_ai_configured()
    try:
        return await ai_draft.draft_rules_from_text(
            session,
            policy_set_key=key,
            text=body.text,
            trusted_config=body.trusted_config,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


class EvaluateScenarioRequest(BaseModel):
    rule: dict
    scenario: str
    reasoning_effort: str = "medium"


@router.post("/rules/evaluate-scenario")
async def evaluate_scenario(body: EvaluateScenarioRequest) -> dict:
    """Advisory-only AI reasoning about how a rule (possibly still being
    edited, not yet saved) would apply to a natural-language scenario. This
    never touches the deterministic evaluator — see ai_scenario_eval's module
    docstring for why that distinction matters."""
    _require_ai_configured()
    try:
        return await ai_scenario_eval.evaluate_scenario(
            body.rule, scenario=body.scenario, reasoning_effort=body.reasoning_effort
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


class RuleScenarioTestRequest(BaseModel):
    scenario: str
    reasoning_effort: str = "medium"


@router.post("/policy-sets/{key}/rules/{rule_id}/test-scenario")
async def test_rule_scenario(
    key: str, rule_id: str, body: RuleScenarioTestRequest, session: AsyncSession = Depends(get_session)
) -> dict:
    """The REAL, deterministic-engine-backed counterpart to
    /rules/evaluate-scenario: AI only translates the scenario into facts and
    explains the result — the actual verdict always comes from
    evaluator.engine.evaluate_policy against this rule's active approved
    version. See ai_scenario_engine's module docstring for why this is a
    distinct tool from the advisory-only one above."""
    try:
        return await ai_scenario_engine.run_rule_scenario(
            session,
            policy_set_key=key,
            rule_id=rule_id,
            scenario=body.scenario,
            reasoning_effort=body.reasoning_effort,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/policy-sets/{key}/compare")
async def compare_versions(
    key: str,
    version_a: int,
    version_b: int,
    narrative: bool = True,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """`narrative=false` skips the AI plain-English summary and returns only the
    deterministic added/removed/changed diff — used by the Policies tab's
    per-rule "version history" panel, which only needs one rule's own
    changed_fields and shouldn't pay for a whole-policy-set AI narrative every
    time a reviewer opens a rule's History tab. The full Compare page keeps
    its default (narrative=true) unchanged.
    """
    try:
        return await ai_compare.compare_versions(
            session,
            policy_set_key=key,
            version_a=version_a,
            version_b=version_b,
            use_ai_narrative=narrative and get_settings().ai_enabled,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/policy-sets/{key}/quality")
async def quality_report(key: str, session: AsyncSession = Depends(get_session)) -> dict:
    try:
        return await ai_quality.evaluate_policy_set_quality(
            session, policy_set_key=key, use_ai_review=get_settings().ai_enabled
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/policy-sets/{key}/quality/history")
async def quality_history(
    key: str,
    scope: str | None = None,
    limit: int = 50,
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """Past quality evaluations for this policy set, newest first.

    Returns summary rows only (counts, not the full findings blob) so the
    history list stays cheap to render; fetch one run's detail via
    `/quality/history/{run_id}`.
    """
    policy_set = await PolicySetRepository(session).get_by_key(key)
    if policy_set is None:
        raise HTTPException(status_code=404, detail=f"policy set '{key}' not found")
    runs = await QualityRunRepository(session).list_by_policy_set(
        policy_set.id, scope=scope, limit=limit
    )
    return [
        {
            "id": str(r.id),
            "scope": r.scope,
            "version_number": r.version_number,
            "rule_count": r.rule_count,
            "high_count": r.high_count,
            "medium_count": r.medium_count,
            "low_count": r.low_count,
            "finding_count": r.high_count + r.medium_count + r.low_count,
            "ai_review_used": r.ai_review_used,
            "methodology_version": r.methodology_version,
            "triggered_by": r.triggered_by,
            "run_at": r.run_at.isoformat(),
        }
        for r in runs
    ]


@router.get("/policy-sets/{key}/quality/history/{run_id}")
async def quality_history_detail(
    key: str, run_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> dict:
    """One past quality run, including its full stored findings."""
    policy_set = await PolicySetRepository(session).get_by_key(key)
    if policy_set is None:
        raise HTTPException(status_code=404, detail=f"policy set '{key}' not found")
    run = await QualityRunRepository(session).get_by_id(run_id)
    if run is None or run.policy_set_id != policy_set.id:
        raise HTTPException(status_code=404, detail=f"quality run '{run_id}' not found")
    return {
        "id": str(run.id),
        "policy_set_key": key,
        "scope": run.scope,
        "version_number": run.version_number,
        "rule_count": run.rule_count,
        "findings": run.findings_json,
        "ai_review_used": run.ai_review_used,
        "methodology_version": run.methodology_version,
        "triggered_by": run.triggered_by,
        "run_at": run.run_at.isoformat(),
    }


@router.get("/policy-sets/{key}/summary")
async def policy_set_summary(
    key: str,
    version_number: int | None = None,
    narrative: bool = True,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Whole-policy-set rollup: deterministic rule-count/scope/override/
    obligation breakdown, plus (when AI is enabled and `narrative=true`) a
    plain-English AI summary of what the policy set as a whole governs.
    `version_number` omitted uses the currently active published version.
    Like `/compare` and `/quality`, this never hard-fails when AI is
    unavailable — the deterministic `stats` block always has value on its own.
    """
    try:
        return await ai_summary.summarize_policy_set(
            session,
            policy_set_key=key,
            version_number=version_number,
            use_ai_narrative=narrative and get_settings().ai_enabled,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/policy-sets/{key}/candidates/quality")
async def candidate_quality_report(key: str, session: AsyncSession = Depends(get_session)) -> dict:
    """Quality report on unpublished (candidate/approved) rules — lets a reviewer
    see structural + AI-flagged issues in freshly AI-extracted rules *before*
    deciding whether to approve/publish them (see ai_quality.evaluate_candidate_quality).
    """
    try:
        return await ai_quality.evaluate_candidate_quality(
            session, policy_set_key=key, use_ai_review=get_settings().ai_enabled
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Correlation: relationships *between* rules
#
# Quality review asks "is this rule well-formed?" one rule at a time. That
# question cannot detect a contradiction, because both rules in a contradictory
# pair are usually well-formed on their own — the defect exists only in the
# relationship. These endpoints cover that blind spot.
# ---------------------------------------------------------------------------


class CorrelationRequest(BaseModel):
    #: Non-actionable classifications (`COMPATIBLE`, `INDEPENDENT`, …) are
    #: evidence the pair was examined, but storing thousands of them buries the
    #: findings that need a decision.
    actionable_only: bool = True
    #: Cap on model calls, for a cheap first pass over a large policy set.
    max_groups: int | None = None


def _finding_row(row: CorrelationFindingRow) -> dict:
    payload = row.payload_json or {}
    return {
        "id": str(row.id),
        "run_id": str(row.run_id),
        "classification": row.classification,
        "analysis_status": row.analysis_status,
        "severity": row.severity,
        "rule_ids": row.rule_ids or [],
        "reason": row.reason,
        "evidence": payload.get("evidence", []),
        "overlap": payload.get("overlap"),
        "requirements": payload.get("requirements", []),
        "disposition": row.disposition,
        "disposition_by": row.disposition_by,
        "disposition_at": row.disposition_at.isoformat() if row.disposition_at else None,
        "disposition_notes": row.disposition_notes,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@router.post("/policy-sets/{key}/correlate")
async def run_correlation(
    key: str,
    body: CorrelationRequest | None = None,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Analyse a policy set for contradictions, overlaps, duplicates and gaps."""
    _require_ai_configured()
    request = body or CorrelationRequest()
    try:
        return await correlation_service.run_correlation_analysis(
            session,
            policy_set_key=key,
            actionable_only=request.actionable_only,
            max_groups=request.max_groups,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/policy-sets/{key}/correlate/runs")
async def correlation_runs(
    key: str, limit: int = 20, session: AsyncSession = Depends(get_session)
) -> list[dict]:
    """Past correlation runs, newest first."""
    policy_set = await PolicySetRepository(session).get_by_key(key)
    if policy_set is None:
        raise HTTPException(status_code=404, detail=f"policy set '{key}' not found")
    result = await session.execute(
        select(CorrelationRun)
        .where(CorrelationRun.policy_set_id == policy_set.id)
        .order_by(desc(CorrelationRun.created_at))
        .limit(limit)
    )
    return [
        {
            "id": str(r.id),
            "status": r.status,
            "rules_analyzed": r.rules_analyzed,
            "groups_analyzed": r.groups_analyzed,
            "groups_available": r.groups_available,
            "rules_uncompared": r.rules_uncompared,
            "rules_budget_skipped": r.rules_budget_skipped,
            "prompt_version": r.prompt_version,
            "error_message": r.error_message,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
        }
        for r in result.scalars()
    ]


@router.get("/policy-sets/{key}/correlate/findings")
async def correlation_findings(
    key: str,
    run_id: uuid.UUID | None = None,
    disposition: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Findings from one correlation run, defaulting to the most recent.

    Defaults to the latest run rather than every run ever: a finding is only
    true of the rules as they stood when it was produced, so merging runs would
    show contradictions that have since been fixed alongside live ones with no
    way to tell them apart.

    "Latest" means the latest *completed* run. A run in progress is a partial
    result — it may have analysed sixty of seventeen hundred groups — and
    showing it as the current state of the policy set would read as "the
    contradictions were fixed" when in fact the analysis has not reached them
    yet. The previous complete answer stays on screen until a new one exists.
    An explicit `run_id` still returns whatever it names, including a run that
    is still going, so progress remains inspectable on request.
    """
    policy_set = await PolicySetRepository(session).get_by_key(key)
    if policy_set is None:
        raise HTTPException(status_code=404, detail=f"policy set '{key}' not found")

    if run_id is None:
        latest = await session.execute(
            select(CorrelationRun.id)
            .where(
                CorrelationRun.policy_set_id == policy_set.id,
                CorrelationRun.status == "completed",
            )
            .order_by(desc(CorrelationRun.created_at))
            .limit(1)
        )
        run_id = latest.scalar_one_or_none()
        if run_id is None:
            return {"run_id": None, "findings": [], "by_classification": {}, "by_severity": {}}

    query = select(CorrelationFindingRow).where(CorrelationFindingRow.run_id == run_id)
    if disposition:
        query = query.where(CorrelationFindingRow.disposition == disposition)
    result = await session.execute(query.order_by(CorrelationFindingRow.severity))
    rows = list(result.scalars())

    by_classification: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    for row in rows:
        by_classification[row.classification] = by_classification.get(row.classification, 0) + 1
        by_severity[row.severity] = by_severity.get(row.severity, 0) + 1

    return {
        "run_id": str(run_id),
        "findings": [_finding_row(r) for r in rows],
        "by_classification": by_classification,
        "by_severity": by_severity,
    }


class DispositionRequest(BaseModel):
    disposition: str
    #: Required: a disposition is an accountability record. Allowing it to
    #: default to empty lets a client silently file "someone decided this was
    #: not a real problem" with no author, which is exactly the claim an
    #: auditor needs to attribute.
    disposition_by: str = Field(min_length=1)
    notes: str = ""


#: What a reviewer can decide about a finding. `accepted` means the finding is
#: real and will be acted on; `dismissed` means it is not a real problem;
#: `resolved` means the underlying rules have been changed.
_DISPOSITIONS = {"open", "accepted", "dismissed", "resolved"}


@router.post("/correlate/findings/{finding_id}/disposition")
async def set_finding_disposition(
    finding_id: uuid.UUID,
    body: DispositionRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Record a reviewer's decision on a finding.

    Without this a finding is a question with nowhere to put the answer: every
    run re-surfaces the same contradiction, and reviewers learn to skim the list.
    """
    if body.disposition not in _DISPOSITIONS:
        raise HTTPException(
            status_code=422,
            detail=f"disposition must be one of {sorted(_DISPOSITIONS)}",
        )
    row = await session.get(CorrelationFindingRow, finding_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"finding '{finding_id}' not found")

    row.disposition = body.disposition
    row.disposition_by = body.disposition_by or None
    row.disposition_at = datetime.now(UTC)
    row.disposition_notes = body.notes or None
    # The audit table is keyed by entity, not by project, so every event has to
    # carry the policy set it belongs to or it cannot be shown alongside the
    # rest of that project's governance history.
    owning_set = await session.get(PolicySet, row.policy_set_id)
    record_audit_event(
        session,
        event_type=FINDING_DISPOSED,
        entity_type="correlation_finding",
        entity_id=row.id,
        actor=body.disposition_by,
        policy_set_key=owning_set.key if owning_set else None,
        details={
            "disposition": body.disposition,
            "classification": row.classification,
            "severity": row.severity,
            "rule_ids": list(row.rule_ids or []),
            "notes": body.notes or "",
        },
    )
    await session.commit()
    await session.refresh(row)
    return _finding_row(row)
