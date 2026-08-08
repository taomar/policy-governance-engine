"""PolicyException endpoints (ADR-0009).

Ad hoc, human-requested, time-bounded waivers of a rule (or an entire
policy set) for one particular case — decided by a human reviewer, never
auto-evaluated. Distinct from `RuleException` (an authoring-time carve-out
baked into a specific ApprovedRule's own definition, evaluated automatically
by the deterministic engine for every matching case — see domain/models.py
for the full contrast).

Fits inside the existing 3-actor model per ADR-0009: a composer or reviewer
requests it, a policy manager decides (grant/deny). No new actor, no
multi-level approval chain, no AI involved.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from policy_platform.api.schemas import (
    CreatePolicyExceptionRequest,
    DecidePolicyExceptionRequest,
    PolicyExceptionResponse,
)
from policy_platform.domain.models import PolicyException
from policy_platform.infrastructure.db import get_session
from policy_platform.infrastructure.repositories import PolicyExceptionRepository, PolicySetRepository

router = APIRouter(prefix="/api/policy-exceptions", tags=["policy-exceptions"])


def _to_response(row: PolicyException) -> PolicyExceptionResponse:
    is_expired = (
        row.decision == "granted"
        and row.expiry_date is not None
        and row.expiry_date < datetime.now(timezone.utc).date()
    )
    return PolicyExceptionResponse(
        id=str(row.id),
        policy_set_id=str(row.policy_set_id),
        rule_id=row.rule_id,
        requester=row.requester,
        justification=row.justification,
        decision=row.decision,
        expiry_date=row.expiry_date,
        decided_by=row.decided_by,
        decided_at=row.decided_at,
        decision_notes=row.decision_notes,
        is_expired=is_expired,
        created_at=row.created_at,
    )


async def _require_policy_set(session: AsyncSession, key: str):
    policy_set = await PolicySetRepository(session).get_by_key(key)
    if policy_set is None:
        raise HTTPException(status_code=404, detail=f"policy set '{key}' not found")
    return policy_set


@router.get("/policy-sets/{key}", response_model=list[PolicyExceptionResponse])
async def list_policy_exceptions(
    key: str,
    decision: str | None = None,
    rule_id: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[PolicyExceptionResponse]:
    policy_set = await _require_policy_set(session, key)
    rows = await PolicyExceptionRepository(session).list_by_policy_set(
        policy_set.id, decision=decision, rule_id=rule_id
    )
    return [_to_response(r) for r in rows]


@router.post("/policy-sets/{key}", response_model=PolicyExceptionResponse, status_code=201)
async def request_policy_exception(
    key: str, body: CreatePolicyExceptionRequest, session: AsyncSession = Depends(get_session)
) -> PolicyExceptionResponse:
    policy_set = await _require_policy_set(session, key)
    row = await PolicyExceptionRepository(session).create(
        policy_set_id=policy_set.id,
        rule_id=body.rule_id,
        requester=body.requester,
        justification=body.justification,
        expiry_date=body.expiry_date,
    )
    await session.commit()
    return _to_response(row)


@router.get("/{exception_id}", response_model=PolicyExceptionResponse)
async def get_policy_exception(
    exception_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> PolicyExceptionResponse:
    row = await PolicyExceptionRepository(session).get_by_id(exception_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"policy exception '{exception_id}' not found")
    return _to_response(row)


@router.post("/{exception_id}/decide", response_model=PolicyExceptionResponse)
async def decide_policy_exception(
    exception_id: uuid.UUID, body: DecidePolicyExceptionRequest, session: AsyncSession = Depends(get_session)
) -> PolicyExceptionResponse:
    """Grant or deny a pending request. Re-deciding an already-decided
    request is allowed (e.g. correcting a mistake) since this is a request
    record, not an immutable governance artifact — see
    `PolicyExceptionRepository` docstring.
    """
    repo = PolicyExceptionRepository(session)
    row = await repo.get_by_id(exception_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"policy exception '{exception_id}' not found")
    updated = await repo.decide(
        row, decision=body.decision, decided_by=body.decided_by, decision_notes=body.decision_notes
    )
    await session.commit()
    return _to_response(updated)
