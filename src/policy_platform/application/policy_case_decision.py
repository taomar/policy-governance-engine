"""One decider, two callers, and only one of them writes a receipt.

WHAT THIS MODULE IS FOR

`ai_case_project.answer_project_case` is the project-case decider. Two very
different callers need it:

  * the in-product reviewer surface (`POST /api/ai/policy-sets/{key}/case-answer`),
    which has answered reviewers for as long as it has existed, persists nothing,
    and must keep behaving exactly as it does; and
  * the external decision API (`POST /api/policy-decisions/{project_key}/case`),
    which answers a machine and therefore owes it a receipt: an identity, a
    caller, the exact version that decided, and an integrity seal.

Wiring the second one straight into the decider would have made every reviewer
click an audited external call. Wiring it into a copy of the decider would have
produced two deciders that agree until one is edited. So both go through here,
and **this module is the only place that calls the decider** — a static test
asserts exactly one call site, so a third one cannot appear without someone
choosing it.

THE ORDER THAT MAKES A RECEIPT TRUE

A case takes on the order of ten seconds of model time. That single fact decides
the whole shape of `decide_project_case`:

1. **Reserve, and commit.** A `pending` row is written and committed *before* the
   model is called. If the process dies mid-call, the evidence that the call was
   made survives. If the reservation cannot be written, no model call is made and
   the caller gets a non-2xx — an unrecorded decision must never be returned as
   though it had been recorded.
2. **Decide, holding no transaction.** The model call runs with nothing open.
3. **Finalise, in a short transaction.** `completed` with the full envelope and
   its hash, or `failed` with a reason and no outcome at all.

If step 3 fails, the caller is told so — `decision_receipt_failed`, carrying only
the decision and correlation ids — and is *not* given the verdict. There is no
"here is your answer, but we could not save it" response, because a verdict that
cannot be cited later is precisely the thing this endpoint exists to stop
shipping.

IDEMPOTENCY IS BOUND TO A CALLER AND A BODY

An `Idempotency-Key` is optional. When supplied it is unique on
(project, authenticated principal, key), and the canonical hash of the request is
stored beside it:

  * same key, same request, completed → the original receipt is replayed, hash
    and all. The model is not called twice.
  * same key, different request → `409`. Answering it would silently hand back a
    receipt for a question the caller did not ask this time.
  * same key, still pending → `409`. The first call is in flight; a second model
    run is exactly what the key exists to prevent.
  * same key, failed → `409`, naming the failed decision. A key is spent; a retry
    is a new key.
  * no key → every call is a new decision. Deduplicating by scenario alone would
    be wrong: asking the same question twice is a thing people legitimately do,
    and the second answer is a second decision.

The race is handled where it happens: a concurrent duplicate reservation raises
`IntegrityError`, which is rolled back, re-selected, and then falls into exactly
the four cases above.

CALLER GUIDANCE IS INPUT, NOT INSTRUCTION

`additional_instructions` lets a caller say how they want the explanation
presented. It is handled here rather than at the route because every one of its
safeguards is a use-case concern: it is normalised (so a byte-for-byte retry
from a text area still matches), length-bounded before anything is reserved,
bound into the idempotency request hash (so reusing a key with changed guidance
is a `409` rather than a silently substituted answer), written into the
reservation's metadata with its digest, echoed on the receipt and sealed by
`decision_hash`.

What it is *not* allowed to do is enforced further down, in two places that are
deliberately not this one. `ai_case_project` admits it to the evaluation gathers
and to nothing else — never the retrieval query, so it cannot steer which
policies are read; never the classifier, so it cannot choose which tracks run.
`ai_case_intent.caller_guidance_block` wraps it in the invariants it may not
cross and marks it lowest priority. This module's job is to make sure the exact
text that was applied is the exact text that is recorded.

THE LANGUAGE BOUNDARY IS CROSSED HERE, AND EXACTLY TWICE

Everything downstream of this module reasons in one language. That is not a
property those modules assert; it is a property this one establishes, by
crossing the boundary in both directions around them:

1. **In, before anything reads the corpus.** The question is reduced to the
   processing language by one unconditional bounded call, and the *rendered*
   text is what reaches retrieval, rule slicing, the classifier and both
   gathers. The original never goes downstream on any path, including a failing
   one — a fallback to it would put a language the prompts were not written for
   into adjudication, which is the whole of what the boundary prevents. So a
   crossing that cannot be made closes the reservation as failed and answers
   `503`, and no verdict is produced.
2. **Out, after every semantic result is frozen.** A closed whitelist of prose
   strings — and nothing else — is rendered back to the language the question
   arrived in. Statuses, booleans, selector keys, rule ids, policy identities,
   counters, hashes and every verbatim source sentence are never handed to that
   step, so they cannot move because a reader asked for another language.

What the caller sent is untouched by both. `request.scenario`,
`request.scenario_hash`, `request.additional_instructions` and the idempotency
request hash are all over the caller's own bytes; a rendering never enters them,
because a rendering that varied would otherwise make a caller's byte-for-byte
retry look like a different request. What was *adjudicated* is recorded beside
them, in the receipt's `language` block, and sealed.

WHAT IS WRITTEN, AND WHAT CAN STILL BE READ

Every new receipt is `case_decision_v2`: two independent tracks, each with its
own status, citations and grounding. Nothing writes v1 any more.

Rows written under v1 are still replayed as v1 — by `GET` and by an idempotency
replay alike. That is not politeness towards old clients; it is the point of
having written a receipt. Re-projecting a stored v1 decision into v2 would
require inventing the two booleans nobody classified for it, and a receipt whose
content changed after the fact is not evidence of anything. So the stored
`schema_version` decides which envelope a row is read as, and the two form a
discriminated union rather than one shape with optional halves.
"""
from __future__ import annotations

import copy
import json
import logging
import time
import uuid
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from policy_platform.contracts.case_decision import (
    CHANNEL_API,
    HASH_BASIS_V2,
    HASH_BASIS_V2_LANG,
    HASH_BASIS_V2_LANG_WITH_VERIFICATION,
    HASH_BASIS_V2_WITH_VERIFICATION,
    MAX_ADDITIONAL_INSTRUCTIONS_CHARS,
    NOT_EVALUATED,
    NOT_REQUESTED,
    ROUTE_DECISION,
    ROUTE_INFORMATIONAL,
    SCHEMA_VERSION_V2,
    SERVES_INFORMATION,
    SERVES_VERDICT,
    STATUS_WITH_VERDICT,
    AskedRef,
    CallerRef,
    CaseDecisionEnvelope,
    CaseDecisionEnvelopeV2,
    CitationRef,
    CitationSourceRef,
    InformationSection,
    LanguageRef,
    MergedCitationRef,
    MissingInformationItem,
    OutcomeRef,
    PolicyRef,
    PolicySetRef,
    RequestRef,
    RetrievalRef,
    RuleSelectionRef,
    SizeRef,
    TraceRef,
    TokenUsageRef,
    VerdictSection,
    VerificationRequirementItem,
    VersionRef,
    additional_instructions_hash,
    compute_decision_hash_v2,
    normalise_additional_instructions,
    request_hash,
    scenario_hash,
    validate_receipt,
)
from policy_platform.contracts.policy_retrieval import (
    PolicyRetrievalEnvelope,
    PolicyRetrievalQueryRef,
)
from policy_platform.contracts.case_decision_light import (
    CaseDecisionLightEnvelope,
    LightAskedRef,
    LightCitationRef,
    LightInformationRef,
    LightOutcomeRef,
    LightPolicyRef,
    LightRequestRef,
    LightRetrievalRef,
    LightTraceRef,
    LightVerdictRef,
)
from policy_platform.domain.models import DocumentProvision, PolicyCaseDecision
from policy_platform.infrastructure.assistants import (
    ai_case_intent,
    ai_case_language,
    ai_case_project,
)
from policy_platform.infrastructure.persistence.repositories.case_decisions import (
    PolicyCaseDecisionRepository,
)
from policy_platform.infrastructure.ai.usage_metering import (
    UsageScope,
    collect_token_usage,
)
from policy_platform.infrastructure.settings import get_settings

logger = logging.getLogger(__name__)

#: Where a receipt is read back. Relative on purpose: production reaches this API
#: through the web tier's `/api` proxy, so an absolute URL built here would name
#: a host the caller never used.
RECEIPT_PATH = "/api/policy-decisions/{decision_id}"

#: Where a policy's full lean record is served. The receipt links here instead of
#: inlining the record — see `contracts/case_decision.py` for why.
POLICY_PAYLOAD_PATH = "/api/policy-payload/{provision_id}"

#: The gather statuses a receipt may carry, mirroring the contract's closed
#: sets. Anything a gather produced that is not in here is recorded as `failed`
#: rather than passed through, because an unrecognised status is not an answer.
#: The two tracks are named apart because their vocabularies genuinely differ:
#: only a verdict can be blocked on missing facts or left unsettled by the rules.
_KNOWN_INFORMATION_STATUSES = frozenset(
    {"answered", "no_rule_bears", "declined", "failed"}
)
_KNOWN_VERDICT_STATUSES = frozenset(
    {
        "answered",
        "missing_required_facts",
        "not_settled_by_rules",
        "no_rule_bears",
        "declined",
        "failed",
    }
)


# ── the closed set of prose the reader's language may reach ──────────
#
# WHY A WHITELIST AND NOT AN INSTRUCTION
#
# The output rendering step is handed these strings and nothing else. It never
# sees a status, a boolean, a selector key, a rule id, a policy identity, a
# counter, a hash or a citation's verbatim source sentence — so it cannot alter
# one. That is the difference between an invariant and a hope: a model told
# "answer in this language" will helpfully translate the quotations too, and
# every safeguard against that which lives in a prompt is one bad sample away
# from not holding.
#
# The identifiers are opaque handles. They are what the renderer is keyed on,
# they carry no meaning it could act on, and they are validated back as an exact
# set — a key that was not sent is discarded and a key that did not return is a
# failure, so a partially rendered answer is never assembled.

#: The classifier's prose account of how it read the question.
PROSE_CLASSIFICATION_REASONING = "classification.reasoning"

#: The information track's own words.
PROSE_INFORMATION_ANSWER = "information.answer"
PROSE_INFORMATION_NOTE = "information.note"

#: The verdict track's own words. `verdict.decision` is the short verdict
#: *string* — prose, and language-dependent by design. `verdict.status` is the
#: machine field a client must key on, and it is not in this set.
PROSE_VERDICT_DECISION = "verdict.decision"
PROSE_VERDICT_EXPLANATION = "verdict.explanation"
PROSE_VERDICT_NOTE = "verdict.note"

#: One missing fact's human-facing halves. `fact` — the selector key a follow-up
#: form is built on — is deliberately absent: it is an identifier, not a
#: sentence, and translating it would change what a caller keys on.
PROSE_MISSING_LABEL = "missing_information.{index}.label"
PROSE_MISSING_WHY_NEEDED = "missing_information.{index}.why_needed"

#: One verification requirement's human-facing halves. `fact` is absent for the
#: same reason it is absent above: it is the selector key a caller confirms
#: against, not a sentence. These are rendered alongside the missing facts so a
#: reader who is owed their language is owed it for the conditions on acting too.
PROSE_VERIFICATION_LABEL = "verification_requirements.{index}.label"
PROSE_VERIFICATION_WHY_NEEDED = "verification_requirements.{index}.why_needed"


