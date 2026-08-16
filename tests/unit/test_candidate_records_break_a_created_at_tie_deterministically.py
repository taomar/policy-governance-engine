"""Which record represents a duplicated rule_id on the draft surface is stable.

WHY THIS EXISTS

`c74d775` made the draft assembly count a rule_id once by keeping the *first*
record the caller supplies for it (the incumbent, the reading the published
surface already shows). That fix made the caller's record order load-bearing:
whichever record `CandidateRuleRepository.list_by_policy_set` returns first for a
rule_id is the wording a reviewer is shown for it.

That order came from `order_by(created_at)` with no tiebreak. `created_at` is a
wall-clock stamp, not a total order: an extraction run batch-inserting many
candidates in one coarse tick (~15 ms on Windows) stamps them identically, and
with only `created_at` to sort by the database is free to return either tied row
first, and free to choose differently between reads. When two records of one
rule_id tie -- a published reading and a later re-extraction of the same
provision, which share the id because it is a hash of the rule's logic, not its
prose -- which sentence represents the rule could then flip between reads. The
count would not move (both are the same rule_id); the wording shown would. This
is the same "`created_at` is not a total order" hazard that grounded the
pagination refusal, now reaching a published choice.

`candidate_rules` has no sequence column to recover true insertion order from,
so the truly-earlier record is unknowable once `created_at` ties -- but
"unknowable" is not "may vary between reads". This pins the achievable property:
the choice is deterministic. The repository breaks the tie on the primary key,
mirroring the quality-run fix in this same file (`93cf639`), so the row returned
first is fixed and reproducible rather than left to the database's plan.

WHAT THE TIEBREAK BUYS, SAID OUT LOUD

`id` is a UUIDv4 (`default=uuid.uuid4`): total and stable (unique, immutable),
so it breaks every tie deterministically -- but arbitrary as to *which* record
is the "true" incumbent, because a random id encodes no recency. This buys
arbitrary-but-stable determinism, not "the right record wins"; with no sequence
column there is no right record to recover once the clock ties. The direction is
ascending, unlike the quality-run fix's descending: that caller wants the latest
run (`runs[0]`), this caller supplies rules in creation order and `assemble`
keeps the first, so ascending keeps "incumbent first" and, among a tie, the
smallest id.

The tie is constructed explicitly -- two records with an identical `created_at`
-- rather than by racing the clock, because a defect that only appears when two
`datetime.now()` calls collide cannot be failed on demand. The live data differs
by a day, which is exactly why this is invisible today. Before the tiebreak the
read returns the row the scan surfaces first (the earlier-inserted one here);
after it, the smaller id. The loser is inserted first so the two diverge.

CONSTRAINT 1

The winner is derived from the fixture's own ids (`min(..., key=str)`, the
ascending-id tiebreak expressed as a relationship), never written as a literal.
No observed count, id or timestamp appears in an assertion.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from policy_platform.contracts.conditions import ConditionOperator, FactComparisonCondition
from policy_platform.contracts.policy import CanonicalRule, EvidenceReference, RuleLineage
from policy_platform.domain.models import Base, CandidateRule, PolicySet
from policy_platform.infrastructure.assembly.policy_assembly import ProvisionGrouping, assemble
from policy_platform.infrastructure.persistence.repositories.candidates import (
    CandidateRuleRepository,
)
from tests.fixtures.factories import make_rule


# JSONB and UUID are Postgres-only; compiling them for SQLite lets the real
# candidate_rules table be created so the real ordering query runs under test.
@compiles(JSONB, "sqlite")
def _compile_jsonb(_type, _compiler, **_kw) -> str:
    return "JSON"


@compiles(UUID, "sqlite")
def _compile_uuid(_type, _compiler, **_kw) -> str:
    return "CHAR(36)"


SET_ID = uuid.UUID("00000000-0000-4000-8000-00000000d001")
SET_KEY = "candidate-tie-guard-set"

# One rule_id carried by two records, in one passage: the shape `c74d775`
# collapses to a single rule, whose representative this fix makes deterministic.
_SHARED_ID = "R-shared"
_SHARED_PASSAGE = "p4-E000007"

# Two records tied on created_at. Fixed ids so the tiebreak has a defined
# winner. `id` ascending is the tiebreak, so the smaller id wins; the winner is
# derived from these ids rather than named, keeping the assertion relational.
_ID_ONE = uuid.UUID("00000000-0000-4000-8000-00000000d0a1")
_ID_TWO = uuid.UUID("00000000-0000-4000-8000-00000000d0a2")
_TITLES = {
    _ID_ONE: "the reading kept when two records tie on the clock",
    _ID_TWO: "the reading dropped when two records tie on the clock",
}
_WINNER_ID = min(_TITLES, key=str)
_LOSER_ID = max(_TITLES, key=str)

# A single instant both records are stamped with. Never asserted on -- it exists
# only to force the tie the clock would otherwise create by accident.
_TIE_INSTANT = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

_PREFACE = ProvisionGrouping(
    key="prov-preface", provision_id="id-prov-preface", heading_path=("Preface",)
)


async def _session() -> tuple[AsyncSession, object]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    return maker(), engine


def _payload(rule_id: str, elements: str, title: str) -> dict:
    """A stored candidate's payload, carrying the provenance assembly reads."""

    rule = make_rule(rule_id, FactComparisonCondition(fact="days", operator=ConditionOperator.EXISTS))
    rule = rule.model_copy(
        update={
            "title": title,
            "lineage": RuleLineage(source_elements=elements),
            "evidence": [EvidenceReference(document_version_id="dv1", source_hash="h", page=1)],
        }
    )
    return rule.model_dump(mode="json")


