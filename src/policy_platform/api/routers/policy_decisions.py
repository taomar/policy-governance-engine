"""The audited external decision API: put a case, receive a receipt.

WHY THIS IS NOT UNDER `/api/ai`

The project-case decider has been reachable for some time at
`POST /api/ai/policy-sets/{key}/case-answer`. That path is the wrong public
seam for an integration in two ways that have nothing to do with the code behind
it: `/api/ai/…` reads as an implementation namespace and carries no
compatibility promise, and the response it returns is an answer rather than a
receipt — nothing correlates a caller's request to a server-side record, so no
external system can cite, replay or audit a verdict it was given.

So this router is the stable contract. Four operations, deliberately:

  * `POST /api/policy-decisions/{project_key}/case` — decide, and record.
  * `POST /api/policy-decisions/{project_key}/case/light` — decide and record,
    then return the compact fixed-schema projection.
  * `POST /api/policy-decisions/{project_key}/policies` — return the filtered
    published policy records without deciding.
  * `GET  /api/policy-decisions/{decision_id}` — read the receipt back.

There is no receipt list endpoint and no identity endpoint here. A caller
composing a console already has `GET /api/policy-sets/{key}` and
`GET /api/policy-sets/{key}/active-version`.

`project_key` IS THE PUBLIC IDENTIFIER

Routing is on the project's stable `key`. Its UUID is returned in every receipt
as trace identity and is never routed on; its `name` is a display string and
changes. A name in the path is a 404 here, and that is the point: a URL built
from a display name would break the day someone renamed a project.

AUTHENTICATION IS NOT THE GLOBAL FLAG

Both operations depend on `require_authenticated_principal`, which establishes
identity independently of `rbac_enabled`. A receipt that names `rbac-disabled`
as its caller is not a receipt, so these two routes require a real, proved
identity even on a deployment that has not switched global enforcement on. The
capability bands in `OPERATION_BANDS` still apply on top of that when it is on.

WHAT A CALLER MAY STEER, AND WHAT THEY MAY NOT

`additional_instructions` exists so an integration can show a user the guidance
being sent and let them add to it. It is caller *input*, echoed back on the
receipt, and it shapes presentation only. The server's own instructions stay
server-side and are named by identifier in `trace`, never returned as text.

That split is the point. A playground that let a user edit the hidden prompt
would be handing them the safeguards, and "let me edit the system prompt" and
"let me say I want a shorter answer" look identical in a text box. They are not
identical here: one is not offered at all, and the other is normalised, bounded,
sealed, recorded, and applied under invariants it cannot cross.

ONE LANGUAGE INSIDE, THE CALLER'S LANGUAGE AT THE EDGE

A question may be asked in any language, and the answer's prose comes back in
it. In between, everything this platform does happens in the single language its
prompts are written in — the question is carried into it before any policy is
read, and only a closed whitelist of finished prose is carried back out.

Two consequences an integrator has to know, both of them in the receipt:

  * **Machine-readable fields do not move with the language.** Statuses, the two
    `asked` booleans, `outcome`, `missing_information[].fact`, every citation's
    `rule_id` and verbatim `source.text`, every retrieval counter and
    `decision_hash` are byte-identical whichever language the question was
    written in. Key on those, never on the verdict string or a label.
  * **A crossing that cannot be made is a refusal, not a fallback.** A decision
    reached from a question the platform could not read would be a decision
    about a different question, so it is answered `503` with a failed receipt
    and no verdict at all.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from policy_platform.api.authz import Principal, require_authenticated_principal
from policy_platform.api.roles import ADMIN, POLICY_AUTHOR
from policy_platform.application.policy_case_decision import (
    Caller,
    CaseDecisionError,
    compact_decision_receipt,
    decide_project_case,
    retrieve_project_policies,
)
from policy_platform.contracts.case_decision import (
    CaseDecisionEnvelope,
    CaseDecisionEnvelopeV2,
    CaseDecisionReceipt,
    validate_receipt,
)
from policy_platform.contracts.policy_retrieval import PolicyRetrievalEnvelope
from policy_platform.contracts.case_decision_light import CaseDecisionLightEnvelope
from policy_platform.infrastructure.assistants import ai_case_intent
from policy_platform.infrastructure.persistence.db import get_session
from policy_platform.infrastructure.persistence.repositories import (
    PolicyCaseDecisionRepository,
    PolicySetRepository,
)

router = APIRouter(prefix="/api/policy-decisions", tags=["policy-decisions"])

#: The header a caller may carry their own correlation id in. Also accepted in
#: the body; the two must agree.
CORRELATION_HEADER = "X-Correlation-Id"

#: The header an optional idempotency key arrives in. Not a body field: it
#: describes the delivery of the request, not the question being asked, and
#: putting it in the body would make it part of the request hash it is compared
#: against.
IDEMPOTENCY_HEADER = "Idempotency-Key"

#: Roles that may read any receipt, over and above its own caller. An author or
#: an administrator is already trusted with the policies the decision was made
#: from; a viewer who did not make the call is not.
_RECEIPT_READER_ROLES = frozenset({POLICY_AUTHOR, ADMIN})


# ── caller-controlled fields are checked against the columns that hold them ──
#
# WHY THIS IS AT THE ROUTE AND NOT LEFT TO THE DATABASE
#
# Every field below lands in a fixed-width column on `policy_case_decisions`.
# Without these checks, an over-long value is discovered by Postgres at the
# moment the reservation is written — and the reservation's failure handler
# cannot tell "the database is briefly unavailable" from "this input can never
# be stored", so it answers `503 decision_receipt_unavailable`, which says
# *retry the request*. A permanent client fault advertised as a transient
# server fault is the worst possible pairing: a well-behaved integration will
# retry it forever, and each attempt looks like a new outage.
#
# So the shape of the input is settled here, before a row is reserved and
# before the model is called, and it is answered `422` with a code naming the
# field. The limits are the column widths, written once and referenced by every
# check, so a schema change that is not reflected here is a change the guard
# test notices.

#: `String(200)` on the columns that store them: `correlation_id`,
#: `idempotency_key`, `calling_system_identity`, `requested_provision_id`.
MAX_IDENTIFIER_CHARS = 200

#: `String(20)` on `reasoning_effort_requested`.
MAX_REASONING_EFFORT_CHARS = 20


def _too_long(*, code: str, field: str, value: str, limit: int, correlation_id: str | None) -> HTTPException:
    """One refusal shape for every over-long caller field.

    The length that was sent is reported and the value is not. A correlation id
    or a system label is caller-controlled free text; echoing it into an error
    body puts it in whatever log that body reaches, and the caller already has
    it.
    """

    detail = {
        "code": code,
        "message": (
            f"{field} is {len(value)} characters; the maximum is {limit}."
        ),
    }
    if correlation_id is not None:
        detail["correlation_id"] = correlation_id
    return HTTPException(status_code=422, detail=detail)


def _validate_correlation_id(header_value: str | None, body_value: str | None) -> None:
    """Both places a correlation id can arrive are bounded, separately.

    Checked before `_resolve_correlation_id` picks one, because a conflict
    between two values is a different fault from either of them being unusable,
    and reporting the conflict first would hide the length problem behind it.
    A server-generated id is a UUID and needs no check.
    """

    for field, value in (
        (f"The {CORRELATION_HEADER} header", (header_value or "").strip()),
        ("correlation_id", (body_value or "").strip()),
    ):
        if len(value) > MAX_IDENTIFIER_CHARS:
            raise _too_long(
                code="correlation_id_too_long",
                field=field,
                value=value,
                limit=MAX_IDENTIFIER_CHARS,
                correlation_id=None,
            )


def _validate_request_fields(
    *,
    provision_id: str | None,
    calling_system_identity: str | None,
    reasoning_effort: str,
    idempotency_key: str | None,
    correlation_id: str,
) -> None:
    """Everything else a caller controls that has a fixed-width home.

    Takes plain values rather than the request model so it can be exercised on
    its own, and so adding a field to the body cannot quietly add an unchecked
    one here.
    """

    if len(idempotency_key or "") > MAX_IDENTIFIER_CHARS:
        raise _too_long(
            code="idempotency_key_too_long",
            field=f"The {IDEMPOTENCY_HEADER} header",
            value=idempotency_key or "",
            limit=MAX_IDENTIFIER_CHARS,
            correlation_id=correlation_id,
        )

    calling_system = (calling_system_identity or "").strip()
    if len(calling_system) > MAX_IDENTIFIER_CHARS:
        raise _too_long(
            code="calling_system_identity_too_long",
            field="calling_system_identity",
            value=calling_system,
            limit=MAX_IDENTIFIER_CHARS,
            correlation_id=correlation_id,
        )

    provision = (provision_id or "").strip()
    if len(provision) > MAX_IDENTIFIER_CHARS:
        raise _too_long(
            code="provision_id_too_long",
            field="provision_id",
            value=provision,
            limit=MAX_IDENTIFIER_CHARS,
            correlation_id=correlation_id,
        )

    _validate_reasoning_effort(reasoning_effort, correlation_id=correlation_id)


def _validate_reasoning_effort(value: str, *, correlation_id: str) -> None:
    """The requested effort must be one this product accepts, and must fit.

    Two checks rather than one, because they are two different faults with two
    different fixes. A 400-character value is a client bug; `"maximum"` is a
    reasonable guess at a vocabulary that happens to be wrong, and the answer to
    it is the list of what is accepted.

    Note what is *not* done here: the value is not silently coerced. The decider
    already falls back to `medium` for anything it does not recognise, which is
    right for an in-product reviewer whose dropdown cannot produce a bad value
    anyway — but an external caller who asked for `high` and was quietly given
    `medium` would have a receipt saying `reasoning_effort_requested: "high"`
    and no way to learn the request was not honoured. Refusing says so.
    """

    requested = (value or "").strip()
    if len(requested) > MAX_REASONING_EFFORT_CHARS:
        raise _too_long(
            code="reasoning_effort_too_long",
            field="reasoning_effort",
            value=requested,
            limit=MAX_REASONING_EFFORT_CHARS,
            correlation_id=correlation_id,
        )
    if requested not in ai_case_intent.VALID_REASONING_EFFORTS:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "reasoning_effort_invalid",
                "message": (
                    f"reasoning_effort must be one of "
                    f"{', '.join(ai_case_intent.VALID_REASONING_EFFORTS)}."
                ),
                "correlation_id": correlation_id,
            },
        )


class ProjectCaseDecisionRequest(BaseModel):
    """The body of an external case decision."""

    scenario: str = Field(
        description=(
            "The case, in natural language, in any language. Stored on the receipt verbatim so it "
            "shows the question it answered, and hashed as sent — a rendering never enters the "
            "idempotency binding. The text every stage actually read is returned beside it in "
            "`language.processing_scenario`."
        )
    )
    provision_id: str | None = Field(
        default=None,
        description=(
            "Optional. Naming one policy bypasses retrieval and decides against that policy alone. "
            "Omitted, the case is put to the project and the policies bearing on it are retrieved."
        ),
    )
    reasoning_effort: str = Field(
        default="medium",
        description=(
            "Requested reasoning effort: `low`, `medium` or `high`. Anything else is a 422 rather "
            "than a silent fallback — a receipt recording `reasoning_effort_requested: \"maximum\"` "
            "for a call that ran at medium would be misleading. A deployment may still decline the "
            "requested effort at the model, which is why only the request is recorded."
        ),
    )
    additional_instructions: str = Field(
        default="",
        description=(
            "Optional guidance about how you want the explanation presented — what to emphasise, "
            "how long to be, what format to use.\n\n"
            "**This shapes the emphasis and wording of the explanation only. It cannot change the "
            "authoritative policy contract.** Specifically, it cannot change which policies were "
            "retrieved or read, what any rule means, which tracks ran, either track's status, the "
            "verdict, the requirement to cite every rule the answer rests on, or the prohibition "
            "on drawing on anything outside the published records. Guidance that asks for any of "
            "those is ignored for that part, and the affected section's `note` says so.\n\n"
            "It is never sent to the retrieval step or to the classifier, so it can steer neither "
            "which policies are considered nor what your question is read as asking for. Maximum "
            "2000 characters after whitespace normalisation; longer is a 422. "
            "The normalised text is stored on the receipt, echoed back in `request."
            "additional_instructions`, and included in the idempotency binding — so reusing an "
            "`Idempotency-Key` with different guidance is a 409, not a replay.\n\n"
            "The server's own instructions are not caller-editable and are not returned; "
            "`trace.prompt_version` and `trace.instruction_profile` identify them instead."
        ),
    )
    correlation_id: str | None = Field(
        default=None,
        description=(
            "Optional. May also be sent as the X-Correlation-Id header; if both are sent they must "
            "match. When neither is sent the server generates one. Maximum 200 characters in "
            "either place."
        ),
    )
    calling_system_identity: str | None = Field(
        default=None,
        description=(
            "Optional free-text label for the calling system, maximum 200 characters. Unverified — "
            "it is recorded beside, never instead of, the authenticated principal."
        ),
    )


class ProjectPolicyRetrievalRequest(BaseModel):
    """A scenario used only to select the published policy records that bear on it."""

    scenario: str = Field(
        description=(
            "The natural-language situation to filter published policies against. It crosses the "
            "same one-language retrieval boundary as a decision, but no classifier, adjudicator, "
            "explanation, or receipt is run."
        )
    )
    correlation_id: str | None = Field(
        default=None,
        description=(
            "Optional. May also be sent as X-Correlation-Id; if both are sent they must match."
        ),
    )


def _resolve_correlation_id(header_value: str | None, body_value: str | None) -> str:
    """One correlation id out of up to two places it can arrive in.

    A conflict is refused rather than resolved by precedence. Silently
    preferring one would mean the id a caller sees in the response is not the id
    they put in their own log for this call, and the whole purpose of a
    correlation id is that both sides can name the same event.
    """

    header = (header_value or "").strip() or None
    body = (body_value or "").strip() or None

    if header and body and header != body:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "correlation_id_conflict",
                "message": (
                    f"The {CORRELATION_HEADER} header and the body's correlation_id are different "
                    "values. Send one, or send the same value in both."
                ),
            },
        )
    return header or body or str(uuid.uuid4())


def _request_metadata(
    request: Request, *, idempotency_key: str | None, correlation_id_supplied: bool
) -> dict:
    """What the receipt records about the call itself.

    Deliberately narrow. The scenario is stored in its own column and nothing
    here duplicates it, so this block can be read, logged and quoted freely
    without carrying the caller's prose with it.

    `correlation_id_supplied` is passed in rather than re-derived from the
    headers. A correlation id may arrive in the header *or* in the body, and
    reading only the header here recorded `false` for every caller who sent one
    in the body — an audit field that is wrong precisely for the callers who
    took the trouble to correlate. The resolution already happened above; this
    records what it resolved, instead of guessing at it a second time from half
    the inputs.
    """

    return {
        "method": request.method,
        "path": request.url.path,
        "user_agent": request.headers.get("user-agent"),
        "idempotency_key_supplied": bool(idempotency_key),
        "correlation_id_supplied": correlation_id_supplied,
    }


@router.post("/{project_key}/policies", response_model=PolicyRetrievalEnvelope)
async def retrieve_policies(
    project_key: str,
    body: ProjectPolicyRetrievalRequest,
    response: Response,
    correlation_id_header: str | None = Header(default=None, alias=CORRELATION_HEADER),
    _principal: Principal = Depends(require_authenticated_principal),
    session: AsyncSession = Depends(get_session),
) -> PolicyRetrievalEnvelope:
    """Return filtered published policy JSON without producing a verdict.

    This is the light integration path. It precision-ranks policy documents,
    cuts the ranking at a meaningful semantic score gap, and then uses the same
    duplicate collapse, rule-level narrowing, and payload fitting machinery as
    the audited decision endpoint. It stops before intent classification and
    every reasoning/generation stage. The response therefore has no decision id,
    verdict, explanation, citations synthesized by a gather, or receipt URL.

    The returned ``policies`` are the exact ``grounding_projection_v1`` records
    the decision path would have read. For a large policy, ``match.rule_selection``
    names the retained rules and the payload contains that slice only.
    """

    _validate_correlation_id(correlation_id_header, body.correlation_id)
    correlation_id = _resolve_correlation_id(correlation_id_header, body.correlation_id)
    response.headers[CORRELATION_HEADER] = correlation_id

    if not body.scenario.strip():
        raise HTTPException(
            status_code=422,
            detail={
                "code": "scenario_empty",
                "message": "scenario must contain non-whitespace text.",
                "correlation_id": correlation_id,
            },
        )

    policy_set = await PolicySetRepository(session).get_by_key(project_key)
    if policy_set is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "project_not_found",
                "message": f"No project with key '{project_key}'.",
                "correlation_id": correlation_id,
            },
        )

    try:
        return await retrieve_project_policies(
            session,
            policy_set=policy_set,
            scenario=body.scenario,
            correlation_id=correlation_id,
        )
    except CaseDecisionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc


async def _execute_case_decision(
    *,
    project_key: str,
    body: ProjectCaseDecisionRequest,
    request: Request,
    response: Response,
    idempotency_key: str | None,
    correlation_id_header: str | None,
    principal: Principal,
    session: AsyncSession,
) -> CaseDecisionEnvelopeV2 | CaseDecisionEnvelope:
    """One audited decision execution shared by full and light responses."""

    _validate_correlation_id(correlation_id_header, body.correlation_id)
    correlation_id_supplied = bool(
        (correlation_id_header or "").strip() or (body.correlation_id or "").strip()
    )
    correlation_id = _resolve_correlation_id(correlation_id_header, body.correlation_id)
    response.headers[CORRELATION_HEADER] = correlation_id

    idempotency_key = (idempotency_key or "").strip() or None
    provision_id = (body.provision_id or "").strip() or None
    calling_system_identity = (body.calling_system_identity or "").strip() or None
    reasoning_effort = (body.reasoning_effort or "").strip()
    _validate_request_fields(
        provision_id=provision_id,
        calling_system_identity=calling_system_identity,
        reasoning_effort=reasoning_effort,
        idempotency_key=idempotency_key,
        correlation_id=correlation_id,
    )

    policy_set = await PolicySetRepository(session).get_by_key(project_key)
    if policy_set is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "project_not_found",
                "message": f"No project with key '{project_key}'.",
                "correlation_id": correlation_id,
            },
        )

    try:
        outcome = await decide_project_case(
            session,
            policy_set=policy_set,
            scenario=body.scenario,
            provision_id=provision_id,
            reasoning_effort=reasoning_effort,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
            caller=Caller(
                identity=principal.identity,
                role=principal.role,
                authentication_source=principal.source,
                calling_system_identity=calling_system_identity,
            ),
            additional_instructions=body.additional_instructions,
            request_metadata=_request_metadata(
                request,
                idempotency_key=idempotency_key,
                correlation_id_supplied=correlation_id_supplied,
            ),
        )
    except CaseDecisionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc

    response.headers[CORRELATION_HEADER] = outcome.envelope.correlation_id
    return outcome.envelope


@router.post("/{project_key}/case", response_model=CaseDecisionReceipt)
async def decide_case(
    project_key: str,
    body: ProjectCaseDecisionRequest,
    request: Request,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias=IDEMPOTENCY_HEADER),
    correlation_id_header: str | None = Header(default=None, alias=CORRELATION_HEADER),
    principal: Principal = Depends(require_authenticated_principal),
    session: AsyncSession = Depends(get_session),
) -> CaseDecisionEnvelopeV2 | CaseDecisionEnvelope:
    """Decide a case against a project's published policies, and record it.

    Every decision made now is answered as `case_decision_v2`. The response is
    typed as the union of that and the older `case_decision_v1` for one reason:
    an `Idempotency-Key` issued before the redesign replays the receipt it named,
    in the shape that receipt was written in. Branch on `schema_version` if you
    hold keys from then; a caller starting today will only ever see v2.

    The decision itself is the existing project-case decider, unchanged in the
    part that matters: the policies bearing on the question are retrieved and the
    rest discarded before anything is evaluated, and the answer is grounded to
    the retained records. What this operation adds is everything an external
    caller needs to rely on that answer afterwards.

    A CASE ASKS FOR UP TO TWO THINGS

    Your question is read as two independent requests: does it ask what the
    retained published policies **state**, and does it ask for the case to be
    **evaluated** and a verdict returned. A question can ask for either or both,
    and both requested answers are gathered — over the same retrieved policies,
    concurrently. There is no request field for this: intent detection is the
    server's, because a caller who could declare "this is a verdict question"
    could choose the shape of their own answer.

    READ `outcome` BEFORE `information` OR `verdict`

    A completed receipt does not imply a determination. `outcome.information` and
    `outcome.verdict` each carry that track's status, plus `not_requested` (you
    did not ask for it, and the section is null) and `not_evaluated` (nothing was
    evaluated at all — the project may have published nothing, its index may not
    be built, or no published policy may bear on the question). Those are
    legitimate `200`s with a full receipt.

    Only `outcome.verdict: "answered"` carries a determination. `verdict.decision`
    is non-empty exactly when `verdict.reached` is true — so a "not compliant" is
    a reached verdict and a case that could not be decided leaves `decision`
    empty and reports `missing_information` instead.

    IDEMPOTENCY

    Send `Idempotency-Key` to make a retry safe. The key is bound to the
    authenticated caller, the project and a canonical hash of the request:
    replaying the same request returns the original receipt (same
    `decision_hash`, no second model call); reusing the key with a different
    body is a `409`; retrying while the first call is still running is a `409`.
    Without a key, every call is a new decision — two identical questions are
    two decisions, and this endpoint will not pretend otherwise.

    A key issued before the two-track receipt existed replays the receipt it
    named, in the shape it was written in. Check `schema_version`.

    CORRELATION

    Send your own id in `X-Correlation-Id` or in the body. Sending both with
    different values is a `422`. It is echoed in the body and in the response
    header either way.

    CALLER GUIDANCE

    `additional_instructions` shapes how the explanation is *presented* and
    nothing else. It cannot change which policies were retrieved, what a rule
    means, which tracks ran, either track's status, the verdict, or the
    requirement to cite — the published policies remain the authoritative
    contract, and guidance that asks otherwise is ignored for that part. It never
    reaches retrieval or the classifier, so it can steer neither which policies
    are considered nor what your question is read as asking for. The normalised
    text is returned in `request.additional_instructions`, so an integration can
    show exactly what was applied. The server's own instructions are not returned
    and are not editable; `trace.prompt_version` and `trace.instruction_profile`
    name them.

    LANGUAGE

    Ask in any language. Your question is carried into the one language this
    platform reasons in before any policy is read, every stage — retrieval,
    classification and both gathers — works in that language, and the
    explanation is carried back to the language you asked in afterwards. The
    `language` block reports both sides of that, including
    `processing_scenario`: the text that was actually adjudicated. Compare it
    with your own words if a decision surprises you.

    **Nothing machine-readable moves with the language.** Statuses, `asked.*`,
    `outcome`, `missing_information[].fact`, every citation's `rule_id`,
    `policy.provision_key` and verbatim `source.text`, `rule_selection.*`, every
    `retrieval.*` counter and `decision_hash` are byte-identical whatever
    language a reader asked in. Key on those. The verdict *string*, the labels
    and the explanations are prose and are language-dependent by design — that
    is what they are for.

    A document's own words are never translated: `citations[].source.text` is
    always the source sentence as stored, in the document's own language.

    `request.scenario`, its hash and the idempotency binding are over your own
    bytes, never over a rendering — so a byte-for-byte retry is still a replay.
    A replay returns the stored receipt without carrying anything across the
    boundary a second time.

    STATUS CODES

    `404` unknown project key, or a `provision_id` naming a policy in another
    project. `422` a malformed id, a conflicting correlation id,
    `additional_instructions` longer than 2000 characters after normalisation,
    a `scenario` longer than the boundary will carry, a `reasoning_effort`
    outside `low | medium | high`, or any of `X-Correlation-Id`,
    `correlation_id`, `Idempotency-Key`, `calling_system_identity` and
    `provision_id` longer than 200 characters — all of which are refused before
    anything is reserved, so a permanent input fault never presents as a
    retryable one. `401` no authenticated caller. `409` an idempotency conflict.
    `503` the model is not configured, the receipt could not be reserved — in
    which case no decision was attempted — or a language boundary that could not
    be crossed: `scenario_translation_unavailable` and
    `scenario_translation_empty` mean the question could not be carried into the
    language decisions are made in, and `response_translation_unavailable` means
    a decision was made but could not be returned in the language it was asked
    in. All three leave a failed receipt and carry no verdict, because a
    decision made from a question the platform could not read — or served half
    in one language and half in another — is not one this endpoint will ship.
    `500` with code `decision_receipt_failed` means a decision was made and
    could not be stored; it carries the decision and correlation ids and
    deliberately carries no verdict.
    """

    return await _execute_case_decision(
        project_key=project_key,
        body=body,
        request=request,
        response=response,
        idempotency_key=idempotency_key,
        correlation_id_header=correlation_id_header,
        principal=principal,
        session=session,
    )


@router.post("/{project_key}/case/light", response_model=CaseDecisionLightEnvelope)
async def decide_case_light(
    project_key: str,
    body: ProjectCaseDecisionRequest,
    request: Request,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias=IDEMPOTENCY_HEADER),
    correlation_id_header: str | None = Header(default=None, alias=CORRELATION_HEADER),
    principal: Principal = Depends(require_authenticated_principal),
    session: AsyncSession = Depends(get_session),
) -> CaseDecisionLightEnvelope:
    """Run and store the same decision, returning only its essential projection.

    ``receipt_url`` reads the complete stored receipt. The compact response keeps
    tracking ids, project/version identity, response type, outcomes, answer or
    verdict, missing/check fields, cited policy ids, necessary citations, and
    the integrity seal. It omits retrieval internals, excluded candidates,
    grounding counters, language transport detail, and duplicate section-level
    citations.
    """

    envelope = await _execute_case_decision(
        project_key=project_key,
        body=body,
        request=request,
        response=response,
        idempotency_key=idempotency_key,
        correlation_id_header=correlation_id_header,
        principal=principal,
        session=session,
    )
    return compact_decision_receipt(envelope)


@router.get("/{decision_id}", response_model=CaseDecisionReceipt)
async def get_decision_receipt(
    decision_id: uuid.UUID,
    response: Response,
    principal: Principal = Depends(require_authenticated_principal),
    session: AsyncSession = Depends(get_session),
) -> CaseDecisionEnvelopeV2 | CaseDecisionEnvelope:
    """The stored receipt for one decision, byte-identical to what was returned.

    The envelope is replayed from storage rather than rebuilt, so verifying a
    receipt is a real check: the `decision_hash` a caller kept must equal the one
    served here, and it will not if the stored content ever changed.

    WHICH ENVELOPE YOU GET

    Whichever one was written. A decision made now is `case_decision_v2`; a
    decision made before the two-track redesign is still served as
    `case_decision_v1`, because re-projecting a stored receipt into a newer shape
    would mean inventing content that decision never had. `schema_version` names
    it, and the two shapes are a discriminated union on that field.

    WHO MAY READ IT

    The caller who made the decision, and any policy author or administrator. A
    receipt carries the requester's own free-text scenario, so it is not
    anonymously readable and not readable by an unrelated viewer — `403`.

    A receipt that never completed has no verdict to serve. `pending` is a `409`
    (the decision is still in flight) and `failed` is a `410` naming the failure,
    so neither can be mistaken for a decision that simply said nothing.
    """

    row = await PolicyCaseDecisionRepository(session).get_by_id(decision_id)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "decision_not_found", "message": f"No decision with id '{decision_id}'."},
        )

    is_owner = row.authenticated_principal_identity == principal.identity
    if not is_owner and principal.role not in _RECEIPT_READER_ROLES:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "decision_not_readable",
                "message": "This receipt may be read by the caller who made the decision, or by a policy author or administrator.",
            },
        )

    response.headers[CORRELATION_HEADER] = row.correlation_id

    if row.status == "pending":
        raise HTTPException(
            status_code=409,
            detail={
                "code": "decision_in_progress",
                "message": "This decision has been reserved but not yet completed.",
                "decision_id": str(row.id),
                "correlation_id": row.correlation_id,
            },
        )

    if row.status != "completed" or not row.response_json:
        raise HTTPException(
            status_code=410,
            detail={
                "code": row.failure_code or "decision_failed",
                "message": row.failure_message or "This decision failed and carries no verdict.",
                "decision_id": str(row.id),
                "correlation_id": row.correlation_id,
            },
        )

    return validate_receipt(row.response_json)