def _prose_slots(evaluation: dict) -> Iterator[tuple[str, dict, str]]:
    """Every place in one evaluation that holds prose a reader is owed.

    Yields `(field_id, container, key)` so the collection pass and the write-back
    pass are the *same* traversal rather than two that have to be kept in step.
    A field that could be collected and not written back — or written back and
    never collected — would be a silent half-rendering, which is precisely the
    outcome the whole step is arranged to make impossible.

    The shape it walks is the decider's own: an evaluation carries up to two
    branches, and both the two-track receipt and the older single-branch one are
    projected from those same two dicts. So covering the branches covers every
    envelope this platform serves.
    """

    if isinstance(evaluation.get("classification_reasoning"), str):
        yield (PROSE_CLASSIFICATION_REASONING, evaluation, "classification_reasoning")

    informational = evaluation.get("informational")
    if isinstance(informational, dict):
        yield (PROSE_INFORMATION_ANSWER, informational, "answer")
        yield (PROSE_INFORMATION_NOTE, informational, "note")

    decision = evaluation.get("decision")
    if isinstance(decision, dict):
        yield (PROSE_VERDICT_DECISION, decision, "verdict")
        yield (PROSE_VERDICT_EXPLANATION, decision, "answer")
        yield (PROSE_VERDICT_NOTE, decision, "note")
        for index, item in enumerate(decision.get("missing_information") or []):
            if not isinstance(item, dict):
                continue
            yield (PROSE_MISSING_LABEL.format(index=index), item, "label")
            yield (PROSE_MISSING_WHY_NEEDED.format(index=index), item, "why_needed")
        for index, item in enumerate(decision.get("verification_requirements") or []):
            if not isinstance(item, dict):
                continue
            yield (PROSE_VERIFICATION_LABEL.format(index=index), item, "label")
            yield (PROSE_VERIFICATION_WHY_NEEDED.format(index=index), item, "why_needed")


def prose_for_rendering(evaluation: dict | None) -> dict[str, str]:
    """The whitelisted prose of one evaluation, keyed by field identifier.

    Empty and whitespace-only values are left out: there is nothing to render,
    and asking for one back would turn "the gather said nothing here" into a
    rendering failure.
    """

    if not isinstance(evaluation, dict):
        return {}
    fields: dict[str, str] = {}
    for field_id, container, key in _prose_slots(evaluation):
        value = container.get(key)
        if isinstance(value, str) and value.strip():
            fields[field_id] = value
    return fields


def _with_rendered_prose(response: dict, rendered: Mapping[str, str]) -> dict:
    """A copy of the decider's answer with the rendered prose put back in place.

    A copy, because the original English is what was reasoned and stays
    available to the caller of this function. Only the evaluation subtree is
    copied deeply — nothing else in the response is touched, so every citation,
    counter, identity and disclosure in it is the same object it was.
    """

    evaluation = response.get("evaluation")
    if not isinstance(evaluation, dict) or not rendered:
        return response

    translated = copy.deepcopy(evaluation)
    for field_id, container, key in _prose_slots(translated):
        if field_id in rendered:
            container[key] = rendered[field_id]
    return {**response, "evaluation": translated}


# ── the boundary, crossed once and used by both paths ────────────────
#
# WHY THE ORCHESTRATION LIVES HERE AND NOT AT EITHER ROUTE
#
# The same reason the decider call does. Two callers need the boundary — the
# audited external contract and the in-product reviewer surface — and a boundary
# implemented twice is a boundary that holds until one copy is edited. So the
# crossing is written once, beside the single decider call site it wraps, and
# both entry points below go through it.
#
# What differs between the two callers is *what a failure costs*, not what the
# crossing does: the audited path has a reservation to close and answers with a
# failed receipt, the reviewer path has none and lets the error reach its route.
# So these helpers raise, and each caller decides what raising means. Neither is
# allowed to fall back to the original text, which is the one behaviour that
# would make the boundary decorative.


@dataclass(frozen=True, slots=True)
class LanguageCrossing:
    """What the inbound crossing produced, and what the outbound one will need.

    `scenario` and `guidance` are the only texts that go downstream. The
    observed source language rides along because the answer has to be rendered
    back towards it, and because the receipt has to say what was observed.
    """

    normalised: ai_case_language.NormalisedScenario
    guidance: str
    guidance_state: str

    @property
    def scenario(self) -> str:
        """The question as every stage below this line will read it."""

        return self.normalised.english


async def cross_into_processing_language(scenario: str, guidance: str) -> LanguageCrossing:
    """Carry one question, and any guidance, into the language the pipeline reasons in.

    Unconditional for the question: there is no detection step and no branch, so
    a question already in the processing language makes the same call and comes
    back as itself. Raises `LanguageBoundaryError` when that crossing cannot be
    made — a caller must refuse rather than pass the original on.

    Guidance crosses in its own call, which carries no question and no policy
    record. It is re-normalised and re-measured afterwards because the ceiling
    belongs to the text that is actually sent, and a rendering that grew past it
    is dropped rather than truncated. A guidance crossing never raises: losing a
    presentation preference is a smaller harm than losing the answer.
    """

    normalised = await ai_case_language.normalise_scenario(scenario)

    rendered = await ai_case_language.normalise_guidance(
        guidance, source_language=normalised.source_language
    )
    text = rendered.text
    state = rendered.state
    if state == ai_case_language.GUIDANCE_RENDERED:
        text = normalise_additional_instructions(text)
        if not text or len(text) > MAX_ADDITIONAL_INSTRUCTIONS_CHARS:
            logger.warning(
                "caller guidance did not survive its own bounds after crossing the boundary "
                "and was dropped"
            )
            text = ""
            state = ai_case_language.GUIDANCE_DROPPED

    return LanguageCrossing(normalised=normalised, guidance=text, guidance_state=state)


async def cross_out_to_the_reader(
    response: dict, crossing: LanguageCrossing, *, projection_profile: str | None = None
) -> tuple[dict, LanguageRef]:
    """Render the whitelisted prose back, and report what both crossings did.

    Called only once every semantic result is frozen — which policies were read,
    which tracks ran, both statuses, every citation and every counter. Only the
    prose moves, and only the prose is ever handed to the rendering step.

    Three outcomes, and none of them is a partial answer:

      * there is no reader-language prose to produce — either the question
        arrived in the processing language, or the evaluation composed no prose
        at all — so the renderer is not called and nothing claims it was;
      * no usable target tag was observed, so the prose is returned as it was
        reasoned and the metadata says exactly that; or
      * the prose is rendered, whole, or the crossing raises.

    WHY AN EMPTY WHITELIST IS `not_required` AND NOT `rendered`

    An evaluation can legitimately carry no prose: retrieval produced nothing to
    answer from, no retained rule bore on the question, or a track failed. There
    is then nothing for the reader's language to apply to. Reporting `rendered`
    with a translation profile beside it would claim a rendering that never
    happened, and would set `response_language` to a language no string in the
    receipt is written in — which is the one thing this block exists to state
    truthfully.

    So the whitelist is collected *first* and the renderer is called only when
    it is non-empty. `not_required` covers both ways a rendering can be
    unnecessary; the two are told apart by `source_language`, which is the
    processing language in the first case and something else in the second.

    Returns the response to serve and the language metadata that describes it.
    The metadata is the same shape on both paths — one is sealed into a receipt
    and one is not, but a reader of either must be able to tell which text was
    adjudicated.
    """

    output_state = ai_case_language.OUTPUT_NOT_REQUIRED
    output_profile: str | None = None
    response_language = ai_case_language.PROCESSING_LANGUAGE
    normalised = crossing.normalised

    if not normalised.is_processing_language:
        # Collected before anything is decided about the crossing: whether there
        # is prose at all is the first question, and a renderer called with an
        # empty payload would be a call made to produce nothing.
        fields = prose_for_rendering(response.get("evaluation"))
        if not fields:
            # `output_state` stays `not_required`, the profile stays null, and
            # the response language stays the processing one — because no string
            # in this answer is written in any other.
            pass
        elif not normalised.target_known:
            # The crossing succeeded and the tag did not. Adjudication is
            # unaffected — it happened in the processing language either way —
            # so the answer stands and the prose is returned as it was reasoned,
            # with the metadata saying why.
            output_state = ai_case_language.OUTPUT_TARGET_UNKNOWN
        else:
            rendered = await ai_case_language.render_prose(
                fields, target_language=normalised.source_language
            )
            response = _with_rendered_prose(response, rendered)
            output_state = ai_case_language.OUTPUT_RENDERED
            output_profile = ai_case_language.TRANSLATION_PROFILE
            response_language = normalised.source_language

    language = LanguageRef(
        source_language=normalised.source_language,
        processing_language=ai_case_language.PROCESSING_LANGUAGE,
        response_language=response_language,
        boundary_state=normalised.boundary_state,
        output_rendering_state=output_state,
        guidance_rendering_state=crossing.guidance_state,
        input_translation_profile=normalised.translation_profile,
        output_translation_profile=output_profile,
        processing_scenario=crossing.scenario,
        processing_scenario_hash=scenario_hash(crossing.scenario),
        processing_additional_instructions=crossing.guidance,
        # The contract the *corpus* was rendered under, taken from the retrieval
        # that actually ran rather than from the constant this process was built
        # with. Those are different facts: the constant says which projection
        # this build expects, and only the retrieval knows which one it matched
        # against — or that it never consulted an index at all, which is what a
        # null here means on the single-policy scope.
        projection_profile=projection_profile,
    )
    return response, language


# ── the caller, as this layer sees them ──────────────────────────────


@dataclass(frozen=True, slots=True)
class Caller:
    """Who the receipt will name.

    `identity`, `role` and `authentication_source` come from the resolved
    principal — what the server proved. `calling_system_identity` is what the
    caller said about itself and is carried as a label, never as evidence.
    """

    identity: str
    role: str
    authentication_source: str
    calling_system_identity: str | None = None
    channel: str = CHANNEL_API


@dataclass(frozen=True, slots=True)
class CaseDecisionOutcome:
    """A finalised receipt and whether it was decided now or replayed.

    `envelope` is a v2 receipt for anything decided now, and may be either
    version on a replay: an idempotency key issued before the two-track redesign
    still names the row it named, and that row is answered as what it was
    written as rather than re-projected into a shape it never had.
    """

    envelope: CaseDecisionEnvelopeV2 | CaseDecisionEnvelope
    replayed: bool


class CaseDecisionError(Exception):
    """A decision that cannot be answered with a verdict, and why.

    Carries the HTTP status the route should use and, where one exists, the
    decision and correlation ids — so even a refusal is traceable to the row it
    is about. The route turns this into a structured body; it does not invent
    statuses of its own.
    """

    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        message: str,
        decision_id: str | None = None,
        correlation_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.decision_id = decision_id
        self.correlation_id = correlation_id

    def as_detail(self) -> dict[str, Any]:
        detail: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.decision_id is not None:
            detail["decision_id"] = self.decision_id
        if self.correlation_id is not None:
            detail["correlation_id"] = self.correlation_id
        return detail


# ── the one call into the decider ────────────────────────────────────


