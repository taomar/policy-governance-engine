"""PolicyAttestation endpoints (ADR-0012).

Employee attestation/acknowledgment tracking (ISO 37301 §7.3): a Policy
Manager launches a campaign assigning one published policy version's
acknowledgment obligation to a batch of employees with a shared due date;
each employee finds and acknowledges their own pending item via a no-login,
name/identifier-based self-service search (see domain/models.py::
PolicyAttestation for the full design rationale).

Two read surfaces intentionally overlap the same table for two different
audiences:
- `list_policy_attestations` — manager oversight, scoped to one policy set.
- `search_policy_attestations` — employee self-service, spans every policy
  set, matched by name/identifier since there is no login.
"""
from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from policy_platform.api.schemas import (
    AcknowledgePolicyAttestationRequest,
    CreatePolicyAttestationCampaignRequest,
    PolicyAttestationResponse,
)
from policy_platform.domain.models import PolicyAttestation
from policy_platform.infrastructure.db import get_session
from policy_platform.infrastructure.repositories import (
    ApprovedPolicyVersionRepository,
    PolicyAttestationRepository,
    PolicySetRepository,
)

router = APIRouter(prefix="/api/policy-attestations", tags=["policy-attestations"])


def _require_manager(actor_role: str) -> None:
    if actor_role != "policy_manager":
        raise HTTPException(
            status_code=403,
            detail="Only a Policy Manager can perform this action. Switch your acting role in the header.",
        )


def _status_of(row: PolicyAttestation) -> str:
    if row.acknowledged_at is not None:
        return "acknowledged"
    if row.due_date < date.today():
        return "overdue"
    return "pending"


def _to_response(row: PolicyAttestation, *, version_number: int) -> PolicyAttestationResponse:
    return PolicyAttestationResponse(
        id=str(row.id),
        policy_set_id=str(row.policy_set_id),
        policy_version_id=str(row.policy_version_id),
        version_number=version_number,
        employee_name=row.employee_name,
        employee_identifier=row.employee_identifier,
        due_date=row.due_date,
        assigned_by=row.assigned_by,
        acknowledged_at=row.acknowledged_at,
        acknowledgment_notes=row.acknowledgment_notes,
        status=_status_of(row),
        created_at=row.created_at,
    )


async def _require_policy_set(session: AsyncSession, key: str):
    policy_set = await PolicySetRepository(session).get_by_key(key)
    if policy_set is None:
        raise HTTPException(status_code=404, detail=f"policy set '{key}' not found")
    return policy_set


@router.get("/policy-sets/{key}", response_model=list[PolicyAttestationResponse])
async def list_policy_attestations(
    key: str,
    status: str | None = Query(default=None, pattern="^(pending|acknowledged|overdue)$"),
    session: AsyncSession = Depends(get_session),
) -> list[PolicyAttestationResponse]:
    policy_set = await _require_policy_set(session, key)
    rows = await PolicyAttestationRepository(session).list_by_policy_set(policy_set.id, status=status)
    # Version numbers are denormalized into the response for display; batch-resolve
    # rather than N+1-querying since a campaign is usually one version for many rows.
    version_repo = ApprovedPolicyVersionRepository(session)
    version_numbers: dict[uuid.UUID, int] = {}
    for row in rows:
        if row.policy_version_id not in version_numbers:
            version = await version_repo.get_by_id(row.policy_version_id)
            version_numbers[row.policy_version_id] = version.version_number if version else 0
    return [_to_response(r, version_number=version_numbers[r.policy_version_id]) for r in rows]


@router.post("/policy-sets/{key}/campaigns", response_model=list[PolicyAttestationResponse], status_code=201)
async def create_attestation_campaign(
    key: str,
    body: CreatePolicyAttestationCampaignRequest,
    session: AsyncSession = Depends(get_session),
) -> list[PolicyAttestationResponse]:
    _require_manager(body.actor_role)
    policy_set = await _require_policy_set(session, key)
    try:
        version_id = uuid.UUID(body.policy_version_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="policy_version_id must be a valid UUID") from exc
    version = await ApprovedPolicyVersionRepository(session).get_by_id(version_id)
    if version is None or version.policy_set_id != policy_set.id:
        raise HTTPException(
            status_code=404, detail=f"published version '{body.policy_version_id}' not found on policy set '{key}'"
        )
    rows = await PolicyAttestationRepository(session).bulk_create(
        policy_set_id=policy_set.id,
        policy_version_id=version.id,
        employees=[(e.name, e.identifier) for e in body.employees],
        due_date=body.due_date,
        assigned_by=body.assigned_by,
    )
    await session.commit()
    return [_to_response(r, version_number=version.version_number) for r in rows]


@router.get("/search", response_model=list[PolicyAttestationResponse])
async def search_policy_attestations(
    q: str = Query(..., min_length=1),
    session: AsyncSession = Depends(get_session),
) -> list[PolicyAttestationResponse]:
    """No-login, self-service lookup: an employee finds their own pending
    (and past) attestations across every policy set by typing their name or
    identifier — see domain.models.PolicyAttestation for why there's no
    real login to key this off instead.
    """
    rows = await PolicyAttestationRepository(session).search_by_employee(q)
    version_repo = ApprovedPolicyVersionRepository(session)
    version_numbers: dict[uuid.UUID, int] = {}
    for row in rows:
        if row.policy_version_id not in version_numbers:
            version = await version_repo.get_by_id(row.policy_version_id)
            version_numbers[row.policy_version_id] = version.version_number if version else 0
    return [_to_response(r, version_number=version_numbers[r.policy_version_id]) for r in rows]


@router.post("/{attestation_id}/acknowledge", response_model=PolicyAttestationResponse)
async def acknowledge_policy_attestation(
    attestation_id: uuid.UUID,
    body: AcknowledgePolicyAttestationRequest,
    session: AsyncSession = Depends(get_session),
) -> PolicyAttestationResponse:
    repo = PolicyAttestationRepository(session)
    row = await repo.get_by_id(attestation_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"attestation '{attestation_id}' not found")
    updated = await repo.acknowledge(row, acknowledgment_notes=body.acknowledgment_notes)
    await session.commit()
    version = await ApprovedPolicyVersionRepository(session).get_by_id(updated.policy_version_id)
    return _to_response(updated, version_number=version.version_number if version else 0)
