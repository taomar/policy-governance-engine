"""Tests for deterministic canonical element identity.

The property under test is not "ids look right" but the one that made the
ordinal scheme unsafe: a *local* change to a document must cause only a *local*
change to identity. Everything else here exists to stop identity from becoming
either too fragile (whitespace changing a rule's id) or too permissive (a
negation or a threshold being folded away).
"""
from __future__ import annotations

import pytest

from policy_platform.contracts.element_identity import (
    assign_element_ids,
    element_identity,
    is_legacy_element_id,
    is_valid_element_id,
    normalize_for_identity,
    structural_path,
)

RELEASE = "a" * 64
OTHER_RELEASE = "b" * 64


def _element(text: str, **overrides) -> dict:
    base = {"element_type": "paragraph", "text": text, "section_path": ["Leave"]}
    base.update(overrides)
    return base


class TestStability:
    def test_identity_is_deterministic(self) -> None:
        first = element_identity(source_release=RELEASE, **_element("Employees must apply."))
        second = element_identity(source_release=RELEASE, **_element("Employees must apply."))
        assert first == second

    def test_inserting_an_element_does_not_shift_its_neighbours(self) -> None:
        """The defect that motivated the whole module.

        Under `E{n:06d}`, adding one element renumbered every element after it,
        silently repointing already-published spans.
        """

        before = [
            _element("First clause.", sibling_index=0),
            _element("Second clause.", sibling_index=1),
        ]
        after = [
            _element("First clause.", sibling_index=0),
            _element("Newly detected header.", element_type="heading", sibling_index=1),
            _element("Second clause.", sibling_index=1),
        ]
        ids_before, _ = assign_element_ids(RELEASE, before)
        ids_after, _ = assign_element_ids(RELEASE, after)

        assert ids_before[0] == ids_after[0]
        assert ids_before[1] == ids_after[2]

    def test_identity_survives_reflowed_whitespace(self) -> None:
        """A converter change that rewraps a line is not a change of policy."""

        flat = element_identity(source_release=RELEASE, **_element("Employees must apply in writing."))
        wrapped = element_identity(
            source_release=RELEASE, **_element("Employees must apply\n   in  writing.")
        )
        assert flat == wrapped

    def test_identity_survives_unicode_compatibility_forms(self) -> None:
        composed = element_identity(source_release=RELEASE, **_element("ﬁve days"))
        decomposed = element_identity(source_release=RELEASE, **_element("five days"))
        assert composed == decomposed


class TestSeparation:
    def test_same_text_in_different_releases_differs(self) -> None:
        one = element_identity(source_release=RELEASE, **_element("Employees must apply."))
        two = element_identity(source_release=OTHER_RELEASE, **_element("Employees must apply."))
        assert one != two

    def test_same_text_under_different_headings_differs(self) -> None:
        leave = element_identity(
            source_release=RELEASE, **_element("Approval is required.", section_path=["Leave"])
        )
        travel = element_identity(
            source_release=RELEASE, **_element("Approval is required.", section_path=["Travel"])
        )
        assert leave != travel

    @pytest.mark.parametrize(
        ("left", "right"),
        [
            ("Expenses must exceed 5 days.", "Expenses must not exceed 5 days."),
            ("Limit is 5 days.", "Limit is 5.0 days."),
            ("Limit is 15 days.", "Limit is 50 days."),
            ("Manager approval required.", "manager approval required."),
        ],
    )
    def test_meaning_changing_edits_change_identity(self, left: str, right: str) -> None:
        """Negation, precision, digits and case must all remain significant.

        Folding any of these would let two genuinely different rules share one
        identity, which is how a policy change disappears from a diff.
        """

        assert element_identity(source_release=RELEASE, **_element(left)) != element_identity(
            source_release=RELEASE, **_element(right)
        )

    def test_table_position_separates_identical_cell_text(self) -> None:
        """The same value means different things in different rows."""

        first = element_identity(
            source_release=RELEASE,
            element_type="table_cell",
            text="5",
            table_id="T1",
            row_index=1,
            column_index=2,
        )
        second = element_identity(
            source_release=RELEASE,
            element_type="table_cell",
            text="5",
            table_id="T1",
            row_index=7,
            column_index=2,
        )
        assert first != second

    def test_element_type_separates_identical_text(self) -> None:
        heading = element_identity(source_release=RELEASE, **_element("Overtime", element_type="heading"))
        para = element_identity(source_release=RELEASE, **_element("Overtime", element_type="paragraph"))
        assert heading != para


class TestCollisions:
    def test_identical_elements_get_distinct_ids_and_are_reported(self) -> None:
        """A repeated table row must stay two rows, and must be visible.

        Merging them would drop content; falling back to output order would
        reintroduce the instability the scheme exists to remove.
        """

        rows = [
            {"element_type": "table_row", "text": "Standard | 5", "table_id": "T1"},
            {"element_type": "table_row", "text": "Standard | 5", "table_id": "T1"},
        ]
        ids, collisions = assign_element_ids(RELEASE, rows)

        assert ids[0] != ids[1]
        assert len(set(ids)) == 2
        assert len(collisions) == 1
        assert "table_row" in collisions[0]

    def test_no_collisions_reported_for_distinct_elements(self) -> None:
        ids, collisions = assign_element_ids(
            RELEASE, [_element("One."), _element("Two."), _element("Three.")]
        )
        assert collisions == []
        assert len(set(ids)) == 3

    def test_collision_suffixes_are_stable_across_runs(self) -> None:
        rows = [{"element_type": "table_row", "text": "x", "table_id": "T1"}] * 3
        first, _ = assign_element_ids(RELEASE, rows)
        second, _ = assign_element_ids(RELEASE, rows)
        assert first == second


class TestFormat:
    def test_generated_ids_are_recognised(self) -> None:
        assert is_valid_element_id(element_identity(source_release=RELEASE, **_element("x")))

    def test_collision_suffixed_ids_are_recognised(self) -> None:
        value = element_identity(source_release=RELEASE, occurrence=2, **_element("x"))
        assert is_valid_element_id(value)

    def test_ids_fit_the_persisted_column(self) -> None:
        """`Clause.element_id` is a bounded column; ids must fit without truncation."""

        value = element_identity(source_release=RELEASE, occurrence=99, **_element("x"))
        assert len(value) <= 64

    def test_legacy_ordinal_ids_are_still_recognised(self) -> None:
        """Published releases keep their original identifiers.

        The directive forbids silently recanonicalizing them, so both shapes
        must be distinguishable rather than one looking like corruption.
        """

        assert is_legacy_element_id("E000001")
        assert not is_valid_element_id("E000001")
        assert not is_legacy_element_id(element_identity(source_release=RELEASE, **_element("x")))


class TestNormalization:
    def test_collapses_all_whitespace_runs(self) -> None:
        assert normalize_for_identity("a \n\t  b") == "a b"

    def test_preserves_case_and_punctuation(self) -> None:
        assert normalize_for_identity("Must NOT exceed 5.0%.") == "Must NOT exceed 5.0%."


class TestStructuralPath:
    def test_path_is_hierarchical_not_ordinal(self) -> None:
        path = structural_path(element_type="paragraph", section_path=["2. Leave", "2.1 Annual"])
        assert path == "sec:2. Leave/sec:2.1 Annual/paragraph"

    def test_table_coordinates_appear_in_path(self) -> None:
        path = structural_path(element_type="table_cell", table_id="T1", row_index=3, column_index=1)
        assert "tbl:T1" in path
        assert "r3" in path
        assert "c1" in path
