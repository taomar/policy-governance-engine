"""Tests for graph-aware context assembly.

The module replaces fixed 4,000-character windows, which failed in two
directions: they split a rule from its exception, and they joined the tail of
one section to the head of the next. These tests assert the replacement does
neither, and that the target/context distinction is real rather than cosmetic —
a definition pulled in for interpretation must never look like the rule's own
text.
"""
from __future__ import annotations

import pytest

from policy_platform.contracts.canonical_document import (
    CanonicalDocument,
    CanonicalElement,
    CanonicalPage,
    SourceFragment,
    TableCellRef,
)
from policy_platform.contracts.reading_plan import (
    build_reading_plan,
    find_cross_references,
)
from policy_platform.contracts.structural_graph import build_structural_graph


def _element(
    element_id: str,
    text: str,
    element_type: str = "paragraph",
    order: int = 0,
    page: int = 1,
    **kwargs,
) -> CanonicalElement:
    return CanonicalElement(
        element_id=element_id,
        element_type=element_type,  # type: ignore[arg-type]
        logical_order=order,
        text=text,
        source_fragments=[
            SourceFragment(page=page, start_offset=0, end_offset=len(text), text=text)
        ],
        **kwargs,
    )


def _document(elements: list[CanonicalElement]) -> CanonicalDocument:
    pages = sorted({f.page for e in elements for f in e.source_fragments} or {1})
    return CanonicalDocument(
        document_id="DOC",
        page_count=len(pages),
        pages=[CanonicalPage(page=p, raw_text="") for p in pages],
        elements=elements,
        parser="docling",
    )


def _plan(elements: list[CanonicalElement], **kwargs):
    document = _document(elements)
    return build_reading_plan(document, build_structural_graph(document), **kwargs)


class TestExhaustiveness:
    def test_every_targetable_element_is_covered(self) -> None:
        """A unit-based reading that omits a paragraph is a parser that lost it."""

        plan = _plan(
            [
                _element("E1", "1. Scope", "heading", 0),
                _element("E2", "First clause.", order=1),
                _element("E3", "Second clause.", order=2),
                _element("E4", "2. Leave", "heading", 3),
                _element("E5", "Third clause.", order=4),
            ]
        )
        covered = {t for unit in plan.units for t in unit.target_element_ids}

        assert covered == {"E2", "E3", "E5"}
        assert plan.is_exhaustive

    def test_headings_are_context_not_targets(self) -> None:
        """A heading scopes a rule; it does not state one."""

        plan = _plan(
            [_element("E1", "1. Scope", "heading", 0), _element("E2", "A clause.", order=1)]
        )
        assert all("E1" not in u.target_element_ids for u in plan.units)
        assert "E1" in plan.units[0].context_element_ids

    def test_furniture_is_neither_target_nor_lost(self) -> None:
        plan = _plan(
            [
                _element("E1", "Confidential", "furniture", 0),
                _element("E2", "A clause.", order=1),
            ]
        )
        assert plan.is_exhaustive
        assert all("E1" not in u.target_element_ids for u in plan.units)

    def test_legacy_table_rows_are_targetable(self) -> None:
        """The two parsers disagree about table granularity.

        Docling emits cells; the legacy parsers emit whole rows. A row like
        "P1 | Active data breach | 15 minutes" is as policy-bearing as the cells
        it is made of, and omitting the type left every legacy-parsed table row
        in no unit at all — reported as content the run had silently ignored.
        """

        plan = _plan(
            [
                _element("E1", "2. Severity", "heading", 0),
                _element("E2", "P1 - Critical | Active breach | 15 minutes", "table_row", 1),
            ]
        )
        covered = {t for unit in plan.units for t in unit.target_element_ids}

        assert "E2" in covered
        assert plan.is_exhaustive

    def test_empty_document_produces_an_exhaustive_empty_plan(self) -> None:
        plan = _plan([])
        assert plan.units == [] or all(not u.target_element_ids for u in plan.units)
        assert plan.is_exhaustive