async def _invoke_decider(
    session: AsyncSession,
    *,
    policy_set,
    scenario: str,
    provision_id: str | None,
    reasoning_effort: str,
    additional_instructions: str,
    with_context: bool,
):
    """The single place in this codebase that calls the project-case decider.

    Both public entry points below funnel through here, so "one decider" is a
    property of the source rather than a convention. A guard test counts the
    call sites of `ai_case_project.answer_project_case` and fails when there is
    more than this one, which is what stops a future route from reaching past
    the receipt machinery and answering without one.

    `additional_instructions` is passed explicitly by both callers rather than
    defaulted here — the reviewer path passes `""` on purpose, so the fact that
    the legacy route carries no caller guidance is written down at its call site
    instead of resting on a default that could later change.

    `scenario` is likewise passed explicitly, and what each caller passes is the
    whole of the language contract: the audited path passes the **rendered**
    question, because everything below this line reasons in one language and a
    receipt must be able to prove which text was read. The reviewer path passes
    the reviewer's own text — see `answer_project_case` for why that difference
    is deliberate and what it costs.
    """

    return await ai_case_project.answer_project_case(
        session,
        policy_set=policy_set,
        scenario=scenario,
        provision_id=provision_id,
        reasoning_effort=reasoning_effort,
        additional_instructions=additional_instructions,
        with_context=with_context,
    )


# ── the unrecorded path (the legacy reviewer route) ──────────────────


async def answer_project_case(
    session: AsyncSession,
    *,
    policy_set,
    scenario: str,
    provision_id: str | None = None,
    reasoning_effort: str = "medium",
) -> dict:
    """The decider's answer, unchanged and unrecorded.

    This is what `POST /api/ai/policy-sets/{key}/case-answer` serves. It returns
    the decider's dict byte-for-byte and writes nothing, which is the behaviour
    that route has always had and the behaviour its existing consumer depends
    on. Its only reason to exist is that the route must not reach the decider
    directly — see this module's docstring.

    It takes no `additional_instructions` parameter and passes empty guidance.
    Caller guidance belongs to the external contract, where it is normalised,
    length-bounded, bound into the idempotency hash, sealed and shown on a
    receipt. None of that machinery exists on this route, and a guidance field
    without it would be an unlogged, unbounded influence on an answer nobody can
    reconstruct afterwards.

    IT CROSSES THE SAME LANGUAGE BOUNDARY, THROUGH THE SAME HELPERS

    Every question this platform answers is reduced to one processing language
    before any policy is read, and this route is not an exception — a reviewer's
    question put in one language to prompts written in another is the same
    cross-lingual reading the boundary exists to remove, receipt or no receipt.
    So the same two helpers run here, and the decider is handed the rendered
    question exactly as it is on the audited path.

    What differs is only what a failure costs. There is no reservation to close,
    so a crossing that cannot be made raises `LanguageBoundaryError` and the
    route answers `503` with the code that names which half failed. It still
    never falls back to the original text: a reviewer would have no way to see
    that their question had been read in a language the prompts were not written
    for, which is precisely the silent failure the boundary removes.

    A project whose index carries no retrieval projection raises
    `IndexProjectionUnavailable` from the decider and is answered `503` the same
    way, for the same reason: matching a rendered question against an unrendered
    corpus produces a confident "nothing bears on your question", and a reviewer
    is owed the difference between that and "nothing could be compared".

    The return is the decider's dict plus one additive `language` block, so a
    reviewer surface can show which text was actually adjudicated. Nothing else
    about the shape moves.
    """

    crossing = await cross_into_processing_language(scenario, "")

    response = await _invoke_decider(
        session,
        policy_set=policy_set,
        scenario=crossing.scenario,
        provision_id=provision_id,
        reasoning_effort=reasoning_effort,
        additional_instructions=crossing.guidance,
        with_context=False,
    )

    response, language = await cross_out_to_the_reader(
        response, crossing, projection_profile=_projection_profile(response)
    )
    return {**response, "language": language.model_dump(mode="json")}


async def _retrieve_project_policies(
    session: AsyncSession,
    *,
    policy_set,
    scenario: str,
    correlation_id: str,
    usage_scope: UsageScope,
    started: float,
) -> PolicyRetrievalEnvelope:
    """Return the filtered records the decision path would read, and stop there.

    This is intentionally outside the receipt lifecycle: no decision is made, so
    there is no decision identity, idempotency key, verdict, or receipt to store.
    The language boundary and approved corpus are identical to the reasoned path.
    The policy cut is precision-first rather than recall-first because this path
    has no grounded gather that can reject an over-kept record.
    """

    settings = get_settings()
    if not settings.ai_enabled:
        raise CaseDecisionError(
            status_code=503,
            code="ai_unavailable",
            message="Azure OpenAI is not configured on this server.",
            correlation_id=correlation_id,
        )
    if len(scenario) > ai_case_language.MAX_SCENARIO_CHARS:
        raise CaseDecisionError(
            status_code=422,
            code="scenario_too_long",
            message=(
                f"scenario is {len(scenario)} characters; the maximum is "
                f"{ai_case_language.MAX_SCENARIO_CHARS}."
            ),
            correlation_id=correlation_id,
        )

    # The stage map this route reports is assembled here rather than read off a
    # single object, because the two halves are measured on opposite sides of
    # the retrieval call: the inbound language crossing happens before there is
    # a context to write into, and the retrieval stages are written into the
    # context by the shared scope helper. Both are wall-clock durations of work
    # this request actually did, so they belong in one map.
    stage_latency_ms: dict[str, int] = {}

    try:
        language_in_started = time.perf_counter()
        try:
            crossing = await cross_into_processing_language(scenario, "")
        finally:
            stage_latency_ms["language_in"] = max(
                0, int((time.perf_counter() - language_in_started) * 1000)
            )
        selected = await ai_case_project.retrieve_project_policies(
            session,
            policy_set=policy_set,
            scenario=crossing.scenario,
            with_context=True,
        )
    except ai_case_language.LanguageBoundaryError as exc:
        raise CaseDecisionError(
            status_code=503,
            code=exc.code,
            message=(
                "The question could not be carried into the language this platform retrieves in, "
                "so no policy was selected."
            ),
            correlation_id=correlation_id,
        ) from exc
    except ai_case_project.IndexProjectionUnavailable as exc:
        raise CaseDecisionError(
            status_code=503,
            code=exc.code,
            message=str(exc),
            correlation_id=correlation_id,
        ) from exc
    except RuntimeError as exc:
        raise CaseDecisionError(
            status_code=503,
            code="ai_unavailable",
            message=str(exc),
            correlation_id=correlation_id,
        ) from exc

    response = selected.response
    # The retrieval stages were already being measured by the shared scope
    # helper and then discarded at this boundary. They are the same keys, with
    # the same meanings, as the ones the decision route reports; this route
    # simply reports fewer of them, because it runs less.
    stage_latency_ms.update(selected.context.get("timings_ms") or {})

    language_out_started = time.perf_counter()
    _, language = await cross_out_to_the_reader(
        response,
        crossing,
        projection_profile=_projection_profile(response),
    )
    # Measured, and normally near zero: this route composes no prose, so the
    # boundary helper resolves the reader's language without calling a model.
    # A key reading 0 here is a real sub-millisecond duration, not a skipped
    # stage — the stage that did not run is the one that is absent.
    stage_latency_ms["language_out"] = max(
        0, int((time.perf_counter() - language_out_started) * 1000)
    )
    project = PolicySetRef(
        id=str(policy_set.id),
        key=policy_set.key,
        name=getattr(policy_set, "name", "") or "",
    )
    return PolicyRetrievalEnvelope(
        correlation_id=correlation_id,
        policy_set=project,
        active_version=_version_ref(selected.context),
        query=PolicyRetrievalQueryRef(
            scenario=scenario,
            scenario_hash=scenario_hash(scenario),
        ),
        retrieval=RetrievalRef(**_retrieval_fields(response.get("retrieval") or {})),
        policies=response.get("policies") or [],
        size=SizeRef(**(response.get("size") or {})),
        language=language,
        token_usage=_token_usage_ref(usage_scope),
        latency_ms=max(0, int((time.perf_counter() - started) * 1000)),
        stage_latency_ms=stage_latency_ms or None,
    )


async def retrieve_project_policies(
    session: AsyncSession,
    *,
    policy_set,
    scenario: str,
    correlation_id: str,
) -> PolicyRetrievalEnvelope:
    """Return filtered policy records with observed duration and model usage."""

    started = time.perf_counter()
    with collect_token_usage() as usage_scope:
        return await _retrieve_project_policies(
            session,
            policy_set=policy_set,
            scenario=scenario,
            correlation_id=correlation_id,
            usage_scope=usage_scope,
            started=started,
        )


