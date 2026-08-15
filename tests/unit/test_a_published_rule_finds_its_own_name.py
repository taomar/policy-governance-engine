"""A published rule reaches the same handle the draft row reached.

WHAT THIS IS ABOUT

A generated handle is stored against the draft row naming ran over, because that
row is what the model was shown. A published version holds no draft row — the
rule *is* the record there — so a reader of a published policy had no id to ask
with and saw no handles at all. That was a difference between two surfaces
showing the same rules, and a difference nobody chose.

So there is a second way in, by the rule's own identifier. These tests hold the
three things that second door has to get right, because each of them fails
silently rather than loudly:

  * it is scoped to a policy set, and a matching identifier in another set is
    somebody else's rule;
  * when several draft rows carry one identifier, the newest handle wins, and it
    wins by time rather than arbitrarily;
  * asking by identifier without saying which set is refused, not guessed;
  * the two doors answer in two maps, so neither can answer the other's
    question.

WHY THE SCOPING TEST IS THE LOAD-BEARING ONE

A canonical rule id records where a rule was found in its document. Two
documents can therefore state the same identifier about entirely unrelated
rules. An unscoped lookup would hand back a handle written about one of them and
render it above the other — our words attached to a record they were never
about, which is precisely the failure this whole feature is arranged to prevent.
It would look completely normal on screen.

Nothing here names a domain, a document or a subject. The identifiers are
invented and carry no meaning beyond being distinct.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from policy_platform.api.routers.ai import RuleNameLookupRequest, lookup_rule_names
from policy_platform.domain.models import CandidateRule, CandidateRuleName, PolicySet
from policy_platform.infrastructure.assembly import rule_name_lookup


@compiles(JSONB, "sqlite")
def _compile_jsonb(_type, _compiler, **_kw) -> str:
    return "JSON"


@compiles(UUID, "sqlite")
def _compile_uuid(_type, _compiler, **_kw) -> str:
    return "CHAR(36)"


SET_ONE = uuid.UUID(int=101)
SET_TWO = uuid.UUID(int=102)
KEY_ONE = "one-set"
KEY_TWO = "another-set"
RUN = uuid.UUID(int=103)

#: An identifier of the shape the pipeline produces, chosen so it says nothing.
SHARED_ID = "p4-E000012"


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        for table in (PolicySet, CandidateRule, CandidateRuleName):
            await connection.run_sync(
                lambda sync, table=table: table.__table__.create(sync, checkfirst=True)
            )
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as active:
        yield active
    await engine.dispose()


async def _add_set(session, *, set_id: uuid.UUID, key: str) -> None:
    session.add(
        PolicySet(id=set_id, key=key, name="A policy set", owner="someone", description="")
    )


async def _add_rule(session, *, set_id: uuid.UUID, rule_id: str) -> uuid.UUID:
    row = CandidateRule(
        id=uuid.uuid4(),
        policy_set_id=set_id,
        extraction_run_id=RUN,
        rule_type="obligation",
        payload_json={"rule_id": rule_id, "statement": "A sentence."},
        review_status="candidate",
    )
    session.add(row)
    return row.id


async def _add_name(session, *, candidate_rule_id: uuid.UUID, text: str, when: datetime) -> None:
    session.add(
        CandidateRuleName(
            id=uuid.uuid4(),
            candidate_rule_id=candidate_rule_id,
            name_text=text,
            model_deployment="a-deployment",
            prompt_version="a-version",
            source_digest=uuid.uuid4().hex,
            generated_at=when,
        )
    )


class TestAskingByRuleIdentifier:
    async def test_it_finds_the_handle_stored_against_the_draft_row(self, session) -> None:
        await _add_set(session, set_id=SET_ONE, key=KEY_ONE)
        draft = await _add_rule(session, set_id=SET_ONE, rule_id=SHARED_ID)
        await _add_name(
            session, candidate_rule_id=draft, text="A handle", when=datetime.now(UTC)
        )
        await session.commit()

        found = await rule_name_lookup.names_for_canonical_rules(
            session, policy_set_id=SET_ONE, rule_ids=[SHARED_ID]
        )

        assert found[SHARED_ID].text == "A handle"

    async def test_a_rule_nobody_named_is_absent_rather_than_null(self, session) -> None:
        # Absent and unavailable are two different states, and the interface
        # draws them differently. Returning a null here would collapse them.
        await _add_set(session, set_id=SET_ONE, key=KEY_ONE)
        await _add_rule(session, set_id=SET_ONE, rule_id=SHARED_ID)
        await session.commit()

        found = await rule_name_lookup.names_for_canonical_rules(
            session, policy_set_id=SET_ONE, rule_ids=[SHARED_ID]
        )

        assert SHARED_ID not in found

    async def test_asking_for_nothing_asks_the_database_nothing(self, session) -> None:
        assert (
            await rule_name_lookup.names_for_canonical_rules(
                session, policy_set_id=SET_ONE, rule_ids=[]
            )
            == {}
        )


class TestOneSetsHandleNeverAnswersForAnother:
    async def test_the_same_identifier_in_another_set_is_not_returned(self, session) -> None:
        await _add_set(session, set_id=SET_ONE, key=KEY_ONE)
        await _add_set(session, set_id=SET_TWO, key=KEY_TWO)
        elsewhere = await _add_rule(session, set_id=SET_TWO, rule_id=SHARED_ID)
        await _add_name(
            session,
            candidate_rule_id=elsewhere,
            text="Written about the other set's rule",
            when=datetime.now(UTC),
        )
        await session.commit()

        found = await rule_name_lookup.names_for_canonical_rules(
            session, policy_set_id=SET_ONE, rule_ids=[SHARED_ID]
        )

        assert found == {}

    async def test_each_set_gets_its_own_handle_for_the_same_identifier(self, session) -> None:
        await _add_set(session, set_id=SET_ONE, key=KEY_ONE)
        await _add_set(session, set_id=SET_TWO, key=KEY_TWO)
        here = await _add_rule(session, set_id=SET_ONE, rule_id=SHARED_ID)
        there = await _add_rule(session, set_id=SET_TWO, rule_id=SHARED_ID)
        await _add_name(session, candidate_rule_id=here, text="Here", when=datetime.now(UTC))
        await _add_name(session, candidate_rule_id=there, text="There", when=datetime.now(UTC))
        await session.commit()

        assert (
            await rule_name_lookup.names_for_canonical_rules(
                session, policy_set_id=SET_ONE, rule_ids=[SHARED_ID]
            )
        )[SHARED_ID].text == "Here"
        assert (
            await rule_name_lookup.names_for_canonical_rules(
                session, policy_set_id=SET_TWO, rule_ids=[SHARED_ID]
            )
        )[SHARED_ID].text == "There"


class TestWhenSeveralDraftRowsCarryOneIdentifier:
    async def test_the_most_recently_generated_handle_wins(self, session) -> None:
        # Re-extraction makes a fresh draft row for the same rule, and naming
        # may have run over more than one. Picking arbitrarily would let one
        # rule show two different handles on two page loads with nothing
        # changed, which reads as the app being unsure what the rule is.
        await _add_set(session, set_id=SET_ONE, key=KEY_ONE)
        older = await _add_rule(session, set_id=SET_ONE, rule_id=SHARED_ID)
        newer = await _add_rule(session, set_id=SET_ONE, rule_id=SHARED_ID)
        now = datetime.now(UTC)
        await _add_name(
            session, candidate_rule_id=newer, text="Newer", when=now
        )
        await _add_name(
            session, candidate_rule_id=older, text="Older", when=now - timedelta(days=1)
        )
        await session.commit()

        found = await rule_name_lookup.names_for_canonical_rules(
            session, policy_set_id=SET_ONE, rule_ids=[SHARED_ID]
        )

        assert found[SHARED_ID].text == "Newer"

    async def test_the_winner_does_not_depend_on_insertion_order(self, session) -> None:
        # The same facts stored in the other order must give the same answer,
        # which is what "by time" means and what "whatever came back first"
        # would fail.
        await _add_set(session, set_id=SET_ONE, key=KEY_ONE)
        newer = await _add_rule(session, set_id=SET_ONE, rule_id=SHARED_ID)
        older = await _add_rule(session, set_id=SET_ONE, rule_id=SHARED_ID)
        now = datetime.now(UTC)
        await _add_name(
            session, candidate_rule_id=older, text="Older", when=now - timedelta(days=1)
        )
        await _add_name(session, candidate_rule_id=newer, text="Newer", when=now)
        await session.commit()

        found = await rule_name_lookup.names_for_canonical_rules(
            session, policy_set_id=SET_ONE, rule_ids=[SHARED_ID]
        )

        assert found[SHARED_ID].text == "Newer"


class TestTheDoorRefusesToGuess:
    async def test_rule_ids_without_a_set_are_refused(self, session) -> None:
        with pytest.raises(HTTPException) as refused:
            await lookup_rule_names(
                RuleNameLookupRequest(rule_ids=[SHARED_ID]), session=session
            )

        assert refused.value.status_code == 422

    async def test_an_unknown_set_is_not_silently_empty(self, session) -> None:
        # An empty answer and a set that does not exist look identical on
        # screen — nothing renders either way — so the caller is told.
        with pytest.raises(HTTPException) as refused:
            await lookup_rule_names(
                RuleNameLookupRequest(rule_ids=[SHARED_ID], policy_set_key="no-such-set"),
                session=session,
            )

        assert refused.value.status_code == 404

    async def test_asking_by_neither_door_is_an_empty_answer_not_an_error(self, session) -> None:
        assert await lookup_rule_names(RuleNameLookupRequest(), session=session) == {
            "names": {},
            "names_by_rule_id": {},
        }


class TestBothDoorsReachOneAnswer:
    async def test_neither_door_can_answer_the_other(self, session) -> None:
        # The identifiers collide here on purpose: the same string is a draft
        # row id in one map and a canonical rule id in the other. Merged into
        # one, an answer to one question would be read as the answer to the
        # other — this app's words above a rule they were never written about,
        # which nothing on screen would reveal.
        await _add_set(session, set_id=SET_ONE, key=KEY_ONE)
        by_draft = await _add_rule(session, set_id=SET_ONE, rule_id="p1-E000001")
        by_rule = await _add_rule(session, set_id=SET_ONE, rule_id=SHARED_ID)
        await _add_name(
            session, candidate_rule_id=by_draft, text="Asked by draft row", when=datetime.now(UTC)
        )
        await _add_name(
            session, candidate_rule_id=by_rule, text="Asked by identifier", when=datetime.now(UTC)
        )
        await session.commit()

        answer = await lookup_rule_names(
            RuleNameLookupRequest(
                candidate_ids=[by_draft], rule_ids=[SHARED_ID], policy_set_key=KEY_ONE
            ),
            session=session,
        )

        assert answer["names"][str(by_draft)]["text"] == "Asked by draft row"
        assert answer["names_by_rule_id"][SHARED_ID]["text"] == "Asked by identifier"
        assert SHARED_ID not in answer["names"]
        assert str(by_draft) not in answer["names_by_rule_id"]

    async def test_every_handle_says_it_was_generated(self, session) -> None:
        # The one property this must never lose: these are our words, not the
        # document's, and the interface marks them so. Stated by the server
        # rather than inferred at the far end.
        await _add_set(session, set_id=SET_ONE, key=KEY_ONE)
        row = await _add_rule(session, set_id=SET_ONE, rule_id=SHARED_ID)
        await _add_name(
            session, candidate_rule_id=row, text="A handle", when=datetime.now(UTC)
        )
        await session.commit()

        answer = await lookup_rule_names(
            RuleNameLookupRequest(rule_ids=[SHARED_ID], policy_set_key=KEY_ONE), session=session
        )

        assert answer["names_by_rule_id"][SHARED_ID]["generated"] is True
