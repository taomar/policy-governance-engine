"""The project a body of policy belongs to, and who owns it.

Split from a single 1169-line module whose sixteen repository classes shared
no helper, no constant and no reference to one another -- so the seam was
already there and this only makes it visible.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from policy_platform.domain.models import (
    PolicyAuthority,
    PolicySet,
)

class PolicySetRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_key(self, key: str) -> PolicySet | None:
        result = await self._session.execute(select(PolicySet).where(PolicySet.key == key))
        return result.scalar_one_or_none()

    async def list_all(self) -> list[PolicySet]:
        result = await self._session.execute(select(PolicySet).order_by(PolicySet.key))
        return list(result.scalars().all())

    async def create(
        self,
        *,
        key: str,
        name: str,
        owner: str,
        description: str = "",
        category: str = "",
        tags: list[str] | None = None,
        accountable_owner: str = "",
        delegate_approver: str = "",
        escalation_contact: str = "",
        consulted_parties: list[str] | None = None,
        informed_parties: list[str] | None = None,
    ) -> PolicySet:
        policy_set = PolicySet(
            key=key,
            name=name,
            owner=owner,
            description=description,
            category=category,
            tags_json=list(tags or []),
            accountable_owner=accountable_owner,
            delegate_approver=delegate_approver,
            escalation_contact=escalation_contact,
            consulted_parties_json=list(consulted_parties or []),
            informed_parties_json=list(informed_parties or []),
        )
        self._session.add(policy_set)
        await self._session.flush()
        return policy_set

    async def update_metadata(
        self,
        policy_set: PolicySet,
        *,
        name: str | None = None,
        description: str | None = None,
        category: str | None = None,
        tags: list[str] | None = None,
        review_due_date: date | None = None,
        clear_review_due_date: bool = False,
        accountable_owner: str | None = None,
        delegate_approver: str | None = None,
        escalation_contact: str | None = None,
        consulted_parties: list[str] | None = None,
        informed_parties: list[str] | None = None,
    ) -> PolicySet:
        if name is not None:
            policy_set.name = name
        if description is not None:
            policy_set.description = description
        if category is not None:
            policy_set.category = category
        if tags is not None:
            policy_set.tags_json = list(tags)
        # `review_due_date` needs a way to be cleared back to null (unlike the
        # fields above, which are never meaningfully "unset"), so it uses an
        # explicit clear flag rather than overloading `None` as "not provided".
        if clear_review_due_date:
            policy_set.review_due_date = None
        elif review_due_date is not None:
            policy_set.review_due_date = review_due_date
        # RACI ownership metadata (ADR-0013) — same "empty string is a valid
        # value, None means not provided" convention as `description`/`category`.
        if accountable_owner is not None:
            policy_set.accountable_owner = accountable_owner
        if delegate_approver is not None:
            policy_set.delegate_approver = delegate_approver
        if escalation_contact is not None:
            policy_set.escalation_contact = escalation_contact
        if consulted_parties is not None:
            policy_set.consulted_parties_json = list(consulted_parties)
        if informed_parties is not None:
            policy_set.informed_parties_json = list(informed_parties)
        await self._session.flush()
        return policy_set

    async def mark_reviewed(
        self,
        policy_set: PolicySet,
        *,
        next_due_date: date | None = None,
    ) -> PolicySet:
        """Record that a human just reviewed this policy set (ISO 37301 §9.3).

        Distinct from `update_metadata`: this always stamps `last_reviewed_at`
        to now, and optionally advances `review_due_date` to the next cycle in
        the same call, so "I reviewed this, next check is in a year" is one
        request rather than two.
        """
        policy_set.last_reviewed_at = datetime.now(timezone.utc)
        if next_due_date is not None:
            policy_set.review_due_date = next_due_date
        await self._session.flush()
        return policy_set


class PolicyAuthorityRepository:
    """Get-or-create access to authority rows (keyed by level+owner)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_or_create(self, *, level: str, owner: str, rank: int) -> PolicyAuthority:
        result = await self._session.execute(
            select(PolicyAuthority).where(PolicyAuthority.level == level, PolicyAuthority.owner == owner)
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            return existing
        authority = PolicyAuthority(level=level, owner=owner, rank=rank)
        self._session.add(authority)
        await self._session.flush()
        return authority
