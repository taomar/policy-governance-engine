"""Guard: a stored row keeps the identity of its table and the labels of its columns.

WHAT THIS PROTECTS
------------------
A grid row reaches storage as one string of values -- "P1 | Active data breach |
15 minutes". The values are all there, and none of them says what it is. The
labels that answer that ("Tier", "Trigger", "Response time") are computed once,
by the converter that read the grid, and are the only record of what the columns
were called: the row itself does not repeat them, and nothing downstream can
recover them from the text.

They used to stop at the clause projection. A document is read back from its
stored clauses rather than re-parsed, so every consumer after storage saw a row
that did not know which table it belonged to or what its columns were named.

These tests pin the carry in both directions, and pin the distinction that makes
it honest.

ABSENT IS NOT EMPTY
-------------------
`table_headers` is `None` when no row of a grid evidenced itself as stating
column labels -- a conclusion ingestion reaches deliberately and warns about.
`[]` would be a different claim: that the grid has no columns. A projection that
collapsed the two would erase the warning and make a headerless grid
indistinguishable from a labelled one, so the round trip is asserted to preserve
each state as itself.

WHAT THIS DOES NOT CLAIM
------------------------
Nothing here says table *structure* survives. Column labels are not coordinates:
a row's labels do not say which value sits under which label, and this module
deliberately never pairs them. `test_clause_projection_boundary.py` holds the
claims about cell position, and those still describe a gap.

Written against synthetic grids of several shapes. No real document, no domain,
no observed count.
"""
from __future__ import annotations

import dataclasses

import pytest

from policy_platform.contracts.canonical_document import (
    CanonicalDocument,
    CanonicalElement,
    CanonicalPage,
    SourceFragment,
)
from policy_platform.contracts.structural_graph import build_structural_graph
from policy_platform.domain.models import Clause
from policy_platform.infrastructure.ingestion.canonical_rebuild import canonical_from_clauses
from policy_platform.infrastructure.ingestion.document_extraction import (
    ClauseData,
    clauses_from_document,
)

#: Grid shapes, so nothing comes to depend on a table having a particular width
#: or a particular number of rows.
GRID_SHAPES = [(1, 2), (1, 5), (3, 3), (2, 4)]


def _row_document(
    body_rows: int,
    columns: int,
    *,
    headers: list[str] | None,
    table_id: str = "t1",
) -> CanonicalDocument:
    """A document whose table is expressed as whole rows, as a row parser emits it.

    `headers=None` models a grid in which no row stated column labels. That is a
    real outcome, not a degenerate one, and it has to travel as itself.
    """

    elements: list[CanonicalElement] = []
    offset = 0
    for row_index in range(body_rows):
        text = " | ".join(f"r{row_index} c{column}" for column in range(columns))
        elements.append(
            CanonicalElement(
                element_id=f"E{row_index:06d}",
                element_type="table_row",
                logical_order=row_index,
                text=text,
                table_id=table_id,
                table_headers=headers,
                source_fragments=[
                    SourceFragment(
                        page=1,
                        start_offset=offset,
                        end_offset=offset + len(text),
                        text=text,
                    )
                ],
            )
        )
        offset += len(text) + 1

    return CanonicalDocument(
        document_id="rows",
        page_count=1,
        pages=[CanonicalPage(page=1, raw_text="")],
        elements=elements,
        parser="test",
    )


def _stored(document: CanonicalDocument) -> list[Clause]:
    """Real ORM rows, built the way the repository builds them.

    The ORM model rather than a stand-in, because the claim under test is that
    the *columns* carry these values: a stand-in with hand-written attributes
    would pass whether or not the table has anywhere to put them.
    """

    return [
        Clause(
            clause_ref=data.clause_ref,
            section=data.section,
            page=data.page,
            text=data.text,
            sequence=index,
            element_id=data.element_id,
            element_type=data.element_type,
            source_fragments=data.source_fragments,
            table_id=data.table_id,
            table_headers=data.table_headers,
        )
        for index, data in enumerate(clauses_from_document(document))
    ]


def _round_trip(document: CanonicalDocument) -> CanonicalDocument:
    return canonical_from_clauses(document.document_id, _stored(document))


@pytest.mark.parametrize(("body_rows", "columns"), GRID_SHAPES)
def test_a_row_keeps_the_identity_of_its_table_through_storage(
    body_rows: int, columns: int
) -> None:
    """Which grid a row belongs to is a fact about the row, and it survives."""

    document = _row_document(body_rows, columns, headers=[f"h{i}" for i in range(columns)])
    rebuilt = _round_trip(document)

    assert [element.table_id for element in rebuilt.elements] == [
        element.table_id for element in document.elements
    ]
    assert all(element.table_id for element in rebuilt.elements)


@pytest.mark.parametrize(("body_rows", "columns"), GRID_SHAPES)
def test_a_row_keeps_the_labels_its_table_stated(body_rows: int, columns: int) -> None:
    """The labels arrive intact, in order, with no value invented or dropped."""

    headers = [f"h{i}" for i in range(columns)]
    rebuilt = _round_trip(_row_document(body_rows, columns, headers=headers))

    assert all(element.table_headers == headers for element in rebuilt.elements)


