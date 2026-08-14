"""A batch may break between provisions, never inside one.

The batch is a *processing* unit: it exists because a context window is finite.
It had also quietly become a *semantic* one, because where it breaks decides
what the model reads together. It broke on a running character count, which
knows nothing about where a policy ends -- so a rule landed in one batch and the
sentence qualifying it in the next, and the model could only read them as two
unrelated statements.

Measured on the documents stored here, the old walk cut 13 provisions on the AIS
handbook and 21 on GMU across a batch boundary. Not one of those cuts was
necessary; they were artefacts of where the running total happened to be.

The rule these tests hold closed:

    a provision is added to a batch whole, or it starts a new one. Only a
    provision that cannot fit alone is divided, and every division is reported.

And the invariant that makes it safe to change batching at all: the grouping
decides where batches *break*, never which clauses are sent. Every clause lands
in exactly one batch, in document order, headings included.
"""
from __future__ import annotations

from policy_platform.domain.models import Clause
from policy_platform.infrastructure.extraction.ai_extraction import (
    _MAX_CHARS_PER_BATCH,
    _batch_clauses,
)


def _clause(seq: int, text: str, element_type: str = "paragraph", section: str | None = None) -> Clause:
    return Clause(
        clause_ref=f"c{seq:03d}",
        section=section,
        page=1,
        text=text,
        sequence=seq,
        element_id=f"E{seq:06d}",
        element_type=element_type,
        source_fragments=[{"page": 1, "start_offset": 0, "end_offset": len(text), "text": text}],
    )


def _provision(start: int, heading: str, bodies: list[str]) -> list[Clause]:
    """A heading and the material it governs, as ingestion would store it.

    Body clauses carry `section=heading`, which is how the persisted shape
    records the heading/body relationship.
    """

    out = [_clause(start, heading, "heading")]
    for offset, body in enumerate(bodies, start=1):
        out.append(_clause(start + offset, body, "paragraph", section=heading))
    return out


def _refs(batches: list[list[Clause]]) -> list[str]:
    return [c.clause_ref for batch in batches for c in batch]


#: Sized so that, after a filler provision that nearly fills a batch, a running
#: character walk takes the following heading and then runs out before its first
#: rule -- separating a heading from the material it introduces. Any shorter and
#: the walk swallows the whole provision and the boundary tests below prove
#: nothing. `TestTheDetectorStillSees` asserts this arithmetic rather than
#: trusting it, because it silently stops holding if the budget moves.
_LONG_A = "a" * 600
_LONG_B = "b" * 600
_LONG_C = "c" * 600


class TestNothingIsLost:
    """Batching decides where breaks fall, not which clauses are sent.

    Asserted in both directions and on order. Any one alone is satisfiable by a
    degenerate result: dropping everything loses no duplicates, and duplicating
    everything orphans nothing.
    """

    def test_every_clause_is_sent(self) -> None:
        clauses = _provision(0, "1. Leave", ["Rule A.", "Rule B."]) + _provision(
            10, "2. Overtime", ["Rule C."]
        )

        batches, _ = _batch_clauses(clauses, "DOC")

        assert set(_refs(batches)) == {c.clause_ref for c in clauses}

    def test_no_clause_is_sent_twice(self) -> None:
        clauses = _provision(0, "1. Leave", ["Rule A.", "Rule B."]) + _provision(
            10, "2. Overtime", ["Rule C."]
        )

        batches, _ = _batch_clauses(clauses, "DOC")
        refs = _refs(batches)

        assert len(refs) == len(set(refs))

    def test_document_order_is_preserved(self) -> None:
        """Policy text is written to be read forwards.

        An exception follows the rule it modifies. Reordering to make batches
        pack more evenly would change what the model concludes, for nothing.
        """

        clauses = _provision(0, "1. Leave", ["Rule A.", "Rule B."]) + _provision(
            10, "2. Overtime", ["Rule C."]
        )

        batches, _ = _batch_clauses(clauses, "DOC")

        assert _refs(batches) == [c.clause_ref for c in clauses]

    def test_headings_are_still_sent(self) -> None:
        """The reading plan targets only targetable elements, and a heading is
        not one. Batching on targets alone would have silently stopped sending
        80 headings on the AIS handbook -- material the previous path did send.
        """

        clauses = _provision(0, "1. Leave", ["Rule A."])

        batches, _ = _batch_clauses(clauses, "DOC")

        assert "c000" in _refs(batches)

    def test_nothing_is_lost_when_a_provision_must_be_divided(self) -> None:
        """Division is where losing or duplicating a clause is easiest."""

        clauses = _provision(0, "1. Leave", ["x" * 1200] * 6)

        batches, divided = _batch_clauses(clauses, "DOC")

        assert len(batches) > 1
        assert divided
        assert _refs(batches) == [c.clause_ref for c in clauses]


