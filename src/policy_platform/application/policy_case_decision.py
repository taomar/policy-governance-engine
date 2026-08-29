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
deliberately not this one. `ai_case_project` admits it to the evaluation gather
and to nothing else — never the retrieval query, so it cannot steer which
policies are read; never the intent classifier, so it cannot choose whether the
answer is a determination. `ai_case_intent.caller_guidance_block` wraps it in
the invariants it may not cross and marks it lowest priority. This module's job
is to make sure the exact text that was applied is the exact text that is
recorded.
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from policy_platform.contracts.case_decision import (
    CHANNEL_API,
    HASH_BASIS,
    MAX_ADDITIONAL_INSTRUCTIONS_CHARS,
    NOT_EVALUATED,
    SCHEMA_VERSION,
    STATUS_WITH_VERDICT,
    CallerRef,
    CaseDecisionEnvelope,
    CitationRef,
    CitationSourceRef,
    DecisionRef,
    PolicyRef,
    PolicySetRef,
    RequestRef,
    RetrievalRef,
    SizeRef,
    TraceRef,
    VersionRef,
    additional_instructions_hash,
    compute_decision_hash,
    normalise_additional_instructions,
    request_hash,
    scenario_hash,
)
from policy_platform.domain.models import DocumentProvision, PolicyCaseDecision
from policy_platform.infrastructure.assistants import ai_case_intent, ai_case_project
from policy_platform.infrastructure.persistence.repositories.case_decisions import (
    PolicyCaseDecisionRepository,
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

#: The decision statuses a receipt may carry, mirroring the contract's closed
#: set. Anything the gather produced that is not in here is recorded as `failed`
#: rather than passed through, because an unrecognised status is not a verdict.
_KNOWN_DECISION_STATUSES = frozenset(
    {
        "answered",
        "missing_required_facts",
        "not_settled_by_rules",
        "no_rule_bears",
        "declined",
        "failed",
    }
)


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
    """A finalised receipt and whether it was decided now or replayed."""

    envelope: CaseDecisionEnvelope
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
    """

    return await _invoke_decider(
        session,
        policy_set=policy_set,
        scenario=scenario,
        provision_id=provision_id,
        reasoning_effort=reasoning_effort,
        additional_instructions="",
        with_context=False,
    )


# ── the audited path ─────────────────────────────────────────────────


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
    """Decide a project case and answer with a persisted receipt.

    `policy_set` is the resolved project — the route has already turned the
    public key into a row and answered 404 if it named nothing.

    `additional_instructions` is optional caller guidance about how the
    explanation should be presented. It is normalised and length-checked here,
    *before* anything is reserved, so an over-long block costs no row and no
    model call. It is then bound into the idempotency request hash, recorded in
    the reservation's metadata with its digest, echoed on the receipt and sealed
    — and passed to the decider, which admits it only to the gather.

    Raises `CaseDecisionError` for every outcome that is not a receipt: guidance
    that is too long, an idempotency conflict, a reservation that could not be
    written, a decider refusal (unknown policy, malformed id, model
    unavailable), and a finalisation that failed. It never returns a verdict
    that was not stored.
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

    # ── decide, with no transaction held ──────────────────────────────
    try:
        answer = await _invoke_decider(
            session,
            policy_set=policy_set,
            scenario=scenario,
            provision_id=normalised_provision_id,
            reasoning_effort=reasoning_effort,
            additional_instructions=guidance,
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

    decided_at = datetime.now(timezone.utc)
    latency_ms = max(0, int((time.perf_counter() - started) * 1000))

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
        received_at=received_at,
        decided_at=decided_at,
        latency_ms=latency_ms,
        response=answer.response,
        context=answer.context,
        provision_ids=await _provision_ids_by_key(
            session, policy_set_id=project_id, response=answer.response
        ),
    )

    try:
        await repo.finalize_completed(
            row,
            policy_version_id=_version_uuid(answer.context.get("policy_version_id")),
            version_number=answer.context.get("version_number"),
            decision_status=envelope.decision_status,
            scope=envelope.request.scope,
            retrieval=envelope.retrieval.model_dump(mode="json"),
            decision_summary=envelope.decision.model_dump(mode="json"),
            citation_ids=[citation.rule_id for citation in envelope.citations],
            trace=envelope.trace.model_dump(mode="json"),
            response=envelope.model_dump(mode="json"),
            decision_hash=envelope.decision_hash,
            hash_basis=HASH_BASIS,
            decided_at=decided_at,
            latency_ms=latency_ms,
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

    return CaseDecisionOutcome(envelope=envelope, replayed=False)


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
        return CaseDecisionOutcome(
            envelope=CaseDecisionEnvelope.model_validate(row.response_json), replayed=True
        )

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
    """Every provision key the receipt will mention, from all three places."""

    keys: set[str] = set()
    for entry in (response.get("considered") or []) + (response.get("excluded") or []):
        key = entry.get("provision_key")
        if key:
            keys.add(str(key))
    provision = response.get("provision")
    if provision and provision.get("provision_key"):
        keys.add(str(provision["provision_key"]))
    branch = _branch(response.get("evaluation"))
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
    provision_ids: dict[str, str] | None = None,
) -> CaseDecisionEnvelope:
    """Project the decider's answer and its context into `case_decision_v1`.

    Kept a module-level function rather than folded into `decide_project_case`
    so the projection can be exercised on its own — the hash, the status guard
    and the "no policy payload" rule are properties of this function, not of the
    endpoint that calls it.

    `project` is a plain value rather than the ORM row, so this cannot trigger a
    lazy load while assembling a response. `provision_ids` maps a policy's
    stable provision key to the provision row that serves its payload; see
    `_provision_ids_by_key` for why the published record does not carry one.

    `additional_instructions` is expected already normalised — this function
    echoes and hashes what it is given, and normalising here as well would let
    the value that was *sent to the model* differ from the value that was
    *sealed*, which is the one thing the echo exists to rule out.
    """

    ids = provision_ids or {}
    evaluation = response.get("evaluation")
    decision = _decision_ref(evaluation)
    citations = _citations(evaluation, provision_ids=ids)

    considered = _considered_refs(response, provision_ids=ids)
    excluded = [_policy_ref(entry, provision_ids=ids) for entry in (response.get("excluded") or [])]

    envelope = CaseDecisionEnvelope(
        schema_version=SCHEMA_VERSION,
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
        decision_status=decision.status,
        retrieval=RetrievalRef(**_retrieval_fields(response.get("retrieval") or {})),
        considered=considered,
        excluded=excluded,
        decision=decision,
        citations=citations,
        grounding=_grounding(evaluation),
        size=SizeRef(**(response.get("size") or {})) if response.get("size") else None,
        trace=_trace_ref(response, context, evaluated=evaluation is not None),
        decision_hash="",
        hash_basis=HASH_BASIS,
        receipt_url=RECEIPT_PATH.format(decision_id=decision_id),
        decided_at=decided_at,
        latency_ms=latency_ms,
    )
    # Assigned after construction because the hash is taken over the envelope's
    # own decision-defining content and cannot exist before it.
    envelope.decision_hash = compute_decision_hash(envelope)
    return envelope


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
    "policy_budget",
    "policy_scan",
    "policies_retrieved",
    "policies_considered",
    "policies_retained",
    "policies_discarded",
    "policies_untestable",
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
    """One policy reference — identity and a link, never the record itself."""

    provision_key = entry.get("provision_key")
    provision_id = entry.get("provision_id") or (provision_ids or {}).get(str(provision_key or ""))
    return PolicyRef(
        provision_id=str(provision_id) if provision_id else None,
        provision_key=provision_key,
        heading_path=list(entry.get("heading_path") or []),
        rules=entry.get("rules"),
        retained=entry.get("retained"),
        best_rank=entry.get("best_rank"),
        best_score=entry.get("best_score"),
        discard_reason=entry.get("discard_reason"),
        reason=entry.get("reason"),
        payload_url=_payload_url(provision_id),
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


def _branch(evaluation: dict | None) -> dict | None:
    """The gather's answer, from whichever branch its intent selected."""

    if not evaluation:
        return None
    intent = evaluation.get("intent")
    if intent == "decision":
        return evaluation.get("decision")
    if intent == "informational":
        return evaluation.get("informational")
    return evaluation.get("decision") or evaluation.get("informational")


def _decision_ref(evaluation: dict | None) -> DecisionRef:
    """The decision block, with `not_evaluated` kept apart from every verdict.

    A retrieval that produced no evaluation is a real outcome and a common one —
    a project with nothing published, an index not built, no policy bearing on
    the question. It is reported as `not_evaluated` with an empty verdict, so no
    client can read "we did not evaluate" as "the policies say no".
    """

    branch = _branch(evaluation)
    if branch is None:
        return DecisionRef(
            intent=(evaluation or {}).get("intent"),
            classification_reasoning=(evaluation or {}).get("classification_reasoning"),
            status=NOT_EVALUATED,
            verdict="",
            explanation="",
            missing_required_facts=[],
            note="",
            decider_route=None,
        )

    status = str(branch.get("status") or "").strip().lower()
    if status not in _KNOWN_DECISION_STATUSES:
        status = "failed"

    return DecisionRef(
        intent=evaluation.get("intent") if evaluation else None,
        classification_reasoning=(evaluation or {}).get("classification_reasoning"),
        status=status,  # type: ignore[arg-type]
        # The gather already empties the verdict for every non-answered status;
        # re-asserting it here means the receipt's own guard does not depend on
        # that remaining true.
        verdict=str(branch.get("verdict") or "") if status == STATUS_WITH_VERDICT else "",
        explanation=str(branch.get("answer") or ""),
        missing_required_facts=[str(item) for item in (branch.get("missing_required_facts") or [])],
        note=str(branch.get("note") or ""),
        decider_route=(evaluation or {}).get("intent"),
    )


def _citations(evaluation: dict | None, *, provision_ids: dict[str, str] | None = None) -> list[CitationRef]:
    branch = _branch(evaluation)
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


def _grounding(evaluation: dict | None) -> dict | None:
    branch = _branch(evaluation)
    if not branch:
        return None
    grounding = branch.get("grounding")
    return dict(grounding) if isinstance(grounding, dict) else None


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
    grounding = _grounding(response.get("evaluation")) or {}
    retrieval = response.get("retrieval") or {}

    return TraceRef(
        prompt_version=grounding.get("prompt_version"),
        instruction_profile=ai_case_intent.CALLER_GUIDANCE_PROFILE if evaluated else None,
        model_deployment=settings.azure_openai_deployment if evaluated else None,
        retrieval_method=retrieval.get("method") or context.get("retrieval_method"),
        index_name=context.get("index_name"),
        index_version_id=context.get("index_version_id"),
    )
