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
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from policy_platform.infrastructure.assistants import ai_chat
from policy_platform.infrastructure.assistants import ai_compare
from policy_platform.infrastructure.assistants import ai_draft
from policy_platform.infrastructure.assistants import policy_explainer
from policy_platform.infrastructure.extraction import ai_extraction
from policy_platform.infrastructure.quality import ai_quality
from policy_platform.infrastructure.assistants import ai_rewrite
from policy_platform.infrastructure.assistants import ai_case_intent
from policy_platform.infrastructure.assistants import ai_case_project
from policy_platform.infrastructure.assistants import ai_scenario_eval
from policy_platform.infrastructure.assistants import ai_scenario_engine
from policy_platform.infrastructure.assistants import ai_summary
from policy_platform.infrastructure.correlation import correlation_service
from policy_platform.infrastructure.extraction import extraction_progress
from policy_platform.infrastructure.extraction.formulation_mapping import (
    SKIP_BATCH_UNREAD,
    SKIP_DISCARDED,
    SKIP_NOT_EXTRACTED,
)
from policy_platform.infrastructure.assistants import rule_change_explainer
from policy_platform.infrastructure.assistants import provision_topic_label
from policy_platform.infrastructure.assistants import rule_namer
from policy_platform.infrastructure.assembly import rule_name_lookup
from policy_platform.infrastructure.projection.policy_case_payload import case_payload_for_provision
from policy_platform.domain.models import (
    CandidateRule,
    CorrelationFindingRow,
    CorrelationRun,
    ExtractionRun,
    PolicySet,
)
from policy_platform.infrastructure.persistence.audit import FINDING_DISPOSED, record_audit_event
from policy_platform.infrastructure.persistence.db import get_session
from policy_platform.infrastructure.persistence.repositories import (
    PolicySetRepository,
    QualityRunRepository,
)
from policy_platform.infrastructure.settings import get_settings

router = APIRouter(prefix="/api/ai", tags=["ai"])

#: Ceiling on any capped list this router serves, matching `audit.py` and
#: `evaluations.py` so the platform has one answer rather than three.
#:
#: The floor matters as much as the ceiling: `truncated` is derived from
#: `count == limit`, which is only a truthful signal while `limit` is at least
#: one. A request for zero rows would come back "truncated" holding nothing.
_MAX_LIST_LIMIT = 500


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
    focus_rule_ids: list[str] | None = None
    """The rules to ground on, by their own `AI-…` ids, in document order.

    Sent when the question is about a whole policy rather than one rule. Ids
    rather than a policy key because a policy is a grouping the client already
    holds and the server would otherwise have to re-derive — and because the
    order the client sends is the order the card shows, which is what makes a
    coverage statement about "the first N" point at something a reader can see.
    `ai_chat.ask` decides how many of them fit and reports how many it used."""
    answer_language: str | None = None
    """IETF BCP-47 tag for the language the reader wants *this app's own words*
    written in — the reflection and the topic headings over the quoted facts.

    Quoted source text is never affected by it: `ai_chat.ask` states that
    separately and `tests/unit/test_ask_answers_in_the_readers_language.py`
    holds it there. No language is named here or anywhere below it; the tag
    arrives from the caller, is checked for shape, and is passed on, so adding a
    language is a change to the interface's string table and to nothing on this
    side. `None` asks in no particular language and is exactly today's request."""
    policy_version_id: str | None = None
    """The published version `focus_rule_ids` name, when the reader is looking
    at one.

    Sent from the published surfaces, omitted from the review queue. A published
    rule and the draft row that produced it share a `rule_id`, so the ids alone
    do not say which of the two a reader is looking at; this does. Given, the
    records are read from that version and never from the drafts, and a version
    that does not resolve grounds nothing rather than falling back — see
    `ai_chat._policy_rule_payloads`."""


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
            focus_rule_ids=body.focus_rule_ids,
            answer_language=body.answer_language,
            policy_version_id=body.policy_version_id,
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