class TestSectionBoundaries:
    def test_units_never_span_two_sections(self) -> None:
        """The defect a fixed window caused: a condition attached to the wrong rule."""

        plan = _plan(
            [
                _element("E1", "2. Leave", "heading", 0),
                _element("E2", "Leave clause.", order=1),
                _element("E3", "3. Travel", "heading", 2),
                _element("E4", "Travel clause.", order=3),
            ]
        )
        for unit in plan.units:
            assert not {"E2", "E4"} <= set(unit.target_element_ids)

    def test_size_limit_splits_within_a_section_only(self) -> None:
        """A bound on unit size must not reintroduce an arbitrary cut."""

        elements = [_element("H", "1. Scope", "heading", 0)]
        elements += [_element(f"E{i}", f"Clause {i}.", order=i) for i in range(1, 6)]
        elements.append(_element("H2", "2. Other", "heading", 6))
        elements.append(_element("E9", "Other clause.", order=7))

        plan = _plan(elements, max_targets_per_unit=2)
        for unit in plan.units:
            paths = {tuple(unit.heading_path)}
            assert len(paths) == 1
            assert "E9" not in unit.target_element_ids or unit.target_element_ids == ["E9"]

    def test_heading_path_is_carried_on_every_unit(self) -> None:
        plan = _plan(
            [
                _element("E1", "Policy", "title", 0),
                _element("E2", "2. Leave", "heading", 1),
                _element("E3", "A clause.", order=2),
            ]
        )
        assert plan.units[0].heading_path == ["Policy", "2. Leave"]


class TestTargetVersusContext:
    def test_context_never_appears_as_a_target(self) -> None:
        """Quoting a definition as the rule's own text misrepresents the source."""

        plan = _plan(
            [
                _element("E1", '"Eligible Employee" means an employee of 12 months.', order=0),
                _element("E2", "An Eligible Employee may request leave.", order=1),
            ]
        )
        for unit in plan.units:
            assert not set(unit.target_element_ids) & set(unit.context_element_ids)

    def test_every_context_element_carries_a_reason(self) -> None:
        plan = _plan(
            [
                _element("E1", "1. Scope", "heading", 0),
                _element("E2", "A clause.", order=1),
            ]
        )
        for unit in plan.units:
            for entry in unit.context:
                assert entry.reason
                assert unit.reasons_for(entry.element_id)

    def test_ordering_follows_the_document(self) -> None:
        """An exception usually follows the rule; shuffling changes the reading."""

        plan = _plan(
            [
                _element("E1", "1. Scope", "heading", 0),
                _element("E2", "A clause.", order=1),
                _element("E3", "Another clause.", order=2),
            ]
        )
        unit = plan.units[0]
        assert unit.ordered_element_ids == ["E1", "E2", "E3"]

    def test_structural_context_is_not_marked_as_candidate(self) -> None:
        """Unverified suggestions must never masquerade as structural fact."""

        plan = _plan(
            [_element("E1", "1. Scope", "heading", 0), _element("E2", "A clause.", order=1)]
        )
        assert all(not c.is_candidate for u in plan.units for c in u.context)


