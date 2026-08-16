"""The production path that records a run also records which checks did not apply.

`test_quality_run_not_applicable_persisted` proves the *repository* keeps the
disclosure when it is handed one. That is necessary but not sufficient: it calls
`QualityRunRepository.create` directly, so it would still pass if nothing in the
product ever passed the disclosure in. The gap this file closes is exactly that
one -- the signature failure of this subsystem, a capability that works and
reaches nobody.

So these tests drive the real entry point, `evaluate_candidate_quality`, the way
the API route does (`use_ai_review=False`, so no model time is spent), and then
read the row back out of the database. A run recorded through the product must
carry its route-applicability disclosure, and that disclosure must read back as
the same three-valued answer it went in as:

  * every disclosed check reads as `not_applicable` -- a check that did not apply
    is never folded in as a finding and never counted as a pass (Constraint 5);
  * the read seam the page loads first, `latest_quality_report`, serves the
    stored disclosure rather than dropping it, so a persisted answer actually
    reaches a reader.

The pre-wiring failure is concrete: `create` defaulted the disclosure to `None`,
so the stored row came back `None` and the whole distinction was gone. No corpus
count is asserted -- every quantity compared is the size of the rule list this
test builds (Constraint 1).
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
from policy_platform.domain.models import Base, CandidateRule, PolicySet, QualityRun
from policy_platform.infrastructure.persistence.repositories.candidates import (
    QualityRunRepository,
)
from policy_platform.infrastructure.quality.ai_quality import (
    evaluate_candidate_quality,
    latest_quality_report,
)
from policy_platform.infrastructure.quality.route_applicability import Applicability
from tests.fixtures.factories import make_rule


# JSONB and UUID are Postgres-only; compiling them for SQLite lets the real
# schema -- including quality_runs.not_applicable_json -- be created so the
# round-trip runs against the columns production actually writes.
@compiles(JSONB, "sqlite")
def _compile_jsonb(_type, _compiler, **_kw) -> str:
    return "JSON"


@compiles(UUID, "sqlite")
def _compile_uuid(_type, _compiler, **_kw) -> str:
    return "CHAR(36)"


SET_ID = uuid.UUID("00000000-0000-4000-8000-0000000000b1")
SET_KEY = "quality-production-path-set"
SCOPE = "candidates"


def _judged_payload(rule_id: str) -> dict:
    """A record decided by reading -- the engine check does not apply to it."""

    return make_rule(rule_id, AllCondition(all=[])).model_dump(mode="json")


def _deterministic_payload(rule_id: str) -> dict:
    """A record the engine computes -- the reading check does not apply to it."""

    rule = make_rule(
        rule_id,
        FactComparisonCondition(
            fact="salary", operator=ConditionOperator.EXISTS, value=None
        ),
    ).model_copy(
        update={"required_facts": [RequiredFact(name="salary", data_type="number")]}
    )
    return rule.model_dump(mode="json")


def _candidate(rule_id: str, payload: dict) -> CandidateRule:
    return CandidateRule(
        policy_set_id=SET_ID,
        extraction_run_id=uuid.uuid4(),
        rule_type="approval_requirement",
        payload_json=payload,
        review_status="candidate",
    )


async def _session_with_candidates() -> tuple[AsyncSession, object]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    session = maker()
    session.add(PolicySet(id=SET_ID, key=SET_KEY, name=SET_KEY, owner="guard"))
    # Both routes present, so both route-specific checks have something to be
    # not-applicable to. The disclosure and its counts come from these rows.
    session.add(_candidate("A1", _judged_payload("A1")))
    session.add(_candidate("D1", _deterministic_payload("D1")))
    await session.commit()
    return session, engine


@pytest.mark.asyncio
async def test_a_run_recorded_through_the_product_stores_its_disclosure() -> None:
    """Evaluating candidates through the real entry point persists non-null.

    Fails before the producer is wired: `create` was called without the
    disclosure, so the stored row's `not_applicable_json` is `None` and this
    asserts it is not. The stored value must also equal what the same run
    returned, so the answer on the page and the answer in the database are one
    answer, not two.
    """
    session, engine = await _session_with_candidates()
    try:
        result = await evaluate_candidate_quality(
            session,
            policy_set_key=SET_KEY,
            use_ai_review=False,
            record_run=True,
            triggered_by="production-path-test",
        )

        assert result["quality_run_id"] is not None
        surfaced = result["not_applicable"]
        # Both routes are in scope, so the disclosure names at least one check.
        assert surfaced, "the run result should disclose the checks that did not apply"

        stored = await QualityRunRepository(session).get_by_id(
            uuid.UUID(result["quality_run_id"])
        )
        # The load-bearing assertion: the product recorded the disclosure.
        assert stored.not_applicable_json is not None
        # And recorded exactly what it reported -- one answer, two surfaces.
        assert stored.not_applicable_json == surfaced

        # Every disclosed check reads as not-applicable, never as a pass, and a
        # check that did not apply never appears among the run's findings.
        assert all(
            entry["applicability"] == Applicability.NOT_APPLICABLE.value
            for entry in stored.not_applicable_json
        )
        finding_categories = {f.get("category") for f in (stored.findings_json or [])}
        disclosed = {entry["check"] for entry in stored.not_applicable_json}
        assert disclosed.isdisjoint(finding_categories)
    finally:
        await session.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_the_latest_report_read_seam_serves_the_stored_disclosure() -> None:
    """The read the page loads first carries the stored disclosure, not a blank.

    Persisting the disclosure only matters if a reader can see it. `latest_quality_report`
    is the read seam for the current evaluation; before it was taught to carry
    the field, a recorded disclosure would sit in the row and never reach this
    reader. Fails then with a missing key; passes once the read carries it,
    three-valued and unchanged.
    """
    session, engine = await _session_with_candidates()
    try:
        recorded = await evaluate_candidate_quality(
            session,
            policy_set_key=SET_KEY,
            use_ai_review=False,
            record_run=True,
            triggered_by="production-path-test",
        )

        report = await latest_quality_report(
            session, policy_set_key=SET_KEY, scope=SCOPE
        )

        assert "not_applicable" in report
        assert report["not_applicable"] == recorded["not_applicable"]
    finally:
        await session.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_route_specific_checks_only_are_disclosed_and_by_their_own_code() -> None:
    """What is disclosed is a route-specific check, keyed by its own code.

    Guards against a disclosure that quietly grows to name route-neutral checks
    -- which apply on both routes and so are never not-applicable -- or that
    reports an entry against the route it actually serves. Each entry names a
    check that does not apply to the record's route and does apply to the other.
    """
    session, engine = await _session_with_candidates()
    try:
        result = await evaluate_candidate_quality(
            session,
            policy_set_key=SET_KEY,
            use_ai_review=False,
            record_run=True,
            triggered_by="production-path-test",
        )
        for entry in result["not_applicable"]:
            # The record's own route is not among the routes the check serves...
            assert entry["route"] not in entry["applies_to_routes"]
            # ...and the check does serve the other route, so this is a genuine
            # cross-route not-applicable, not a neutral check misfiled.
            assert entry["applies_to_routes"]
    finally:
        await session.close()
        await engine.dispose()
