"""Viewer feedback on published policy versions.

A viewer can submit comments/feedback on any published policy version. The
feedback has its own lifecycle (open → acknowledged → actioned/dismissed,
or open → withdrawn) entirely separate from the policy version's lifecycle.
Submitting, acknowledging, resolving, or withdrawing feedback never touches
the ``ApprovedPolicyVersion`` row — the structural isolation in the data
model makes this invariant impossible to break without adding a column.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from policy_platform.api.schemas import (
    AcknowledgePolicyReviewRequestRequest,
    CreatePolicyReviewRequestRequest,
    PolicyReviewRequestResponse,
    ResolvePolicyReviewRequestRequest,
)
from policy_platform.infrastructure.persistence.db import get_session
from policy_platform.infrastructure.persistence.repositories.review_requests import (
    PolicyReviewRequestRepository,
)
from policy_platform.infrastructure.persistence.repositories.versions import (
    ApprovedPolicyVersionRepository,
)

router = APIRouter(prefix="/api/policy-review-requests", tags=["policy-review-requests"])


def _to_response(row) -> PolicyReviewRequestResponse:
    return PolicyReviewRequestResponse(
        id=str(row.id),
        policy_set_key=row.policy_set_key,
        approved_policy_version_id=str(row.approved_policy_version_id),
        submitted_by=row.submitted_by,
        submitted_at=row.submitted_at,
        comment=row.comment,
        categories=row.categories,
        status=row.status,
        resolved_by=row.resolved_by,
        resolved_at=row.resolved_at,
        resolution_note=row.resolution_note,
        created_at=row.created_at,
    )


@router.post("", response_model=PolicyReviewRequestResponse, status_code=201)
async def submit_review_request(
    payload: CreatePolicyReviewRequestRequest,
    session: AsyncSession = Depends(get_session),
) -> PolicyReviewRequestResponse:
    version_id = uuid.UUID(payload.approved_policy_version_id)

    # The FK on approved_policy_version_id is the structural backstop, but a
    # viewer who sends a stale or mistyped id deserves a 404 they can act on,
    # not a 500 that reads as "the product is broken". Check first; catch the
    # race (row deleted between check and insert) below.
    version_repo = ApprovedPolicyVersionRepository(session)
    version = await version_repo.get_by_id(version_id)
    if version is None:
        raise HTTPException(
            status_code=404,
            detail=f"approved policy version '{payload.approved_policy_version_id}' not found",
        )

    repo = PolicyReviewRequestRepository(session)
    try:
        row = await repo.create(
            policy_set_key=payload.policy_set_key,
            approved_policy_version_id=version_id,
            submitted_by=payload.submitted_by,
            comment=payload.comment,
            categories=payload.categories,
        )
        await session.commit()
    except IntegrityError:
        # The version existed at check time but was deleted before the insert
        # landed — the FK caught it. Same answer as the check: the version is
        # gone, so the feedback has nowhere to attach.
        await session.rollback()
        raise HTTPException(
            status_code=404,
            detail=f"approved policy version '{payload.approved_policy_version_id}' not found",
        )
    return _to_response(row)


@router.get("", response_model=list[PolicyReviewRequestResponse])
async def list_review_requests(
    policy_set_key: str | None = None,
    status: str | None = None,
    submitted_by: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[PolicyReviewRequestResponse]:
    repo = PolicyReviewRequestRepository(session)
    rows = await repo.list_filtered(
        policy_set_key=policy_set_key,
        status=status,
        submitted_by=submitted_by,
    )
    return [_to_response(r) for r in rows]


@router.post("/{request_id}/acknowledge", response_model=PolicyReviewRequestResponse)
async def acknowledge_review_request(
    request_id: uuid.UUID,
    payload: AcknowledgePolicyReviewRequestRequest,
    session: AsyncSession = Depends(get_session),
) -> PolicyReviewRequestResponse:
    repo = PolicyReviewRequestRepository(session)
    row = await repo.get_by_id(request_id)
    if row is None:
        raise HTTPException(status_code=404, detail="review request not found")
    if row.status != "open":
        raise HTTPException(
            status_code=409,
            detail=f"cannot acknowledge a request whose status is '{row.status}'",
        )
    row = await repo.acknowledge(row, resolved_by=payload.resolved_by)
    await session.commit()
    return _to_response(row)


@router.post("/{request_id}/resolve", response_model=PolicyReviewRequestResponse)
async def resolve_review_request(
    request_id: uuid.UUID,
    payload: ResolvePolicyReviewRequestRequest,
    session: AsyncSession = Depends(get_session),
) -> PolicyReviewRequestResponse:
    repo = PolicyReviewRequestRepository(session)
    row = await repo.get_by_id(request_id)
    if row is None:
        raise HTTPException(status_code=404, detail="review request not found")
    if row.status not in ("open", "acknowledged"):
        raise HTTPException(
            status_code=409,
            detail=f"cannot resolve a request whose status is '{row.status}'",
        )
    if payload.disposition == "dismissed" and not payload.resolution_note:
        raise HTTPException(
            status_code=422,
            detail="resolution_note is required when dismissing a review request",
        )
    row = await repo.resolve(
        row,
        disposition=payload.disposition,
        resolved_by=payload.resolved_by,
        resolution_note=payload.resolution_note,
    )
    await session.commit()
    return _to_response(row)


@router.delete("/{request_id}", status_code=204, response_model=None)
async def withdraw_review_request(
    request_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> None:
    repo = PolicyReviewRequestRepository(session)
    row = await repo.get_by_id(request_id)
    if row is None:
        raise HTTPException(status_code=404, detail="review request not found")
    if row.status != "open":
        raise HTTPException(
            status_code=409,
            detail=f"cannot withdraw a request whose status is '{row.status}'",
        )
    await repo.withdraw(row)
    await session.commit()