class TestDependencyClosure:
    def test_ancestor_headings_are_pulled_in(self) -> None:
        plan = _plan(
            [
                _element("E1", "Policy", "title", 0),
                _element("E2", "2. Leave", "heading", 1),
                _element("E3", "2.1 Annual", "heading", 2),
                _element("E4", "Employees accrue 20 days.", order=3),
            ]
        )
        context = set(plan.units[0].context_element_ids)
        assert {"E1", "E2", "E3"} <= context

    def test_list_parent_and_siblings_are_pulled_in(self) -> None:
        """'(c) except where (a) applies' is unreadable without its siblings."""

        plan = _plan(
            [
                _element("E1", "Eligible if:", "list_item", 0, list_level=0),
                _element("E2", "employed 12 months", "list_item", 1, list_level=1),
                _element("E3", "except during probation", "list_item", 2, list_level=1),
            ],
            max_targets_per_unit=1,
        )
        unit = next(u for u in plan.units if u.target_element_ids == ["E3"])
        reasons = {r for eid in unit.context_element_ids for r in unit.reasons_for(eid)}

        assert "list_parent" in reasons
        assert "list_sibling" in reasons

    def test_table_headers_are_pulled_in_for_a_cell(self) -> None:
        """A cell reading '15 minutes' states nothing on its own."""

        plan = _plan(
            [
                _element(
                    "H1",
                    "SLA",
                    "table_cell",
                    0,
                    table_id="#/tables/0",
                    table_cell=TableCellRef(row_index=0, column_index=0, is_header=True),
                ),
                _element(
                    "C1",
                    "15 minutes",
                    "table_cell",
                    1,
                    table_id="#/tables/0",
                    table_cell=TableCellRef(row_index=1, column_index=0),
                ),
            ]
        )
        unit = plan.units[0]
        assert "H1" in unit.context_element_ids
        assert "table_header" in unit.reasons_for("H1")

    def test_header_cells_are_not_extraction_targets(self) -> None:
        plan = _plan(
            [
                _element(
                    "H1",
                    "SLA",
                    "table_cell",
                    0,
                    table_id="#/tables/0",
                    table_cell=TableCellRef(row_index=0, column_index=0, is_header=True),
                ),
                _element(
                    "C1",
                    "15 minutes",
                    "table_cell",
                    1,
                    table_id="#/tables/0",
                    table_cell=TableCellRef(row_index=1, column_index=0),
                ),
            ]
        )
        assert all("H1" not in u.target_element_ids for u in plan.units)

    def test_only_the_row_label_is_pulled_in_not_the_whole_table(self) -> None:
        """Pulling every sibling cell is a sliding window under another name.

        A large table has ~94 cells; putting all of them into each cell's
        context defeats the purpose of targeted assembly, and the row above is
        rarely relevant to the row below.
        """

        elements = [
            _element(
                f"H{c}",
                f"Header {c}",
                "table_cell",
                c,
                table_id="#/tables/0",
                table_cell=TableCellRef(row_index=0, column_index=c, is_header=True),
            )
            for c in range(3)
        ]
        for r in (1, 2):
            for c in range(3):
                elements.append(
                    _element(
                        f"R{r}C{c}",
                        f"value {r}{c}",
                        "table_cell",
                        10 * r + c,
                        table_id="#/tables/0",
                        table_cell=TableCellRef(row_index=r, column_index=c),
                    )
                )

        plan = _plan(elements, max_targets_per_unit=1)
        unit = next(u for u in plan.units if u.target_element_ids == ["R1C2"])
        row_labels = [
            eid for eid in unit.context_element_ids if "table_row_label" in unit.reasons_for(eid)
        ]

        assert row_labels == ["R1C0"]
        assert "R2C0" not in unit.context_element_ids
        assert "R1C1" not in unit.context_element_ids

    def test_continuation_across_pages_is_pulled_in(self) -> None:
        """Half a sentence is not a rule, and the missing half carries the caveat."""

        plan = _plan(
            [
                _element("E1", "Employees may take leave provided that", order=0, page=1),
                _element("E2", "the manager approves in advance.", order=1, page=2),
            ],
            max_targets_per_unit=1,
        )
        unit = next(u for u in plan.units if u.target_element_ids == ["E1"])
        assert "continuation" in unit.reasons_for("E2")

    def test_definitions_are_pulled_in_where_the_term_is_used(self) -> None:
        plan = _plan(
            [
                _element("E1", '"Eligible Employee" means an employee of 12 months.', order=0),
                _element("E2", "An Eligible Employee may request leave.", order=1),
            ],
            max_targets_per_unit=1,
        )
        unit = next(u for u in plan.units if u.target_element_ids == ["E2"])
        assert "definition" in unit.reasons_for("E1")

    def test_unrelated_definitions_are_not_pulled_in(self) -> None:
        """A false definition link changes how a rule reads."""

        plan = _plan(
            [
                _element("E1", '"Contractor" means a non-employee worker.', order=0),
                _element("E2", "Employees may request leave.", order=1),
            ],
            max_targets_per_unit=1,
        )
        unit = next(u for u in plan.units if u.target_element_ids == ["E2"])
        assert "definition" not in unit.reasons_for("E1")

    def test_immediately_preceding_scope_sentence_is_included(self) -> None:
        plan = _plan(
            [
                _element("E1", "The following applies to full-time employees:", order=0),
                _element("E2", "Leave must be approved.", order=1),
            ],
            max_targets_per_unit=1,
        )
        unit = next(u for u in plan.units if u.target_element_ids == ["E2"])
        assert "preceding_context" in unit.reasons_for("E1")


class TestCrossReferences:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("See Section 4.2 for details.", ["4.2"]),
            ("as set out in clause 7", ["7"]),
            ("per paragraph 3.1(a) above", ["3.1(a)"]),
            ("Refer to Appendix B.", ["B"]),
        ],
    )
    def test_explicit_references_are_found(self, text: str, expected: list[str]) -> None:
        assert find_cross_references(text) == expected

    @pytest.mark.parametrize(
        "text",
        [
            "Leave must be taken within 5 days.",
            "A maximum of 20 days applies.",
            "Version 3.2 supersedes the previous release.",
        ],
    )
    def test_bare_numbers_are_not_treated_as_references(self, text: str) -> None:
        """Treating '5' as a section reference pulls in unrelated material."""

        assert find_cross_references(text) == []
