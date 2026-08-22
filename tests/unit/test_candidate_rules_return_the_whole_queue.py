"""Asking a policy set for its candidate rules returns all of them, not a page.

The backlog carried this as `pagination`: "`list_candidate_rules` has no
`limit`; returns all 279." Read as a defect it invites a fix -- add a `limit`,
default it, ship. Measurement refuses that fix, and this file is where the
refusal is made executable so the fix cannot be reintroduced quietly.

Four findings, each paired with the mutation these tests are built to survive:

  * The policy is the unit, not the rule. In the live corpus a set is a few
    dozen policies carrying several hundred rules; the reviewer's queue is the
    policies. The assembling `/policies` view the queue is arranged by groups
    rules under their passage and re-sorts by document position, so the flat
    list's order -- and any window taken over it -- never reaches what the
    reviewer reads. A `[:k]` slice of the flat list drops whole policy units
    from the queue while a count taken in policy units still looks plausible.
    `test_the_queue_spans_more_rules_than_policy_units` fails on that slice.

  * The flat list has no total order to page over. `list_by_policy_set` orders
    by `created_at` alone, and an extraction inserts a policy's rules in one
    flush so they share a timestamp (the domain model carries a separate
    `sequence` for exactly this reason). An offset window over a non-total
    order drops and repeats rows between pages, and the reviewer paging forward
    is never told which -- the wall Constraint 10 forbids.

  * Every caller needs the whole set. Of the four product call sites, two count
    the result -- one of them in policy units -- and the other two build a
    finding lookup and render the assembled queue; none passes a limit. A
    default limit does not shorten a list, it falsifies a total.
    `test_a_policy_set_read_returns_every_candidate_in_it` fails on any cap.

So there is no limit to add. What there is to protect is the contract the
callers already lean on: ask for a set, receive all of it. These tests pin it.

Constraint 1: the sizes asserted here are the fixture's own, taken with
`len(...)`. No observed corpus count appears in an assertion. The fixture's
shape -- a handful of provisions, a few rules each -- is chosen only so that
rules outnumber policy units, which is what makes a rule-window visibly wrong.
"""
from __future__ import annotations

import inspect
import uuid

import pytest
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from policy_platform.api.routers.candidate_rules import list_candidate_rules
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
from tests.fixtures.factories import make_rule


# JSONB and UUID are Postgres-only. Compiling them for SQLite lets the real
# tables be created, so the real columns and the real query run under the test.
@compiles(JSONB, "sqlite")
def _compile_jsonb(_type, _compiler, **_kw) -> str:
    return "JSON"


@compiles(UUID, "sqlite")
def _compile_uuid(_type, _compiler, **_kw) -> str:
    return "CHAR(36)"


_TEST = FactComparisonCondition(fact="days", operator=ConditionOperator.EXISTS)

# Fixed, not drawn. Set-equality assertions do not depend on id order, but a
# fixture whose contents change run to run is not a fixture.
SET_ID = uuid.UUID("00000000-0000-4000-8000-00000000f001")
SET_KEY = "whole-queue-guard-set"

# A provision is a policy unit. Each holds one or more rules; several of the
# provisions hold more than one, so the rule count exceeds the unit count.
# (provision_id, number_of_rules_in_that_provision)
_PROVISIONS: tuple[tuple[uuid.UUID, int], ...] = (
    (uuid.UUID("00000000-0000-4000-8000-0000000000a1"), 3),
    (uuid.UUID("00000000-0000-4000-8000-0000000000a2"), 2),
    (uuid.UUID("00000000-0000-4000-8000-0000000000a3"), 2),
    (uuid.UUID("00000000-0000-4000-8000-0000000000a4"), 1),
)


def _payload(rule_id: str, clause_id: str) -> dict:
    """A real rule object dumped to JSON, so the endpoint's validate/derive
    pipeline runs over the same shapes extraction writes, not a bare stub."""
    rule = make_rule(rule_id, _TEST).model_copy(
        update={
            "title": rule_id,
            "lineage": RuleLineage(source_elements=clause_id),
            "evidence": [
                EvidenceReference(
                    document_version_id="version-1",
                    source_hash="h" * 16,
                    page=1,
                    clause_id=clause_id,
                )
            ],
        }
    )
    return rule.model_dump(mode="json")


async def _session() -> tuple[AsyncSession, object]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    return maker(), engine


async def _build(session: AsyncSession) -> dict[uuid.UUID, set[str]]:
    """One set, one document, one run, several provisions carrying its rules.

    Returns provision_id -> the set of candidate ids filed under it, so a test
    can assert both the whole population and its grouping into policy units
    without naming a size.
    """
    session.add(PolicySet(id=SET_ID, key=SET_KEY, name=SET_KEY, owner="guard"))

    document_id = uuid.UUID("00000000-0000-4000-8000-00000000f004")
    version_id = uuid.UUID("00000000-0000-4000-8000-00000000f002")
    run_id = uuid.UUID("00000000-0000-4000-8000-00000000f003")
    session.add(
        SourceDocument(id=document_id, title="Handbook", owner="guard", policy_set_id=SET_ID)
    )
    session.add(
        DocumentVersion(
            id=version_id,
            document_id=document_id,
            version_number=1,
            content_hash="c" * 64,
            storage_path="/handbook.pdf",
        )
    )
    session.add(
        ExtractionRun(id=run_id, document_version_id=version_id, status="succeeded")
    )

    filed: dict[uuid.UUID, set[str]] = {}
    counter = 0
    for provision_id, rule_count in _PROVISIONS:
        filed[provision_id] = set()
        clause_id = f"clause-{provision_id.hex[-4:]}"
        for _ in range(rule_count):
            counter += 1
            candidate_id = uuid.UUID(int=counter)
            session.add(
                CandidateRule(
                    id=candidate_id,
                    policy_set_id=SET_ID,
                    extraction_run_id=run_id,
                    provision_id=provision_id,
                    rule_type="obligation",
                    review_status="candidate",
                    delta_status="new",
                    payload_json=_payload(f"AI-{counter:010d}", clause_id),
                )
            )
            filed[provision_id].add(str(candidate_id))

    await session.commit()
    return filed


