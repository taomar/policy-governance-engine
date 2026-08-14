"""Running the pass twice must change nothing, and what it removes must come back.

Both were stated as non-optional when this pass was commissioned, and neither
was evidence until this file existed. The reasoning offered instead -- that
identity is computed from payloads, that nothing is merged, that the pass had
not been pointed at a policy set -- is consistent with both properties and
proves neither.

They matter here more than usual. Supersession has already fired during a run
that then failed and left a reviewer with fewer records than they started
with; that is written up under `docs/failures/`. A remedy for duplicated
records that shared a failure mode with the defect it treats would be worse
than the defect.

These run against a real session over in-memory SQLite, following the pattern
already used for the stage table: the schema's actual columns and constraints
are exercised, and no policy set is touched. Idempotence is asserted as *the
whole table is byte-identical afterwards*, not as *the counts match*, because
a pass that churned which copy it kept would satisfy the second and violate
the first -- and would show up later as a number that quietly differs each
time somebody runs it.
"""
from __future__ import annotations

import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from policy_platform.domain.models import CandidateRule

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from consolidate_duplicates import (  # noqa: E402
    NOTE,
    restore,
    supersede_repetitions,
)


# JSONB and UUID are Postgres-only. Compiling them for SQLite lets the table
# actually be created, so the real columns are exercised rather than a stand-in.
@compiles(JSONB, "sqlite")
def _compile_jsonb(_type, _compiler, **_kw) -> str:
    return "JSON"


@compiles(UUID, "sqlite")
def _compile_uuid(_type, _compiler, **_kw) -> str:
    return "CHAR(36)"


POLICY_SET = uuid.uuid4()
OTHER_SET = uuid.uuid4()
RUN = uuid.uuid4()

SPAN = "p13-E000250"
OTHER_SPAN = "p14-E000267"


def _payload(span: str, subject: str, title: str = "Return of equipment") -> dict:
    """A payload shaped like a real one, carrying its span where the pass looks.

    The span lives in `lineage`, which identity treats as provenance and
    excludes -- which is exactly why it can serve as the group key. Two records
    are compared for sameness *within* a span, never across one.
    """
    return {
        "rule_id": "AI-0000000001",
        "rule_type": "obligation",
        "effect": "permit",
        "title": title,
        "description": "The employee returns issued equipment.",
        "lineage": {"source_elements": span},
        "evidence": [{"element_id": span, "page": 13}],
        "formulation": {
            "source_text": "The employee shall return all issued equipment.",
            "canonical": {
                "rule": {
                    "subject": subject,
                    "predicate": "shall return",
                    "object": "all issued equipment",
                    "modality": "obligation",
                }
            },
        },
        "attributes": {"subject": subject},
    }


async def _add(session: AsyncSession, payload: dict, **columns) -> uuid.UUID:
    row = CandidateRule(
        id=columns.pop("id", uuid.uuid4()),
        policy_set_id=columns.pop("policy_set_id", POLICY_SET),
        extraction_run_id=columns.pop("extraction_run_id", RUN),
        rule_type=columns.pop("rule_type", "obligation"),
        payload_json=payload,
        review_status="candidate",
        **columns,
    )
    session.add(row)
    await session.commit()
    return row.id


#: Which copy is kept is decided by sorting the keys, so a test that cares
#: which one that is has to say which key is which. Random ids would make such
#: a test pass or fail on the draw.
FIRST = uuid.UUID(int=1)
SECOND = uuid.UUID(int=2)


async def _snapshot(session: AsyncSession) -> dict:
    """Every column this pass could possibly move, for every row in the table.

    Expired before selecting so the values come from the database rather than
    from the session's identity map -- otherwise this would compare the pass's
    own in-memory beliefs against themselves and agree with anything.
    """
    session.expire_all()
    rows = (await session.execute(select(CandidateRule))).scalars().all()
    return {
        str(row.id): (
            row.payload_json,
            row.superseded_at,
            row.review_notes,
            row.review_status,
            row.superseded_by_run_id,
        )
        for row in rows
    }


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync: CandidateRule.__table__.create(sync, checkfirst=True)
        )
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as active:
        yield active
    await engine.dispose()


