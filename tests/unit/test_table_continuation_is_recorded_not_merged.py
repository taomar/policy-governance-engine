"""A table continued across a page break is recorded, and nothing is merged.

`page.find_tables()` is a per-page API, so a table running onto the next page is
rediscovered there as a separate grid with a different id. Whether the two grids
are one table is a question structure alone cannot settle, and the measurements
that motivated this module say why:

* the governing heading of a real bilingual schedule repeated on all seven of
  its pages -- but text equality is not structure, and a running heading over
  genuinely distinct tables says exactly the same thing;
* column counts across pages of that one table were 18, 10, 11, 18, 8, 18, 8,
  so grid width is not stable even within a single logical table;
* "the grid runs to the bottom margin" misses a page ending 97pt above it that
  continues anyway.

So the observation is recorded with its evidence attached and the `table_id`s
are left alone. Two tables stay two. The tests below hold that line from both
directions: a continuation must be seen, and things that merely resemble one
must not be.

Everything here is synthetic. Nothing keys on a heading's wording, a numbering
scheme or a page size, so no real document is a target.
"""
from __future__ import annotations

from policy_platform.contracts.canonical_document import (
    CanonicalDocument,
    CanonicalElement,
    CanonicalPage,
    SourceFragment,
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
        element_type=element_type,
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
        parser="legacy",
    )


def _rows(table_id: str, page: int, start_order: int, count: int, *, headers=None):
    return [
        _element(
            f"{table_id}-r{i}",
            f"{i} | some provision | a consequence",
            "table_row",
            start_order + i,
            page,
            table_id=table_id,
            table_headers=headers,
        )
        for i in range(count)
    ]


def _continued(heading_text: str = "Schedule") -> CanonicalDocument:
    """One table across two pages, with its heading repeated on the second."""

    return _document(
        [
            _element("H1", heading_text, "heading", 0, page=1),
            *_rows("p1-t1", 1, 1, 3),
            _element("H2", heading_text, "heading", 4, page=2),
            *_rows("p2-t1", 2, 5, 3),
        ]
    )


class TestAContinuationIsSeen:
    def test_consecutive_grids_under_a_repeated_heading_are_recorded(self) -> None:
        graph = build_structural_graph(_continued())

        assert len(graph.table_continuations) == 1
        record = graph.table_continuations[0]
        assert (record.from_table_id, record.to_table_id) == ("p1-t1", "p2-t1")
        assert (record.from_page, record.to_page) == (1, 2)

    def test_the_record_names_which_signals_fired(self) -> None:
        """A record that asserts a continuation without saying on what evidence
        is an opinion. Naming the signals lets a reader disagree with it."""

        record = build_structural_graph(_continued()).table_continuations[0]

        assert record.signals, "a record was emitted with no corroboration at all"
        assert "repeated_governing_heading" in record.signals

    def test_an_edge_joins_the_last_row_to_the_first(self) -> None:
        graph = build_structural_graph(_continued())
        edges = [e for e in graph.edges if e.kind == "table_continues_on"]

        assert len(edges) == 1
        assert edges[0].source == "p1-t1-r2"
        assert edges[0].target == "p2-t1-r0"


class TestNothingIsMerged:
    """The riskier direction. Recording is reversible; merging is not."""

    def test_the_table_ids_are_left_alone(self) -> None:
        document = _continued()
        before = [e.table_id for e in document.elements]
        build_structural_graph(document)

        assert [e.table_id for e in document.elements] == before
        assert {e.table_id for e in document.elements if e.table_id} == {
            "p1-t1",
            "p2-t1",
        }

    def test_no_headers_are_invented_for_the_continuation(self) -> None:
        """Page one's headers are not inherited by page two.

        They were measured wrong on page one often enough that copying them
        forward would propagate a value ingestion had just stopped asserting --
        and a fabricated header is indistinguishable, downstream, from a read one.
        """

        document = _document(
            [
                _element("H1", "Schedule", "heading", 0, page=1),
                *_rows("p1-t1", 1, 1, 2, headers=["No.", "Offence", "Penalty"]),
                _element("H2", "Schedule", "heading", 3, page=2),
                *_rows("p2-t1", 2, 4, 2),
            ]
        )
        build_structural_graph(document)

        continuation = [e for e in document.elements if e.table_id == "p2-t1"]
        assert all(row.table_headers is None for row in continuation)

    def test_a_missing_header_row_on_the_continuation_is_itself_a_signal(self) -> None:
        """Only observable because ingestion stopped assuming grid row 0 is a
        header row. While every table carried headers -- wrongly -- page two was
        indistinguishable from a table's first page."""

        document = _document(
            [
                _element("H1", "Schedule", "heading", 0, page=1),
                *_rows("p1-t1", 1, 1, 2, headers=["No.", "Offence", "Penalty"]),
                _element("H2", "Different heading", "heading", 3, page=2),
                *_rows("p2-t1", 2, 4, 2),
            ]
        )
        record = build_structural_graph(document).table_continuations[0]

        assert "continuation_has_no_header_row" in record.signals
        assert "repeated_governing_heading" not in record.signals


class TestThingsThatOnlyResembleAContinuation:
    def test_two_tables_on_one_page_are_not_a_continuation(self) -> None:
        """There is no page break, so there is nothing to have been split."""

        document = _document(
            [
                _element("H1", "Schedule", "heading", 0, page=1),
                *_rows("p1-t1", 1, 1, 2, headers=["a", "b"]),
                _element("H2", "Schedule", "heading", 3, page=1),
                *_rows("p1-t2", 1, 4, 2),
            ]
        )

        assert build_structural_graph(document).table_continuations == []

    def test_intervening_prose_means_two_tables(self) -> None:
        """A paragraph between them is content, not a page break. Whatever else
        agrees, the second grid does not continue the first."""

        document = _document(
            [
                _element("H1", "Schedule", "heading", 0, page=1),
                *_rows("p1-t1", 1, 1, 2, headers=["a", "b"]),
                _element("P1", "A separate provision applies.", order=3, page=2),
                _element("H2", "Schedule", "heading", 4, page=2),
                *_rows("p2-t1", 2, 5, 2),
            ]
        )

        assert build_structural_graph(document).table_continuations == []

    def test_a_gap_in_pages_means_two_tables(self) -> None:
        document = _document(
            [
                _element("H1", "Schedule", "heading", 0, page=1),
                *_rows("p1-t1", 1, 1, 2, headers=["a", "b"]),
                _element("H2", "Schedule", "heading", 3, page=3),
                *_rows("p3-t1", 3, 4, 2),
            ]
        )

        assert build_structural_graph(document).table_continuations == []

    def test_no_corroborating_signal_means_no_record(self) -> None:
        """Consecutive pages and nothing but a heading between them are the
        preconditions, not the evidence. On their own they describe every table
        that merely follows another."""

        document = _document(
            [
                _element("H1", "First schedule", "heading", 0, page=1),
                *_rows("p1-t1", 1, 1, 2, headers=["a", "b"]),
                _element("H2", "Second schedule", "heading", 3, page=2),
                *_rows("p2-t1", 2, 4, 2, headers=["c", "d"]),
            ]
        )

        assert build_structural_graph(document).table_continuations == []

    def test_a_document_with_one_table_records_nothing(self) -> None:
        document = _document(
            [
                _element("H1", "Schedule", "heading", 0, page=1),
                *_rows("p1-t1", 1, 1, 3, headers=["a", "b"]),
            ]
        )
        graph = build_structural_graph(document)

        assert graph.table_continuations == []
        assert [e for e in graph.edges if e.kind == "table_continues_on"] == []
