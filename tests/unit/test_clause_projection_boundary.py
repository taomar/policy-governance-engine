"""Guard: how far the cell/header association actually travels.

WHAT THIS PROTECTS
------------------
`test_document_extraction_converter_seam.py` states the invariant this platform
exists to keep:

    A cell in a table means nothing on its own. So a parse that keeps cells must
    keep the *association* too, and that association must survive all the way to
    what the model reads.

It then proves that invariant across the seam, in memory: `extract_document` ->
`build_structural_graph` -> `build_reading_plan`. Every assertion there passes.

But nothing downstream is handed that in-memory document. An upload is flattened
to clauses by `clauses_from_document`, the clauses are stored, and every later
stage rebuilds a canonical document from the stored rows via
`canonical_from_clauses` -- `infrastructure/extraction/ai_extraction.py`,
`infrastructure/extraction/provision_linking.py` and the structure, reading-plan
and coverage endpoints all do exactly this. So there is a boundary between "the
converter recovered it" and "something read it", and the existing guard stops
before that boundary.

These tests describe where the association currently stops. The projection
carries a clause's text, section, element id, element type, source fragments and
-- since the table-identity migration -- the id of the table a row belongs to
and the column labels that table stated, because those are the columns the table
has. It carries no row index, no column index and no header flag. So a graph
rebuilt from stored clauses still has no *cell* edges to build, whatever produced
the clauses -- and that is a property of the projection, not of any converter.

WHY ASSERT SOMETHING THAT IS A GAP
----------------------------------
Because the gap is invisible otherwise, and this repository has a documented
history of capabilities that are built, tested against their own output, and
reach nobody. A test that pins the boundary makes the next person's change
speak: when the projection is widened to carry cell structure, these tests fail
and say exactly which claim changed. That is the moment the converter choice
starts to matter downstream, and it is the moment someone should be told.

Written against synthetic grids of several shapes, like the module it extends.
No real document, no domain, no observed count -- the claims are structural and
hold for a table of any size.
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
from policy_platform.infrastructure.ingestion.canonical_rebuild import canonical_from_clauses
from policy_platform.infrastructure.ingestion.document_extraction import clauses_from_document

#: Grid shapes, so nothing comes to depend on a table having a particular width
#: or a header sitting in a particular place.
GRID_SHAPES = [(1, 2), (1, 5), (3, 3), (2, 4)]

#: The edge kinds that exist only because a cell knows where it sits.
TABLE_EDGE_KINDS = ("table_cell_of", "header_for", "merged_with")


class _StoredClause:
    """A clause as the database holds it.

    Carries exactly the attributes `canonical_from_clauses` reads, which are
    exactly the columns `clauses` has. Constructing the ORM model would need a
    session and would measure nothing more.
    """

    def __init__(self, data, sequence: int) -> None:
        self.element_id = data.element_id
        self.element_type = data.element_type
        self.sequence = sequence
        self.text = data.text
        self.section = data.section
        self.source_fragments = data.source_fragments
        self.table_id = data.table_id
        self.table_headers = data.table_headers


def _cell_document(body_rows: int, columns: int) -> CanonicalDocument:
    """A document whose table cells are fully articulated.

    Built directly rather than via a converter: the claim under test is about
    what happens to cell structure *after* a converter produced it, so the
    strongest starting point is a document that unambiguously has it.
    """

    elements: list[CanonicalElement] = []
    order = 0
    text = "Enclosing Section"
    elements.append(
        CanonicalElement(
            element_id="E000000",
            element_type="heading",
            logical_order=order,
            text=text,
            source_fragments=[
                SourceFragment(page=1, start_offset=0, end_offset=len(text), text=text)
            ],
        )
    )
    offset = len(text)
    for row in range(body_rows + 1):
        for column in range(columns):
            order += 1
            is_header = row == 0
            cell_text = f"{'Header' if is_header else 'Body'} r{row} c{column}"
            elements.append(
                CanonicalElement(
                    element_id=f"E{order:06d}",
                    element_type="table_cell",
                    logical_order=order,
                    text=cell_text,
                    table_id="t1",
                    table_cell=TableCellRef(
                        row_index=row, column_index=column, is_header=is_header
                    ),
                    source_fragments=[
                        SourceFragment(
                            page=1,
                            start_offset=offset,
                            end_offset=offset + len(cell_text),
                            text=cell_text,
                        )
                    ],
                )
            )
            offset += len(cell_text)

    raw = "".join(
        fragment.text for element in elements for fragment in element.source_fragments
    )
    return CanonicalDocument(
        document_id="grid",
        page_count=1,
        pages=[CanonicalPage(page=1, raw_text=raw)],
        elements=elements,
        parser="test",
    )


def _round_trip(document: CanonicalDocument) -> CanonicalDocument:
    """Flatten to clauses and rebuild, exactly as an upload and a later stage do."""

    stored = [
        _StoredClause(data, index)
        for index, data in enumerate(clauses_from_document(document))
    ]
    return canonical_from_clauses(document.document_id, stored)


@pytest.mark.parametrize(("body_rows", "columns"), GRID_SHAPES)
def test_structure_is_present_before_the_clause_projection(body_rows: int, columns: int) -> None:
    """The starting point really does carry cell structure and table edges."""

    document = _cell_document(body_rows, columns)
    graph = build_structural_graph(document)

    assert all(
        element.table_cell is not None
        for element in document.elements
        if element.element_type == "table_cell"
    )
    assert any(edge.kind in TABLE_EDGE_KINDS for edge in graph.edges)


@pytest.mark.parametrize(("body_rows", "columns"), GRID_SHAPES)
def test_the_clause_projection_carries_no_cell_structure(body_rows: int, columns: int) -> None:
    """Text survives the round trip; where the text sat in its table does not.

    The table a cell belongs to now survives, which is why this asserts the
    absence of the coordinate and not the absence of the identity: the two are
    different fields carried by different columns, and only one of them is
    stored. Keeping the claim narrow is the point -- a reader must be able to
    tell "this row knows its table" from "this cell knows its position".
    """

    document = _cell_document(body_rows, columns)
    rebuilt = _round_trip(document)

    assert [element.text for element in rebuilt.elements] == [
        element.text for element in document.elements
    ]
    assert all(element.table_cell is None for element in rebuilt.elements)


@pytest.mark.parametrize(("body_rows", "columns"), GRID_SHAPES)
def test_a_graph_rebuilt_from_clauses_has_no_table_edges(body_rows: int, columns: int) -> None:
    """No cell coordinates, so no edge the coordinates would have justified."""

    rebuilt = _round_trip(_cell_document(body_rows, columns))
    graph = build_structural_graph(rebuilt)

    assert not [edge for edge in graph.edges if edge.kind in TABLE_EDGE_KINDS]


@pytest.mark.parametrize(("body_rows", "columns"), GRID_SHAPES)
def test_the_reading_plan_cannot_frame_a_cell_after_the_round_trip(
    body_rows: int, columns: int
) -> None:
    """The header is in the plan's reach before the round trip and not after.

    This is the claim that decides whether a converter change alone can reach a
    model: `_add_table_context` frames a bare value from `header_for`, and after
    the round trip there is no such edge to read.
    """

    document = _cell_document(body_rows, columns)
    graph = build_structural_graph(document)
    plan = build_reading_plan(document, graph)
    body_cells = [
        element.element_id
        for element in document.elements
        if element.table_cell is not None and not element.table_cell.is_header
    ]
    framed_before = {
        target
        for unit in plan.units
        for target in unit.target_element_ids
        if target in body_cells and graph.sources(target, "header_for")
    }
    assert framed_before

    rebuilt = _round_trip(document)
    rebuilt_graph = build_structural_graph(rebuilt)
    rebuilt_plan = build_reading_plan(rebuilt, rebuilt_graph)
    assert not [
        target
        for unit in rebuilt_plan.units
        for target in unit.target_element_ids
        if rebuilt_graph.sources(target, "header_for")
    ]


def test_a_row_joined_into_one_clause_keeps_its_values_together() -> None:
    """What a row-shaped element still carries once cell structure is gone.

    Stated because it is the other half of the comparison and it cuts the other
    way: an element holding a whole row keeps the association between the values
    in that row inside its own text, and that text is the one thing the
    projection does carry. A parse that splits the same row into one element per
    cell has nowhere to put the association once coordinates are dropped.

    The row's column labels now survive alongside its text. They are labels, not
    positions: nothing here pairs a label with a value, because the joined text
    is a rendering of the row and splitting it back into cells would be this
    system guessing where the boundaries were.
    """

    row_text = "Body r1 c0 | Body r1 c1 | Body r1 c2"
    headers = ["Header c0", "Header c1", "Header c2"]
    document = CanonicalDocument(
        document_id="row",
        page_count=1,
        pages=[CanonicalPage(page=1, raw_text=row_text)],
        elements=[
            CanonicalElement(
                element_id="E000000",
                element_type="table_row",
                logical_order=0,
                text=row_text,
                table_id="t1",
                table_headers=headers,
                source_fragments=[
                    SourceFragment(
                        page=1, start_offset=0, end_offset=len(row_text), text=row_text
                    )
                ],
            )
        ],
        parser="test",
    )

    rebuilt = _round_trip(document)
    survivor = rebuilt.elements[0]
    assert survivor.text == row_text
    assert survivor.table_headers == headers
    assert survivor.table_cell is None
