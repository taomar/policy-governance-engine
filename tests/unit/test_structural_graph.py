"""Tests for the deterministic structural graph.

The graph's whole value is that it is *lossless* and *recomputable*: coverage
accounting later asserts "every canonical leaf has a disposition", and that
claim is worthless if the graph silently dropped elements first. Most of these
tests therefore probe loss and structure rather than convenience methods.
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
from policy_platform.contracts.structural_graph import (
    build_structural_graph,
    verify_structural_coverage,
)


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
        parser="docling",
    )


class TestLosslessness:
    def test_every_element_becomes_a_node(self) -> None:
        document = _document(
            [
                _element("E1", "Title", "title", 0),
                _element("E2", "1. Scope", "heading", 1),
                _element("E3", "A clause.", order=2),
            ]
        )
        graph = build_structural_graph(document)

        assert set(graph.nodes) == {"E1", "E2", "E3"}
        assert verify_structural_coverage(document, graph) == []

    def test_coverage_check_detects_a_dropped_element(self) -> None:
        """Guards the guard: silent loss must be reported, not inferred."""

        document = _document([_element("E1", "A clause.", order=0)])
        graph = build_structural_graph(document)
        graph.nodes.pop("E1")

        problems = verify_structural_coverage(document, graph)
        assert problems and "absent from the graph" in problems[0]

    def test_coverage_check_detects_an_invented_node(self) -> None:
        document = _document([_element("E1", "A clause.", order=0)])
        graph = build_structural_graph(document)
        graph.nodes["E999"] = graph.nodes["E1"]

        problems = verify_structural_coverage(document, graph)
        assert any("not present in the canonical document" in p for p in problems)

    def test_empty_document_produces_an_empty_valid_graph(self) -> None:
        document = _document([])
        graph = build_structural_graph(document)
        assert graph.nodes == {}
        assert verify_structural_coverage(document, graph) == []


class TestHeadingHierarchy:
    def test_nested_headings_build_an_ancestor_path(self) -> None:
        """The outer heading usually carries the scope of the inner rule."""

        document = _document(
            [
                _element("E1", "Policy", "title", 0),
                _element("E2", "2. Leave", "heading", 1),
                _element("E3", "2.1 Annual", "heading", 2),
                _element("E4", "Employees accrue 20 days.", order=3),
            ]
        )
        graph = build_structural_graph(document)

        assert graph.heading_path("E4") == ["E1", "E2", "E3"]

    def test_returning_to_a_shallower_heading_closes_deeper_ones(self) -> None:
        document = _document(
            [
                _element("E1", "2. Leave", "heading", 0),
                _element("E2", "2.1 Annual", "heading", 1),
                _element("E3", "Under annual.", order=2),
                _element("E4", "3. Travel", "heading", 3),
                _element("E5", "Under travel.", order=4),
            ]
        )
        graph = build_structural_graph(document)

        assert graph.heading_path("E3") == ["E1", "E2"]
        assert graph.heading_path("E5") == ["E4"]

    def test_unnumbered_headings_stay_flat_rather_than_inventing_depth(self) -> None:
        """A guessed hierarchy is worse than an honestly shallow one."""

        document = _document(
            [
                _element("E1", "Purpose", "heading", 0),
                _element("E2", "Scope", "heading", 1),
                _element("E3", "A clause.", order=2),
            ]
        )
        graph = build_structural_graph(document)

        assert graph.heading_path("E3") == ["E2"]

    def test_heading_path_terminates_on_a_cycle(self) -> None:
        """A malformed graph must not hang a caller."""

        from policy_platform.contracts.structural_graph import StructuralEdge

        document = _document(
            [_element("E1", "A", "heading", 0), _element("E2", "B", "heading", 1)]
        )
        graph = build_structural_graph(document)
        graph.edges.append(StructuralEdge("E1", "E2", "parent_heading"))
        graph.index()

        assert len(graph.heading_path("E2")) <= len(graph.nodes)


class TestUnnumberedHeadingsInsideANumberedScheme:
    """An unnumbered heading between two numbered ones belongs to the earlier one.

    The defect: depth came from a heading's own text alone, so an unnumbered
    sub-heading returned 1 and the `>=` pop evicted its parent, making it a
    *sibling* of the section it sits inside. On the GMU handbook that turned
    "Policy Details", written under "1. Manpower Planning, Recruitment &
    Selection", into a top-level section whose only available name was the words
    "Policy Details" — which is what the reviewer saw as a card title.
    """

    def test_unnumbered_heading_between_numbered_ones_is_a_child(self) -> None:
        document = _document(
            [
                _element("E1", "1. Manpower Planning", "heading", 0),
                _element("E2", "Policy Details", "heading", 1),
                _element("E3", "GMU carries out annual manpower planning.", order=2),
                _element("E4", "2. Compensation", "heading", 3),
            ]
        )
        graph = build_structural_graph(document)

        assert graph.heading_path("E2") == ["E1"]
        assert graph.heading_path("E3") == ["E1", "E2"]
        assert graph.heading_path("E4") == []

    def test_consecutive_unnumbered_headings_become_siblings_not_a_ladder(
        self,
    ) -> None:
        """The document wrote them at one level and drew no line between them.

        Nesting each inside the last would invent a hierarchy out of nothing but
        adjacency — the same invention the old flat fallback existed to avoid.
        """

        document = _document(
            [
                _element("E1", "1. Manpower Planning", "heading", 0),
                _element("E2", "Purpose", "heading", 1),
                _element("E3", "Policy Details", "heading", 2),
                _element("E4", "A clause.", order=3),
                _element("E5", "2. Compensation", "heading", 4),
            ]
        )
        graph = build_structural_graph(document)

        assert graph.heading_path("E2") == ["E1"]
        assert graph.heading_path("E3") == ["E1"]
        assert graph.heading_path("E4") == ["E1", "E3"]

    def test_unnumbered_heading_after_the_numbering_ends_stays_outermost(
        self,
    ) -> None:
        """The AIS penalty schedule, and why the test has to be two-sided.

        A one-sided rule — "an unnumbered heading following a numbered one is
        its child" — reads the same in a sentence and is wrong on real data: it
        folds the AIS handbook's unnumbered `Table of Violations and Penalties`,
        an appendix of seventy-two rows written after the numbering has
        finished, into `10. ACKNOWLEDGEMENT`, which does not state it.
        """

        document = _document(
            [
                _element("E1", "9. Discipline", "heading", 0),
                _element("E2", "A clause.", order=1),
                _element("E3", "10. Acknowledgement", "heading", 2),
                _element("E4", "Another clause.", order=3),
                _element("E5", "Table of Violations and Penalties", "heading", 4),
                _element("E6", "A penalty row.", order=5),
            ]
        )
        graph = build_structural_graph(document)

        assert graph.heading_path("E5") == []
        assert graph.heading_path("E6") == ["E5"]

    def test_a_document_that_numbers_nothing_stays_flat(self) -> None:
        """No scheme is running, so no heading can be opting out of one."""

        document = _document(
            [
                _element("E1", "Purpose", "heading", 0),
                _element("E2", "Scope", "heading", 1),
                _element("E3", "A clause.", order=2),
            ]
        )
        graph = build_structural_graph(document)

        assert graph.heading_path("E2") == []
        assert graph.heading_path("E3") == ["E2"]
        assert graph.unnamed_section_headings == set()

    def test_names_a_section_marks_only_the_subordinate_label(self) -> None:
        document = _document(
            [
                _element("E0", "Staff Handbook", "title", 0),
                _element("E1", "1. Manpower Planning", "heading", 1),
                _element("E2", "Policy Details", "heading", 2),
                _element("E3", "A clause.", order=3),
                _element("E4", "2. Compensation", "heading", 4),
            ]
        )
        graph = build_structural_graph(document)

        # Only the label the document declined to number. A title, a numbered
        # heading and a paragraph are all things the document named itself.
        assert graph.unnamed_section_headings == {"E2"}

    def test_a_subordinate_label_is_still_a_container_for_coverage(self) -> None:
        """Reparenting must not turn a heading into unaccounted content.

        Coverage is asserted over leaves, and a heading that stopped containing
        its paragraphs would become one — reporting a structural change as
        missing content, which is exactly the silent loss coverage exists to
        expose.
        """

        document = _document(
            [
                _element("E1", "1. Manpower Planning", "heading", 0),
                _element("E2", "Policy Details", "heading", 1),
                _element("E3", "A clause.", order=2),
                _element("E4", "2. Compensation", "heading", 3),
            ]
        )
        graph = build_structural_graph(document)

        assert "E2" not in graph.leaf_element_ids
        assert verify_structural_coverage(document, graph) == []

    def test_deeper_numbering_still_governs_an_unnumbered_label(self) -> None:
        document = _document(
            [
                _element("E1", "2. Leave", "heading", 0),
                _element("E2", "2.1 Annual Leave", "heading", 1),
                _element("E3", "Entitlement", "heading", 2),
                _element("E4", "A clause.", order=3),
                _element("E5", "3. Pay", "heading", 4),
            ]
        )
        graph = build_structural_graph(document)

        assert graph.heading_path("E3") == ["E1", "E2"]
        assert graph.heading_path("E4") == ["E1", "E2", "E3"]
        assert graph.heading_path("E5") == []


class TestReadingOrder:
    def test_precedes_edges_follow_logical_order(self) -> None:
        document = _document(
            [
                _element("E1", "First.", order=0),
                _element("E2", "Second.", order=1),
                _element("E3", "Third.", order=2),
            ]
        )
        graph = build_structural_graph(document)

        assert graph.targets("E1", "precedes") == ["E2"]
        assert graph.targets("E2", "precedes") == ["E3"]
        assert [n.element_id for n in graph.reading_order()] == ["E1", "E2", "E3"]

    def test_continuation_edge_links_a_clause_split_across_pages(self) -> None:
        """Half a rule handed to a model is a rule missing its exception."""

        document = _document(
            [
                _element("E1", "Employees may take leave provided that", order=0, page=1),
                _element("E2", "the manager approves in advance.", order=1, page=2),
            ]
        )
        graph = build_structural_graph(document)

        assert graph.targets("E1", "continues_on") == ["E2"]

    def test_completed_sentence_across_pages_is_not_a_continuation(self) -> None:
        document = _document(
            [
                _element("E1", "Employees may take leave.", order=0, page=1),
                _element("E2", "Managers approve requests.", order=1, page=2),
            ]
        )
        graph = build_structural_graph(document)

        assert graph.targets("E1", "continues_on") == []


class TestLists:
    def test_nested_items_link_to_their_parent_item(self) -> None:
        """A sub-item routinely qualifies its parent."""

        document = _document(
            [
                _element("E1", "Eligible if:", "list_item", 0, list_level=0),
                _element("E2", "employed 12 months", "list_item", 1, list_level=1),
                _element("E3", "except probation", "list_item", 2, list_level=1),
            ]
        )
        graph = build_structural_graph(document)

        assert set(graph.targets("E1", "list_child")) == {"E2", "E3"}

    def test_non_list_content_breaks_the_nesting_stack(self) -> None:
        document = _document(
            [
                _element("E1", "Eligible if:", "list_item", 0, list_level=0),
                _element("E2", "An unrelated paragraph.", order=1),
                _element("E3", "A new item", "list_item", 2, list_level=1),
            ]
        )
        graph = build_structural_graph(document)

        assert graph.targets("E1", "list_child") == []


class TestTables:
    def _table_document(self) -> CanonicalDocument:
        return _document(
            [
                _element(
                    "H0",
                    "Severity",
                    "table_cell",
                    0,
                    table_id="#/tables/0",
                    table_cell=TableCellRef(row_index=0, column_index=0, is_header=True),
                ),
                _element(
                    "H1",
                    "SLA",
                    "table_cell",
                    1,
                    table_id="#/tables/0",
                    table_cell=TableCellRef(row_index=0, column_index=1, is_header=True),
                ),
                _element(
                    "C0",
                    "P1",
                    "table_cell",
                    2,
                    table_id="#/tables/0",
                    table_cell=TableCellRef(row_index=1, column_index=0),
                ),
                _element(
                    "C1",
                    "15 minutes",
                    "table_cell",
                    3,
                    table_id="#/tables/0",
                    table_cell=TableCellRef(row_index=1, column_index=1),
                ),
            ]
        )

    def test_cells_link_to_their_table(self) -> None:
        graph = build_structural_graph(self._table_document())
        assert graph.targets("C1", "table_cell_of") == ["#/tables/0"]

    def test_column_header_qualifies_its_cells(self) -> None:
        """'15 minutes' is meaningless without 'SLA'."""

        graph = build_structural_graph(self._table_document())
        assert "C1" in graph.targets("H1", "header_for")
        assert "C0" in graph.targets("H0", "header_for")

    def test_header_is_not_its_own_header(self) -> None:
        graph = build_structural_graph(self._table_document())
        assert "H1" not in graph.targets("H1", "header_for")

    def test_merged_header_qualifies_every_column_it_covers(self) -> None:
        """The meaning the legacy prose flattening destroyed."""

        document = _document(
            [
                _element(
                    "M",
                    "Approval limits",
                    "table_cell",
                    0,
                    table_id="#/tables/0",
                    table_cell=TableCellRef(
                        row_index=0, column_index=0, column_span=3, is_header=True
                    ),
                ),
                _element(
                    "A",
                    "Manager",
                    "table_cell",
                    1,
                    table_id="#/tables/0",
                    table_cell=TableCellRef(row_index=0, column_index=1),
                ),
                _element(
                    "B",
                    "Director",
                    "table_cell",
                    2,
                    table_id="#/tables/0",
                    table_cell=TableCellRef(row_index=0, column_index=2),
                ),
            ]
        )
        graph = build_structural_graph(document)

        assert set(graph.targets("M", "merged_with")) == {"A", "B"}

    def test_table_reference_endpoints_do_not_fail_coverage(self) -> None:
        """`#/tables/0` is a converter reference, not a canonical element."""

        document = self._table_document()
        graph = build_structural_graph(document)
        assert verify_structural_coverage(document, graph) == []


class TestLeaves:
    def test_headings_are_containers_not_leaves(self) -> None:
        """Coverage is asserted over content, not over section wrappers."""

        document = _document(
            [
                _element("E1", "1. Scope", "heading", 0),
                _element("E2", "A clause.", order=1),
                _element("E3", "Another clause.", order=2),
            ]
        )
        graph = build_structural_graph(document)

        assert set(graph.leaf_element_ids) == {"E2", "E3"}

    def test_flat_document_treats_every_element_as_a_leaf(self) -> None:
        document = _document(
            [_element("E1", "One.", order=0), _element("E2", "Two.", order=1)]
        )
        graph = build_structural_graph(document)
        assert set(graph.leaf_element_ids) == {"E1", "E2"}


class TestDeterminism:
    def test_graph_is_identical_across_rebuilds(self) -> None:
        """The structural graph must be recomputable, never stored as truth."""

        document = _document(
            [
                _element("E1", "1. Scope", "heading", 0),
                _element("E2", "A clause.", order=1),
            ]
        )
        first = build_structural_graph(document)
        second = build_structural_graph(document)

        assert first.edges == second.edges
        assert list(first.nodes) == list(second.nodes)


@pytest.mark.parametrize("kind", ["contains", "precedes", "parent_heading"])
def test_edges_reference_known_nodes(kind: str) -> None:
    document = _document(
        [
            _element("E1", "Policy", "title", 0),
            _element("E2", "2. Leave", "heading", 1),
            _element("E3", "A clause.", order=2),
        ]
    )
    graph = build_structural_graph(document)
    for edge in [e for e in graph.edges if e.kind == kind]:
        assert edge.source in graph.nodes
        assert edge.target in graph.nodes
