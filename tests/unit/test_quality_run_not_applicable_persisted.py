"""A stored quality run keeps which checks did not apply -- distinctly.

The route seam computes, for one run, which route-specific checks did not apply
to the records in scope (`_route_applicability_disclosure`). That answer used to
live only in the HTTP response of a fresh run: `QualityRunRepository.create`
stored the findings and the severity counts and dropped the disclosure. A stored
run -- what the Quality page reads back -- then carried its findings and nothing
about which checks did not apply, so a reader had no way to tell a check that did
not apply from a check that ran and found nothing.

These tests pin that the disclosure survives the round-trip through the
repository, and -- the load-bearing part -- that it survives as its own thing.
Three states have to stay three states (Constraint 5):

  * `None`  -> the disclosure was never recorded for this run (a row written
              before the column, or a caller that did not compute it). It must
              read back as `None`, not as an empty list.
  * `[]`    -> the disclosure was recorded and set nothing aside. It must read
              back as `[]`, not as `None`.
  * `[...]` -> the disclosure was recorded and names checks that did not apply.
              Each entry must read back as `not_applicable`, and its check must
              never appear among the findings, because a check that did not
              apply is not a finding and did not pass.

No corpus count is asserted: every quantity compared is the length of a list
these tests build (Constraint 1).
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from policy_platform.contracts.conditions import (
    AllCondition,
    ConditionOperator,
    FactComparisonCondition,
)
from policy_platform.contracts.policy import EvaluationMode, RequiredFact
from policy_platform.domain.models import Base, PolicySet, QualityRun
from policy_platform.infrastructure.persistence.repositories.candidates import (
    QualityRunRepository,
)
from policy_platform.infrastructure.quality.ai_quality import (
    _route_applicability_disclosure,
)
from policy_platform.infrastructure.quality.route_applicability import Applicability
from tests.fixtures.factories import make_rule


# JSONB and UUID are Postgres-only; compiling them for SQLite lets the real
# quality_runs table -- including the new not_applicable_json column -- be
# created so the round-trip runs against the real schema.
@compiles(JSONB, "sqlite")
def _compile_jsonb(_type, _compiler, **_kw) -> str:
    return "JSON"


@compiles(UUID, "sqlite")
def _compile_uuid(_type, _compiler, **_kw) -> str:
    return "CHAR(36)"


SET_ID = uuid.UUID("00000000-0000-4000-8000-00000000a001")
SET_KEY = "quality-not-applicable-guard-set"


def _judged_rule(rule_id: str):
    """A record decided by reading -- the engine check does not apply to it."""

    return make_rule(rule_id, AllCondition(all=[])).model_copy(
        update={"evaluation_mode": EvaluationMode.AI_READY}
    )


def _deterministic_rule(rule_id: str):
    """A record the engine computes -- the reading check does not apply to it."""

    return make_rule(
        rule_id,
        FactComparisonCondition(
            fact="salary", operator=ConditionOperator.EXISTS, value=None
        ),
    ).model_copy(
        update={
            "evaluation_mode": EvaluationMode.DETERMINISTIC,
            "required_facts": [RequiredFact(name="salary", data_type="number")],
        }
    )


async def _session() -> tuple[AsyncSession, object]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    session = maker()
    session.add(PolicySet(id=SET_ID, key=SET_KEY, name=SET_KEY, owner="guard"))
    await session.flush()
    return session, engine


async def _create(session: AsyncSession, *, findings, not_applicable):
    repo = QualityRunRepository(session)
    run = await repo.create(
        policy_set_id=SET_ID,
        scope="published",
        version_number=1,
        rule_count=1,
        findings=findings,
        ai_review_used=True,
        not_applicable=not_applicable,
    )
    await session.commit()
    return run


@pytest.mark.asyncio
async def test_a_recorded_skip_reads_back_as_not_applicable_and_never_as_a_finding() -> None:
    """A disclosed skip survives storage as not-applicable, and is not a finding.

    Fails before the disclosure is persisted: `create` dropped it, so the
    read-back row carries `None` and the entry's applicability -- the whole
    distinction -- is gone. The check is also asserted absent from findings, so
    the skip can never have been folded in as a defect either.
    """
    session, engine = await _session()
    try:
        # Records that all take the reading route, so the engine's own check is
        # the one that does not apply. The disclosure and its count come from
        # these rules, not from any assumed corpus size.
        judged = [_judged_rule("A1"), _judged_rule("A2"), _judged_rule("A3")]
        disclosure = _route_applicability_disclosure(judged)
        assert disclosure, "the seam should disclose at least one skipped check"

        run = await _create(session, findings=[], not_applicable=disclosure)

        read_back = await QualityRunRepository(session).get_by_id(run.id)
        stored = read_back.not_applicable_json

        # Recorded, and recorded as the same thing that went in.
        assert stored is not None
        assert len(stored) == len(disclosure)
        # Every disclosed check reads as not-applicable -- never as a pass.
        assert all(
            entry["applicability"] == Applicability.NOT_APPLICABLE.value
            for entry in stored
        )
        # Count is the records these rules put in scope, carried through intact.
        assert all(entry["records_in_scope"] == len(judged) for entry in stored)

        # A check that did not apply is not a finding: no disclosed check may
        # appear among the run's findings, and a skip contributes nothing to the
        # severity counts (so it is never stored as a defect).
        finding_categories = {f.get("category") for f in read_back.findings_json}
        disclosed_checks = {entry["check"] for entry in stored}
        assert disclosed_checks.isdisjoint(finding_categories)
        assert (read_back.high_count, read_back.medium_count, read_back.low_count) == (0, 0, 0)
    finally:
        await session.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_not_recorded_and_recorded_empty_stay_distinct() -> None:
    """`None` (never recorded) and `[]` (recorded, nothing set aside) do not merge.

    The two are different answers -- "we did not look" versus "we looked and
    every check applied" -- and collapsing either into the other is the state
    confusion this column exists to prevent. Fails if `create` were to coerce
    `None` to `[]` (or the reverse) on the way in or out.
    """
    session, engine = await _session()
    try:
        not_recorded = await _create(session, findings=[], not_applicable=None)
        recorded_empty = await _create(session, findings=[], not_applicable=[])

        repo = QualityRunRepository(session)
        not_recorded_row = await repo.get_by_id(not_recorded.id)
        recorded_empty_row = await repo.get_by_id(recorded_empty.id)

        assert not_recorded_row.not_applicable_json is None
        assert recorded_empty_row.not_applicable_json == []
        # The distinction is the point: absent is not empty.
        assert not_recorded_row.not_applicable_json != recorded_empty_row.not_applicable_json
    finally:
        await session.close()
        await engine.dispose()
