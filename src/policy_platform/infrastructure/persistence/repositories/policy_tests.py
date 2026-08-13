"""Saved tests, the batches they run in, and the results of each run.

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
    PolicyTest,
    PolicyTestBatch,
    PolicyTestRun,
)

class PolicyTestRepository:
    """Access to saved `PolicyTest` definitions.

    Updates in place are expected here (`review_status`, `is_active`, etc.)
    — like `CandidateRuleRepository`, a test's own definition is not yet an
    authoritative published artifact, so this is not a Rule 5.3 violation.
    Only `PolicyTestRunRepository` (the recorded results of executing a
    test) is append-only.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        policy_set_id: uuid.UUID,
        name: str,
        description: str,
        test_kind: str,
        input_facts_json: dict,
        evaluation_timestamp_override: datetime | None,
        expected_overall_status: str,
        expected_rule_id: str | None,
        expected_rule_status: str | None,
        expected_missing_facts_json: list | None,
        proposed_by: str,
        review_status: str,
        is_active: bool,
        generation_batch_id: uuid.UUID | None = None,
        scenario_text: str = "",
        expectation_hash: str | None = None,
    ) -> PolicyTest:
        test = PolicyTest(
            policy_set_id=policy_set_id,
            name=name,
            description=description,
            test_kind=test_kind,
            input_facts_json=input_facts_json,
            evaluation_timestamp_override=evaluation_timestamp_override,
            expected_overall_status=expected_overall_status,
            expected_rule_id=expected_rule_id,
            expected_rule_status=expected_rule_status,
            expected_missing_facts_json=expected_missing_facts_json,
            proposed_by=proposed_by,
            review_status=review_status,
            is_active=is_active,
            generation_batch_id=generation_batch_id,
            scenario_text=scenario_text,
            expectation_hash=expectation_hash,
        )
        self._session.add(test)
        await self._session.flush()
        return test

    async def list_by_policy_set(
        self, policy_set_id: uuid.UUID, *, is_active: bool | None = None, test_kind: str | None = None
    ) -> list[PolicyTest]:
        stmt = select(PolicyTest).where(PolicyTest.policy_set_id == policy_set_id)
        if is_active is not None:
            stmt = stmt.where(PolicyTest.is_active == is_active)
        if test_kind is not None:
            stmt = stmt.where(PolicyTest.test_kind == test_kind)
        stmt = stmt.order_by(PolicyTest.created_at)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id(self, test_id: uuid.UUID) -> PolicyTest | None:
        result = await self._session.execute(select(PolicyTest).where(PolicyTest.id == test_id))
        return result.scalar_one_or_none()

    async def list_by_batch(self, batch_id: uuid.UUID) -> list[PolicyTest]:
        result = await self._session.execute(
            select(PolicyTest).where(PolicyTest.generation_batch_id == batch_id).order_by(PolicyTest.created_at)
        )
        return list(result.scalars().all())

    async def set_review_status(
        self,
        test: PolicyTest,
        *,
        review_status: str,
        is_active: bool,
        reviewed_by: str,
        review_notes: str | None = None,
    ) -> PolicyTest:
        test.review_status = review_status
        test.is_active = is_active
        test.reviewed_by = reviewed_by
        test.reviewed_at = datetime.now(timezone.utc)
        test.review_notes = review_notes
        await self._session.flush()
        return test


class PolicyTestBatchRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        policy_set_id: uuid.UUID,
        policy_version_id: uuid.UUID,
        grounding_mode: str,
        selected_rule_ids_json: list[str],
        grounding_context_json: dict,
        scenario_count: int,
        reasoning_effort: str,
        guidance: str,
        created_by: str,
    ) -> PolicyTestBatch:
        batch = PolicyTestBatch(
            policy_set_id=policy_set_id,
            policy_version_id=policy_version_id,
            grounding_mode=grounding_mode,
            selected_rule_ids_json=selected_rule_ids_json,
            grounding_context_json=grounding_context_json,
            scenario_count=scenario_count,
            reasoning_effort=reasoning_effort,
            guidance=guidance,
            created_by=created_by,
            status="generated",
        )
        self._session.add(batch)
        await self._session.flush()
        return batch

    async def get_by_id(self, batch_id: uuid.UUID) -> PolicyTestBatch | None:
        result = await self._session.execute(select(PolicyTestBatch).where(PolicyTestBatch.id == batch_id))
        return result.scalar_one_or_none()

    async def list_by_policy_set(self, policy_set_id: uuid.UUID, *, limit: int = 20) -> list[PolicyTestBatch]:
        result = await self._session.execute(
            select(PolicyTestBatch)
            .where(PolicyTestBatch.policy_set_id == policy_set_id)
            .order_by(PolicyTestBatch.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def mark_executed(self, batch: PolicyTestBatch) -> PolicyTestBatch:
        batch.status = "executed"
        batch.executed_at = datetime.now(timezone.utc)
        await self._session.flush()
        return batch


class PolicyTestRunRepository:
    """Append-only execution history for `PolicyTest` rows.

    Mirrors `EvaluationRepository`: every call to `record` inserts a new row,
    never updates an existing one, so the full pass/fail history for a test
    across every published version is preserved.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(
        self,
        *,
        policy_test_id: uuid.UUID,
        policy_version_id: uuid.UUID,
        status: str,
        explanation: str,
        actual_response_json: dict | None,
        run_trigger: str,
        triggered_by: str,
        expected_assertions_json: dict | None = None,
        expectation_hash: str | None = None,
        run_at: datetime | None = None,
    ) -> PolicyTestRun:
        run = PolicyTestRun(
            policy_test_id=policy_test_id,
            policy_version_id=policy_version_id,
            status=status,
            explanation=explanation,
            actual_response_json=actual_response_json,
            expected_assertions_json=expected_assertions_json,
            expectation_hash=expectation_hash,
            run_trigger=run_trigger,
            triggered_by=triggered_by,
            run_at=run_at or datetime.now(timezone.utc),
        )
        self._session.add(run)
        await self._session.flush()
        return run

    async def list_by_test(self, policy_test_id: uuid.UUID) -> list[PolicyTestRun]:
        stmt = (
            select(PolicyTestRun)
            .where(PolicyTestRun.policy_test_id == policy_test_id)
            .order_by(PolicyTestRun.run_at.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_latest_by_test(self, policy_test_id: uuid.UUID) -> PolicyTestRun | None:
        stmt = (
            select(PolicyTestRun)
            .where(PolicyTestRun.policy_test_id == policy_test_id)
            .order_by(PolicyTestRun.run_at.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_latest_for_tests(self, policy_test_ids: list[uuid.UUID]) -> dict[uuid.UUID, PolicyTestRun]:
        """Batch-fetch the single most recent run per test id.

        Uses Postgres `DISTINCT ON` (this project only ever targets
        Postgres — see infrastructure/settings.py — so there is no
        cross-dialect portability concern here, same reasoning as the
        JSONB columns used throughout domain/models.py).
        """
        if not policy_test_ids:
            return {}
        stmt = (
            select(PolicyTestRun)
            .where(PolicyTestRun.policy_test_id.in_(policy_test_ids))
            .distinct(PolicyTestRun.policy_test_id)
            .order_by(PolicyTestRun.policy_test_id, PolicyTestRun.run_at.desc())
        )
        result = await self._session.execute(stmt)
        rows = result.scalars().all()
        return {row.policy_test_id: row for row in rows}

    async def list_for_tests(self, policy_test_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[PolicyTestRun]]:
        if not policy_test_ids:
            return {}
        result = await self._session.execute(
            select(PolicyTestRun)
            .where(PolicyTestRun.policy_test_id.in_(policy_test_ids))
            .order_by(PolicyTestRun.policy_test_id, PolicyTestRun.run_at.desc())
        )
        grouped: dict[uuid.UUID, list[PolicyTestRun]] = {}
        for row in result.scalars().all():
            grouped.setdefault(row.policy_test_id, []).append(row)
        return grouped