@pytest.mark.parametrize(("body_rows", "columns"), GRID_SHAPES)
def test_a_grid_that_stated_no_labels_stays_headerless(body_rows: int, columns: int) -> None:
    """Absent must not become empty.

    `None` records that no row of the grid named its columns -- something
    ingestion establishes and reports. `[]` would assert the grid has no columns.
    A round trip that turned the first into the second would silently answer a
    question the source never answered.
    """

    rebuilt = _round_trip(_row_document(body_rows, columns, headers=None))

    assert all(element.table_headers is None for element in rebuilt.elements)
    assert not any(element.table_headers == [] for element in rebuilt.elements)
    # The row is still a row of a known grid; only its labels are unknown.
    assert all(element.table_id for element in rebuilt.elements)


def test_an_empty_label_list_is_not_folded_into_absent() -> None:
    """The two states stay distinguishable in the other direction too.

    Nothing writes `[]` today. The projection is asserted not to normalise it
    anyway, because the moment it did, "no labels stated" and "labels stated and
    then lost" would arrive at a reader as the same value.
    """

    document = _row_document(1, 2, headers=[])
    rebuilt = _round_trip(document)

    assert rebuilt.elements[0].table_headers == []
    assert rebuilt.elements[0].table_headers is not None


def test_an_element_that_is_not_a_row_carries_neither_field() -> None:
    """Table identity belongs to table elements and is not spread to prose."""

    text = "A paragraph that is not part of any grid."
    document = CanonicalDocument(
        document_id="prose",
        page_count=1,
        pages=[CanonicalPage(page=1, raw_text=text)],
        elements=[
            CanonicalElement(
                element_id="E000000",
                element_type="paragraph",
                logical_order=0,
                text=text,
                source_fragments=[
                    SourceFragment(page=1, start_offset=0, end_offset=len(text), text=text)
                ],
            )
        ],
        parser="test",
    )

    rebuilt = _round_trip(document)

    assert rebuilt.elements[0].table_id is None
    assert rebuilt.elements[0].table_headers is None


@pytest.mark.parametrize(("body_rows", "columns"), GRID_SHAPES)
def test_the_flatten_direction_carries_what_the_converter_produced(
    body_rows: int, columns: int
) -> None:
    """Measured on the flatten alone, so a failure names which half broke."""

    headers = [f"h{i}" for i in range(columns)]
    document = _row_document(body_rows, columns, headers=headers)

    flattened = clauses_from_document(document)

    assert [data.table_id for data in flattened] == [
        element.table_id for element in document.elements
    ]
    assert [data.table_headers for data in flattened] == [
        element.table_headers for element in document.elements
    ]


def test_every_field_the_flatten_produces_has_a_column_to_land_in() -> None:
    """The invariant that makes the projection a projection and not a filter.

    `ClauseData` is what an upload hands to storage. A field on it with no column
    of the same name is a value computed, passed along, and dropped at the
    insert -- which is the exact shape of the defect this module was written
    for, and it is invisible until someone reads the two definitions side by
    side. Asserting the correspondence makes the next added field say so.

    Names only. Types are the migration's business, and asserting them here
    would make this test a second, weaker copy of the schema.
    """

    produced = {field.name for field in dataclasses.fields(ClauseData)}
    columns = set(Clause.__table__.columns.keys())

    assert produced <= columns, produced - columns


@pytest.mark.parametrize(("body_rows", "columns"), GRID_SHAPES)
def test_carrying_labels_builds_no_cell_edge(body_rows: int, columns: int) -> None:
    """A label is not a coordinate, and this must not read as though it were.

    Stated as its own claim so that "the row knows its columns are called X"
    can never be mistaken for "the structure of the table is available". Cell
    edges need a position; a row has none, and none is invented from a label.
    """

    rebuilt = _round_trip(
        _row_document(body_rows, columns, headers=[f"h{i}" for i in range(columns)])
    )
    graph = build_structural_graph(rebuilt)

    assert all(element.table_cell is None for element in rebuilt.elements)
    assert not [
        edge
        for edge in graph.edges
        if edge.kind in ("table_cell_of", "header_for", "merged_with")
    ]


def test_a_grid_continued_across_a_page_is_recognisable_after_storage() -> None:
    """The consumer this carry exists for, exercised through the round trip.

    `structural_graph` tells a grid continued from the previous page from a new
    grid that merely follows one by grouping on `table_id` and looking for
    labels above and none below. Both inputs are row-level; neither is a
    coordinate. Before the carry, both were absent after storage and the
    detection could never fire on a rebuilt document -- which is the only kind
    of document anything downstream sees.
    """

    heading = "Governing Heading"
    elements: list[CanonicalElement] = []
    order = 0

    def add(element_type: str, text: str, page: int, **kwargs) -> None:
        nonlocal order
        elements.append(
            CanonicalElement(
                element_id=f"E{order:06d}",
                element_type=element_type,  # type: ignore[arg-type]
                logical_order=order,
                text=text,
                source_fragments=[
                    SourceFragment(page=page, start_offset=0, end_offset=len(text), text=text)
                ],
                **kwargs,
            )
        )
        order += 1

    add("heading", heading, 1)
    add("table_row", "a | b", 1, table_id="t1", table_headers=["h0", "h1"])
    add("heading", heading, 2)
    add("table_row", "c | d", 2, table_id="t2", table_headers=None)

    document = CanonicalDocument(
        document_id="continued",
        page_count=2,
        pages=[CanonicalPage(page=1, raw_text=""), CanonicalPage(page=2, raw_text="")],
        elements=elements,
        parser="test",
    )

    assert build_structural_graph(document).table_continuations
    assert build_structural_graph(_round_trip(document)).table_continuations