@pytest.mark.asyncio
async def test_a_policy_set_read_returns_every_candidate_in_it() -> None:
    """The whole review queue, or the reviewer cannot trust the bottom of it.

    Exact-set equality rather than a length check on purpose: it catches a cap
    of any size -- `[:1]`, `[:50]`, `[:len-1]` -- because the failure this
    guards against is a reviewer believing an empty scroll means an empty queue.
    """
    session, engine = await _session()
    try:
        filed = await _build(session)
        expected = {candidate_id for ids in filed.values() for candidate_id in ids}

        result = await list_candidate_rules(key=SET_KEY, session=session)

        returned = {response.id for response in result}
        assert returned == expected
        # No silent cap: the set came back whole, not a prefix of itself.
        assert len(result) == len(expected)
    finally:
        await session.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_the_queue_spans_more_rules_than_policy_units() -> None:
    """Paginating rules would fracture policies, so the unit is wrong.

    The reviewer counts policies; the endpoint returns rules, more of them than
    there are policies. This asserts that gap exists and that every policy unit
    comes back with all of its rules -- the property a rule-window breaks by
    cutting a page boundary through the middle of a provision.
    """
    session, engine = await _session()
    try:
        filed = await _build(session)

        result = await list_candidate_rules(key=SET_KEY, session=session)

        returned_by_provision: dict[str, set[str]] = {}
        for response in result:
            returned_by_provision.setdefault(response.provision_id, set()).add(response.id)

        rule_total = sum(len(ids) for ids in filed.values())
        policy_units = len(filed)
        # The premise of the whole argument: rules outnumber policy units, so a
        # page measured in rules cannot align with the queue measured in policies.
        assert policy_units < rule_total

        # Every policy unit is present, and present whole -- no provision lost a
        # rule to a window.
        assert set(returned_by_provision) == {str(pid) for pid in filed}
        for provision_id, candidate_ids in filed.items():
            assert returned_by_provision[str(provision_id)] == candidate_ids
    finally:
        await session.close()
        await engine.dispose()


def test_the_endpoint_exposes_no_row_limit_knob() -> None:
    """No cap a caller did not ask for -- the refusal, pinned to the exact change.

    The proposed fix was `limit: int = Query(default=50, le=_MAX_LIST_LIMIT)`,
    copied from the list endpoints in ai.py. The behavioural tests above cannot
    catch it on their own: a fixture small enough to read is smaller than that
    default, so the truncation would not fire under test while still cutting a
    live handbook's queue in production. This asserted the knob was simply
    absent, so the fix could not be added without first deleting the test that
    records why it must not be -- which is the point of writing the argument
    down as code.

    THE ARGUMENT WAS MADE, AND IT HELD IN PART. Cursor pagination was added to
    this endpoint, and this test fired exactly as designed. Of the three
    findings in the module docstring, the keyset design answers two:

      * The flat list has no total order to page over. Answered: the cursor
        orders by a unique tiebreaker as well as `created_at`, so rows sharing
        a timestamp are still totally ordered and no row is dropped or repeated
        between pages. Verified by walking the live corpus -- 448 records,
        9 pages, zero duplicates, same set as the unpaginated read.
      * A default limit does not shorten a list, it falsifies a total.
        Answered: `limit` has **no default**. Omit it and the response is the
        same list, in the same shape, as before pagination existed. Every
        current caller omits it, so the contract they lean on is untouched.

    The first finding is NOT answered, and that is why this test still exists
    rather than being deleted. **The policy is the unit, not the rule.** A
    window over the flat rule list can split one policy across two pages, and
    the reviewer's queue is assembled in policy units -- so a paginated client
    would render a policy card built from part of its rules and show no sign
    that the rest were elsewhere. That is the falsified unit the module
    docstring describes, and adding a cursor did not make it safe.

    So the refusal narrows rather than lifts: the endpoint may page, and the
    **policy-assembled queue may not use it** until paging happens in policy
    units. What is pinned below is the property that survived the change --
    that no caller is ever capped without asking.
    """
    parameters = inspect.signature(list_candidate_rules).parameters
    assert "offset" not in parameters, (
        "offset paging over a non-total order drops and repeats rows between "
        "pages, and the reviewer is never told which"
    )

    limit = parameters["limit"]
    default = getattr(limit.default, "default", limit.default)
    assert default is None, (
        "`limit` has acquired a default, so a caller that asked for a set now "
        f"receives a page of {default!r} and a total that describes neither. "
        "The whole-queue contract is that omitting the parameter returns "
        "everything."
    )
