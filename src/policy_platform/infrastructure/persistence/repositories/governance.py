"""What people record around the rules rather than in them: waivers,
acknowledgement campaigns, and free-form notes.

Split from a single 1169-line module whose sixteen repository classes shared
no helper, no constant and no reference to one another -- so the seam was
already there and this only makes it visible.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from policy_platform.domain.models import (
    Note,
    PolicyAttestation,
    PolicyException,
)

class PolicyExceptionRepository:
    """CRUD + decide workflow for ad hoc, human-requested policy exceptions
    (ADR-0009; see domain.models.PolicyException for the full contrast with
    the standing, auto-evaluated `RuleException`).

    Mutable in place for the decide step (`decision`/`decided_by`
    /`decided_at`/`decision_notes`) — same posture as `PolicyTestRepository`:
    a request record, not an immutable governance artifact like
    `ApprovedRule`, so updating it in place is not a Rule 5.3 violation.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        policy_set_id: uuid.UUID,
        rule_id: str | None,
        requester: str,
        justification: str,
        expiry_date: date | None,
    ) -> PolicyException:
        row = PolicyException(
            policy_set_id=policy_set_id,
            rule_id=rule_id,
            requester=requester,
            justification=justification,
            decision="pending",
            expiry_date=expiry_date,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def list_by_policy_set(
        self, policy_set_id: uuid.UUID, *, decision: str | None = None, rule_id: str | None = None
    ) -> list[PolicyException]:
        stmt = select(PolicyException).where(PolicyException.policy_set_id == policy_set_id)
        if decision is not None:
            stmt = stmt.where(PolicyException.decision == decision)
        if rule_id is not None:
            stmt = stmt.where(PolicyException.rule_id == rule_id)
        stmt = stmt.order_by(PolicyException.created_at.desc())
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id(self, exception_id: uuid.UUID) -> PolicyException | None:
        result = await self._session.execute(select(PolicyException).where(PolicyException.id == exception_id))
        return result.scalar_one_or_none()

    async def decide(
        self,
        row: PolicyException,
        *,
        decision: str,
        decided_by: str,
        decision_notes: str | None,
    ) -> PolicyException:
        row.decision = decision
        row.decided_by = decided_by
        row.decided_at = datetime.now(timezone.utc)
        row.decision_notes = decision_notes
        await self._session.flush()
        return row


class PolicyAttestationRepository:
    """CRUD + acknowledge workflow for employee attestation tracking
    (ADR-0012; see domain.models.PolicyAttestation for the full design
    rationale — free-text employee identity, version-binding, computed
    status).

    Mutable in place for the acknowledge step (`acknowledged_at`
    /`acknowledgment_notes`) — same posture as `PolicyExceptionRepository`
    /`PolicyTestRepository`: a request/assignment record, not an immutable
    governance artifact.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def bulk_create(
        self,
        *,
        policy_set_id: uuid.UUID,
        policy_version_id: uuid.UUID,
        employees: list[tuple[str, str | None]],
        due_date: date,
        assigned_by: str,
    ) -> list[PolicyAttestation]:
        rows = [
            PolicyAttestation(
                policy_set_id=policy_set_id,
                policy_version_id=policy_version_id,
                employee_name=name,
                employee_identifier=identifier,
                due_date=due_date,
                assigned_by=assigned_by,
            )
            for name, identifier in employees
        ]
        self._session.add_all(rows)
        await self._session.flush()
        return rows

    async def list_by_policy_set(
        self, policy_set_id: uuid.UUID, *, status: str | None = None
    ) -> list[PolicyAttestation]:
        stmt = select(PolicyAttestation).where(PolicyAttestation.policy_set_id == policy_set_id)
        stmt = self._apply_status_filter(stmt, status)
        stmt = stmt.order_by(PolicyAttestation.due_date.asc(), PolicyAttestation.employee_name.asc())
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def search_by_employee(self, query: str) -> list[PolicyAttestation]:
        """Cross-policy-set, no-login self-service lookup: matches `query`
        as a case-insensitive substring of either `employee_name` or
        `employee_identifier`. This is the employee-facing counterpart to
        `list_by_policy_set` (the manager oversight view) — see
        domain.models.PolicyAttestation docstring for why there's no real
        login to key this off instead.
        """
        like = f"%{query.strip()}%"
        stmt = (
            select(PolicyAttestation)
            .where(
                or_(
                    PolicyAttestation.employee_name.ilike(like),
                    PolicyAttestation.employee_identifier.ilike(like),
                )
            )
            .order_by(PolicyAttestation.due_date.asc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id(self, attestation_id: uuid.UUID) -> PolicyAttestation | None:
        result = await self._session.execute(
            select(PolicyAttestation).where(PolicyAttestation.id == attestation_id)
        )
        return result.scalar_one_or_none()

    async def acknowledge(
        self, row: PolicyAttestation, *, acknowledgment_notes: str | None
    ) -> PolicyAttestation:
        row.acknowledged_at = datetime.now(timezone.utc)
        row.acknowledgment_notes = acknowledgment_notes
        await self._session.flush()
        return row

    @staticmethod
    def _apply_status_filter(stmt, status: str | None):
        if status is None:
            return stmt
        if status == "acknowledged":
            return stmt.where(PolicyAttestation.acknowledged_at.is_not(None))
        if status == "pending":
            return stmt.where(
                PolicyAttestation.acknowledged_at.is_(None),
                PolicyAttestation.due_date >= date.today(),
            )
        if status == "overdue":
            return stmt.where(
                PolicyAttestation.acknowledged_at.is_(None),
                PolicyAttestation.due_date < date.today(),
            )
        return stmt


class NoteRepository:
    """Access to human-authored collaboration notes (see domain/models.py:Note).

    Append-mostly: notes are created and (optionally) deleted by their
    author, never edited in place — this mirrors the audit-trail posture of
    the rest of the domain rather than introducing a new "editable comment"
    concept.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self, *, entity_type: str, entity_id: str, author: str, author_role: str, body: str
    ) -> Note:
        note = Note(
            entity_type=entity_type,
            entity_id=entity_id,
            author=author,
            author_role=author_role,
            body=body,
        )
        self._session.add(note)
        await self._session.flush()
        return note

    async def list_for_entity(self, *, entity_type: str, entity_id: str) -> list[Note]:
        stmt = (
            select(Note)
            .where(Note.entity_type == entity_type, Note.entity_id == entity_id)
            .order_by(Note.created_at)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id(self, note_id: uuid.UUID) -> Note | None:
        result = await self._session.execute(select(Note).where(Note.id == note_id))
        return result.scalar_one_or_none()

    async def delete(self, note: Note) -> None:
        await self._session.delete(note)
        await self._session.flush()
