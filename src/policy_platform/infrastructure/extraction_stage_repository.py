"""Persistence for extraction stage records.

Kept beside the other repositories rather than inside the Docling package: the
extraction pipeline must not own database access, and a repository living in
`infrastructure/docling` would be exactly that with a different import path.

WHY STAGES ARE PERSISTED AT ALL
--------------------------------
An extraction run is long and multi-phase. PDF conversion alone takes roughly
three minutes before a model is called. A run that keeps its progress in memory
tells an operator nothing when it dies partway, and gives no basis for deciding
whether re-running is safe or duplicative.

Persisted stages answer both: what happened, and whether this exact work has
already been done.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from policy_platform.domain.models import ExtractionStage


class ExtractionStageRepository:
    """Records and replays the stages of one extraction run."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(
        self,
        *,
        document_version_id: uuid.UUID,
        idempotency_key: str,
        stage_name: str,
        sequence: int,
        status: str = "ok",
        attempt: int = 1,
        input_hash: str | None = None,
        output_hash: str | None = None,
        detail: str | None = None,
        duration_seconds: float | None = None,
        diagnostics: dict | None = None,
        extraction_run_id: uuid.UUID | None = None,
    ) -> ExtractionStage:
        stage = ExtractionStage(
            document_version_id=document_version_id,
            extraction_run_id=extraction_run_id,
            idempotency_key=idempotency_key,
            stage_name=stage_name,
            sequence=sequence,
            status=status,
            attempt=attempt,
            input_hash=input_hash,
            output_hash=output_hash,
            detail=detail,
            duration_seconds=duration_seconds,
            diagnostics_json=diagnostics,
        )
        self._session.add(stage)
        await self._session.flush()
        return stage

    async def list_for_run(self, idempotency_key: str) -> list[ExtractionStage]:
        """Every recorded stage for one run, in pipeline order.

        Ordered by `sequence` then `attempt` rather than by `created_at`:
        several stages of one run routinely complete inside the same clock tick,
        so a timestamp is not a reliable total order.
        """

        result = await self._session.execute(
            select(ExtractionStage)
            .where(ExtractionStage.idempotency_key == idempotency_key)
            .order_by(ExtractionStage.sequence, ExtractionStage.attempt)
        )
        return list(result.scalars().all())

    async def completed_stage_names(self, idempotency_key: str) -> set[str]:
        """Stages of this run that have already succeeded.

        Used to skip work on a retry. A failed attempt is deliberately excluded:
        the stage did not produce an output, so re-running is the only correct
        response.
        """

        result = await self._session.execute(
            select(ExtractionStage.stage_name).where(
                ExtractionStage.idempotency_key == idempotency_key,
                ExtractionStage.status == "ok",
            )
        )
        return set(result.scalars().all())

    async def next_attempt(self, idempotency_key: str, stage_name: str) -> int:
        """The attempt number a re-run of `stage_name` should record.

        Derived rather than passed in, because a caller that guesses would
        collide with the unique constraint and turn a legitimate retry into a
        write failure.
        """

        result = await self._session.execute(
            select(ExtractionStage.attempt).where(
                ExtractionStage.idempotency_key == idempotency_key,
                ExtractionStage.stage_name == stage_name,
            )
        )
        attempts = list(result.scalars().all())
        return (max(attempts) + 1) if attempts else 1

    async def latest_status(self, idempotency_key: str) -> str | None:
        """Terminal status of the run, or None when nothing was recorded.

        A run is failed if any stage failed, regardless of what ran afterwards:
        a later stage succeeding does not repair content an earlier one lost.
        """

        stages = await self.list_for_run(idempotency_key)
        if not stages:
            return None
        if any(stage.status == "failed" for stage in stages):
            return "failed"
        return "ok"