def compact_decision_receipt(
    envelope: CaseDecisionEnvelopeV2 | CaseDecisionEnvelope,
) -> CaseDecisionLightEnvelope:
    """Project a full stored receipt into the fixed light response contract."""

    if isinstance(envelope, CaseDecisionEnvelopeV2):
        if envelope.asked.information_requested and envelope.asked.verdict_requested:
            response_type = "mixed"
        elif envelope.asked.verdict_requested:
            response_type = "decision"
        elif envelope.asked.information_requested:
            response_type = "informational"
        else:
            response_type = "not_evaluated"

        information = (
            LightInformationRef(
                status=envelope.information.status,
                answer=envelope.information.answer,
                explanation=envelope.information.explanation,
                note=envelope.information.note,
            )
            if envelope.information is not None
            else None
        )
        verdict = (
            LightVerdictRef(
                status=envelope.verdict.status,
                reached=envelope.verdict.reached,
                decision=envelope.verdict.decision,
                explanation=envelope.verdict.explanation,
                missing_information=envelope.verdict.missing_information,
                verification_requirements=envelope.verdict.verification_requirements,
                note=envelope.verdict.note,
            )
            if envelope.verdict is not None
            else None
        )
        citations = [
            LightCitationRef(
                rule_id=citation.rule_id,
                policy=_light_policy(citation.policy),
                source=citation.source,
                serves=list(citation.serves),
            )
            for citation in envelope.citations
        ]
        grounding = (
            (envelope.verdict.grounding if envelope.verdict else None)
            or (envelope.information.grounding if envelope.information else None)
            or {}
        )
        asked = LightAskedRef(
            information_requested=envelope.asked.information_requested,
            verdict_requested=envelope.asked.verdict_requested,
            classifier_version=envelope.asked.classifier_version,
        )
        outcome = LightOutcomeRef(
            information=envelope.outcome.information,
            verdict=envelope.outcome.verdict,
        )
    else:
        route = envelope.decision.decider_route or envelope.decision.intent or ROUTE_DECISION
        status = envelope.decision_status
        informational = route == ROUTE_INFORMATIONAL
        response_type = (
            "not_evaluated"
            if status == NOT_EVALUATED
            else "informational"
            if informational
            else "decision"
        )
        information_status = (
            status
            if informational and status in {"answered", "no_rule_bears", "declined", "failed"}
            else NOT_EVALUATED
            if status == NOT_EVALUATED
            else NOT_REQUESTED
        )
        verdict_status = (
            NOT_REQUESTED
            if informational
            else NOT_EVALUATED
            if status == NOT_EVALUATED
            else status
        )
        information = (
            LightInformationRef(
                status=status,
                answer=envelope.decision.explanation if status == STATUS_WITH_VERDICT else "",
                explanation=(
                    None
                    if status == STATUS_WITH_VERDICT
                    else envelope.decision.explanation or None
                ),
                note=envelope.decision.note,
            )
            if informational and status != NOT_EVALUATED
            else None
        )
        verdict = (
            LightVerdictRef(
                status=status,
                reached=status == STATUS_WITH_VERDICT and bool(envelope.decision.verdict),
                decision=envelope.decision.verdict,
                explanation=envelope.decision.explanation,
                missing_information=[
                    MissingInformationItem(fact=fact, label=fact)
                    for fact in envelope.decision.missing_required_facts
                ],
                note=envelope.decision.note,
            )
            if not informational and status != NOT_EVALUATED
            else None
        )
        serves = ["information"] if informational else ["verdict"]
        citations = [
            LightCitationRef(
                rule_id=citation.rule_id,
                policy=_light_policy(citation.policy),
                source=citation.source,
                serves=serves,
            )
            for citation in envelope.citations
        ]
        grounding = {}
        asked = LightAskedRef(
            information_requested=informational and status != NOT_EVALUATED,
            verdict_requested=not informational and status != NOT_EVALUATED,
            classifier_version=None,
        )
        outcome = LightOutcomeRef(
            information=information_status,
            verdict=verdict_status,
        )

    policies: list[LightPolicyRef] = []
    seen_policies: set[tuple[str | None, str | None]] = set()
    for citation in citations:
        if citation.policy is None:
            continue
        identity = (citation.policy.provision_id, citation.policy.provision_key)
        if identity in seen_policies:
            continue
        seen_policies.add(identity)
        policies.append(citation.policy)

    return CaseDecisionLightEnvelope(
        response_type=response_type,
        decision_id=envelope.decision_id,
        correlation_id=envelope.correlation_id,
        idempotency_key=envelope.idempotency_key,
        policy_set=envelope.policy_set,
        active_version=envelope.active_version,
        request=LightRequestRef(
            scenario=envelope.request.scenario,
            scenario_hash=envelope.request.scenario_hash,
        ),
        asked=asked,
        outcome=outcome,
        information=information,
        verdict=verdict,
        retrieval=LightRetrievalRef(
            status=envelope.retrieval.status,
            method=envelope.retrieval.method,
            policies_retained=envelope.retrieval.policies_retained,
            rule_rescued_policies=envelope.retrieval.rule_rescued_policies,
            reason=envelope.retrieval.reason,
        ),
        policies=policies,
        citations=citations,
        trace=LightTraceRef(
            classifier_version=asked.classifier_version,
            prompt_version=envelope.trace.prompt_version,
            plan_profile=grounding.get("plan_profile"),
            selector_catalogue_version=grounding.get("selector_catalogue_version"),
            model_deployment=envelope.trace.model_deployment,
            stage_latency_ms=envelope.trace.stage_latency_ms,
            token_usage=envelope.trace.token_usage,
        ),
        decision_hash=envelope.decision_hash,
        hash_basis=envelope.hash_basis,
        receipt_url=envelope.receipt_url,
        latency_ms=envelope.latency_ms,
    )


def _light_policy(policy: PolicyRef | None) -> LightPolicyRef | None:
    if policy is None:
        return None
    return LightPolicyRef(
        provision_id=policy.provision_id,
        provision_key=policy.provision_key,
        heading_path=list(policy.heading_path),
    )


def _projection_profile(response: dict) -> str | None:
    """The corpus projection the retrieval that actually ran matched against.

    Read from the decider's own retrieval block rather than from the constant
    this process was built with, because those are two different claims: the
    constant says which projection this build *expects*, and only the retrieval
    knows which one it *used* — or that it consulted no index at all, which is
    what the single-policy scope reports and what a null here means.

    Sealed into the decision hash by way of the language block, so a stored
    receipt cannot be relabelled with a projection it was not produced under.
    """

    retrieval = response.get("retrieval")
    if not isinstance(retrieval, dict):
        return None
    profile = retrieval.get("projection_profile")
    return str(profile) if profile else None


# ── the audited path ─────────────────────────────────────────────────


