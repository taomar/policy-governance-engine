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