@pytest.fixture
async def populated(session):
    """One repetition, plus three records that must survive it untouched.

    The same content in a *different* span is the trap this pass must not fall
    into: a document can state one obligation twice in two places, and that is
    two facts rather than one repeated.
    """
    kept_a = await _add(session, _payload(SPAN, "the employee"))
    kept_b = await _add(session, _payload(SPAN, "the employee"))
    distinct = await _add(session, _payload(SPAN, "the manager", title="Manager duty"))
    elsewhere = await _add(session, _payload(OTHER_SPAN, "the employee"))
    return session, sorted([str(kept_a), str(kept_b)]), str(distinct), str(elsewhere)


class TestItRemovesTheRightThing:
    """Without this, the properties below would hold trivially over a no-op."""

    async def test_one_copy_of_a_repetition_is_superseded(self, populated) -> None:
        session, pair, distinct, elsewhere = populated

        outcome = await supersede_repetitions(session, policy_set_id=POLICY_SET, apply=True)

        assert outcome.superseded == (pair[1],), "the later key is the redundant one"
        assert list(outcome.repeats[0].redundant) == [pair[1]]

    async def test_the_same_content_in_another_span_survives(self, populated) -> None:
        session, _, distinct, elsewhere = populated

        await supersede_repetitions(session, policy_set_id=POLICY_SET, apply=True)
        current = await _current_ids(session)

        assert elsewhere in current, "a document may state one obligation twice"
        assert distinct in current

    async def test_a_dry_run_writes_nothing(self, populated) -> None:
        session, *_ = populated
        before = await _snapshot(session)

        outcome = await supersede_repetitions(session, policy_set_id=POLICY_SET, apply=False)

        assert outcome.redundant, "it must still find the repetition"
        assert outcome.superseded == ()
        assert await _snapshot(session) == before


class TestIdempotent:
    async def test_a_second_pass_removes_nothing(self, populated) -> None:
        session, *_ = populated
        await supersede_repetitions(session, policy_set_id=POLICY_SET, apply=True)

        second = await supersede_repetitions(session, policy_set_id=POLICY_SET, apply=True)

        assert second.redundant == ()
        assert second.superseded == ()

    async def test_the_whole_table_is_unchanged_by_the_second_pass(self, populated) -> None:
        """Counts matching is not the property. Nothing having moved is."""
        session, *_ = populated
        await supersede_repetitions(session, policy_set_id=POLICY_SET, apply=True)
        after_first = await _snapshot(session)

        await supersede_repetitions(session, policy_set_id=POLICY_SET, apply=True)

        assert await _snapshot(session) == after_first

    async def test_running_it_does_not_move_the_payload_it_reads(self, populated) -> None:
        """Identity is computed from the payload, so a pass that edited a payload
        -- a counter, a flag, a reordering -- would see different records next
        time and could act again on records it had already settled."""
        session, *_ = populated
        before = {key: value[0] for key, value in (await _snapshot(session)).items()}

        await supersede_repetitions(session, policy_set_id=POLICY_SET, apply=True)

        assert {key: value[0] for key, value in (await _snapshot(session)).items()} == before

    async def test_apply_undo_apply_reaches_the_same_state(self, populated) -> None:
        """Which copy is kept is arbitrary, so it has to be *stably* arbitrary.

        A pass that kept a different copy each cycle would leave the counts
        alone and rewrite the audit trail underneath them.
        """
        session, *_ = populated
        first = await supersede_repetitions(session, policy_set_id=POLICY_SET, apply=True)
        after_first = await _snapshot(session)

        await restore(session, policy_set_id=POLICY_SET)
        second = await supersede_repetitions(session, policy_set_id=POLICY_SET, apply=True)

        assert second.superseded == first.superseded
        assert {k: v[0] for k, v in (await _snapshot(session)).items()} == {
            k: v[0] for k, v in after_first.items()
        }