async def _decide_project_case(
    session: AsyncSession,
    *,
    policy_set,
    scenario: str,
    provision_id: str | None,
    reasoning_effort: str,
    correlation_id: str,
    idempotency_key: str | None,
    caller: Caller,
    additional_instructions: str = "",
    request_metadata: dict | None = None,
    usage_scope: UsageScope,
) -> CaseDecisionOutcome:
    """Decide a project case and answer with a persisted receipt.

    `policy_set` is the resolved project — the route has already turned the
    public key into a row and answered 404 if it named nothing.

    `additional_instructions` is optional caller guidance about how the
    explanation should be presented. It is normalised and length-checked here,
    *before* anything is reserved, so an over-long block costs no row and no
    model call. It is then bound into the idempotency request hash, recorded in
    the reservation's metadata with its digest, echoed on the receipt and sealed
    — and passed to the decider, which admits it only to the gather.

    THE ORDER THE BOUNDARY IMPOSES

    The question is carried into the processing language *after* the reservation
    and *before* the decider, and that order is not arbitrary. After the
    reservation, because the crossing is a model call and a call that fails must
    close a receipt rather than vanish. Before the decider, because the whole
    point is that nothing downstream ever sees the original. An idempotency
    replay happens earlier still and therefore crosses nothing: a caller
    retrying an answered request gets their stored receipt back without a second
    rendering, let alone a second decision.

    Raises `CaseDecisionError` for every outcome that is not a receipt: a
    question or guidance that is too long, an idempotency conflict, a
    reservation that could not be written, a boundary crossing that could not be
    made, a decider refusal (unknown policy, malformed id, model unavailable),
    and a finalisation that failed. It never returns a verdict that was not
    stored, and never returns one composed from a question it could not read.
    """

    settings = get_settings()
    if not settings.ai_enabled:
        # Checked before anything is reserved. A row written for a call that can
        # never run is not evidence of a decision, it is litter.
        raise CaseDecisionError(
            status_code=503,
            code="ai_unavailable",
            message="Azure OpenAI is not configured on this server.",
            correlation_id=correlation_id,
        )

    # Bounded here, with the guidance, and for the same reason: a question the
    # boundary could never carry is a permanent client fault, and discovering it
    # after the reservation would advertise it as the retryable server fault the
    # crossing's own failure is. Refusing it now costs no row and no model call.
    if len(scenario) > ai_case_language.MAX_SCENARIO_CHARS:
        raise CaseDecisionError(
            status_code=422,
            code="scenario_too_long",
            message=(
                f"scenario is {len(scenario)} characters; the maximum is "
                f"{ai_case_language.MAX_SCENARIO_CHARS}."
            ),
            correlation_id=correlation_id,
        )

    # Normalise first, then measure. Checking the raw length would refuse a
    # request that is within the limit once its formatting is collapsed — and
    # the caller, looking at a text area they believe holds 1,900 characters,
    # would have no way to see why.
    guidance = normalise_additional_instructions(additional_instructions)
    if len(guidance) > MAX_ADDITIONAL_INSTRUCTIONS_CHARS:
        raise CaseDecisionError(
            status_code=422,
            code="additional_instructions_too_long",
            message=(
                f"additional_instructions is {len(guidance)} characters after normalisation; "
                f"the maximum is {MAX_ADDITIONAL_INSTRUCTIONS_CHARS}."
            ),
            correlation_id=correlation_id,
        )
    guidance_hash = additional_instructions_hash(guidance)

    # The project's identity is read into plain values once, here, and every
    # line below uses those rather than the ORM instance. Two of the paths in
    # this function roll the session back, and a rollback expires every loaded
    # object — so `policy_set.key` after one is not a field read, it is a lazy
    # database load, and inside an async session it fails with `MissingGreenlet`
    # instead of returning a string. That failure lands in the error handler for
    # some *other* fault, which is the worst possible place to acquire a second
    # one: it replaces a precise refusal with an unhandled 500.
    project = PolicySetRef(
        id=str(policy_set.id), key=policy_set.key, name=getattr(policy_set, "name", "") or ""
    )
    project_id = policy_set.id

    repo = PolicyCaseDecisionRepository(session)
    normalised_provision_id = (provision_id or "").strip() or None
    scope_requested = (
        ai_case_project.SCOPE_SINGLE if normalised_provision_id else ai_case_project.SCOPE_PROJECT
    )
    canonical_request_hash = request_hash(
        policy_set_key=project.key,
        scenario=scenario,
        provision_id=normalised_provision_id,
        reasoning_effort=reasoning_effort,
        additional_instructions=guidance,
    )

    # The guidance rides in the reservation's metadata as well as in the
    # envelope, because the reservation is written *before* the model runs and
    # the envelope only exists after it. A receipt stuck at `pending` — a crash
    # mid-call — still shows what the caller asked for.
    reservation_metadata = {
        **(request_metadata or {}),
        "additional_instructions": guidance,
        "additional_instructions_hash": guidance_hash,
        "additional_instructions_chars": len(guidance),
        "instruction_profile": ai_case_intent.CALLER_GUIDANCE_PROFILE,
    }

    if idempotency_key:
        existing = await repo.find_by_idempotency_key(
            policy_set_id=project_id,
            authenticated_principal_identity=caller.identity,
            idempotency_key=idempotency_key,
        )
        if existing is not None:
            return _resolve_existing(existing, request_hash_now=canonical_request_hash)

    received_at = datetime.now(timezone.utc)
    started = time.perf_counter()
    timings_ms: dict[str, int] = {}

    try:
        row = await repo.reserve(
            policy_set_id=project_id,
            scenario_text=scenario,
            scenario_hash=scenario_hash(scenario),
            request_hash=canonical_request_hash,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
            authenticated_principal_identity=caller.identity,
            authenticated_principal_role=caller.role,
            authentication_source=caller.authentication_source,
            calling_system_identity=caller.calling_system_identity,
            channel=caller.channel,
            scope=scope_requested,
            requested_provision_id=normalised_provision_id,
            reasoning_effort_requested=reasoning_effort,
            request_metadata=reservation_metadata,
            received_at=received_at,
        )
        timings_ms["reservation"] = max(
            0, int((time.perf_counter() - started) * 1000)
        )
    except IntegrityError:
        # Two calls with one key raced. The loser rolls back and reads what the
        # winner wrote, rather than deciding a second time.
        await session.rollback()
        if idempotency_key:
            existing = await repo.find_by_idempotency_key(
                policy_set_id=project_id,
                authenticated_principal_identity=caller.identity,
                idempotency_key=idempotency_key,
            )
            if existing is not None:
                return _resolve_existing(existing, request_hash_now=canonical_request_hash)
        raise CaseDecisionError(
            status_code=409,
            code="decision_reservation_conflict",
            message="This decision could not be reserved because a conflicting record exists.",
            correlation_id=correlation_id,
        )
    except Exception as exc:  # noqa: BLE001 - the reservation is the precondition
        await _safe_rollback(session)
        logger.warning(
            "case decision reservation failed for project %s (correlation %s): %s",
            project.key,
            correlation_id,
            exc,
        )
        raise CaseDecisionError(
            status_code=503,
            code="decision_receipt_unavailable",
            message=(
                "The decision receipt could not be reserved, so no decision was attempted. "
                "Retry the request."
            ),
            correlation_id=correlation_id,
        ) from exc

    decision_id = str(row.id)

    # ── in, across the boundary ───────────────────────────────────────
    #
    # The same helper the reviewer path uses, so the two cannot drift. What is
    # local to this path is what a failure costs: the reservation is already
    # written, so it is closed as failed and the caller gets a 503 naming which
    # half of the boundary could not be crossed.
    language_in_started = time.perf_counter()
    try:
        crossing = await cross_into_processing_language(scenario, guidance)
    except ai_case_language.LanguageBoundaryError as exc:
        raise await _fail(
            session,
            repo,
            row,
            decision_id=decision_id,
            code=exc.code,
            message=(
                "The question could not be carried into the language this platform decides in, "
                "so no policy was read and no verdict was produced. Retry the request."
            ),
            status_code=503,
            correlation_id=correlation_id,
            started=started,
        ) from exc
    except Exception as exc:  # noqa: BLE001 - an unexpected boundary fault is still a refusal
        logger.exception("case decision %s could not cross the language boundary", decision_id)
        raise await _fail(
            session,
            repo,
            row,
            decision_id=decision_id,
            code=ai_case_language.SCENARIO_TRANSLATION_UNAVAILABLE,
            message=(
                "The question could not be carried into the language this platform decides in, "
                "so no policy was read and no verdict was produced. Retry the request."
            ),
            status_code=503,
            correlation_id=correlation_id,
            started=started,
        ) from exc
    timings_ms["language_in"] = max(
        0, int((time.perf_counter() - language_in_started) * 1000)
    )

    # ── decide, with no transaction held ──────────────────────────────
    decider_started = time.perf_counter()
    try:
        answer = await _invoke_decider(
            session,
            policy_set=policy_set,
            scenario=crossing.scenario,
            provision_id=normalised_provision_id,
            reasoning_effort=reasoning_effort,
            additional_instructions=crossing.guidance,
            with_context=True,
        )
    except LookupError as exc:
        raise await _fail(
            session,
            repo,
            row,
            decision_id=decision_id,
            code="policy_not_in_project",
            message=str(exc),
            status_code=404,
            correlation_id=correlation_id,
            started=started,
        ) from exc
    except ValueError as exc:
        raise await _fail(
            session,
            repo,
            row,
            decision_id=decision_id,
            code="invalid_request",
            message=str(exc),
            status_code=422,
            correlation_id=correlation_id,
            started=started,
        ) from exc
    except ai_case_project.IndexProjectionUnavailable as exc:
        # Caught before the generic `RuntimeError` it derives from, and closed as
        # a failed receipt rather than served as an answer. The reservation is
        # already written, so the refusal closes it; and the refusal is the whole
        # point — an index that carries no retrieval projection cannot be matched
        # against by a question rendered into the processing language, and the
        # answer that would come back is a confident "no published policy bears
        # on this". A caller has to be able to tell that from "the corpus could
        # not be compared", which is what this code says.
        raise await _fail(
            session,
            repo,
            row,
            decision_id=decision_id,
            code=exc.code,
            message=str(exc),
            status_code=503,
            correlation_id=correlation_id,
            started=started,
        ) from exc
    except RuntimeError as exc:
        raise await _fail(
            session,
            repo,
            row,
            decision_id=decision_id,
            code="ai_unavailable",
            message=str(exc),
            status_code=503,
            correlation_id=correlation_id,
            started=started,
        ) from exc
    except Exception as exc:  # noqa: BLE001 - an unexpected decider fault is still a failed receipt
        logger.exception("case decision %s failed unexpectedly", decision_id)
        raise await _fail(
            session,
            repo,
            row,
            decision_id=decision_id,
            code="decision_failed",
            message="The decision could not be completed.",
            status_code=500,
            correlation_id=correlation_id,
            started=started,
        ) from exc

    timings_ms["decider_wall"] = max(
        0, int((time.perf_counter() - decider_started) * 1000)
    )
    answer.context.setdefault("timings_ms", {}).update(timings_ms)

    decided_at = datetime.now(timezone.utc)
    latency_ms = max(0, int((time.perf_counter() - started) * 1000))

    # ── out, across the boundary ──────────────────────────────────────
    #
    # Again the shared helper, and again the difference is only what a failure
    # costs. A rendering that cannot be completed leaves a decision that was
    # made and will not be served: half in one language and half in another is
    # worse evidence than none.
    language_out_started = time.perf_counter()
    try:
        response, language = await cross_out_to_the_reader(
            answer.response, crossing, projection_profile=_projection_profile(answer.response)
        )
    except ai_case_language.LanguageBoundaryError as exc:
        raise await _fail(
            session,
            repo,
            row,
            decision_id=decision_id,
            code=exc.code,
            message=(
                "The decision was made but its explanation could not be returned in the "
                "language the question was asked in, so no partial answer is served. "
                "Retry with a new Idempotency-Key."
            ),
            status_code=503,
            correlation_id=correlation_id,
            started=started,
        ) from exc
    except Exception as exc:  # noqa: BLE001 - a mixed-language answer is not an answer
        logger.exception("case decision %s could not be rendered for its reader", decision_id)
        raise await _fail(
            session,
            repo,
            row,
            decision_id=decision_id,
            code=ai_case_language.RESPONSE_TRANSLATION_UNAVAILABLE,
            message=(
                "The decision was made but its explanation could not be returned in the "
                "language the question was asked in, so no partial answer is served. "
                "Retry with a new Idempotency-Key."
            ),
            status_code=503,
            correlation_id=correlation_id,
            started=started,
        ) from exc
    answer.context["timings_ms"]["language_out"] = max(
        0, int((time.perf_counter() - language_out_started) * 1000)
    )

    links_started = time.perf_counter()
    provision_ids = await _provision_ids_by_key(
        session, policy_set_id=project_id, response=response
    )
    answer.context["timings_ms"]["policy_link_lookup"] = max(
        0, int((time.perf_counter() - links_started) * 1000)
    )
    answer.context["timings_ms"]["to_envelope"] = max(
        0, int((time.perf_counter() - started) * 1000)
    )
    answer.context["token_usage"] = _token_usage_ref(usage_scope).model_dump(mode="json")

    # ── past the point where a duration can be inside the receipt ─────
    #
    # `to_envelope` above is the last timing this receipt can carry. Everything
    # from here on — building the envelope, sealing it, writing it — finishes
    # *after* the object that would have to report it, and the stored row is
    # that object's own dump. There is no honest way to put these numbers in the
    # response:
    #
    #   * mutating the returned envelope after the write would leave the caller
    #     holding a receipt the database does not have, so the POST body and the
    #     later GET replay would disagree;
    #   * writing the row and then updating it would stop persistence being one
    #     atomic act, and a crash between the two would store a receipt that was
    #     never returned to anyone.
    #
    # So they are measured and emitted beside the receipt instead of inside it.
    # They are operator telemetry, deliberately not caller telemetry, and
    # `_finalisation_ms` below never touches `answer.context` — the map that
    # became `trace.stage_latency_ms` is finished and is not written to again.
    finalisation_ms: dict[str, int] = {}

    envelope_build_started = time.perf_counter()
    envelope = build_envelope(
        decision_id=decision_id,
        correlation_id=correlation_id,
        idempotency_key=idempotency_key,
        project=project,
        caller=caller,
        scenario=scenario,
        reasoning_effort=reasoning_effort,
        requested_provision_id=normalised_provision_id,
        additional_instructions=guidance,
        language=language,
        received_at=received_at,
        decided_at=decided_at,
        latency_ms=latency_ms,
        response=response,
        context=answer.context,
        provision_ids=provision_ids,
    )
    finalisation_ms["envelope_build"] = max(
        0, int((time.perf_counter() - envelope_build_started) * 1000)
    )

    finalize_started = time.perf_counter()
    try:
        try:
            await repo.finalize_completed(
                row,
                policy_version_id=_version_uuid(answer.context.get("policy_version_id")),
                version_number=answer.context.get("version_number"),
                schema_version=envelope.schema_version,
                decision_status=legacy_decision_status(envelope),
                information_requested=envelope.asked.information_requested,
                verdict_requested=envelope.asked.verdict_requested,
                information_status=(
                    envelope.information.status if envelope.information is not None else None
                ),
                verdict_status=envelope.verdict.status if envelope.verdict is not None else None,
                scope=envelope.request.scope,
                retrieval=envelope.retrieval.model_dump(mode="json"),
                decision_summary=_decision_summary(envelope),
                citation_ids=[citation.rule_id for citation in envelope.citations],
                trace=envelope.trace.model_dump(mode="json"),
                response=envelope.model_dump(mode="json"),
                decision_hash=envelope.decision_hash,
                hash_basis=envelope.hash_basis,
                decided_at=decided_at,
                latency_ms=latency_ms,
            )
        finally:
            # In `finally`, because a write that failed still consumed the time
            # it took to fail, and a receipt that could not be stored is the
            # case an operator most needs the number for.
            finalisation_ms["receipt_finalize"] = max(
                0, int((time.perf_counter() - finalize_started) * 1000)
            )
            finalisation_ms["request_total"] = max(
                0, int((time.perf_counter() - started) * 1000)
            )
    except Exception as exc:  # noqa: BLE001 - an unstored verdict is not a verdict
        await _safe_rollback(session)
        logger.error(
            "case decision %s produced an answer that could not be stored (correlation %s): %s",
            decision_id,
            correlation_id,
            exc,
        )
        # Best effort: mark the reservation failed so it does not sit `pending`
        # forever. If even this cannot be written, the response is unchanged —
        # the caller still gets no verdict, which is the property that matters.
        try:
            await repo.finalize_failed(
                row,
                failure_code="decision_receipt_failed",
                failure_message="The decision was made but its receipt could not be stored.",
                decided_at=decided_at,
                latency_ms=latency_ms,
            )
        except Exception:  # noqa: BLE001
            await _safe_rollback(session)
        # Emitted last on this path, after the compensating write. Ahead of it,
        # a fault while measuring would skip `finalize_failed` and strand the
        # reservation at `pending` for good — the telemetry would have caused
        # the exact orphan the line above exists to prevent, and would have
        # replaced a mapped 500 with an unmapped exception.
        _log_finalisation(
            decision_id=decision_id,
            correlation_id=correlation_id,
            stage_latency_ms=answer.context.get("timings_ms"),
            finalisation_ms=finalisation_ms,
            stored=False,
        )
        raise CaseDecisionError(
            status_code=500,
            code="decision_receipt_failed",
            message=(
                "The decision was made but its receipt could not be stored, so no verdict is "
                "returned. Retry with a new Idempotency-Key."
            ),
            decision_id=decision_id,
            correlation_id=correlation_id,
        ) from exc

    # Emitted here, outside the block that guards the write, and not inside it.
    # Inside, a telemetry fault would be caught by the `except` above and a
    # decision that *was* stored would be rolled back, re-marked failed and
    # answered 500 — the receipt turned into a failure by the act of measuring
    # it. Nothing about observing a request may change its outcome.
    _log_finalisation(
        decision_id=decision_id,
        correlation_id=correlation_id,
        stage_latency_ms=answer.context.get("timings_ms"),
        finalisation_ms=finalisation_ms,
        stored=True,
    )
    return CaseDecisionOutcome(envelope=envelope, replayed=False)