class TestAProvisionIsNotSplitBetweenBatches:
    def _batch_of(self, batches: list[list[Clause]], ref: str) -> int:
        for index, batch in enumerate(batches):
            if any(c.clause_ref == ref for c in batch):
                return index
        raise AssertionError(f"{ref} was not sent at all")

    def test_a_provision_that_fits_lands_in_one_batch(self) -> None:
        clauses = _provision(0, "1. Leave", [_LONG_A, _LONG_B, _LONG_C])

        batches, _ = _batch_clauses(clauses, "DOC")

        assert len({self._batch_of(batches, c.clause_ref) for c in clauses} ) == 1

    def test_a_provision_is_not_cut_by_a_neighbour_filling_the_batch(self) -> None:
        """The defect, reproduced.

        A long first provision leaves just enough room that the old running
        total would take the second provision's heading and first rule, then
        break -- stranding the rest of that provision in the next batch. The
        provision must move whole instead.
        """

        filler = _provision(0, "1. Filler", ["y" * (_MAX_CHARS_PER_BATCH - 700)])
        target = _provision(10, "2. Leave", [_LONG_A, _LONG_B, _LONG_C])

        batches, _ = _batch_clauses(filler + target, "DOC")

        homes = {self._batch_of(batches, c.clause_ref) for c in target}
        assert len(homes) == 1, "the second provision was split across batches"

    def test_a_heading_travels_with_the_material_it_introduces(self) -> None:
        """A heading keyed to its parent would end the *previous* provision.

        That is the same cut this stage removes, applied to the one element
        whose entire purpose is to say what comes next.
        """

        filler = _provision(0, "1. Filler", ["y" * (_MAX_CHARS_PER_BATCH - 700)])
        target = _provision(10, "2. Leave", [_LONG_A, _LONG_B])

        batches, _ = _batch_clauses(filler + target, "DOC")

        heading_home = self._batch_of(batches, "c010")
        assert heading_home == self._batch_of(batches, "c011")


class TestADivisionIsReported:
    def test_a_provision_too_large_for_any_batch_is_divided(self) -> None:
        clauses = _provision(0, "1. Leave", ["x" * 1200] * 6)

        batches, _ = _batch_clauses(clauses, "DOC")

        assert len(batches) > 1

    def test_and_the_division_is_reported(self) -> None:
        """The whole point. A silent split is indistinguishable from a document
        that was always in pieces.
        """

        clauses = _provision(0, "1. Leave", ["x" * 1200] * 6)

        _, divided = _batch_clauses(clauses, "DOC")

        assert len(divided) == 1

    def test_the_report_names_the_provision_and_its_size(self) -> None:
        """A reader must be able to tell a huge provision from a low budget."""

        clauses = _provision(0, "1. Leave", ["x" * 1200] * 6)

        _, divided = _batch_clauses(clauses, "DOC")

        assert divided[0].heading_path == ["1. Leave"]
        assert divided[0].characters > _MAX_CHARS_PER_BATCH
        assert divided[0].unit_count > 1

    def test_a_provision_that_fits_is_never_reported(self) -> None:
        """Reporting a division that did not happen trains readers to ignore
        the report, which costs more than saying nothing.
        """

        clauses = _provision(0, "1. Leave", ["Rule A.", "Rule B."])

        _, divided = _batch_clauses(clauses, "DOC")

        assert divided == []

    def test_only_the_overflowing_provision_is_reported(self) -> None:
        clauses = _provision(0, "1. Leave", ["x" * 1200] * 6) + _provision(
            20, "2. Overtime", ["Short."]
        )

        _, divided = _batch_clauses(clauses, "DOC")

        assert [d.heading_path for d in divided] == [["1. Leave"]]


class TestGroupingFailureDegrades:
    """A document whose structure defeats grouping is still worth extracting.

    Batching is a resource decision. Failing a whole run because the *grouping*
    failed would trade a better reading for no reading.
    """

    def test_clauses_with_no_structure_are_still_batched(self) -> None:
        clauses = [_clause(i, f"Sentence {i}.") for i in range(5)]

        batches, _ = _batch_clauses(clauses, "DOC")

        assert _refs(batches) == [c.clause_ref for c in clauses]

    def test_an_empty_document_produces_no_batches(self) -> None:
        batches, divided = _batch_clauses([], "DOC")

        assert batches == []
        assert divided == []


class TestTheDetectorStillSees:
    """These assertions must be capable of failing.

    Each was checked by mutating the production code and observing which tests
    went red. These fixtures pin the conditions that made the mutations
    detectable, so the suite cannot quietly stop testing anything.
    """

    def test_the_splitting_fixture_would_have_been_cut_by_a_character_walk(self) -> None:
        """Guards `test_a_provision_is_not_cut_by_a_neighbour_filling_the_batch`.

        If the filler did not nearly fill a batch, the running-total walk would
        not have cut the following provision either, and the test would pass
        against the very code it exists to reject.
        """

        filler = _provision(0, "1. Filler", ["y" * (_MAX_CHARS_PER_BATCH - 700)])
        target = _provision(10, "2. Leave", [_LONG_A, _LONG_B, _LONG_C])

        used = sum(len(c.text) + 40 for c in filler)
        assert used < _MAX_CHARS_PER_BATCH, "filler must fit its own batch"
        heading_only = used + len(target[0].text) + 40
        assert heading_only < _MAX_CHARS_PER_BATCH, (
            "a character walk must take the target's heading"
        )
        assert heading_only + len(target[1].text) + 40 > _MAX_CHARS_PER_BATCH, (
            "and must then break before its first rule, stranding the heading"
        )

    def test_the_overflow_fixture_genuinely_exceeds_the_budget(self) -> None:
        """Guards the division tests: they must fail if dividing stops."""

        clauses = _provision(0, "1. Leave", ["x" * 1200] * 6)

        assert sum(len(c.text) + 40 for c in clauses) > _MAX_CHARS_PER_BATCH

    def test_the_fitting_fixture_genuinely_fits(self) -> None:
        """Guards `test_a_provision_that_fits_is_never_reported`."""

        clauses = _provision(0, "1. Leave", ["Rule A.", "Rule B."])

        assert sum(len(c.text) + 40 for c in clauses) < _MAX_CHARS_PER_BATCH
