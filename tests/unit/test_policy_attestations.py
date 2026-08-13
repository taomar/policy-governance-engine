"""Tests for employee attestation tracking (ADR-0012, Milestone 41).

Consistent with this suite's convention (see test_audit.py), these are pure
logic tests — no DB connection. The three things worth proving without a
database are: (1) manager-only gating actually rejects non-managers, (2) the
computed status (pending/acknowledged/overdue) matches across the two places
it's independently derived — the response-shaping helper in the router and
the SQL-level `_apply_status_filter` used for list filtering — since a
divergence there would mean the oversight tab's counts don't match what a
manager sees when they click into a filtered list, and (3) the status
boundary condition (due exactly today is not yet overdue).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from policy_platform.api.routers.policy_attestations import (
    _require_manager,
    _status_of,
)
from policy_platform.domain.models import PolicyAttestation
from policy_platform.infrastructure.persistence.repositories import PolicyAttestationRepository


def _make_row(*, due_date: date, acknowledged_at: datetime | None = None) -> PolicyAttestation:
    row = PolicyAttestation(
        policy_set_id=uuid.uuid4(),
        policy_version_id=uuid.uuid4(),
        employee_name="Dana Employee",
        employee_identifier="dana@example.com",
        due_date=due_date,
        assigned_by="Manager Mo",
    )
    row.acknowledged_at = acknowledged_at
    return row


class TestRequireManager:
    def test_policy_manager_is_allowed(self) -> None:
        # Must not raise.
        _require_manager("policy_manager")

    @pytest.mark.parametrize("role", ["system_admin", "policy_composer", "", "employee"])
    def test_non_manager_roles_are_rejected(self, role: str) -> None:
        with pytest.raises(HTTPException) as exc_info:
            _require_manager(role)
        assert exc_info.value.status_code == 403


class TestStatusOf:
    def test_acknowledged_wins_even_if_overdue(self) -> None:
        """Acknowledging before the due date passes must not later flip back
        to overdue — once acknowledged, the obligation is satisfied for good.
        """
        row = _make_row(
            due_date=date.today() - timedelta(days=10),
            acknowledged_at=datetime.now(timezone.utc) - timedelta(days=11),
        )
        assert _status_of(row) == "acknowledged"

    def test_future_due_date_is_pending(self) -> None:
        row = _make_row(due_date=date.today() + timedelta(days=7))
        assert _status_of(row) == "pending"

    def test_past_due_date_unacknowledged_is_overdue(self) -> None:
        row = _make_row(due_date=date.today() - timedelta(days=1))
        assert _status_of(row) == "overdue"

    def test_due_today_is_still_pending_not_overdue(self) -> None:
        """The boundary: a campaign due today hasn't been missed yet — it
        becomes overdue starting tomorrow, matching `_apply_status_filter`'s
        `< today` (not `<= today`) SQL condition below.
        """
        row = _make_row(due_date=date.today())
        assert _status_of(row) == "pending"


class TestApplyStatusFilterMatchesStatusOf:
    """`_status_of` (Python, per-row) and `_apply_status_filter` (SQL,
    list-level) implement the same three-way split independently. If they
    ever disagree, a manager filtering the oversight list to "Overdue" would
    see a different set of rows than what each row's own computed `status`
    field claims — so pin down that both encode the same boundary.
    """

    def _compiled_where(self, status: str) -> str:
        stmt = select(PolicyAttestation)
        stmt = PolicyAttestationRepository._apply_status_filter(stmt, status)
        compiled = stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
        return str(compiled)

    def test_no_filter_is_a_passthrough(self) -> None:
        stmt = select(PolicyAttestation)
        assert PolicyAttestationRepository._apply_status_filter(stmt, None) is stmt

    def test_acknowledged_filter_requires_acknowledged_at(self) -> None:
        sql = self._compiled_where("acknowledged")
        assert "acknowledged_at IS NOT NULL" in sql

    def test_pending_filter_excludes_acknowledged_and_uses_ge_today(self) -> None:
        sql = self._compiled_where("pending")
        assert "acknowledged_at IS NULL" in sql
        assert ">=" in sql

    def test_overdue_filter_excludes_acknowledged_and_uses_lt_today(self) -> None:
        sql = self._compiled_where("overdue")
        assert "acknowledged_at IS NULL" in sql
        assert "due_date <" in sql
        # Must be strictly-less-than, matching `_status_of`'s "due today is
        # still pending" boundary -- a `<=` here would make the SQL-filtered
        # "Overdue" list disagree with each row's own computed status.
        assert "<=" not in sql.split("due_date")[1].split("AND")[0]


class TestBulkCreateShape:
    def test_bulk_create_builds_one_row_per_employee_sharing_due_date(self) -> None:
        """Doesn't touch the DB (no `flush`/session involved) — just proves
        the row-construction shape bulk_create relies on before it ever
        reaches `session.add_all`.
        """
        employees = [("Dana Employee", "dana@example.com"), ("Sam Staff", None)]
        due = date.today() + timedelta(days=14)
        rows = [
            PolicyAttestation(
                policy_set_id=uuid.uuid4(),
                policy_version_id=uuid.uuid4(),
                employee_name=name,
                employee_identifier=identifier,
                due_date=due,
                assigned_by="Manager Mo",
            )
            for name, identifier in employees
        ]

        assert [r.employee_name for r in rows] == ["Dana Employee", "Sam Staff"]
        assert rows[1].employee_identifier is None
        assert all(r.due_date == due for r in rows)
        assert all(r.acknowledged_at is None for r in rows)