async def decide_project_case(
    session: AsyncSession,
    *,
    policy_set,
    scenario: str,
    provision_id: str | None,
    reasoning_effort: str,
    correlation_id: str,
    idempotency_key: str | None,
    caller: Caller,
    additional_instructions: str = "",
    request_metadata: dict | None = None,
) -> CaseDecisionOutcome:
    """Decide and persist one case while collecting every model call's usage."""

    with collect_token_usage() as usage_scope:
        return await _decide_project_case(
            session,
            policy_set=policy_set,
            scenario=scenario,
            provision_id=provision_id,
            reasoning_effort=reasoning_effort,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
            caller=caller,
            additional_instructions=additional_instructions,
            request_metadata=request_metadata,
            usage_scope=usage_scope,
        )


# ── replay and refusal ───────────────────────────────────────────────


def _resolve_existing(row: PolicyCaseDecision, *, request_hash_now: str) -> CaseDecisionOutcome:
    """What an already-used idempotency key means, in the four cases it can mean.

    The body check comes first on purpose: a caller who reused a key by accident
    must be told that, not handed someone else's — or their own earlier —
    answer to a different question.
    """

    decision_id = str(row.id)

    if row.request_hash != request_hash_now:
        raise CaseDecisionError(
            status_code=409,
            code="idempotency_key_reused",
            message=(
                "This Idempotency-Key was already used for a different request. "
                "Use a new key, or resend the original request unchanged."
            ),
            decision_id=decision_id,
            correlation_id=row.correlation_id,
        )

    if row.status == "completed" and row.response_json:
        # Whichever envelope wrote it. A receipt stored before the two-track
        # redesign is replayed as v1 — the bytes the caller was given — rather
        # than re-projected into a shape that decision never had.
        return CaseDecisionOutcome(envelope=validate_receipt(row.response_json), replayed=True)

    if row.status == "pending":
        raise CaseDecisionError(
            status_code=409,
            code="decision_in_progress",
            message=(
                "A decision for this Idempotency-Key is still in progress. "
                "Retry the same request shortly to receive its receipt."
            ),
            decision_id=decision_id,
            correlation_id=row.correlation_id,
        )

    raise CaseDecisionError(
        status_code=409,
        code="decision_previously_failed",
        message=(
            "The decision for this Idempotency-Key failed and carries no verdict. "
            "Retry with a new Idempotency-Key."
        ),
        decision_id=decision_id,
        correlation_id=row.correlation_id,
    )


async def _fail(
    session: AsyncSession,
    repo: PolicyCaseDecisionRepository,
    row: PolicyCaseDecision,
    *,
    decision_id: str,
    code: str,
    message: str,
    status_code: int,
    correlation_id: str,
    started: float,
) -> CaseDecisionError:
    """Close the reservation out as failed and build the error to raise.

    Returns the error rather than raising it so the call site reads
    `raise await _fail(...) from exc`, which keeps the original cause attached.

    `decision_id` is passed in as a string rather than read from `row`: the
    rollback below expires the instance, and reading an expired attribute inside
    an async session is a database call, not a field access. Taking one here
    would replace a precise refusal with an unrelated failure.
    """

    await _safe_rollback(session)
    try:
        await repo.finalize_failed(
            row,
            failure_code=code,
            failure_message=message,
            latency_ms=max(0, int((time.perf_counter() - started) * 1000)),
        )
    except Exception:  # noqa: BLE001 - the refusal stands even if the note does not
        await _safe_rollback(session)
        logger.error("could not mark case decision %s failed", decision_id)

    return CaseDecisionError(
        status_code=status_code,
        code=code,
        message=message,
        decision_id=decision_id,
        correlation_id=correlation_id,
    )


async def _safe_rollback(session: AsyncSession) -> None:
    try:
        await session.rollback()
    except Exception:  # noqa: BLE001 - a session that cannot roll back is already lost
        logger.warning("rollback failed while handling a case decision fault")


# ── telemetry that cannot live in the receipt ────────────────────────

#: Durations reported only beside the receipt, never inside it. Each one ends
#: after the envelope it would have to be reported in has already been built and
#: sealed, so there is no version of this map that a caller could be handed
#: without the stored receipt and the returned receipt ceasing to be the same
#: object. Keys are wall-clock milliseconds, like every other timing this
#: service reports.
FINALISATION_TELEMETRY_KEYS: tuple[str, ...] = (
    "envelope_build",
    "receipt_finalize",
    "request_total",
)

#: Stable prefix so an operator can select these lines out of a log stream. The
#: body is JSON because the previous form interpolated a Python dict into a
#: format string, which is readable by a person and not by anything else.
FINALISATION_LOG_EVENT: str = "case_decision.finalisation"


def _log_finalisation(
    *,
    decision_id: str,
    correlation_id: str,
    stage_latency_ms: Mapping[str, int] | None,
    finalisation_ms: Mapping[str, int],
    stored: bool,
) -> None:
    """Emit the timings that the receipt itself cannot carry.

    Called on both outcomes on purpose. A store that failed spent real time
    failing, and the run where the receipt could not be written is the one an
    operator most needs the numbers for — so `stored` reports which case this
    was rather than the line being absent for one of them.

    This function is deliberately incapable of changing what was returned or
    stored: it reads, formats and logs. Nothing here is written back into the
    context that became `trace.stage_latency_ms`, which is finished by the time
    this runs, and a fault in this function is contained rather than raised —
    a decision that was made, sealed and stored must not be turned into a
    failure by the act of measuring it.
    """

    # Only durations. Every value in these maps is documented as whole
    # milliseconds, so a value that is not one is not a duration and has no
    # meaning here — dropping it keeps the record readable as a timing record
    # and keeps `json.dumps` total over its own input.
    #
    # The whole body is inside the guard, not just the emit: building the
    # payload reads two caller-supplied mappings, and a fault while reading one
    # would escape a function whose entire purpose is to observe without
    # consequence.
    try:
        payload = {
            "decision_id": decision_id,
            "correlation_id": correlation_id,
            "stored": stored,
            "stage_latency_ms": _durations_only(stage_latency_ms),
            "finalisation_ms": {
                key: value
                for key, value in _durations_only(finalisation_ms).items()
                if key in FINALISATION_TELEMETRY_KEYS
            },
        }
        logger.info("%s %s", FINALISATION_LOG_EVENT, json.dumps(payload, sort_keys=True))
    except Exception:  # noqa: BLE001 - telemetry never decides a request's fate
        logger.warning(
            "case decision %s finalisation telemetry could not be emitted", decision_id
        )


def _durations_only(values: Mapping[str, int] | None) -> dict[str, int]:
    """Keep the entries that are actually milliseconds.

    `bool` is excluded explicitly: it is a subclass of `int` in Python, and a
    flag reported as a duration is exactly the confusion the timing contract
    exists to prevent.
    """

    return {
        str(key): value
        for key, value in (values or {}).items()
        if isinstance(value, int) and not isinstance(value, bool)
    }


def _version_uuid(value: object) -> uuid.UUID | None:
    if not value:
        return None
    try:
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        # The decider's version identity is stubbed in some tests with a
        # non-UUID string. A receipt that cannot store the surrogate key still
        # carries the version number and the whole envelope, so this degrades
        # rather than refusing an otherwise complete decision.
        return None


def _referenced_provision_keys(response: dict) -> set[str]:
    """Every provision key the receipt will mention, from all four places.

    Both tracks' citations are read, not just the primary one: a mixed case cites
    from two gathers, and a policy named only by the track this function did not
    look at would lose its payload link for no reason a reader could see.
    """

    keys: set[str] = set()
    for entry in (response.get("considered") or []) + (response.get("excluded") or []):
        key = entry.get("provision_key")
        if key:
            keys.add(str(key))
    provision = response.get("provision")
    if provision and provision.get("provision_key"):
        keys.add(str(provision["provision_key"]))
    evaluation = response.get("evaluation") or {}
    for branch in (evaluation.get("informational"), evaluation.get("decision")):
        for citation in (branch or {}).get("citations") or []:
            policy = citation.get("policy") or {}
            if policy.get("provision_key"):
                keys.add(str(policy["provision_key"]))
    return keys


async def _provision_ids_by_key(
    session: AsyncSession, *, policy_set_id: uuid.UUID, response: dict
) -> dict[str, str]:
    """Resolve each policy's stable key to the provision that serves its payload.

    A *published* policy is identified by its version plus its `provision_key`,
    and the published projection carries no provision id — correctly, because a
    published record is not a row in `document_provisions`. But the lean payload
    is served at `GET /api/policy-payload/{provision_id}`, so a receipt that
    wants to link a reader to the policy has to make that join once, here.

    Two deliberate limits:

      * a key that resolves to more than one provision in this project is left
        unresolved. The same heading chain appearing under two document versions
        is a real situation, and picking one would put a link in an audit record
        that points at a policy nobody chose.
      * the lookup is best effort. It is a convenience link, not part of the
        decision, so a failure here omits the URL rather than discarding an
        otherwise complete receipt — which is also why it is not inside the
        finalising transaction.
    """

    keys = _referenced_provision_keys(response)
    if not keys:
        return {}

    try:
        rows = await session.execute(
            select(DocumentProvision.provision_key, DocumentProvision.id).where(
                DocumentProvision.policy_set_id == policy_set_id,
                DocumentProvision.provision_key.in_(sorted(keys)),
            )
        )
        found = rows.all()
    except Exception:  # noqa: BLE001 - a missing link never invalidates a decision
        logger.warning("could not resolve policy payload links for a case decision")
        return {}

    counts: dict[str, list[str]] = {}
    for provision_key, provision_id in found:
        counts.setdefault(str(provision_key), []).append(str(provision_id))
    return {key: ids[0] for key, ids in counts.items() if len(ids) == 1}


# ── envelope assembly ────────────────────────────────────────────────


