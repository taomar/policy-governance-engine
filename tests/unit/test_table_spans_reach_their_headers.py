"""A cell is governed by every column it covers, not just the one it starts in.

Two defects lived in `_add_table_edges`, and both were invisible because they
produced *plausible* output rather than obviously broken output.

The first resolved a cell's header from `column_index` alone. A value spanning
four columns was therefore attributed to the first of them — so a source saying
"this applies across the whole band" was recorded as saying "this applies to the
first column", which is a narrower and more confident claim than the source made.

The second built `merged_with` edges by searching for *other cells* at the
positions a merged cell covers. A converter that emits one cell per merged
region — which is the normal shape — has no cells at those positions, so the
search never matched and the span information was silently discarded. The only
fixtures that exercised it hand-placed the very placeholder cells the search
needed, so the mechanism passed its tests while doing nothing on real output.

These tests are therefore written against table *shapes*, generated over several
widths and span positions. No fixture here is a copy of any document, and no
assertion depends on what any particular table happens to say.
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
from policy_platform.contracts.reading_plan import build_reading_plan
from policy_platform.contracts.structural_graph import build_structural_graph

TABLE = "#/tables/0"

#: Widths and span positions to generate. A defect that only shows up at one
#: width is still a defect, and a guard that only checks one width would let the
#: next one through.
SHAPES = [
    (2, 0, 2),
    (3, 0, 3),
    (4, 1, 3),
    (5, 0, 2),
    (5, 2, 3),
]


def _cell(
    element_id: str,
    text: str,
    order: int,
    *,
    row: int,
    column: int,
    column_span: int = 1,
    is_header: bool = False,
) -> CanonicalElement:
    return CanonicalElement(
        element_id=element_id,
        element_type="table_cell",
        logical_order=order,
        text=text,
        source_fragments=[
            SourceFragment(page=1, start_offset=0, end_offset=len(text), text=text)
        ],
        table_id=TABLE,
        table_cell=TableCellRef(
            row_index=row,
            column_index=column,
            column_span=column_span,
            is_header=is_header,
        ),
    )


def _document(elements: list[CanonicalElement]) -> CanonicalDocument:
    return CanonicalDocument(
        document_id="DOC",
        page_count=1,
        pages=[CanonicalPage(page=1, raw_text="")],
        elements=elements,
        parser="docling",
    )


def header_text(column: int) -> str:
    return f"Header {column}"


def _table(
    columns: int,
    span_start: int,
    span: int,
    *,
    merged_header: bool = False,
) -> CanonicalDocument:
    """A header row, an optional band header above it, and one body row.

    The body row holds a cell spanning `span` columns from `span_start`, and
    single-column cells everywhere the span does not reach. Crucially it holds
    *no* placeholder cells inside the span: that is the shape a converter
    actually emits, and the shape the old `merged_with` search could not see.
    """

    elements: list[CanonicalElement] = []
    order = 0
    header_row = 0

    if merged_header:
        elements.append(
            _cell(
                "BAND",
                "Band",
                order,
                row=0,
                column=0,
                column_span=columns,
                is_header=True,
            )
        )
        order += 1
        header_row = 1

    for column in range(columns):
        elements.append(
            _cell(
                f"H{column}",
                header_text(column),
                order,
                row=header_row,
                column=column,
                is_header=True,
            )
        )
        order += 1

    body_row = header_row + 1
    column = 0
    while column < columns:
        if column == span_start:
            elements.append(
                _cell(
                    "SPAN",
                    "spanning value",
                    order,
                    row=body_row,
                    column=column,
                    column_span=span,
                )
            )
            order += 1
            column += span
            continue
        elements.append(
            _cell(f"B{column}", f"plain {column}", order, row=body_row, column=column)
        )
        order += 1
        column += 1

    return _document(elements)


def _headers_of(graph, element_id: str, kind: str) -> set[str]:
    return {
        graph.nodes[source].text
        for source in graph.sources(element_id, kind)
        if source in graph.nodes
    }


class TestTheFixturesStillSayWhatTheyClaim:
    """A guard that silently stops generating spans proves nothing.

    Asserted against the fixture data itself, never against the graph builder,
    so this cannot be satisfied by the code under test agreeing with itself.
    """

    @pytest.mark.parametrize(("columns", "span_start", "span"), SHAPES)
    def test_the_generated_table_really_contains_a_multi_column_cell(
        self, columns: int, span_start: int, span: int
    ) -> None:
        document = _table(columns, span_start, span)
        spanning = [
            e
            for e in document.elements
            if e.table_cell is not None and e.table_cell.column_span > 1
        ]
        assert spanning, "the fixture generated no spanning cell to test"
        assert spanning[0].table_cell is not None
        assert spanning[0].table_cell.column_span == span

    @pytest.mark.parametrize(("columns", "span_start", "span"), SHAPES)
    def test_the_span_covers_more_than_one_header(
        self, columns: int, span_start: int, span: int
    ) -> None:
        """If the span covered one column the defect could not show itself."""

        assert span > 1
        assert span_start + span <= columns

    @pytest.mark.parametrize(("columns", "span_start", "span"), SHAPES)
    def test_no_placeholder_cell_sits_inside_the_span(
        self, columns: int, span_start: int, span: int
    ) -> None:
        """The old mechanism needed these. Their absence is the point."""

        document = _table(columns, span_start, span)
        inside = [
            e
            for e in document.elements
            if e.table_cell is not None
            and not e.table_cell.is_header
            and span_start < e.table_cell.column_index < span_start + span
        ]
        assert inside == [], (
            "the fixture placed a cell inside the span, which would let a "
            "placeholder-based lookup pass without covering the real shape"
        )


class TestASpanningCellIsHeadedByEveryColumnItCovers:
    @pytest.mark.parametrize(("columns", "span_start", "span"), SHAPES)
    def test_every_covered_column_header_reaches_the_cell(
        self, columns: int, span_start: int, span: int
    ) -> None:
        graph = build_structural_graph(_table(columns, span_start, span))

        expected = {header_text(c) for c in range(span_start, span_start + span)}
        assert _headers_of(graph, "SPAN", "header_for") == expected

    @pytest.mark.parametrize(("columns", "span_start", "span"), SHAPES)
    def test_a_single_column_cell_is_not_over_connected(
        self, columns: int, span_start: int, span: int
    ) -> None:
        """Widening the lookup must not attach every header to every cell."""

        document = _table(columns, span_start, span)
        graph = build_structural_graph(document)

        for element in document.elements:
            assert element.table_cell is not None
            if element.table_cell.is_header or element.table_cell.column_span > 1:
                continue
            assert _headers_of(graph, element.element_id, "header_for") == {
                header_text(element.table_cell.column_index)
            }


class TestAMergedHeaderNeedsNoPlaceholders:
    @pytest.mark.parametrize(("columns", "span_start", "span"), SHAPES)
    def test_the_band_header_reaches_body_cells_in_later_rows(
        self, columns: int, span_start: int, span: int
    ) -> None:
        document = _table(columns, span_start, span, merged_header=True)
        graph = build_structural_graph(document)

        body = [
            e.element_id
            for e in document.elements
            if e.table_cell is not None
            and not e.table_cell.is_header
        ]
        assert body, "no body cells generated"
        for element_id in body:
            assert "Band" in _headers_of(graph, element_id, "merged_with"), (
                f"{element_id} lost the merged header spanning its column"
            )

    @pytest.mark.parametrize(("columns", "span_start", "span"), SHAPES)
    def test_a_merged_header_is_not_reported_as_a_plain_column_header(
        self, columns: int, span_start: int, span: int
    ) -> None:
        """The two say different things and are surfaced under different reasons."""

        graph = build_structural_graph(
            _table(columns, span_start, span, merged_header=True)
        )
        assert "Band" not in _headers_of(graph, "SPAN", "header_for")

    @pytest.mark.parametrize(("columns", "span_start", "span"), SHAPES)
    def test_a_sub_header_does_not_become_the_header_of_the_band_above_it(
        self, columns: int, span_start: int, span: int
    ) -> None:
        graph = build_structural_graph(
            _table(columns, span_start, span, merged_header=True)
        )
        assert _headers_of(graph, "BAND", "header_for") == set()


class TestTheReaderReceivesTheWholeSpan:
    """The edges only matter if the reading plan hands them to the model."""

    @pytest.mark.parametrize(("columns", "span_start", "span"), SHAPES)
    def test_a_spanning_cell_arrives_with_every_header_it_is_governed_by(
        self, columns: int, span_start: int, span: int
    ) -> None:
        document = _table(columns, span_start, span, merged_header=True)
        graph = build_structural_graph(document)
        plan = build_reading_plan(document, graph)

        unit = next(u for u in plan.units if "SPAN" in u.target_element_ids)
        by_reason: dict[str, set[str]] = {}
        for context in unit.context:
            by_reason.setdefault(context.reason, set()).add(context.element_id)

        covered = {f"H{c}" for c in range(span_start, span_start + span)}
        seen = by_reason.get("table_header", set())
        assert covered <= seen, (
            f"the reader saw headers {sorted(seen)} for a cell spanning "
            f"columns {span_start}..{span_start + span - 1}, expected {sorted(covered)}"
        )
        assert "BAND" in by_reason.get("merged_header", set()), (
            "the merged header did not reach the reader"
        )
