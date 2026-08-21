"""Repository for viewer-submitted policy review requests.

Mutable in place for the status transitions (open → acknowledged,
open|acknowledged → actioned|dismissed, open → withdrawn) — same
posture as `PolicyExceptionRepository` and `PolicyTestRepository`:
a request record, not an immutable governance artifact.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from policy_platform.domain.models import PolicyReviewRequest


class PolicyReviewRequestRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        policy_set_key: str,
        approved_policy_version_id: uuid.UUID,
        submitted_by: str,
        comment: str,
        categories: list[str] | None = None,
    ) -> PolicyReviewRequest:
        row = PolicyReviewRequest(
            policy_set_key=policy_set_key,
            approved_policy_version_id=approved_policy_version_id,
            submitted_by=submitted_by,
            submitted_at=datetime.now(timezone.utc),
            comment=comment,
            categories=categories,
            status="open",
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def list_filtered(
        self,
        *,
        policy_set_key: str | None = None,
        status: str | None = None,
        submitted_by: str | None = None,
    ) -> list[PolicyReviewRequest]:
        stmt = select(PolicyReviewRequest)
        if policy_set_key is not None:
            stmt = stmt.where(PolicyReviewRequest.policy_set_key == policy_set_key)
        if status is not None:
            stmt = stmt.where(PolicyReviewRequest.status == status)
        if submitted_by is not None:
            stmt = stmt.where(PolicyReviewRequest.submitted_by == submitted_by)
        stmt = stmt.order_by(PolicyReviewRequest.submitted_at.desc())
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id(self, request_id: uuid.UUID) -> PolicyReviewRequest | None:
        result = await self._session.execute(
            select(PolicyReviewRequest).where(PolicyReviewRequest.id == request_id)
        )
        return result.scalar_one_or_none()

    async def acknowledge(
        self, row: PolicyReviewRequest, *, resolved_by: str
    ) -> PolicyReviewRequest:
        row.status = "acknowledged"
        row.resolved_by = resolved_by
        row.resolved_at = datetime.now(timezone.utc)
        await self._session.flush()
        return row

    async def resolve(
        self,
        row: PolicyReviewRequest,
        *,
        disposition: str,
        resolved_by: str,
        resolution_note: str | None,
    ) -> PolicyReviewRequest:
        row.status = disposition
        row.resolved_by = resolved_by
        row.resolved_at = datetime.now(timezone.utc)
        row.resolution_note = resolution_note
        await self._session.flush()
        return row

    async def withdraw(self, row: PolicyReviewRequest) -> None:
        row.status = "withdrawn"
        row.resolved_at = datetime.now(timezone.utc)
        await self._session.flush()