class TestReversible:
    async def test_undo_restores_exactly_what_the_pass_removed(self, populated) -> None:
        session, *_ = populated
        before = await _snapshot(session)

        outcome = await supersede_repetitions(session, policy_set_id=POLICY_SET, apply=True)
        restored = await restore(session, policy_set_id=POLICY_SET)

        assert restored == len(outcome.superseded)
        assert await _snapshot(session) == before, "the round trip must land where it started"

    async def test_a_second_undo_restores_nothing(self, populated) -> None:
        session, *_ = populated
        await supersede_repetitions(session, policy_set_id=POLICY_SET, apply=True)
        await restore(session, policy_set_id=POLICY_SET)

        assert await restore(session, policy_set_id=POLICY_SET) == 0

    async def test_undo_leaves_rows_superseded_by_anything_else_alone(self, session) -> None:
        """The failure this borrows its mechanism from, not repeated.

        Supersession is used by the extraction pipeline and by reviewers. An
        undo that restored every superseded row would be a second way to
        overturn a decision nobody asked it to overturn.
        """
        run_id = uuid.uuid4()
        moment = datetime(2024, 1, 1, tzinfo=timezone.utc)
        theirs = await _add(
            session,
            _payload(OTHER_SPAN, "the contractor"),
            superseded_at=moment,
            superseded_by_run_id=run_id,
            review_notes="Superseded by a later extraction",
        )

        assert await restore(session, policy_set_id=POLICY_SET) == 0

        row = await session.get(CandidateRule, theirs)
        # SQLite stores no offset, so the value comes back naive here where
        # Postgres would return it aware. The property under test is that the
        # instant is untouched, not how the substrate spells it.
        assert row.superseded_at.replace(tzinfo=None) == moment.replace(tzinfo=None)
        assert row.review_notes == "Superseded by a later extraction"

    async def test_a_copy_carrying_a_reviewers_note_is_left_where_it_is(
        self, session
    ) -> None:
        """`--undo` finds its rows by the note, so superseding a row that already
        carries one would either destroy the note or strand the row."""
        first = await _add(session, _payload(SPAN, "the employee"), id=FIRST)
        annotated = str(SECOND)
        await _add(
            session,
            _payload(SPAN, "the employee"),
            id=SECOND,
            review_notes="Checked, keep this one",
        )
        assert str(first) < annotated, "the annotated copy must be the redundant one"

        outcome = await supersede_repetitions(session, policy_set_id=POLICY_SET, apply=True)

        assert outcome.skipped == (annotated,)
        assert outcome.superseded == ()
        assert annotated in await _current_ids(session)

    async def test_the_note_says_what_happened_and_is_the_undo_key(
        self, populated
    ) -> None:
        """A reviewer meeting a missing record can find out where it went, and
        the same string is what makes the removal findable again."""
        session, *_ = populated
        outcome = await supersede_repetitions(session, policy_set_id=POLICY_SET, apply=True)

        row = await session.get(CandidateRule, uuid.UUID(outcome.superseded[0]))

        assert row.review_notes == NOTE
        assert "repetition" in NOTE and "same source span" in NOTE


class TestScope:
    async def test_another_policy_set_is_not_touched(self, session) -> None:
        """A pass told to consolidate one set must not reach into another."""
        theirs = await _add(
            session, _payload(SPAN, "the employee"), policy_set_id=OTHER_SET
        )
        await _add(session, _payload(SPAN, "the employee"), policy_set_id=OTHER_SET)
        mine_a = await _add(session, _payload(SPAN, "the employee"), id=FIRST)
        await _add(session, _payload(SPAN, "the employee"), id=SECOND)

        outcome = await supersede_repetitions(session, policy_set_id=POLICY_SET, apply=True)

        assert outcome.considered == 2
        assert str(theirs) in await _current_ids(session)
        assert str(mine_a) in await _current_ids(session)


async def _current_ids(session: AsyncSession) -> set[str]:
    rows = (
        (
            await session.execute(
                select(CandidateRule).where(CandidateRule.superseded_at.is_(None))
            )
        )
        .scalars()
        .all()
    )
    return {str(row.id) for row in rows}