def build_envelope(
    *,
    decision_id: str,
    correlation_id: str,
    idempotency_key: str | None,
    project: PolicySetRef,
    caller: Caller,
    scenario: str,
    reasoning_effort: str,
    requested_provision_id: str | None,
    received_at: datetime,
    decided_at: datetime,
    latency_ms: int,
    response: dict,
    context: dict,
    additional_instructions: str = "",
    language: LanguageRef | None = None,
    provision_ids: dict[str, str] | None = None,
) -> CaseDecisionEnvelopeV2:
    """Project the decider's answer and its context into `case_decision_v2`.

    Kept a module-level function rather than folded into `decide_project_case`
    so the projection can be exercised on its own — the hash, the two-track
    outcome guard and the "no policy payload" rule are properties of this
    function, not of the endpoint that calls it.

    `project` is a plain value rather than the ORM row, so this cannot trigger a
    lazy load while assembling a response. `provision_ids` maps a policy's
    stable provision key to the provision row that serves its payload; see
    `_provision_ids_by_key` for why the published record does not carry one.

    `additional_instructions` is expected already normalised — this function
    echoes and hashes what it is given, and normalising here as well would let
    the value that was *sent to the model* differ from the value that was
    *sealed*, which is the one thing the echo exists to rule out.

    `language` records which language each stage worked in and carries the
    question as it was actually adjudicated. **Its presence is what selects the
    seal**: given one, the receipt is written under `case_decision_v2_lang` and
    the rendered question and the translation profiles join the preimage;
    without one, the receipt is written under `case_decision_v2` and sealed by
    exactly the rule that basis has always named. That is why introducing the
    boundary migrates nothing — an old receipt and a new one each verify under
    the basis they were written with, and a verifier branches on the stored
    `hash_basis` to know which.

    `response` is expected to carry the prose in the language it will be served
    in. The rendering happens upstream, before this function is called, so what
    the seal covers is what the caller was given rather than an intermediate
    nobody saw.

    WHAT IT DOES WITH AN EVALUATION IT DOES NOT RECOGNISE

    The decider's evaluation block is read defensively in one specific way: when
    it carries neither `information_requested` nor `verdict_requested` — a
    gather written against the exclusive cut, or a test double of one — the
    booleans are derived from which branches are actually present. That is not a
    guess about the caller; it is the honest reading of a record that says which
    gathers ran, and it keeps this projection working over any shape the decider
    has ever returned.
    """

    ids = provision_ids or {}
    evaluation = response.get("evaluation")

    asked = _asked_ref(evaluation)
    information = (
        _information_section(evaluation, provision_ids=ids)
        if asked.information_requested
        else None
    )
    verdict = _verdict_section(evaluation, provision_ids=ids) if asked.verdict_requested else None

    envelope = CaseDecisionEnvelopeV2(
        schema_version=SCHEMA_VERSION_V2,
        decision_id=decision_id,
        correlation_id=correlation_id,
        idempotency_key=idempotency_key,
        policy_set=project,
        active_version=_version_ref(context),
        caller=CallerRef(
            principal_identity=caller.identity,
            principal_role=caller.role,
            authentication_source=caller.authentication_source,
            calling_system_identity=caller.calling_system_identity,
            channel=caller.channel,
        ),
        request=RequestRef(
            scenario=scenario,
            scenario_hash=scenario_hash(scenario),
            additional_instructions=additional_instructions,
            additional_instructions_hash=additional_instructions_hash(additional_instructions),
            scope=str(response.get("scope") or ai_case_project.SCOPE_PROJECT),
            requested_provision_id=requested_provision_id,
            reasoning_effort_requested=reasoning_effort,
            received_at=received_at,
        ),
        language=language,
        asked=asked,
        outcome=OutcomeRef(
            information=_track_outcome(
                evaluated=evaluation is not None,
                requested=asked.information_requested,
                section=information,
            ),
            verdict=_track_outcome(
                evaluated=evaluation is not None,
                requested=asked.verdict_requested,
                section=verdict,
            ),
        ),
        information=information,
        verdict=verdict,
        retrieval=RetrievalRef(**_retrieval_fields(response.get("retrieval") or {})),
        considered=_considered_refs(response, provision_ids=ids),
        excluded=[_policy_ref(entry, provision_ids=ids) for entry in (response.get("excluded") or [])],
        citations=_merged_citations(information, verdict),
        size=SizeRef(**(response.get("size") or {})) if response.get("size") else None,
        trace=_trace_ref(response, context, evaluated=evaluation is not None),
        decision_hash="",
        hash_basis=(
            HASH_BASIS_V2_LANG_WITH_VERIFICATION
            if language is not None
            else HASH_BASIS_V2_WITH_VERIFICATION
        ),
        receipt_url=RECEIPT_PATH.format(decision_id=decision_id),
        decided_at=decided_at,
        latency_ms=latency_ms,
    )
    # Assigned after construction because the hash is taken over the envelope's
    # own decision-defining content and cannot exist before it.
    envelope.decision_hash = compute_decision_hash_v2(envelope)
    return envelope


def legacy_decision_status(envelope: CaseDecisionEnvelopeV2) -> str:
    """The one scalar the stored row's `decision_status` column still carries.

    The column predates the two-track receipt and is what operational queries —
    "how many decisions declined last week" — are written against. Dropping it
    would break those for no gain, so it is *derived* rather than kept as a
    second source of truth: the verdict track when there is one, the information
    track otherwise, and `not_evaluated` when neither ran.

    Verdict wins the tie for the same reason `intent` does: it is the stronger
    claim, and an operator counting "answered" decisions means the ones that
    reached a verdict. The envelope remains the authority; this is an index.
    """

    if envelope.verdict is not None:
        return envelope.verdict.status
    if envelope.information is not None:
        return envelope.information.status
    return NOT_EVALUATED


def _decision_summary(envelope: CaseDecisionEnvelopeV2) -> dict:
    """The row's at-a-glance summary column, in the two-track shape.

    A summary column that still described one branch would be read as the whole
    answer by exactly the queries it exists to serve, so it names both tracks and
    what each came to.
    """

    return {
        "schema_version": envelope.schema_version,
        "asked": envelope.asked.model_dump(mode="json"),
        "outcome": envelope.outcome.model_dump(mode="json"),
        "information": (
            None if envelope.information is None else envelope.information.model_dump(mode="json")
        ),
        "verdict": None if envelope.verdict is None else envelope.verdict.model_dump(mode="json"),
    }


def _asked_ref(evaluation: dict | None) -> AskedRef:
    """What the classifier read the question as asking for.

    When no evaluation ran the classifier never ran either, so both booleans are
    false and the classifier is unnamed: that is the truth, and the envelope's
    `outcome` reports `not_evaluated` for both tracks so a reader is not left to
    infer "you asked for nothing" from it.
    """

    if not evaluation:
        return AskedRef(
            information_requested=False,
            verdict_requested=False,
            classification_reasoning=None,
            classifier_version=None,
        )

    information = evaluation.get("information_requested")
    verdict = evaluation.get("verdict_requested")
    if information is None and verdict is None:
        # An evaluation from the exclusive cut. Which gathers ran is recorded in
        # which branches are present, so that is what is read — never guessed.
        intent = evaluation.get("intent")
        information = evaluation.get("informational") is not None or intent == "informational"
        verdict = evaluation.get("decision") is not None or intent == "decision"

    return AskedRef(
        information_requested=bool(information),
        verdict_requested=bool(verdict),
        classification_reasoning=evaluation.get("classification_reasoning"),
        classifier_version=evaluation.get("classifier_version"),
        # `.get`, not `[...]`: an evaluation produced before the readings were
        # sampled, or by a caller that classified elsewhere, carries no consensus
        # and is not thereby malformed. Null then says exactly that.
        classifier_consensus=evaluation.get("classifier_consensus"),
    )


def _track_outcome(
    *,
    evaluated: bool,
    requested: bool,
    section: InformationSection | VerdictSection | None,
) -> str:
    """One track's outcome: what it came to, or why it has nothing to say.

    Three cases, deliberately not two.

      * Nothing was evaluated at all — retrieval produced no record to answer
        from — so no classifier ran and neither track could have. Both tracks
        report `not_evaluated`, whatever the (necessarily false) booleans say.
      * The track was not asked for: `not_requested`, and the section is null.
      * Otherwise the gather's own status.

    The first two must not collapse. `not_requested` says the caller did not ask;
    `not_evaluated` says the corpus had nothing to answer from. Reporting the
    second as the first would let a caller read their own silence as the
    corpus's — and, worse, would make an unbuilt index look like a question that
    never wanted an answer.
    """

    if not evaluated:
        return NOT_EVALUATED
    if not requested:
        return NOT_REQUESTED
    if section is None:
        return NOT_EVALUATED
    return section.status


def _information_section(
    evaluation: dict | None, *, provision_ids: dict[str, str] | None = None
) -> InformationSection | None:
    """What the policies state, or `None` when nothing was evaluated."""

    branch = (evaluation or {}).get("informational")
    if not isinstance(branch, dict):
        return None

    status = str(branch.get("status") or "").strip().lower()
    if status not in _KNOWN_INFORMATION_STATUSES:
        status = "failed"
    prose = str(branch.get("answer") or "")
    if status == STATUS_WITH_VERDICT and not prose.strip():
        # A gather that claims to have answered and composed nothing has not
        # answered. `InformationSection` refuses that combination outright, so
        # normalising here is what keeps a malformed reply a *reported* state
        # rather than a 500 on an otherwise complete receipt.
        status = "declined"
    answered = status == STATUS_WITH_VERDICT

    return InformationSection(
        status=status,  # type: ignore[arg-type]
        answered=answered,
        # The gather only composes prose when it answered; asserting it here
        # means the section's own invariant does not rest on that staying true.
        answer=prose if answered else "",
        # Prose from a branch that did not answer is not an answer and must not
        # be presented as one — it is why there is none. Today the gather empties
        # it for every non-answered state, so this is normally null.
        explanation=(prose or None) if not answered else None,
        route=ROUTE_INFORMATIONAL,
        citations=_citation_refs(branch, provision_ids=provision_ids),
        note=str(branch.get("note") or ""),
        grounding=_grounding(branch),
    )


def _verdict_section(
    evaluation: dict | None, *, provision_ids: dict[str, str] | None = None
) -> VerdictSection | None:
    """The determination, or `None` when nothing was evaluated.

    The verdict string is re-emptied for every status but `answered`. The gather
    already does that; re-asserting it means the receipt's invariant — a refusal
    is a *reached* verdict, and an undecided case carries no decision at all —
    holds even if a future gather forgets.

    Verification requirements are carried only for a verdict that was reached,
    for the mirror-image reason: a condition on *acting* on a determination is
    meaningless where there is no determination, and admitting one on a blocked
    case would blur the single distinction this section exists to keep sharp.
    """

    branch = (evaluation or {}).get("decision")
    if not isinstance(branch, dict):
        return None

    status = str(branch.get("status") or "").strip().lower()
    if status not in _KNOWN_VERDICT_STATUSES:
        status = "failed"
    decision = str(branch.get("verdict") or "").strip()
    if status == STATUS_WITH_VERDICT and not decision:
        # The gather normalises this away already; re-asserting it here is what
        # makes the invariant a property of the receipt rather than of the
        # gather remembering. A determination with no verdict named is not a
        # determination, and `VerdictSection` refuses the combination outright —
        # so a reply in that shape becomes a reported state instead of a 500.
        status = "not_settled_by_rules"
        decision = ""
    reached = status == STATUS_WITH_VERDICT
    blocked = status == "missing_required_facts"

    missing_flat = [str(item) for item in (branch.get("missing_required_facts") or [])] if blocked else []

    return VerdictSection(
        status=status,  # type: ignore[arg-type]
        reached=reached,
        decision=decision if reached else "",
        explanation=str(branch.get("answer") or ""),
        missing_information=_missing_information_refs(branch, flat=missing_flat) if blocked else [],
        missing_required_facts=missing_flat,
        verification_requirements=_verification_requirement_refs(branch) if reached else [],
        route=ROUTE_DECISION,
        citations=_citation_refs(branch, provision_ids=provision_ids),
        note=str(branch.get("note") or ""),
        grounding=_grounding(branch),
    )


