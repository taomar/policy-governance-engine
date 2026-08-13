"""The append-only record of every decision the evaluator made.

Split from a single 1169-line module whose sixteen repository classes shared
no helper, no constant and no reference to one another -- so the seam was
already there and this only makes it visible.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from policy_platform.domain.models import (
    Evaluation,
)

class EvaluationRepository:
    """Append-only audit log of runtime evaluation calls."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(
        self,
        *,
        policy_set_id: uuid.UUID,
        policy_version_id: uuid.UUID,
        correlation_id: str | None,
        calling_system_identity: str | None,
        request_facts: dict,
        overall_status: str,
        result_hash: str,
        response_json: dict,
        evaluation_timestamp: datetime,
    ) -> Evaluation:
        evaluation = Evaluation(
            policy_set_id=policy_set_id,
            policy_version_id=policy_version_id,
            correlation_id=correlation_id,
            calling_system_identity=calling_system_identity,
            request_facts_json=request_facts,
            overall_status=overall_status,
            result_hash=result_hash,
            response_json=response_json,
            evaluation_timestamp=evaluation_timestamp or datetime.now(timezone.utc),
        )
        self._session.add(evaluation)
        await self._session.flush()
        return evaluation

    async def list_by_policy_set(
        self,
        policy_set_id: uuid.UUID,
        *,
        overall_status: str | None = None,
        correlation_id: str | None = None,
        calling_system_identity: str | None = None,
        limit: int = 100,
    ) -> list[Evaluation]:
        """Most recent evaluation calls first — the decision-log read path.

        Mirrors `audit.py`'s `list_audit_events`: optional AND-combined
        filters plus a hard `limit`, no separate COUNT(*) query, since the
        caller only needs to know "is there more than fits on one page"
        (see the `truncated` flag the router derives from `len(rows) == limit`).
        """
        stmt = select(Evaluation).where(Evaluation.policy_set_id == policy_set_id)
        if overall_status:
            stmt = stmt.where(Evaluation.overall_status == overall_status)
        if correlation_id:
            stmt = stmt.where(Evaluation.correlation_id == correlation_id)
        if calling_system_identity:
            stmt = stmt.where(Evaluation.calling_system_identity == calling_system_identity)
        stmt = stmt.order_by(Evaluation.evaluation_timestamp.desc()).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id(self, evaluation_id: uuid.UUID) -> Evaluation | None:
        result = await self._session.execute(select(Evaluation).where(Evaluation.id == evaluation_id))
        return result.scalar_one_or_none()
