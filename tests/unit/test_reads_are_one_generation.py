"""A reader asking for a policy set gets one state of it, not every state it has had.

Re-extracting into an existing set retires the previous rules rather than
deleting them, which is right: a reviewer who has been working through a queue
needs to see what stopped being found, not to have it vanish. The retired rows
therefore accumulate, one generation per run, and every read has to decide which
of them it means.

Most reads decided correctly and say so. `list_by_policy_set` filters on
`superseded_at IS NULL` and takes `include_superseded` as an explicit opt-in;
correlation writes down why it must never see a retired rule. The "no longer
found" panel did not: it selected every retired rule in the set. On a set
extracted four times that is four generations at once -- rules replaced three
runs ago, listed beside rules replaced by the run currently on screen, under a
heading that claims all of them describe the present. That is what a reviewer
reports as old runs mixing when they view.

Three generations, not two, and the number matters. With a single retired
generation "every retired rule" and "the generation the current run retired"
select the same rows, so a two-run fixture passes either way and proves
nothing. The defect only becomes visible once a retired run has itself been
retired, which needs a third. `test_a_two_run_fixture_cannot_see_this_defect`
asserts that rather than leaving it as a remark, because the next person to
extend this file will reach for two runs first.

What is asserted:

  * the default read returns the current generation and nothing else;
  * history is still reachable, but only by asking for it;
  * the assembling view never groups rules from two runs under one passage --
    and, since it has no current-ness logic of its own, that its caller is what
    protects it, so nobody moves the filter later believing the view is safe;
  * "no longer found" is the generation the current run retired, not the union;
  * a rule in another policy set cannot suppress a removed rule in this one;
  * the counts beside a list agree with the list.

Each assertion is paired with the mutation it is meant to survive, so a filter
silently dropped out of a query fails here rather than in a reviewer's queue.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from policy_platform.contracts.conditions import ConditionOperator, FactComparisonCondition
from policy_platform.contracts.policy import EvidenceReference, RuleLineage
from policy_platform.domain.models import (
    Base,
    CandidateRule,
    DocumentVersion,
    ExtractionRun,
    PolicySet,
    SourceDocument,
)
from policy_platform.infrastructure.assembly.policy_assembly import assemble
from policy_platform.infrastructure.persistence.repositories.candidates import (
    CandidateRuleRepository,
)
from policy_platform.infrastructure.persistence.review_facets import build_review_facets
from tests.fixtures.factories import make_rule


# JSONB and UUID are Postgres-only. Compiling them for SQLite lets the real
# tables be created, so the real columns and the real queries are exercised.
@compiles(JSONB, "sqlite")
def _compile_jsonb(_type, _compiler, **_kw) -> str:
    return "JSON"


@compiles(UUID, "sqlite")
def _compile_uuid(_type, _compiler, **_kw) -> str:
    return "CHAR(36)"


_TEST = FactComparisonCondition(fact="days", operator=ConditionOperator.EXISTS)

# Fixed rather than random. Two tests in this repo have already passed on the
# draw because `uuid4()` decided which fixture sorted higher; a fixture whose
# outcome depends on generated ids is not a fixture.
SET_ID = uuid.UUID("00000000-0000-4000-8000-00000000005e")
OTHER_SET_ID = uuid.UUID("00000000-0000-4000-8000-0000000000a1")
GEN1 = uuid.UUID("00000000-0000-4000-8000-000000000001")
GEN2 = uuid.UUID("00000000-0000-4000-8000-000000000002")
GEN3 = uuid.UUID("00000000-0000-4000-8000-000000000003")

# One passage. Every generation re-extracts it, so if two generations ever reach
# the assembling view together they land under this one key and are visible as a
# policy holding twice the rules it should.
PASSAGE = "p7-E000042"


def _rule(rule_id: str, title: str = "Rule"):
    """A real rule object, not a dict poured into one.

    `model_copy(update=...)` does not validate, so a dict passed here stays a
    dict and only fails later inside whatever reads the attribute. Building the
    contract types directly is what makes the fixture exercise the same shapes
    the extraction writes.
    """
    return make_rule(rule_id, _TEST).model_copy(
        update={
            "title": title,
            "lineage": RuleLineage(source_elements=PASSAGE),
            "evidence": [
                EvidenceReference(
                    document_version_id="version-1",
                    source_hash="h" * 16,
                    page=7,
                    clause_id=PASSAGE,
                )
            ],
        }
    )


def _payload(rule_id: str, title: str) -> dict:
    return _rule(rule_id, title).model_dump(mode="json")


async def _session() -> tuple[AsyncSession, object]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    return maker(), engine


async def _build(session: AsyncSession) -> dict[str, list[uuid.UUID]]:
    """One set, one document, three runs, two retired generations.

    Generation 1 was retired by generation 2, which was itself retired by
    generation 3. Only generation 3 stands.
    """
    started = datetime(2026, 1, 1, tzinfo=timezone.utc)

    for set_id, key in ((SET_ID, "guard-set"), (OTHER_SET_ID, "guard-other-set")):
        session.add(PolicySet(id=set_id, key=key, name=key, owner="guard"))

    document_id = uuid.uuid4()
    version_id = uuid.uuid4()
    session.add(
        SourceDocument(id=document_id, title="Handbook", owner="guard", policy_set_id=SET_ID)
    )
    session.add(
        DocumentVersion(
            id=version_id,
            document_id=document_id,
            version_number=1,
            content_hash="c" * 64,
            storage_path="/tmp/handbook.pdf",
        )
    )
    for index, run_id in enumerate((GEN1, GEN2, GEN3)):
        session.add(
            ExtractionRun(
                id=run_id,
                document_version_id=version_id,
                status="succeeded",
                started_at=started + timedelta(hours=index),
            )
        )

    ids: dict[str, list[uuid.UUID]] = {"gen1": [], "gen2": [], "gen3": []}

    def add(generation: str, run_id, rule_id: str, title: str, **columns) -> None:
        row = CandidateRule(
            id=uuid.uuid4(),
            policy_set_id=SET_ID,
            extraction_run_id=run_id,
            rule_type="obligation",
            review_status="candidate",
            delta_status="new",
            payload_json=_payload(rule_id, title),
            **columns,
        )
        session.add(row)
        ids[generation].append(row.id)

    retired_by_gen2 = {
        "superseded_at": started + timedelta(hours=1),
        "superseded_by_run_id": GEN2,
    }
    retired_by_gen3 = {
        "superseded_at": started + timedelta(hours=2),
        "superseded_by_run_id": GEN3,
    }

    add("gen1", GEN1, "AI-0000000001", "First run, long gone", **retired_by_gen2)
    add("gen1", GEN1, "AI-0000000002", "First run, also gone", **retired_by_gen2)
    add("gen2", GEN2, "AI-0000000003", "Second run, just retired", **retired_by_gen3)
    add("gen3", GEN3, "AI-0000000004", "Current")
    add("gen3", GEN3, "AI-0000000005", "Also current")

    await session.commit()
    return ids


@pytest.mark.asyncio
async def test_the_default_read_returns_one_generation() -> None:
    session, engine = await _session()
    try:
        ids = await _build(session)
        rules = await CandidateRuleRepository(session).list_by_policy_set(SET_ID)

        assert {r.id for r in rules} == set(ids["gen3"])
        assert {r.extraction_run_id for r in rules} == {GEN3}
    finally:
        await session.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_history_is_reachable_only_by_asking_for_it() -> None:
    """The boundary: current by default, history on request.

    This is the line the fix draws. A caller that wants every generation can
    still have it -- the delta and the idempotency check genuinely need it --
    but it costs a named argument, so no read acquires history by forgetting a
    predicate.
    """
    session, engine = await _session()
    try:
        ids = await _build(session)
        repo = CandidateRuleRepository(session)

        current = await repo.list_by_policy_set(SET_ID)
        everything = await repo.list_by_policy_set(SET_ID, include_superseded=True)

        expected = set(ids["gen1"]) | set(ids["gen2"]) | set(ids["gen3"])
        assert {r.id for r in everything} == expected
        assert len(everything) > len(current)
    finally:
        await session.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_the_assembling_view_never_groups_two_runs_into_one_policy() -> None:
    """The case the producer asked to be verified before anything else.

    All five rules cite the same passage, so if retired generations reached
    `assemble()` they would arrive under one key and present as a single policy
    of five rules -- indistinguishable, to a reviewer, from the fragmentation
    grouping was built to fix, and worse, because the extra rules are real
    records from runs that no longer stand.
    """
    session, engine = await _session()
    try:
        ids = await _build(session)
        rules = await CandidateRuleRepository(session).list_by_policy_set(SET_ID)
        policies = assemble([_rule(r.payload_json["rule_id"]) for r in rules])

        assert len(policies) == 1
        assert policies[0].rule_count == len(ids["gen3"]) == 2
    finally:
        await session.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_the_assembling_view_is_protected_by_its_caller_not_by_itself() -> None:
    """Where the protection lives, asserted so it is not moved by mistake.

    `assemble()` groups whatever it is handed; it has no notion of a run and
    should not acquire one, because a grouping is a fact about the rules in
    view. Handing it every generation produces the five-rule policy the previous
    test forbids. That is not a defect in `assemble()` -- it is the reason its
    caller must filter, and this test is what tells the next reader so.
    """
    session, engine = await _session()
    try:
        await _build(session)
        unfiltered = await CandidateRuleRepository(session).list_by_policy_set(
            SET_ID, include_superseded=True
        )
        policies = assemble([_rule(r.payload_json["rule_id"]) for r in unfiltered])

        assert len(policies) == 1
        assert policies[0].rule_count == 5
    finally:
        await session.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_no_longer_found_is_the_generation_the_current_run_retired() -> None:
    session, engine = await _session()
    try:
        ids = await _build(session)
        policy_set = (
            await session.execute(select(PolicySet).where(PolicySet.id == SET_ID))
        ).scalar_one()

        facets = await build_review_facets(session, policy_set)
        removed = {uuid.UUID(row["id"]) for row in facets["removed"]}

        assert removed == set(ids["gen2"])
        assert removed.isdisjoint(set(ids["gen1"]))
        assert all(row["superseded_by_run_id"] == str(GEN3) for row in facets["removed"])
    finally:
        await session.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_a_two_run_fixture_cannot_see_this_defect() -> None:
    """The sensitivity check, and the reason the fixture has three runs.

    Restricted to the two most recent generations the set has only one retired
    generation, and "every retired rule" and "the generation the current run
    retired" agree. A test built on two runs would have passed against the
    unfixed query. Asserting the blind spot keeps someone from simplifying the
    fixture later and quietly disarming the file.
    """
    session, engine = await _session()
    try:
        ids = await _build(session)

        for row_id in ids["gen1"]:
            row = await session.get(CandidateRule, row_id)
            await session.delete(row)
        await session.commit()

        policy_set = (
            await session.execute(select(PolicySet).where(PolicySet.id == SET_ID))
        ).scalar_one()
        facets = await build_review_facets(session, policy_set)

        every_retired = (
            await session.execute(
                select(CandidateRule.id).where(
                    CandidateRule.policy_set_id == SET_ID,
                    CandidateRule.superseded_at.is_not(None),
                )
            )
        ).scalars().all()

        assert {uuid.UUID(r["id"]) for r in facets["removed"]} == set(every_retired)
    finally:
        await session.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_another_policy_set_cannot_suppress_a_removed_rule() -> None:
    """The continuation subquery is scoped to the set being read.

    It selects `baseline_candidate_id` to find retired rules a later rule
    carried forward. Unscoped, a rule in any other set naming this id
    suppressed the row here -- the two sets need not share a document or a run.
    It hid a removal rather than showing a stale one, which is why it survived:
    the failure is a row that should appear and does not.
    """
    session, engine = await _session()
    try:
        ids = await _build(session)
        retired = ids["gen2"][0]

        session.add(
            CandidateRule(
                id=uuid.uuid4(),
                policy_set_id=OTHER_SET_ID,
                extraction_run_id=uuid.uuid4(),
                rule_type="obligation",
                review_status="candidate",
                payload_json=_payload("AI-0000000009", "Unrelated set"),
                baseline_candidate_id=retired,
            )
        )
        await session.commit()

        policy_set = (
            await session.execute(select(PolicySet).where(PolicySet.id == SET_ID))
        ).scalar_one()
        facets = await build_review_facets(session, policy_set)

        assert retired in {uuid.UUID(row["id"]) for row in facets["removed"]}
    finally:
        await session.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_a_continuation_in_the_same_set_still_suppresses_it() -> None:
    """Scoping the subquery must not disable what it is for.

    The paired half of the previous test: a later rule in this set claiming the
    retired rule as its continuation means the rule was carried forward, not
    dropped, so it is not "no longer found".
    """
    session, engine = await _session()
    try:
        ids = await _build(session)
        retired = ids["gen2"][0]

        successor = await session.get(CandidateRule, ids["gen3"][0])
        successor.baseline_candidate_id = retired
        await session.commit()

        policy_set = (
            await session.execute(select(PolicySet).where(PolicySet.id == SET_ID))
        ).scalar_one()
        facets = await build_review_facets(session, policy_set)

        assert facets["removed"] == []
    finally:
        await session.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_the_counts_agree_with_the_list_beside_them() -> None:
    """A number rendered next to a list has to be the length of that list.

    The totals were already filtered while `removed` was not, so the filter bar
    could report two current rules above a panel naming three more from runs
    that no longer stand.
    """
    session, engine = await _session()
    try:
        ids = await _build(session)
        policy_set = (
            await session.execute(select(PolicySet).where(PolicySet.id == SET_ID))
        ).scalar_one()

        facets = await build_review_facets(session, policy_set)

        assert facets["status_totals"] == {"candidate": len(ids["gen3"])}
        assert sum(facets["delta_totals"].values()) == len(ids["gen3"])
        assert [run["id"] for run in facets["runs"]] == [str(GEN3)]
        assert sum(run["total"] for run in facets["runs"]) == len(ids["gen3"])
    finally:
        await session.close()
        await engine.dispose()