class TopicLabelRequest(BaseModel):
    """How many provisions to name, and whether to name them again."""

    #: A ceiling on one run, so a request cannot become an unbounded spend and a
    #: caller can name a handful first and look at them before naming the rest.
    limit: int = Field(default=25, ge=1, le=500)
    #: Re-name provisions that already carry a label. Off by default: running
    #: this twice should cost nothing the second time.
    regenerate: bool = False


@router.post("/policy-sets/{key}/topic-labels")
async def generate_topic_labels(
    key: str,
    body: TopicLabelRequest | None = None,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Name the subject each policy of this set is about.

    A card is titled by the heading the document wrote, and that stays its
    title. This produces a second, shorter string beside it — a few words naming
    the subject — because a heading written for somebody reading in order often
    names nothing to somebody scanning a queue.

    What comes back is ours and is stored as ours, in a table of its own with
    the model, the instruction and a digest of the words it was generated from.
    It is never written into the row holding the document's headings.

    Provisions that produced nothing usable are recorded as such rather than
    skipped silently, so the interface can say the label is unavailable instead
    of showing a card that looks un-generated forever.
    """

    policy_set = await PolicySetRepository(session).get_by_key(key)
    if policy_set is None:
        raise HTTPException(status_code=404, detail=f"policy set '{key}' not found")

    _require_ai_configured()
    try:
        result = await provision_topic_label.label_provisions(
            session,
            policy_set_id=policy_set.id,
            limit=body.limit if body else 25,
            regenerate=body.regenerate if body else False,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    await session.commit()
    return result


class RuleNameRequest(BaseModel):
    """How many policies' rules to name, and whether to name them again."""

    #: A ceiling on one run, counted in policies rather than rules. A policy is
    #: the unit that can be named: its rules are named together, because what
    #: tells one from another is only visible when they are seen side by side.
    limit: int = Field(default=25, ge=1, le=500)
    #: Name rules that already carry one. Off by default: running this twice
    #: should cost nothing the second time.
    regenerate: bool = False


class RuleNameLookupRequest(BaseModel):
    """The rules a page is drawing, so their handles can be fetched at once.

    Two ways of naming a rule, because two surfaces hold different records of
    it. The review queue holds draft rows and asks by their ids. A published
    version holds no draft row at all — the rule is the record — so it asks by
    the rule's own identifier instead. Both reach the same stored handle; only
    the way in differs.
    """

    #: Capped at the router's ceiling, so one request cannot ask for everything.
    candidate_ids: list[uuid.UUID] = Field(default_factory=list, max_length=_MAX_LIST_LIMIT)
    #: Canonical rule identifiers. Meaningful only within a policy set: a rule
    #: id is derived from where the rule was found in its document, so two
    #: documents can state the same one about entirely different rules.
    rule_ids: list[str] = Field(default_factory=list, max_length=_MAX_LIST_LIMIT)
    #: Which set the `rule_ids` belong to. Required with them, for the reason
    #: above — an unscoped lookup could hand back another document's handle,
    #: which is the one failure this feature must not have.
    policy_set_key: str | None = None


@router.post("/policy-sets/{key}/rule-names")
async def generate_rule_names(
    key: str,
    body: RuleNameRequest | None = None,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Write a short handle for each rule saying what that rule is for.

    A card lists the rules drawn from one passage. Several of them open with the
    same words, because they were decomposed from the same sentence, and the
    identifier beside each is a hash. This gives every rule a line or two naming
    what it is for, so a reviewer can land on the right one and then read it.

    What comes back is ours. It is stored in a table of its own, with the model,
    the instruction and a digest of the record it was written from, and it is
    never written into the rule's payload — which is exported and published, and
    must hold only what a document stated and an extraction produced.

    The model is shown the extracted records and never the document's sentences,
    for the reason the explainer sets out and one more besides: siblings share a
    sentence, so a name written from the sentence would be the same name for all
    of them.

    A POST because it spends model calls.
    """

    policy_set = await PolicySetRepository(session).get_by_key(key)
    if policy_set is None:
        raise HTTPException(status_code=404, detail=f"policy set '{key}' not found")

    _require_ai_configured()
    try:
        result = await rule_namer.name_rules(
            session,
            policy_set_id=policy_set.id,
            limit=body.limit if body else 25,
            regenerate=body.regenerate if body else False,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    await session.commit()
    return result


@router.post("/rule-names/lookup")
async def lookup_rule_names(
    body: RuleNameLookupRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Read stored handles for the rules a page is drawing.

    Reads only. It never generates, so drawing a queue cannot spend a model call
    — the same separation `topic_label_lookup` keeps, and for the same reason.

    A POST because the ids go in a body: a queue draws dozens of rules at once
    and a query string of that many identifiers is a URL length limit waiting to
    be found. Nothing is written.

    Rules with no stored handle are absent from the reply rather than present as
    a null, so "nobody has asked" stays distinguishable from "asked, and nothing
    usable came back".

    It is asked for by rule id and answers off to one side, deliberately. A
    handle is this app's commentary about a rule, so it is never served as part
    of one — that is what keeps it out of every export and every published
    version.

    A published version is asked about by canonical rule id, because it holds no
    draft row to ask about. That path is scoped to a policy set: a canonical id
    records where a rule was found in its document, so unscoped it could name a
    different rule in a different document. Asking with rule ids and no set is
    refused rather than answered from whatever matched first.

    The two doors answer in two maps rather than one. A draft row id and a
    canonical rule id are both strings, and a single map keyed on the bare value
    would let an answer to one question be read as the answer to the other — a
    handle rendered above a rule it was never written about, which is the one
    failure this feature must not have and the one nothing on screen reveals.
    """

    stored = await rule_name_lookup.names_for_rules(session, body.candidate_ids)
    names = {rule_id: name.as_payload() for rule_id, name in stored.items()}
    names_by_rule_id: dict[str, object] = {}

    if body.rule_ids:
        if not body.policy_set_key:
            raise HTTPException(
                status_code=422,
                detail="rule_ids must be asked for within a policy set",
            )
        policy_set = await PolicySetRepository(session).get_by_key(body.policy_set_key)
        if policy_set is None:
            raise HTTPException(
                status_code=404, detail=f"policy set '{body.policy_set_key}' not found"
            )
        by_rule_id = await rule_name_lookup.names_for_canonical_rules(
            session, policy_set_id=policy_set.id, rule_ids=body.rule_ids
        )
        names_by_rule_id = {rule_id: name.as_payload() for rule_id, name in by_rule_id.items()}

    return {"names": names, "names_by_rule_id": names_by_rule_id}


@router.post("/provisions/{provision_id}/explain")
async def explain_provision(
    provision_id: uuid.UUID,
    regenerate: bool = False,
    narrative: bool = True,
    answer_language: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Say in plain words what one policy's extracted record requires.

    Answers the question a reviewer faces on a card holding several rules: the
    record is complete but is a decomposition, and reassembling it into a
    sentence is work they should not have to do by hand.

    The deterministic half — every rule, the parts the extraction identified,
    and the document's own sentence for each — is always returned and is the
    substance. The explanation is an aid to reading it and is omitted rather
    than guessed when the model is unavailable, unconfigured or unwilling.

    The model is shown the extracted record and never the document's verbatim
    text. That is deliberate and is set out at length on the module: an
    explanation written from the source would reconcile the two and hide the
    extraction error the reviewer is here to find. What comes back describes
    what was extracted, which is the thing under review.

    `answer_language` is an optional BCP-47 tag for the language the reading
    should come back in; omitted, it is the heading's own. Only this app's
    reading takes it — the document's verbatim sentences are never sent to the
    model and are returned unchanged, so no quotation is translated. A value that
    is not a well-formed tag is treated as none rather than refused.

    A POST because it may spend a model call. It writes nothing.
    """

    try:
        return await policy_explainer.explain_provision(
            session,
            provision_id=provision_id,
            use_ai=narrative,
            regenerate=regenerate,
            answer_language=answer_language,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


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


def _run_coverage(run: ExtractionRun) -> dict | None:
    """What this run passed over, split by whether the document was read.

    Returns None when the run kept no record — every run predating the
    `skipped_json` column. That is not the same as a run that skipped nothing,
    and reporting zeroes for it would invent a coverage claim nobody made.
    """
    skipped = run.skipped_json
    if skipped is None:
        return None
    by_kind = Counter(s.get("kind") or SKIP_BATCH_UNREAD for s in skipped)
    unread = by_kind.get(SKIP_BATCH_UNREAD, 0)
    return {
        "complete": unread == 0,
        "batches_unread": unread,
        "passages_discarded": by_kind.get(SKIP_DISCARDED, 0),
        "read_not_extracted": by_kind.get(SKIP_NOT_EXTRACTED, 0),
        "skipped": skipped,
    }


@router.get("/documents/{document_version_id}/extraction-runs")
async def list_extraction_runs(
    document_version_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> list[dict]:
    """Every extraction attempt against a document version, newest first.

    A reviewer looking at 363 candidates needs to know which run produced them
    and what re-running would do. Counts are derived from `candidate_rules`
    rather than stored on the run, so they stay true as rules are reviewed —
    a stored count would drift the moment somebody approved something.

    `coverage` is here because this list is the only place a reviewer is told
    how much of the document a run accounts for, and until now it said only how
    much came out. A run reports `rules_total: 411` whether it read every page
    or lost three, and material it declined to extract left no trace at all. The
    two are separated: `batches_unread` is document the run never read;
    `read_not_extracted` is sentences it read and judged to carry no rule. Only
    the first is a coverage gap, but the second is where recall goes quietly,
    so `skipped` carries the entries themselves rather than just a count.
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
            "coverage": _run_coverage(run),
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
    # Which published version to compute against. Omitted means the active one,
    # which is the only behaviour this endpoint used to have. An administrator
    # asking whether a superseded version still behaves the way the current one
    # does is asking about a specific version, and a test that silently retargets
    # the active one answers a different question while looking like a success.
    policy_version_id: str | None = None


class ComputeScenarioRequest(BaseModel):
    rule: dict
    scenario: str
    reasoning_effort: str = "medium"


@router.post("/rules/compute-scenario")
async def compute_scenario(body: ComputeScenarioRequest) -> dict:
    """The deterministic engine, run against a rule the caller hands over.

    The computed counterpart to /rules/evaluate-scenario above, and deliberately
    the same shape. A reviewer deciding whether to approve a draft is asking
    about that draft: it belongs to no published version, and on a set that has
    never been published there is no version to ask about at all. Routing them to
    the version-scoped endpoint below answers a question about a different rule,
    or raises.

    The verdict comes from `evaluator.engine.evaluate_policy`, unmodified, so this
    is not an advisory reading — it is the same engine with the same guarantees,
    applied to one rule rather than to an assembled version. Nothing is persisted.
    """
    try:
        return await ai_scenario_engine.compute_rule_scenario(
            body.rule, scenario=body.scenario, reasoning_effort=body.reasoning_effort
        )
    except ValueError as exc:
        # A rule payload this app cannot read is the caller's to fix. pydantic's
        # ValidationError is a ValueError, so one clause covers both a malformed
        # rule and a rejected reasoning effort.
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


class PolicyCaseAnswerRequest(BaseModel):
    provision_id: str
    scenario: str
    reasoning_effort: str = "medium"


@router.post("/policy-case/answer")
async def answer_policy_case(
    body: PolicyCaseAnswerRequest, session: AsyncSession = Depends(get_session)
) -> dict:
    """Classify what a case put to a whole policy *is*, and — when it asks what
    the policy provides rather than for a determination — gather the answer the
    policy already holds and state it, citing the rules it read.

    The input is a `provision_id`, not a bag of client-supplied rules. The
    provision is projected server-side into the lean `grounding_projection_v1`
    payload (`case_payload_for_provision`) — the same record the JSON tab renders
    — and that closed payload is the only thing the gather may draw on, so the
    model is tested against a record a reviewer can see and cannot be handed rules
    no projection ever vouched for. An unknown provision is a 404.

    Like /rules/compute-scenario and /rules/evaluate-scenario, this belongs to no
    published version: a reviewer asking a policy a question is asking the record
    in front of them, drafts included, and a set that has never published still
    has rules that state things. So no version is named or needed.

    This never runs a determination. When the case is a determination, the reply
    carries only the classification and the caller runs the per-rule deciders it
    already has — the same single routing rule and policy scope share — so this
    endpoint cannot become a second, drifting decider. See ai_case_intent's
    module docstring for why the intent is read from the question alone.

    WHY THIS IS IN THE OPENAPI SURFACE

    It carries no `include_in_schema=False`. An earlier draft of this endpoint hid
    it from the schema on the theory that a product-only seam need not appear in
    the human `docs/api.md` reference. That was wrong: the coverage guard in
    `test_capped_lists_are_wrapped` (`test_the_scan_reaches_every_route_the_application_serves`)
    asserts that every route the app *serves* also appears in `app.openapi()`,
    precisely so a route cannot slip past the schema-walking scans by being hidden.
    A route absent from the schema is a route no schema-level guard can see — the
    exact narrowing that guard exists to catch — so this endpoint stays visible.
    The one consequence is that `docs/api.md`'s hand-maintained surface totals now
    undercount by this operation until its owner reconciles them; that file is out
    of scope for this change, so the reconciliation is reported rather than made
    here.
    """
    _require_ai_configured()
    try:
        payload = await case_payload_for_provision(session, body.provision_id)
    except ValueError as exc:
        # A `provision_id` that is not a well-formed identifier, or a stored rule
        # that no longer validates, is the caller's malformed input (422) — the
        # same clause the client-rules shape used, now surfaced from the projection.
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if payload is None:
        raise HTTPException(status_code=404, detail="No provision with that id")
    try:
        return await ai_case_intent.answer_policy_case(
            payload, scenario=body.scenario, reasoning_effort=body.reasoning_effort
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


class ProjectCaseAnswerRequest(BaseModel):
    scenario: str
    #: When set, the reviewer has chosen one policy and retrieval is bypassed
    #: entirely — that provision is answered directly. When omitted, the case is
    #: put to the project and the policies bearing on the question are retrieved
    #: and the rest discarded before anything is evaluated.
    provision_id: str | None = None
    reasoning_effort: str = "medium"


@router.post("/policy-sets/{key}/case-answer")
async def answer_project_case(
    key: str, body: ProjectCaseAnswerRequest, session: AsyncSession = Depends(get_session)
) -> dict:
    """Put a case to a *project's* policies: retrieve the ones that bear on the
    question, discard the rest, and evaluate only the survivors — never the set.

    The project counterpart of /policy-case/answer. That endpoint answers one
    policy a reviewer already chose; this one answers a question the reviewer has
    *not* narrowed, and the narrowing is the feature: "u never run against all
    published, u must use AI search and any technique possible to retrieve highest
    policies match before evaluation, non matching policies are discarded." So this
    never evaluates against every policy. It embeds the question and runs the same
    hybrid clause retrieval the Ask-AI chat uses (`ai_chat.ask`), scoped to this
    project's own documents, maps the retrieved clauses back to the policies that
    own them by the join the index and the projection already share, and keeps only
    those. Reusing that one retrieval path rather than standing up a second is
    deliberate — a second copy drifts.

    WHAT RETRIEVAL DID IS REPORTED, NOT HIDDEN

    The response's `retrieval` block and `considered` list name every candidate
    policy, which were retained, which discarded, and on what basis, so a reviewer
    can always see how much narrowing happened (constraint 10). Retrieval's outcome
    is one of six distinct `status` values, none of which ever degrades to
    "evaluate against all" (constraint 5):

      - `narrowed`     — a subset was kept and evaluated; `evaluation` is present.
      - `no_match`     — retrieval ran and the project is indexed, but nothing it
                         surfaced bears; `evaluation` is null. A real answer.
      - `index_empty`  — the project's policies are not in the grounding index, so
                         retrieval cannot be relied on for it; `evaluation` null.
      - `unavailable`  — search is not configured on this server; `evaluation` null.
      - `failed`       — the search call raised; `evaluation` null.
      - `empty`        — the project has no policy with live rules to test.

    When `provision_id` is set the reviewer chose one policy: retrieval is bypassed
    (`status: bypassed`, `scope: single`) and that policy is answered directly.

    REQUEST

        { "scenario": str,                 # required, the reviewer's question
          "provision_id": str | null,      # optional; set = one policy, omit = project
          "reasoning_effort": str }        # optional, default "medium"

    RESPONSE (project scope)

        { "scope": "project",
          "policy_set_key": str,
          "retrieval": { "status": str, "method": str, "clause_budget": int,
                         "clause_scan": int, "clauses_retrieved": int,
                         "policies_considered": int, "policies_retained": int,
                         "policies_discarded": int, "policies_untestable": int,
                         "reason": str? },
          "considered": [ { "provision_id": str, "provision_key": str,
                            "heading_path": [str], "rules": int, "retained": bool,
                            "best_score": float?, "best_rank": int?,
                            "matched_clauses": int?, "discard_reason": str? } ],
          "excluded":   [ { "provision_id": str, "provision_key": str,
                            "heading_path": [str], "reason": "no_live_rules" } ],
          "evaluation": <case result> | null,
          "size": { "combined_chars": int, "budget_chars": int, "oversize": bool } }

    RESPONSE (single scope)

        { "scope": "single", "policy_set_key": str,
          "provision": { "provision_id", "provision_key", "heading_path", "rules" },
          "retrieval": { "status": "bypassed", "reason": str },
          "evaluation": <case result>,
          "size": { ... } }

    The `evaluation` object is the multi-policy case result: `intent`
    (informational | decision), `classification_reasoning`, and — informational
    only — `informational` with `status`, `answer`, `citations` (each carrying its
    `rule_id`, verbatim `source`, and the `policy` it was drawn from), and a
    `grounding` block reporting `rules_available`, `rules_cited`,
    `fabricated_citations`, `policies_grounded`, and `oversize`. For a
    determination `informational` is null and the caller runs the per-rule
    deciders it already has, one policy's rule at a time.

    An unknown project key is 404, as is a `provision_id` that names a policy in a
    different project; a malformed id is 422; an unconfigured model is 503.
    """
    policy_set = await PolicySetRepository(session).get_by_key(key)
    if policy_set is None:
        raise HTTPException(status_code=404, detail=f"policy set '{key}' not found")

    _require_ai_configured()
    try:
        return await ai_case_project.answer_project_case(
            session,
            policy_set=policy_set,
            scenario=body.scenario,
            provision_id=body.provision_id,
            reasoning_effort=body.reasoning_effort,
        )
    except LookupError as exc:
        # A named provision that is unknown or belongs to another project — the
        # reviewer pointed at a policy this project does not hold. A 404, told
        # apart from a malformed id (422) below.
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/policy-sets/{key}/rules/{rule_id}/test-scenario")
async def test_rule_scenario(
    key: str, rule_id: str, body: RuleScenarioTestRequest, session: AsyncSession = Depends(get_session)
) -> dict:
    """The REAL, deterministic-engine-backed counterpart to
    /rules/evaluate-scenario: AI only translates the scenario into facts and
    explains the result — the actual verdict always comes from
    evaluator.engine.evaluate_policy against a published version of this rule.
    Which version is `body.policy_version_id`, or the active one when that is
    omitted. See ai_scenario_engine's module docstring for why the target is the
    caller's to name, and /rules/compute-scenario for the unversioned draft."""
    try:
        return await ai_scenario_engine.run_rule_scenario(
            session,
            policy_set_key=key,
            rule_id=rule_id,
            scenario=body.scenario,
            reasoning_effort=body.reasoning_effort,
            policy_version_id=body.policy_version_id,
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
    """The most recent recorded quality evaluation of the published version.

    Reads only. This used to run a full AI evaluation and append a history row,
    which meant simply opening the page cost minutes of model time and wrote a
    new entry into the very sequence the page asks a reviewer to read as a
    trend. Producing a new evaluation is now `POST .../quality/runs`.

    When nothing has ever been evaluated, the response says so explicitly
    (`evaluated: false`, `findings: null`) rather than returning an empty
    findings list that would read as a clean bill of health.
    """
    try:
        return await ai_quality.latest_quality_report(
            session, policy_set_key=key, scope="published"
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/policy-sets/{key}/quality/runs")
async def run_quality_evaluation(key: str, session: AsyncSession = Depends(get_session)) -> dict:
    """Evaluate the published version now and record the result.

    Expensive (a full AI review over every rule) and non-idempotent (it appends
    to the evaluation history), which is why it is a POST: a run has to be
    something a reviewer asked for. It changes no rule, no approval and no
    published version -- the only thing it writes is the record of having
    looked.
    """
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
    limit: int = Query(default=50, ge=1, le=_MAX_LIST_LIMIT),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Past quality evaluations for this policy set, newest first.

    Returns summary rows only (counts, not the full findings blob) so the
    history list stays cheap to render; fetch one run's detail via
    `/quality/history/{run_id}`.

    Capped, and says so. This list used to be a bare array, which gave a caller
    no way to tell "these are all the evaluations" from "these are the newest
    fifty of them" -- and the page built on it exists specifically to show a
    trend over time, which is the reading a hidden older half distorts.
    """
    policy_set = await PolicySetRepository(session).get_by_key(key)
    if policy_set is None:
        raise HTTPException(status_code=404, detail=f"policy set '{key}' not found")
    runs = await QualityRunRepository(session).list_by_policy_set(
        policy_set.id, scope=scope, limit=limit
    )
    return {
        "runs": [
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
        ],
        "count": len(runs),
        # Same "is there more" heuristic as audit.py and evaluations.py: a full
        # page is the signal, rather than a second COUNT(*) over a table that
        # only ever grows.
        "truncated": len(runs) == limit,
    }


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
        # A stored run carries which route-specific checks did not apply to its
        # records (or NULL if the run predates that being recorded). Serve it so
        # the page reading a stored run can say so, rather than showing only
        # findings and letting their absence read as a clean result the run
        # never established. Passed through as stored: NULL, [], and a populated
        # list are three different answers and stay three different answers.
        "not_applicable": run.not_applicable_json,
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
    """The most recent recorded quality evaluation of unpublished rules.

    Reads only, for the same reason as the published-scope endpoint above.
    Producing a new evaluation is `POST .../candidates/quality/runs`.
    """
    try:
        return await ai_quality.latest_quality_report(
            session, policy_set_key=key, scope="candidates"
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/policy-sets/{key}/candidates/quality/runs")
async def run_candidate_quality_evaluation(
    key: str, session: AsyncSession = Depends(get_session)
) -> dict:
    """Evaluate unpublished (candidate/approved) rules now and record the result.

    Lets a reviewer see structural + AI-flagged issues in freshly AI-extracted
    rules *before* deciding whether to approve/publish them (see
    ai_quality.evaluate_candidate_quality). Approves and rejects nothing.
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
    key: str,
    limit: int = Query(default=20, ge=1, le=_MAX_LIST_LIMIT),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Past correlation runs, newest first.

    Capped, and says so -- see `quality_history`. This list feeds a run picker,
    where silence about the cap is worse than usual: an option that is absent
    from a dropdown does not look withheld, it looks non-existent.
    """
    policy_set = await PolicySetRepository(session).get_by_key(key)
    if policy_set is None:
        raise HTTPException(status_code=404, detail=f"policy set '{key}' not found")
    result = await session.execute(
        select(CorrelationRun)
        .where(CorrelationRun.policy_set_id == policy_set.id)
        .order_by(desc(CorrelationRun.created_at))
        .limit(limit)
    )
    rows = list(result.scalars())
    return {
        "runs": [
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
            for r in rows
        ],
        "count": len(rows),
        "truncated": len(rows) == limit,
    }


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
