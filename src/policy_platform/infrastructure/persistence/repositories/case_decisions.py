"""The append-only store of audited external project-case decisions.

Two things distinguish this repository from its siblings, and both come from
the same fact: the decision it records takes ten seconds of model time, and a
database transaction must not be held open across it.

**Reservation is its own commit.** `reserve` writes a `pending` row and commits
it before anything expensive happens. That is what makes a receipt exist even
if the process dies mid-call, and what makes the idempotency constraint do its
work *before* two concurrent callers can both pay for a model run.

**Finalisation is a second, short commit.** `finalize_completed` and
`finalize_failed` write the outcome and nothing else. The row is otherwise
append-only: no method here updates a completed row, and there is no delete.

`reserve` deliberately does not catch `IntegrityError`. A duplicate idempotency
key is not a storage problem, it is a decision the application layer has to make
(replay, refuse as in-progress, or refuse as a conflicting body), and swallowing
it here would take that decision away from the only code that can make it.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from policy_platform.domain.models import PolicyCaseDecision


class PolicyCaseDecisionRepository:
    """Reserve, finalise and read back case-decision receipts."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def reserve(
        self,
        *,
        policy_set_id: uuid.UUID,
        scenario_text: str,
        scenario_hash: str,
        request_hash: str,
        correlation_id: str,
        idempotency_key: str | None,
        authenticated_principal_identity: str,
        authenticated_principal_role: str,
        authentication_source: str,
        calling_system_identity: str | None,
        channel: str,
        scope: str,
        requested_provision_id: str | None,
        reasoning_effort_requested: str,
        request_metadata: dict,
        received_at: datetime | None = None,
    ) -> PolicyCaseDecision:
        """Write and commit a `pending` receipt.

        Commits rather than flushes: the point of the reservation is that it
        survives the request that made it, and a flush inside an uncommitted
        transaction survives nothing. Raises `IntegrityError` when the caller's
        idempotency key is already taken — see the module docstring for why that
        is not handled here.
        """

        row = PolicyCaseDecision(
            policy_set_id=policy_set_id,
            status="pending",
            scenario_text=scenario_text,
            scenario_hash=scenario_hash,
            request_hash=request_hash,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
            authenticated_principal_identity=authenticated_principal_identity,
            authenticated_principal_role=authenticated_principal_role,
            authentication_source=authentication_source,
            calling_system_identity=calling_system_identity,
            channel=channel,
            scope=scope,
            requested_provision_id=requested_provision_id,
            reasoning_effort_requested=reasoning_effort_requested,
            request_metadata_json=request_metadata or {},
            received_at=received_at or datetime.now(timezone.utc),
        )
        self._session.add(row)
        await self._session.commit()
        return row

    async def finalize_completed(
        self,
        row: PolicyCaseDecision,
        *,
        policy_version_id: uuid.UUID | None,
        version_number: int | None,
        decision_status: str,
        scope: str,
        retrieval: dict | None,
        decision_summary: dict | None,
        citation_ids: list[str],
        trace: dict | None,
        response: dict,
        decision_hash: str,
        hash_basis: str,
        decided_at: datetime,
        latency_ms: int,
    ) -> PolicyCaseDecision:
        """Turn the reservation into the receipt a caller may be shown.

        `scope` is written here as well as at reservation because the decider
        settles it: a caller who named no policy is `project`, and the row must
        agree with the envelope it stores rather than with the guess made before
        the call.
        """

        row.status = "completed"
        row.policy_version_id = policy_version_id
        row.version_number = version_number
        row.decision_status = decision_status
        row.scope = scope
        row.retrieval_json = retrieval
        row.decision_summary_json = decision_summary
        row.citation_ids_json = list(citation_ids)
        row.trace_json = trace
        row.response_json = response
        row.decision_hash = decision_hash
        row.hash_basis = hash_basis
        row.decided_at = decided_at
        row.latency_ms = latency_ms
        await self._session.commit()
        return row

    async def finalize_failed(
        self,
        row: PolicyCaseDecision,
        *,
        failure_code: str,
        failure_message: str,
        decided_at: datetime | None = None,
        latency_ms: int | None = None,
    ) -> PolicyCaseDecision:
        """Close out a reservation that produced no usable decision.

        No `decision_status`, no envelope and no hash are written: a failed
        receipt has no outcome, and leaving those columns null is what stops one
        being read out of it later.
        """

        row.status = "failed"
        row.failure_code = failure_code
        row.failure_message = failure_message
        row.decided_at = decided_at or datetime.now(timezone.utc)
        row.latency_ms = latency_ms
        await self._session.commit()
        return row

    async def get_by_id(self, decision_id: uuid.UUID) -> PolicyCaseDecision | None:
        result = await self._session.execute(
            select(PolicyCaseDecision).where(PolicyCaseDecision.id == decision_id)
        )
        return result.scalar_one_or_none()

    async def find_by_idempotency_key(
        self,
        *,
        policy_set_id: uuid.UUID,
        authenticated_principal_identity: str,
        idempotency_key: str,
    ) -> PolicyCaseDecision | None:
        """The one row that key can name, scoped to its caller and project.

        The scoping is the security property, not an optimisation: without the
        principal in the predicate, one caller could name — and replay — another
        caller's receipt by guessing a key.
        """

        result = await self._session.execute(
            select(PolicyCaseDecision).where(
                PolicyCaseDecision.policy_set_id == policy_set_id,
                PolicyCaseDecision.authenticated_principal_identity
                == authenticated_principal_identity,
                PolicyCaseDecision.idempotency_key == idempotency_key,
            )
        )
        return result.scalar_one_or_none()