def _missing_information_refs(branch: dict, *, flat: list[str]) -> list[MissingInformationItem]:
    """The structured missing facts, from the gather or from the flat list.

    The gather supplies `missing_information` under the current prompt. A reply
    that carried only the flat list — an older gather, or a model that ignored
    the structured field — still produces one item per fact here, with the fields
    it did not supply left empty rather than composed. A reason invented in this
    layer would read to a caller exactly like one the policy gave.
    """

    structured = branch.get("missing_information")
    items: list[MissingInformationItem] = []
    if isinstance(structured, list):
        for entry in structured:
            if not isinstance(entry, dict):
                continue
            fact = str(entry.get("fact") or "").strip()
            label = str(entry.get("label") or "").strip()
            if not fact and not label:
                continue
            items.append(
                MissingInformationItem(
                    fact=fact or label,
                    label=label or fact,
                    why_needed=str(entry.get("why_needed") or ""),
                    required_by_rule_ids=[
                        str(rule_id) for rule_id in (entry.get("required_by_rule_ids") or [])
                    ],
                )
            )
    if items:
        return items

    return [
        MissingInformationItem(fact=fact, label=fact, why_needed="", required_by_rule_ids=[])
        for fact in flat
    ]


def _verification_requirement_refs(branch: dict) -> list[VerificationRequirementItem]:
    """The structured conditions to confirm before acting on a reached verdict.

    Read exactly as the missing facts are read, with one deliberate omission:
    there is no flat-list fallback, because there is no older flat field to fall
    back to. An entry with neither a key nor a label is dropped rather than
    guessed at, and nothing here composes a reason the gather did not give.
    """

    structured = branch.get("verification_requirements")
    if not isinstance(structured, list):
        return []

    items: list[VerificationRequirementItem] = []
    for entry in structured:
        if not isinstance(entry, dict):
            continue
        fact = str(entry.get("fact") or "").strip()
        label = str(entry.get("label") or "").strip()
        if not fact and not label:
            continue
        items.append(
            VerificationRequirementItem(
                fact=fact or label,
                label=label or fact,
                why_needed=str(entry.get("why_needed") or ""),
                required_by_rule_ids=[
                    str(rule_id) for rule_id in (entry.get("required_by_rule_ids") or [])
                ],
            )
        )
    return items


def _merged_citations(
    information: InformationSection | None, verdict: VerdictSection | None
) -> list[MergedCitationRef]:
    """Every rule either track rested on, once, tagged with who rested on it.

    The two tracks cite independently and overlap often — the rule that states a
    limit is usually the rule that decides whether something was within it.
    Listing it twice would make a reader count two authorities where the policies
    hold one, so the merge is by `rule_id` and the tags accumulate. The first
    occurrence keeps its resolved policy and verbatim source; a second sighting
    of the same rule id is the same rule, by construction — rule ids are unique
    across the corpus.
    """

    merged: dict[str, MergedCitationRef] = {}
    for section, tag in ((information, SERVES_INFORMATION), (verdict, SERVES_VERDICT)):
        if section is None:
            continue
        for citation in section.citations:
            existing = merged.get(citation.rule_id)
            if existing is None:
                merged[citation.rule_id] = MergedCitationRef(
                    rule_id=citation.rule_id,
                    policy=citation.policy,
                    source=citation.source,
                    serves=[tag],  # type: ignore[list-item]
                )
            elif tag not in existing.serves:
                existing.serves.append(tag)  # type: ignore[arg-type]
    return list(merged.values())


def _version_ref(context: dict) -> VersionRef | None:
    version_id = context.get("policy_version_id")
    if not version_id:
        return None
    return VersionRef(
        version_id=str(version_id),
        version_number=context.get("version_number"),
        effective_from=context.get("effective_from"),
        effective_to=context.get("effective_to"),
    )


_RETRIEVAL_FIELDS = (
    "status",
    "method",
    "precision_mode",
    "semantic_candidates",
    "semantic_selected",
    "semantic_largest_gap",
    "semantic_cutoff_score",
    "semantic_elbow_applied",
    "direct_policy_order",
    "coverage_expanded_policies",
    "coverage_semantic_floor",
    "rule_rescue_candidates",
    "rule_rescued_policies",
    "rule_rescue_floor",
    "rule_rescue_margin",
    "rule_semantic_window",
    "rule_semantic_candidates",
    "policy_budget",
    "policy_scan",
    "policies_retrieved",
    "policies_considered",
    "policies_retained",
    "policies_discarded",
    "policies_untestable",
    "payload_budget_chars",
    "policies_over_payload_budget",
    "large_policy_rule_threshold",
    "selected_rule_budget",
    "policies_rule_sliced",
    "policies_duplicate_collapsed",
    "policy_selection_order",
    "policies_diversity_deferred",
    # What the search itself was, and whether it could be made at all. Named
    # here for the same reason every other counter is: a decider field that is
    # not in this tuple does not reach the receipt, so the contract stays the
    # thing that decides what an audited answer carries.
    "rule_scan",
    "projection_profile",
    "projection_ready",
    "policy_documents_matched",
    "rule_documents_matched",
    "policies_elevated_by_rule",
    "rule_index_state",
    "reason",
)


def _retrieval_fields(retrieval: dict) -> dict:
    """Only the fields the contract names, so a decider addition cannot leak in.

    `status` is defaulted rather than assumed present: the single-policy scope
    reports a two-field block, and a missing status would otherwise raise inside
    the projection instead of being visible in the receipt.
    """

    fields = {name: retrieval.get(name) for name in _RETRIEVAL_FIELDS if name in retrieval}
    fields.setdefault("status", str(retrieval.get("status") or "unknown"))
    return fields


def _payload_url(provision_id: object) -> str | None:
    if not provision_id:
        return None
    return POLICY_PAYLOAD_PATH.format(provision_id=provision_id)


def _policy_ref(entry: dict, *, provision_ids: dict[str, str] | None = None) -> PolicyRef:
    """One policy reference — identity, a link, and which of its rules were read.

    Never the record itself. `rule_selection` rides along because a policy that
    was narrowed to a slice of its rules must not appear on a receipt as though
    all of it was weighed; it is absent when the policy was never carried into an
    evaluation, which is the honest reading of "nothing was selected from it".
    `duplicate_of_provision_key` rides along for the same reason inverted: a
    policy collapsed as an exact duplicate was not read, but its terms were — in
    the policy it names — and a receipt that showed the discard without the
    representative would read as though those terms went unweighed.
    """

    provision_key = entry.get("provision_key")
    provision_id = entry.get("provision_id") or (provision_ids or {}).get(str(provision_key or ""))
    selection = entry.get("rule_selection")
    return PolicyRef(
        provision_id=str(provision_id) if provision_id else None,
        provision_key=provision_key,
        heading_path=list(entry.get("heading_path") or []),
        rules=entry.get("rules"),
        retained=entry.get("retained"),
        best_rank=entry.get("best_rank"),
        best_score=entry.get("best_score"),
        discard_reason=entry.get("discard_reason"),
        duplicate_of_provision_key=entry.get("duplicate_of_provision_key"),
        reason=entry.get("reason"),
        payload_url=_payload_url(provision_id),
        rule_selection=RuleSelectionRef(**selection) if isinstance(selection, dict) else None,
    )


def _considered_refs(response: dict, *, provision_ids: dict[str, str] | None = None) -> list[PolicyRef]:
    """The policies the decision saw, in whichever shape the scope produced.

    The project scope reports a `considered` list with retrieval's verdict on
    each. The single scope reports one `provision` and no list, because
    retrieval never ran — so it is projected as a list of one, `retained` set
    from whether that policy was actually carried into an evaluation rather than
    from a retrieval verdict that does not exist.
    """

    if response.get("considered") is not None:
        return [_policy_ref(entry, provision_ids=provision_ids) for entry in response["considered"]]

    provision = response.get("provision")
    if not provision:
        return []
    return [
        _policy_ref(
            {**provision, "retained": response.get("evaluation") is not None},
            provision_ids=provision_ids,
        )
    ]


def _citation_refs(
    branch: dict | None, *, provision_ids: dict[str, str] | None = None
) -> list[CitationRef]:
    """One track's citations, each with its policy link and verbatim source."""

    if not branch:
        return []

    refs: list[CitationRef] = []
    for citation in branch.get("citations") or []:
        source = citation.get("source") or {}
        policy = citation.get("policy") or None
        refs.append(
            CitationRef(
                rule_id=str(citation.get("rule_id") or ""),
                policy=_policy_ref(policy, provision_ids=provision_ids) if policy else None,
                source=CitationSourceRef(
                    state=str(source.get("state") or "unresolved"),
                    # Absent fields stay absent. The projection reports four
                    # honest states for a missing quote; filling one in with a
                    # placeholder would turn "not stored" into "empty text".
                    text=source.get("text"),
                    page=source.get("page"),
                    section=source.get("section"),
                ),
            )
        )
    return refs


def _grounding(branch: dict | None) -> dict | None:
    """One track's grounding report, per track rather than per receipt.

    The two tracks ground separately — different prompts, different citation
    sets, different refusals — so a single grounding block would have to pick
    one and present it as the receipt's, which is the kind of narrowing a reader
    cannot see.
    """

    if not branch:
        return None
    grounding = branch.get("grounding")
    return dict(grounding) if isinstance(grounding, dict) else None


def _primary_branch(evaluation: dict | None) -> dict | None:
    """The track a single-value reader should read, when one must be picked.

    Used only for `trace`, which reports one prompt version. The verdict track
    wins for the same reason it wins everywhere else here: it is the stronger
    claim. Both tracks run the same prompt family, so the value is the same
    either way today; the rule is written down so it stays a choice rather than
    an accident if that ever stops being true.
    """

    if not evaluation:
        return None
    decision = evaluation.get("decision")
    if isinstance(decision, dict):
        return decision
    informational = evaluation.get("informational")
    return informational if isinstance(informational, dict) else None


def _trace_ref(response: dict, context: dict, *, evaluated: bool) -> TraceRef:
    """What produced the answer, reported only where it is knowable.

    `prompt_version` is taken from the gather's own grounding block rather than
    from a constant, so it names the prompt that actually ran. `model_deployment`
    is reported only when a gather happened — a retrieval that stopped short
    called no model, and naming one would suggest otherwise. There is no
    "reasoning effort used": see `contracts/case_decision.TraceRef`.

    `instruction_profile` names the server-side framing caller guidance is
    applied under, and is reported whenever a gather ran — including when no
    guidance was supplied, because the framing is a property of the server, not
    of the request. The prompts themselves are never returned: a caller sees
    their own guidance echoed in `request` and the server's contribution named
    by identifier, which is the whole of the asymmetry that makes the field safe.
    """

    settings = get_settings()
    grounding = _grounding(_primary_branch(response.get("evaluation"))) or {}
    retrieval = response.get("retrieval") or {}

    return TraceRef(
        prompt_version=grounding.get("prompt_version"),
        instruction_profile=ai_case_intent.CALLER_GUIDANCE_PROFILE if evaluated else None,
        model_deployment=settings.azure_openai_deployment if evaluated else None,
        retrieval_method=retrieval.get("method") or context.get("retrieval_method"),
        index_name=context.get("index_name"),
        index_version_id=context.get("index_version_id"),
        stage_latency_ms=context.get("timings_ms") or None,
        token_usage=context.get("token_usage") or None,
    )


def _token_usage_ref(scope: UsageScope) -> TokenUsageRef:
    report = scope.report()
    return TokenUsageRef(
        calls=report.calls,
        calls_without_usage=report.calls_without_usage,
        prompt_tokens=report.prompt_tokens,
        completion_tokens=report.completion_tokens,
        total_tokens=report.total_tokens,
        reasoning_tokens=report.reasoning_tokens,
    )
