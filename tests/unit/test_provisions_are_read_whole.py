"""A provision is divided only when it does not fit, and never quietly.

The defect these tests exist to hold closed is that a *processing* unit had
become a *semantic* one. Extraction batched by running character count -- a
resource concern and nothing else -- and that batching decided what the model
saw together, and therefore what it read apart. An implementation detail was
deciding where a policy ended.

The reading plan already grouped by provision, but then divided every group at
four targets. A count of targets measures nothing about whether a provision
fits: across the documents held here it cut 106 provisions, and 101 of them
fitted the character budget comfortably. Those were cut for no reason at all.

So the rule asserted below is:

    the semantic unit is the provision; the processing unit is whatever fits;
    a provision is never split across processing units -- and when one genuinely
    cannot fit, that is a reportable condition, not a silent split.

The last clause is the load-bearing one. A division that is recorded can be
read, counted and argued with. A division that is not recorded looks exactly
like a policy that was always in pieces, which is the failure mode the whole
stage exists to remove.
"""
from __future__ import annotations

from policy_platform.contracts.canonical_document import (
    CanonicalDocument,
    CanonicalElement,
    CanonicalPage,
    SourceFragment,
)
from policy_platform.contracts.reading_plan import build_reading_plan
from policy_platform.contracts.structural_graph import build_structural_graph


def _element(
    element_id: str,
    text: str,
    element_type: str = "paragraph",
    order: int = 0,
) -> CanonicalElement:
    return CanonicalElement(
        element_id=element_id,
        element_type=element_type,  # type: ignore[arg-type]
        logical_order=order,
        text=text,
        source_fragments=[
            SourceFragment(page=1, start_offset=0, end_offset=len(text), text=text)
        ],
    )


def _plan(elements: list[CanonicalElement], **kwargs):
    document = CanonicalDocument(
        document_id="DOC",
        page_count=1,
        pages=[CanonicalPage(page=1, raw_text="")],
        elements=elements,
        parser="docling",
    )
    return build_reading_plan(document, build_structural_graph(document), **kwargs)


def _section(heading: str, bodies: list[str], start: int = 0) -> list[CanonicalElement]:
    elements = [_element(f"H{start}", heading, "heading", start)]
    for offset, text in enumerate(bodies, start=1):
        elements.append(_element(f"E{start + offset}", text, "paragraph", start + offset))
    return elements


class TestNothingIsLost:
    """Every element belongs to exactly one provision -- asserted both ways.

    One direction alone is not enough. A plan that duplicated every element
    would satisfy "nothing orphaned" perfectly, and a plan that emitted no
    units at all would satisfy "nothing duplicated". Only the pair pins it.
    """

    def test_no_targetable_element_is_orphaned(self) -> None:
        plan = _plan(_section("1. Leave", [f"Rule {i}." for i in range(9)]))

        assert plan.is_exhaustive
        assert plan.uncovered_target_ids == []

    def test_no_element_appears_in_two_units(self) -> None:
        plan = _plan(_section("1. Leave", [f"Rule {i}." for i in range(9)]))

        seen = [tid for unit in plan.units for tid in unit.target_element_ids]
        assert len(seen) == len(set(seen))

    def test_both_directions_hold_when_a_provision_is_divided(self) -> None:
        """Division is where losing or duplicating an element is easiest."""

        plan = _plan(_section("1. Leave", ["x" * 600] * 12), max_chars_per_unit=1000)

        assert len(plan.units) > 1, "fixture must actually force a division"
        seen = [tid for unit in plan.units for tid in unit.target_element_ids]
        assert len(seen) == len(set(seen))
        assert plan.uncovered_target_ids == []
        assert set(seen) == {e.element_id for e in _section("1. Leave", ["x" * 600] * 12)[1:]}


class TestAProvisionThatFitsIsNeverDivided:
    def test_nine_short_rules_under_one_heading_stay_together(self) -> None:
        """The GMU induction paragraph: nine duties, one provision.

        "the supervisor will discuss work rules, show the work area, introduce
        key people, review the probationary report and make known any safety
        regulations" -- these are genuinely nine rules, and they are genuinely
        one policy. Under the old count-of-four bound this became three units,
        so a model reading the third never saw the sentence that governs it.
        """

        plan = _plan(_section("3. Induction", [f"The supervisor will {i}." for i in range(9)]))

        assert len(plan.units) == 1
        assert len(plan.units[0].target_element_ids) == 9
        assert plan.divided_provisions == []
        assert plan.reads_every_provision_whole

    def test_a_provision_of_one_element_is_normal(self) -> None:
        """Most provisions are one element. That is not a degraded case."""

        plan = _plan(_section("1. Scope", ["This handbook applies to all staff."]))

        assert len(plan.units) == 1
        assert plan.divided_provisions == []

    def test_a_provision_just_under_budget_is_not_divided(self) -> None:
        """The boundary, from the safe side."""

        plan = _plan(_section("1. Leave", ["x" * 400] * 5), max_chars_per_unit=2000)

        assert len(plan.units) == 1
        assert plan.divided_provisions == []

    def test_sections_are_still_separate_provisions(self) -> None:
        """Fitting is permission to keep a provision whole, not to merge two.

        Removing the count bound must not let one unit swallow the next
        section: a section boundary is the document's own statement that the
        subject changed.
        """

        elements = _section("1. Leave", ["Short."], start=0) + _section(
            "2. Overtime", ["Short."], start=10
        )
        plan = _plan(elements)

        assert len(plan.units) == 2
        assert plan.divided_provisions == []


