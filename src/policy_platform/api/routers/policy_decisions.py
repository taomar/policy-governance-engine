"""The audited external decision API: put a case, receive a receipt.

WHY THIS IS NOT UNDER `/api/ai`

The project-case decider has been reachable for some time at
`POST /api/ai/policy-sets/{key}/case-answer`. That path is the wrong public
seam for an integration in two ways that have nothing to do with the code behind
it: `/api/ai/…` reads as an implementation namespace and carries no
compatibility promise, and the response it returns is an answer rather than a
receipt — nothing correlates a caller's request to a server-side record, so no
external system can cite, replay or audit a verdict it was given.

So this router is the stable contract. Two operations, deliberately:

  * `POST /api/policy-decisions/{project_key}/case` — decide, and record.
  * `GET  /api/policy-decisions/{decision_id}` — read the receipt back.

There is no list endpoint and no identity endpoint here. A caller composing a
console already has `GET /api/policy-sets/{key}` and
`GET /api/policy-sets/{key}/active-version`; a third read contract over the same
data would be one more thing to keep in step with them.

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
    decide_project_case,
)
from policy_platform.contracts.case_decision import CaseDecisionEnvelope
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
        description="The case, in natural language. Stored on the receipt so it shows the question it answered."
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
            "retrieved or read, what any rule means, the `decision_status`, the verdict, the "
            "requirement to cite every rule the answer rests on, or the prohibition on drawing on "
            "anything outside the published records. Guidance that asks for any of those is ignored "
            "for that part, and the answer's `decision.note` says so.\n\n"
            "It is never sent to the retrieval step, so it cannot steer which policies are "
            "considered. Maximum 2000 characters after whitespace normalisation; longer is a 422. "
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


@router.post("/{project_key}/case", response_model=CaseDecisionEnvelope)
async def decide_case(
    project_key: str,
    body: ProjectCaseDecisionRequest,
    request: Request,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias=IDEMPOTENCY_HEADER),
    correlation_id_header: str | None = Header(default=None, alias=CORRELATION_HEADER),
    principal: Principal = Depends(require_authenticated_principal),
    session: AsyncSession = Depends(get_session),
) -> CaseDecisionEnvelope:
    """Decide a case against a project's published policies, and record it.

    The decision itself is the existing project-case decider, unchanged: the
    policies bearing on the question are retrieved and the rest discarded before
    anything is evaluated, and the answer is grounded to the retained records.
    What this operation adds is everything an external caller needs to rely on
    that answer afterwards.

    READ `decision_status` BEFORE `decision.verdict`

    A completed receipt does not imply a determination. `not_evaluated` means
    retrieval produced no evaluation — the project may have published nothing,
    its index may not be built, or no published policy may bear on the question.
    Those are legitimate outcomes with a `200` and a full receipt, and their
    `verdict` is empty. Only `decision_status: "answered"` carries one.

    IDEMPOTENCY

    Send `Idempotency-Key` to make a retry safe. The key is bound to the
    authenticated caller, the project and a canonical hash of the request:
    replaying the same request returns the original receipt (same
    `decision_hash`, no second model call); reusing the key with a different
    body is a `409`; retrying while the first call is still running is a `409`.
    Without a key, every call is a new decision — two identical questions are
    two decisions, and this endpoint will not pretend otherwise.

    CORRELATION

    Send your own id in `X-Correlation-Id` or in the body. Sending both with
    different values is a `422`. It is echoed in the body and in the response
    header either way.

    CALLER GUIDANCE

    `additional_instructions` shapes how the explanation is *presented* and
    nothing else. It cannot change which policies were retrieved, what a rule
    means, the `decision_status`, the verdict, or the requirement to cite — the
    published policies remain the authoritative contract, and guidance that asks
    otherwise is ignored for that part. It never reaches retrieval, so it cannot
    steer which policies are considered. The normalised text is returned in
    `request.additional_instructions`, so an integration can show exactly what
    was applied. The server's own instructions are not returned and are not
    editable; `trace.prompt_version` and `trace.instruction_profile` name them.

    STATUS CODES

    `404` unknown project key, or a `provision_id` naming a policy in another
    project. `422` a malformed id, a conflicting correlation id,
    `additional_instructions` longer than 2000 characters after normalisation,
    a `reasoning_effort` outside `low | medium | high`, or any of
    `X-Correlation-Id`, `correlation_id`, `Idempotency-Key`,
    `calling_system_identity` and `provision_id` longer than 200 characters —
    all of which are refused before anything is reserved, so a permanent input
    fault never presents as a retryable one. `401` no authenticated caller.
    `409` an idempotency conflict. `503` the model is not configured, or the
    receipt could not be reserved — in which case no decision was attempted.
    `500` with code `decision_receipt_failed` means a decision was made and
    could not be stored; it carries the decision and correlation ids and
    deliberately carries no verdict.
    """

    # Shape first, in this order: bound the correlation id before resolving one
    # (so an unusable value is reported as itself rather than as a conflict),
    # then echo the resolved id so every refusal below can carry it, then bound
    # everything else. All of it happens before the project is looked up, before
    # a row is reserved and before the model is called — a request that can
    # never be stored costs no database write and no model time.
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

    # A replay is the same decision, not a new one, so the correlation echoed is
    # the receipt's own — the id the stored decision was made under.
    response.headers[CORRELATION_HEADER] = outcome.envelope.correlation_id
    return outcome.envelope


@router.get("/{decision_id}", response_model=CaseDecisionEnvelope)
async def get_decision_receipt(
    decision_id: uuid.UUID,
    response: Response,
    principal: Principal = Depends(require_authenticated_principal),
    session: AsyncSession = Depends(get_session),
) -> CaseDecisionEnvelope:
    """The stored receipt for one decision, byte-identical to what was returned.

    The envelope is replayed from storage rather than rebuilt, so verifying a
    receipt is a real check: the `decision_hash` a caller kept must equal the one
    served here, and it will not if the stored content ever changed.

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

    return CaseDecisionEnvelope.model_validate(row.response_json)
