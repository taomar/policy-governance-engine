"""Published policy. Versions are immutable snapshots, never edited in
place, so everything here is insert-only by construction.

Split from a single 1169-line module whose sixteen repository classes shared
no helper, no constant and no reference to one another -- so the seam was
already there and this only makes it visible.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from policy_platform.domain.models import (
    ApprovedPolicyVersion,
    ApprovedRule,
    PolicyAggregateLimit,
)

class ApprovedPolicyVersionRepository:
    """Read/insert access to immutable approved policy versions and rules."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_active_version(self, policy_set_id: uuid.UUID) -> ApprovedPolicyVersion | None:
        stmt = (
            select(ApprovedPolicyVersion)
            .where(
                ApprovedPolicyVersion.policy_set_id == policy_set_id,
                ApprovedPolicyVersion.is_active.is_(True),
            )
            .options(
                selectinload(ApprovedPolicyVersion.rules).selectinload(ApprovedRule.authority),
                selectinload(ApprovedPolicyVersion.rules).selectinload(ApprovedRule.exceptions),
                selectinload(ApprovedPolicyVersion.rules).selectinload(ApprovedRule.evidence),
                selectinload(ApprovedPolicyVersion.aggregate_limits),
            )
            .order_by(ApprovedPolicyVersion.version_number.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id(self, policy_version_id: uuid.UUID) -> ApprovedPolicyVersion | None:
        stmt = (
            select(ApprovedPolicyVersion)
            .where(ApprovedPolicyVersion.id == policy_version_id)
            .options(
                selectinload(ApprovedPolicyVersion.rules).selectinload(ApprovedRule.authority),
                selectinload(ApprovedPolicyVersion.rules).selectinload(ApprovedRule.exceptions),
                selectinload(ApprovedPolicyVersion.rules).selectinload(ApprovedRule.evidence),
                selectinload(ApprovedPolicyVersion.aggregate_limits),
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def insert_version(self, version: ApprovedPolicyVersion) -> ApprovedPolicyVersion:
        """Insert a brand-new immutable version row (never call session.merge on an existing one)."""

        self._session.add(version)
        await self._session.flush()
        return version

    async def list_all_versions(self, policy_set_id: uuid.UUID) -> list[ApprovedPolicyVersion]:
        """All versions of a policy set, newest first, rules eager-loaded.

        Used by the admin UI's version-history timeline — unlike
        `get_active_version`/`get_by_id`, this deliberately returns every
        version (active and superseded) so reviewers can see the full history.
        """
        stmt = (
            select(ApprovedPolicyVersion)
            .where(ApprovedPolicyVersion.policy_set_id == policy_set_id)
            .options(
                selectinload(ApprovedPolicyVersion.rules).selectinload(ApprovedRule.authority),
                selectinload(ApprovedPolicyVersion.rules).selectinload(ApprovedRule.exceptions),
                selectinload(ApprovedPolicyVersion.rules).selectinload(ApprovedRule.evidence),
                selectinload(ApprovedPolicyVersion.aggregate_limits),
            )
            .order_by(ApprovedPolicyVersion.version_number.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().unique().all())

    async def get_max_version_number(self, policy_set_id: uuid.UUID) -> int:
        stmt = select(ApprovedPolicyVersion.version_number).where(
            ApprovedPolicyVersion.policy_set_id == policy_set_id
        )
        result = await self._session.execute(stmt)
        numbers = [row[0] for row in result.all()]
        return max(numbers) if numbers else 0

    async def deactivate_all(self, policy_set_id: uuid.UUID) -> None:
        """Flip `is_active` off for every existing version of this policy set.

        Called before activating a newly-published version so exactly one
        version is active at a time (the `is_active` flag itself is mutable
        lifecycle metadata, not a substantive/audited column — Rule 5.3
        immutability applies to the rule content, not this flag).
        """
        stmt = select(ApprovedPolicyVersion).where(ApprovedPolicyVersion.policy_set_id == policy_set_id)
        result = await self._session.execute(stmt)
        for version in result.scalars().all():
            version.is_active = False
        await self._session.flush()


class PolicyAggregateLimitRepository:
    """CRUD access to mutable draft aggregate limits (see domain/models.py).

    Unlike `CandidateRuleRepository`, there is no review workflow here —
    aggregate limits are structural policy-set configuration a Policy
    Manager edits directly (same posture as `PolicySetRepository.update_metadata`
    for tags/category), not prose subject to per-candidate human review.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_by_policy_set(self, policy_set_id: uuid.UUID) -> list[PolicyAggregateLimit]:
        stmt = (
            select(PolicyAggregateLimit)
            .where(PolicyAggregateLimit.policy_set_id == policy_set_id)
            .order_by(PolicyAggregateLimit.aggregate_key)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_key(self, policy_set_id: uuid.UUID, aggregate_key: str) -> PolicyAggregateLimit | None:
        stmt = select(PolicyAggregateLimit).where(
            PolicyAggregateLimit.policy_set_id == policy_set_id,
            PolicyAggregateLimit.aggregate_key == aggregate_key,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        policy_set_id: uuid.UUID,
        aggregate_key: str,
        description: str,
        contributing_rules: list[dict],
        aggregator: str = "SUM",
        max_value: float,
        period: str | None = None,
    ) -> PolicyAggregateLimit:
        row = PolicyAggregateLimit(
            policy_set_id=policy_set_id,
            aggregate_key=aggregate_key,
            description=description,
            contributing_rules_json=contributing_rules,
            aggregator=aggregator,
            max_value=max_value,
            period=period,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def update(
        self,
        row: PolicyAggregateLimit,
        *,
        description: str,
        contributing_rules: list[dict],
        aggregator: str,
        max_value: float,
        period: str | None,
    ) -> PolicyAggregateLimit:
        """Full-replace update (mirrors `create`'s signature).

        Aggregate limits are small, fully-specified structural rows edited
        via a single form — unlike `PolicySetRepository.update_metadata`
        there is no ambiguity to resolve between "field omitted" and "field
        cleared to None", since every field is always supplied.
        """
        row.description = description
        row.contributing_rules_json = contributing_rules
        row.aggregator = aggregator
        row.max_value = max_value
        row.period = period
        await self._session.flush()
        return row

    async def delete(self, row: PolicyAggregateLimit) -> None:
        await self._session.delete(row)
        await self._session.flush()