def _candidate(candidate_id: uuid.UUID, title: str) -> CandidateRule:
    payload = _payload(_SHARED_ID, _SHARED_PASSAGE, title)
    # extraction_run_id is NOT NULL but its FK is not enforced under SQLite, so
    # a dangling id satisfies the column without seeding an unrelated run.
    return CandidateRule(
        id=candidate_id,
        policy_set_id=SET_ID,
        extraction_run_id=uuid.uuid4(),
        rule_type=payload["rule_type"],
        payload_json=payload,
        review_status="candidate",
        created_at=_TIE_INSTANT,
    )


async def _seed_the_tie(session: AsyncSession) -> None:
    session.add(PolicySet(id=SET_ID, key=SET_KEY, name=SET_KEY, owner="guard"))
    # Loser first: an unbroken created_at tie surfaces rows in insertion order,
    # so before the tiebreak the first row is the loser, not the winner.
    session.add(_candidate(_LOSER_ID, _TITLES[_LOSER_ID]))
    await session.flush()
    session.add(_candidate(_WINNER_ID, _TITLES[_WINNER_ID]))
    await session.commit()


@pytest.mark.asyncio
async def test_a_created_at_tie_is_broken_the_same_way_every_read() -> None:
    """Two records of one rule_id tie on created_at; the first is fixed.

    Fails on `order_by(created_at)` alone: with the tie unbroken the first row
    is whatever the scan surfaces, which is the earlier-inserted loser here, not
    the ascending-id winner. Passes once the primary key breaks the tie, so
    every keep-first consumer that takes the first record for a rule_id is shown
    the same one on every read.
    """
    session, engine = await _session()
    try:
        await _seed_the_tie(session)
        repo = CandidateRuleRepository(session)

        records = await repo.list_by_policy_set(SET_ID)

        # The record kept for the shared rule_id (the first the caller sees) is
        # the ascending-id winner, not the row insertion order happened to put
        # first.
        assert records[0].id == _WINNER_ID
        # And it is the same choice on a second read: determinism, not a
        # particular winner, is the property being bought.
        again = await repo.list_by_policy_set(SET_ID)
        assert [r.id for r in again] == [r.id for r in records]
    finally:
        await session.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_the_tiebreak_fixes_which_wording_represents_the_rule() -> None:
    """The wording a reviewer is shown for the collapsed rule is deterministic.

    Traces the repository order through `assemble`'s keep-first collapse (the
    `c74d775` seam) to the sentence shown. Before the tiebreak the repository
    hands `assemble` the loser first, so the loser's prose represents the rule;
    after it, the ascending-id winner's does, on every read.
    """
    session, engine = await _session()
    try:
        await _seed_the_tie(session)

        records = await CandidateRuleRepository(session).list_by_policy_set(SET_ID)
        rules = [CanonicalRule.model_validate(record.payload_json) for record in records]
        provisions = {rule.rule_id: _PREFACE for rule in rules}

        policies = assemble(rules, provisions=provisions)

        assert len(policies) == 1, "the fixture is one provision and should be one policy"
        kept = [rule for rule in policies[0].rules if rule.rule_id == _SHARED_ID]
        assert len(kept) == 1, "the shared rule_id must collapse to one rule"
        assert kept[0].title == _TITLES[_WINNER_ID]
    finally:
        await session.close()
        await engine.dispose()