class TestADivisionIsReported:
    def test_a_provision_that_does_not_fit_is_divided(self) -> None:
        plan = _plan(_section("1. Leave", ["x" * 600] * 6), max_chars_per_unit=1000)

        assert len(plan.units) > 1

    def test_and_the_division_is_recorded(self) -> None:
        """The whole point of the stage. A silent split is the defect."""

        plan = _plan(_section("1. Leave", ["x" * 600] * 6), max_chars_per_unit=1000)

        assert len(plan.divided_provisions) == 1
        assert not plan.reads_every_provision_whole

    def test_the_record_says_what_forced_it(self) -> None:
        """A reader must be able to tell a huge provision from a low budget."""

        plan = _plan(_section("1. Leave", ["x" * 600] * 6), max_chars_per_unit=1000)
        divided = plan.divided_provisions[0]

        assert divided.characters == 3600
        assert divided.unit_count == len(plan.units)
        assert len(divided.element_ids) == 6
        assert divided.heading_path == ["1. Leave"]

    def test_an_exhaustive_plan_can_still_have_cut_a_provision(self) -> None:
        """These are two different claims and must not be conflated.

        Exhaustiveness asks whether every element was read. Whole-provision
        reading asks whether any was read apart from what qualifies it. A plan
        can pass the first and fail the second, which is why the second needed
        to exist at all.
        """

        plan = _plan(_section("1. Leave", ["x" * 600] * 6), max_chars_per_unit=1000)

        assert plan.is_exhaustive
        assert not plan.reads_every_provision_whole

    def test_division_preserves_document_order(self) -> None:
        """An exception follows the rule it modifies.

        Packing for even piece sizes rather than in order would break that for
        no gain, so the division is greedy and forward-only.
        """

        plan = _plan(_section("1. Leave", ["x" * 600] * 6), max_chars_per_unit=1000)

        seen = [tid for unit in plan.units for tid in unit.target_element_ids]
        assert seen == sorted(seen, key=lambda t: int(t[1:]))

    def test_an_element_larger_than_the_whole_budget_is_placed_alone(self) -> None:
        """There is no smaller unit to fall back to.

        Dropping it, or refusing to emit it, would lose content -- strictly
        worse than one unit that overruns. It is still reported.
        """

        plan = _plan(
            _section("1. Leave", ["x" * 5000, "short one"]), max_chars_per_unit=1000
        )

        assert plan.is_exhaustive
        assert len(plan.divided_provisions) == 1
        first = plan.units[0]
        assert first.target_element_ids == ["E1"]

    def test_only_the_provisions_that_overflow_are_reported(self) -> None:
        """A neighbouring provision that fits must not be swept into the report."""

        elements = _section("1. Leave", ["x" * 600] * 6, start=0) + _section(
            "2. Overtime", ["Short."] * 6, start=20
        )
        plan = _plan(elements, max_chars_per_unit=1000)

        assert len(plan.divided_provisions) == 1
        assert plan.divided_provisions[0].heading_path == ["1. Leave"]


class TestTheExplicitCountOverride:
    """Callers may still ask for small units -- but not for silent ones."""

    def test_an_explicit_count_still_bounds_units(self) -> None:
        plan = _plan(_section("1. Leave", ["Short."] * 6), max_targets_per_unit=1)

        assert len(plan.units) == 6

    def test_and_choosing_it_does_not_make_the_division_invisible(self) -> None:
        """Opting into cutting is fine. Hiding that you cut is not."""

        plan = _plan(_section("1. Leave", ["Short."] * 6), max_targets_per_unit=1)

        assert len(plan.divided_provisions) == 1
        assert plan.divided_provisions[0].unit_count == 6

    def test_a_count_that_does_not_bite_reports_nothing(self) -> None:
        plan = _plan(_section("1. Leave", ["Short."] * 2), max_targets_per_unit=4)

        assert len(plan.units) == 1
        assert plan.divided_provisions == []


class TestTheDetectorStillSees:
    """The assertions above must be capable of failing.

    Every claim here was checked by mutating the production code and observing
    which tests went red; these fixtures pin the conditions that made those
    mutations detectable, so the suite cannot quietly stop testing anything.
    """

    def test_the_fitting_fixture_would_have_been_divided_by_the_old_bound(self) -> None:
        """Guards `test_nine_short_rules_under_one_heading_stay_together`.

        If that fixture had four targets or fewer, it would pass under the old
        count-of-four behaviour too, and would prove nothing about the change.
        """

        plan = _plan(_section("3. Induction", [f"The supervisor will {i}." for i in range(9)]))

        assert len(plan.units[0].target_element_ids) > 4

    def test_the_overflow_fixture_would_not_be_divided_by_size_alone(self) -> None:
        """Guards the division tests.

        They must fail if `_divide_provision` stops dividing. That requires the
        fixture to exceed the budget it is given -- and to sit comfortably under
        the production default, so it is the budget under test that bites and
        not an accident of the constant.
        """

        elements = _section("1. Leave", ["x" * 600] * 6)
        assert sum(len(e.text) for e in elements[1:]) > 1000
        assert sum(len(e.text) for e in elements[1:]) < 4000

        assert _plan(elements).divided_provisions == []
