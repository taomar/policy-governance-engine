"""Deterministic structural graph over a canonical document.

This is the *lossless reading skeleton* the directive requires as a separate
layer from Docling Graph's semantic candidates. The two must not be confused:

* this graph is built without an LLM, contains every canonical element, and is
  a pure restatement of document structure — it can be recomputed exactly from
  the canonical artifact at any time;
* the candidate graph proposes meaning, may be wrong, and is never authoritative.

Keeping them apart is what makes coverage accounting honest. "Every canonical
element appears in the structural graph" is a mechanical fact this module
guarantees by construction. "Every material clause was discovered" is a claim
about the candidate graph that must be measured, not assumed. If the two were
one graph, a node missing because the model failed would be indistinguishable
from a node missing because the document did not contain it.

The graph is deliberately built from plain dataclasses rather than a graph
library. Nothing here needs traversal algorithms — the operations are "children
of", "ancestors of", "reading order" — and a dependency-free structure keeps
this importable in the API runtime, which does not install the extraction
extra.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Literal

from policy_platform.contracts.canonical_document import (
    CanonicalDocument,
    CanonicalElement,
    TableCellRef,
)

#: Relationships between structural nodes. Each is a fact about the document's
#: own layout, never an interpretation of what the text means.
EdgeKind = Literal[
    "contains",
    "precedes",
    "parent_heading",
    "list_child",
    "table_cell_of",
    "header_for",
    "merged_with",
    "caption_for",
    "footnote_marker_to_note",
    "continues_on",
    "table_continues_on",
]


@dataclass(frozen=True)
class StructuralEdge:
    """One directed relationship between two structural nodes."""

    source: str
    target: str
    kind: EdgeKind


@dataclass(frozen=True)
class TableContinuation:
    """A record that one page's grid may continue the previous page's.

    Deliberately not a merge. `page.find_tables()` is a per-page API, so a table
    running across a page break is emitted as two grids with different ids, and
    the question of whether they are one table has no answer that structure alone
    can give. Measured on a real bilingual schedule spanning seven pages:

    * the governing heading repeats on all seven pages -- but that is text
      equality, not structure, and a running heading over genuinely distinct
      tables would say the same thing;
    * column counts across pages of that one table were 18, 10, 11, 18, 8, 18, 8,
      so grid width is not stable even within a single logical table;
    * "the table runs to the bottom margin" misses a page that ends 97pt above
      the bottom and still continues.

    So no single signal identifies a continuation. This record states what was
    observed and names every signal that fired, leaving the judgement to the
    consumer. `table_id`s are never merged: two tables stay two, because that is
    what the evidence supports, and grouping records for a reviewer is done a
    level up by governing heading rather than by a claim about layout.
    """

    #: The table that may continue onto the next page.
    from_table_id: str
    #: The table that may be its continuation.
    to_table_id: str
    from_page: int
    to_page: int
    #: Every signal that fired, in a fixed order so the record is comparable
    #: between runs. Never empty: a record with no corroboration is not emitted.
    signals: tuple[str, ...]


@dataclass
class StructuralNode:
    """One canonical element, plus its place in the document's structure."""

    element_id: str
    element_type: str
    #: Position in the document's total reading order. Used for ordering and
    #: adjacency only; never for identity, which the ordinal scheme proved
    #: unsafe.
    reading_order: int
    text: str
    page: int | None = None
    section: str | None = None
    table_id: str | None = None


@dataclass
class StructuralGraph:
    """The complete structural view of one canonical document."""

    document_id: str
    nodes: dict[str, StructuralNode] = field(default_factory=dict)
    edges: list[StructuralEdge] = field(default_factory=list)
    #: Cell coordinates, kept beside the nodes so consumers can reason about
    #: table position without holding the canonical document as well.
    table_cells: dict[str, TableCellRef] = field(default_factory=dict)
    #: Observed, never merged. See `TableContinuation`.
    table_continuations: list[TableContinuation] = field(default_factory=list)
    #: Headings the document wrote but did not declare as sections of its own
    #: numbering scheme — "Purpose", "Policy Details" — which it wrote as labels
    #: *inside* the section above them. See `_resolve_heading_levels`.
    #:
    #: Recorded during the build because the distinction is drawn from the
    #: headings around one heading and cannot be recovered from a single node
    #: afterwards. Kept here, beside the heading structure it comes from, so
    #: that anything deciding what counts as a policy has one answer to "did the
    #: document name this" rather than re-deriving the document's outline from
    #: its text — which would be a second definition of the same thing.
    unnamed_section_headings: set[str] = field(default_factory=set)

    _outgoing: dict[tuple[str, str], list[str]] = field(default_factory=dict, repr=False)
    _incoming: dict[tuple[str, str], list[str]] = field(default_factory=dict, repr=False)

    def index(self) -> None:
        """Build adjacency lookups. Called once after construction."""

        outgoing: dict[tuple[str, str], list[str]] = defaultdict(list)
        incoming: dict[tuple[str, str], list[str]] = defaultdict(list)
        for edge in self.edges:
            outgoing[(edge.source, edge.kind)].append(edge.target)
            incoming[(edge.target, edge.kind)].append(edge.source)
        self._outgoing = dict(outgoing)
        self._incoming = dict(incoming)

    def targets(self, element_id: str, kind: EdgeKind) -> list[str]:
        return list(self._outgoing.get((element_id, kind), ()))

    def sources(self, element_id: str, kind: EdgeKind) -> list[str]:
        return list(self._incoming.get((element_id, kind), ()))

    def heading_path(self, element_id: str) -> list[str]:
        """Every heading governing `element_id`, outermost first.

        Walks `parent_heading` edges rather than re-reading `section`, which
        holds only the nearest heading. A rule under "2.1 Annual Leave" is also
        under "2. Leave", and the outer heading routinely carries the scope that
        makes the inner rule interpretable.

        The walk is bounded by the node count, so a malformed graph containing a
        cycle cannot hang the caller.
        """

        path: list[str] = []
        seen: set[str] = set()
        current = element_id
        for _ in range(len(self.nodes) + 1):
            parents = self.targets(current, "parent_heading")
            if not parents:
                break
            parent = parents[0]
            if parent in seen:
                break
            seen.add(parent)
            path.append(parent)
            current = parent
        return list(reversed(path))

    def reading_order(self) -> list[StructuralNode]:
        return sorted(self.nodes.values(), key=lambda n: n.reading_order)

    @property
    def leaf_element_ids(self) -> list[str]:
        """Elements carrying content, i.e. those that contain nothing else.

        Coverage is asserted over leaves: a heading is accounted for through the
        clauses beneath it, and requiring a separate disposition for every
        container would make the coverage report noise rather than signal.
        """

        containers = {edge.source for edge in self.edges if edge.kind == "contains"}
        return [node_id for node_id in self.nodes if node_id not in containers]


def build_structural_graph(document: CanonicalDocument) -> StructuralGraph:
    """Build the lossless structural graph for `document`.

    Every canonical element becomes exactly one node. That is the property
    coverage accounting depends on, and it is asserted rather than assumed by
    `verify_structural_coverage`.
    """

    graph = StructuralGraph(document_id=document.document_id)

    for element in document.elements:
        fragment = element.source_fragments[0] if element.source_fragments else None
        graph.nodes[element.element_id] = StructuralNode(
            element_id=element.element_id,
            element_type=element.element_type,
            reading_order=element.logical_order,
            text=element.text,
            page=fragment.page if fragment else None,
            section=element.section,
            table_id=element.table_id,
        )
        if element.table_cell is not None:
            graph.table_cells[element.element_id] = element.table_cell

    ordered = sorted(document.elements, key=lambda e: e.logical_order)
    _add_reading_order_edges(graph, ordered)
    _add_heading_edges(graph, ordered)
    _add_list_edges(graph, ordered)
    _add_table_edges(graph, ordered)
    _add_reference_edges(graph, ordered)
    _add_continuation_edges(graph, ordered)
    _add_table_continuations(graph, ordered)

    graph.index()
    return graph


def _add_reading_order_edges(graph: StructuralGraph, ordered: list[CanonicalElement]) -> None:
    for previous, nxt in zip(ordered, ordered[1:]):
        graph.edges.append(StructuralEdge(previous.element_id, nxt.element_id, "precedes"))


def _add_heading_edges(graph: StructuralGraph, ordered: list[CanonicalElement]) -> None:
    """Attach every element to the heading stack in force at its position.

    The stack is maintained by walking the document once, so a heading that
    returns to a shallower level correctly closes the deeper ones. `contains`
    is emitted from the nearest heading only, keeping the containment tree a
    tree rather than a fan from every ancestor.

    Levels are resolved for the whole document before the walk begins, because
    the depth of an unnumbered heading is not a property of that heading alone —
    see `_resolve_heading_levels`.
    """

    headings = [
        element for element in ordered if element.element_type in ("title", "heading")
    ]
    stated = [_stated_heading_depth(e) for e in headings]
    level_of = dict(
        zip(
            (element.element_id for element in headings),
            _resolve_heading_levels(stated),
        )
    )
    # A heading whose depth we resolved rather than read is one the document did
    # not declare as a section. Recorded, not inferred again later.
    graph.unnamed_section_headings.update(
        element.element_id
        for element, depth, resolved in zip(
            headings, stated, (level_of[e.element_id] for e in headings)
        )
        if depth is None and resolved > 1
    )

    stack: list[tuple[int, str]] = []

    for element in ordered:
        if element.element_type in ("title", "heading"):
            level = level_of[element.element_id]
            while stack and stack[-1][0] >= level:
                stack.pop()
            if stack:
                parent = stack[-1][1]
                graph.edges.append(
                    StructuralEdge(element.element_id, parent, "parent_heading")
                )
                graph.edges.append(StructuralEdge(parent, element.element_id, "contains"))
            stack.append((level, element.element_id))
            continue

        if stack:
            parent = stack[-1][1]
            graph.edges.append(StructuralEdge(element.element_id, parent, "parent_heading"))
            graph.edges.append(StructuralEdge(parent, element.element_id, "contains"))


def _stated_heading_depth(element: CanonicalElement) -> int | None:
    """The depth the heading's own numbering states, or `None` if it states none.

    A title is depth 0 and outermost. "2.1.3" states depth 3. A heading that
    carries no numbering states nothing, which is a different answer from
    stating depth 1 — resolving that difference needs the headings around it,
    so it is deferred to `_resolve_heading_levels` rather than guessed here.
    """

    if element.element_type == "title":
        return 0
    label = element.text.split(None, 1)[0].rstrip(".") if element.text.split() else ""
    if label and all(part.isdigit() for part in label.split(".") if part):
        return max(len([part for part in label.split(".") if part]), 1)
    return None


def _resolve_heading_levels(stated: list[int | None]) -> list[int]:
    """Give every heading a depth, reading an unnumbered one in its context.

    **An unnumbered heading lying strictly between two numbered ones is a child
    of the earlier one.** Numbering, once a document uses it, is that document's
    own statement of its structure; a heading that opts out of the scheme while
    the scheme is still running is subordinate to the section it appears in, and
    one that appears after the scheme has ended is not governed by it and stays
    outermost.

    The defect this fixes: depth used to be inferred from a heading's own text
    alone, so an unnumbered sub-heading returned 1, and the `>=` pop in
    `_add_heading_edges` evicted its parent — making it a *sibling* of the
    section it sits inside. On the GMU handbook that turned "Policy Details"
    under "1. Manpower Planning, Recruitment & Selection" into a top-level
    section whose only available name was "Policy Details".

    The two-sided test is what keeps this safe rather than merely plausible. A
    one-sided rule ("an unnumbered heading following a numbered one is its
    child") reads the same in a sentence and is wrong on real data: it folds the
    AIS handbook's unnumbered `Table of Violations and Penalties` — an appendix
    of seventy-two rows after the numbering has finished — into
    `10. ACKNOWLEDGEMENT`, which does not state it.

    Measured across both stored documents: GMU reclassifies exactly two headings
    ("Purpose" and "Policy Details"), both correctly; AIS reclassifies none.

    Depth is taken from the nearest *preceding* stated depth, so consecutive
    unnumbered headings become siblings of each other rather than nesting one
    inside the next — the document wrote them at one level and drew no line
    between them.
    """

    resolved: list[int] = []
    for position, depth in enumerate(stated):
        if depth is not None:
            resolved.append(depth)
            continue
        governing = next(
            (d for d in reversed(stated[:position]) if d is not None), None
        )
        numbering_continues = any(d is not None for d in stated[position + 1 :])
        resolved.append(
            governing + 1 if governing is not None and numbering_continues else 1
        )
    return resolved


def _add_list_edges(graph: StructuralGraph, ordered: list[CanonicalElement]) -> None:
    """Link nested list items to their parent item.

    A sub-item routinely qualifies its parent ("...except where (a) applies"),
    so losing nesting turns one conditional rule into two unrelated statements.
    """

    stack: list[tuple[int, str]] = []
    for element in ordered:
        if element.element_type != "list_item":
            stack.clear()
            continue
        level = element.list_level or 0
        while stack and stack[-1][0] >= level:
            stack.pop()
        if stack:
            graph.edges.append(
                StructuralEdge(stack[-1][1], element.element_id, "list_child")
            )
        stack.append((level, element.element_id))


def _covered_columns(cell: TableCellRef) -> range:
    """Every column index a cell occupies, not merely the one it starts in."""

    return range(cell.column_index, cell.column_index + cell.column_span)


def _add_table_edges(graph: StructuralGraph, ordered: list[CanonicalElement]) -> None:
    """Connect cells to their table, to their headers, and across merges."""

    cells_by_table: dict[str, list[CanonicalElement]] = defaultdict(list)
    for element in ordered:
        if element.table_id and element.table_cell is not None:
            cells_by_table[element.table_id].append(element)

    for table_id, cells in cells_by_table.items():
        headers_by_column: dict[int, list[CanonicalElement]] = defaultdict(list)
        for cell in cells:
            assert cell.table_cell is not None
            if cell.table_cell.is_header:
                # A header that spans columns heads every one of them. Filing it
                # only under the column it starts in leaves the rest unheaded.
                for column in _covered_columns(cell.table_cell):
                    headers_by_column[column].append(cell)

        for cell in cells:
            assert cell.table_cell is not None
            graph.edges.append(StructuralEdge(cell.element_id, table_id, "table_cell_of"))

            # A cell spanning several columns is qualified by the header of every
            # column it covers. Resolving only its starting column attributes a
            # value that holds across the whole span to one column of it, which
            # reads as a specific claim the source never made — and it is exactly
            # how a deliberately uniform value becomes indistinguishable from a
            # flattened sequence of different ones.
            attached: set[str] = set()
            for column in _covered_columns(cell.table_cell):
                for header in headers_by_column.get(column, ()):
                    assert header.table_cell is not None
                    if header.element_id == cell.element_id:
                        continue
                    # A column header sits at or above what it governs; without
                    # this a sub-header would be recorded as explaining the
                    # merged header above it, inverting the relationship.
                    if header.table_cell.row_index > cell.table_cell.row_index:
                        continue
                    if header.element_id in attached:
                        continue
                    attached.add(header.element_id)
                    # A merged header is reported separately from a plain column
                    # header because it says something different: it qualifies a
                    # band of columns rather than identifying one.
                    kind = (
                        "merged_with"
                        if header.table_cell.column_span > 1
                        else "header_for"
                    )
                    graph.edges.append(
                        StructuralEdge(header.element_id, cell.element_id, kind)
                    )


def _add_reference_edges(graph: StructuralGraph, ordered: list[CanonicalElement]) -> None:
    """Attach captions to what they describe and footnotes to their markers."""

    for element in ordered:
        if element.caption_for:
            graph.edges.append(
                StructuralEdge(element.element_id, element.caption_for, "caption_for")
            )
        for footnote_id in element.references_footnote_ids:
            graph.edges.append(
                StructuralEdge(element.element_id, footnote_id, "footnote_marker_to_note")
            )


def _add_continuation_edges(graph: StructuralGraph, ordered: list[CanonicalElement]) -> None:
    """Link an element to the one continuing it across a page boundary.

    A sentence split by a page break is one statement. Without this edge, the
    reading plan can hand a model half a rule and the half that carries the
    exception is silently missing.
    """

    for previous, nxt in zip(ordered, ordered[1:]):
        previous_pages = previous.pages
        next_pages = nxt.pages
        if not previous_pages or not next_pages:
            continue
        if previous_pages[-1] == next_pages[0]:
            continue
        if previous.element_type != nxt.element_type:
            continue
        if _ends_mid_sentence(previous.text):
            graph.edges.append(
                StructuralEdge(previous.element_id, nxt.element_id, "continues_on")
            )


def _ends_mid_sentence(text: str) -> bool:
    stripped = text.rstrip()
    return bool(stripped) and stripped[-1] not in ".!?:;"


#: Signals that corroborate a continuation. At least one must fire on top of the
#: two structural preconditions; neither is trusted on its own, because each was
#: measured failing on a real document (see `TableContinuation`).
#:
#: Column count is deliberately absent. It was measured varying 18/10/11/18/8/18/8
#: across pages of a single logical table, so it misses real continuations; and
#: two unrelated tables of equal width match trivially, so it also fires on false
#: ones. A signal with both failure directions is not evidence.
_CORROBORATING = (
    "repeated_governing_heading",
    "continuation_has_no_header_row",
)


def _add_table_continuations(
    graph: StructuralGraph, ordered: list[CanonicalElement]
) -> None:
    """Record where one page's grid appears to continue the previous page's.

    Two preconditions must both hold, and then at least one corroborating signal
    on top of them. The conjunction is the point: every individual signal was
    measured producing a wrong answer somewhere, so any one of them alone would
    be an opinion rather than an observation.

    Nothing here reads a heading's wording, a numbering scheme or a layout
    constant, so no document is a target.
    """

    rows_by_table: dict[str, list[CanonicalElement]] = {}
    for element in ordered:
        if element.table_id:
            rows_by_table.setdefault(element.table_id, []).append(element)
    if len(rows_by_table) < 2:
        return

    order = {element.element_id: index for index, element in enumerate(ordered)}
    table_ids = list(rows_by_table)

    for earlier_id, later_id in zip(table_ids, table_ids[1:]):
        earlier = rows_by_table[earlier_id]
        later = rows_by_table[later_id]
        earlier_page = _last_page(earlier)
        later_page = _first_page(later)
        if earlier_page is None or later_page is None:
            continue

        # Precondition 1: the pages are consecutive. A gap means intervening
        # content that is not a page break, whatever else agrees.
        if later_page != earlier_page + 1:
            continue

        # Precondition 2: nothing but headings sits between the two grids. The
        # repeated heading of a continued table lands exactly here, which is
        # also why `_add_continuation_edges` cannot see these -- it requires
        # strict reading-order adjacency and identical element types.
        between = ordered[order[earlier[-1].element_id] + 1 : order[later[0].element_id]]
        if any(element.element_type != "heading" for element in between):
            continue

        signals: list[str] = []

        earlier_heading = _governing_heading(ordered, order, earlier[0])
        later_heading = _governing_heading(ordered, order, later[0])
        if (
            earlier_heading
            and later_heading
            and " ".join(earlier_heading.split()) == " ".join(later_heading.split())
        ):
            signals.append("repeated_governing_heading")

        # Only observable because ingestion stopped assuming grid row 0 is a
        # header row. While every table carried headers -- wrongly -- a
        # continuation page was indistinguishable from a table's first page.
        if any(row.table_headers for row in earlier) and not any(
            row.table_headers for row in later
        ):
            signals.append("continuation_has_no_header_row")

        if not signals:
            continue

        graph.table_continuations.append(
            TableContinuation(
                from_table_id=earlier_id,
                to_table_id=later_id,
                from_page=earlier_page,
                to_page=later_page,
                signals=tuple(s for s in _CORROBORATING if s in signals),
            )
        )
        graph.edges.append(
            StructuralEdge(
                earlier[-1].element_id, later[0].element_id, "table_continues_on"
            )
        )


def _last_page(elements: list[CanonicalElement]) -> int | None:
    pages = [page for element in elements for page in element.pages]
    return max(pages) if pages else None


def _first_page(elements: list[CanonicalElement]) -> int | None:
    pages = [page for element in elements for page in element.pages]
    return min(pages) if pages else None


def _governing_heading(
    ordered: list[CanonicalElement],
    order: dict[str, int],
    element: CanonicalElement,
) -> str | None:
    """The nearest heading before `element` in reading order, verbatim."""

    for candidate in reversed(ordered[: order[element.element_id]]):
        if candidate.element_type == "heading":
            return candidate.text
    return None


def verify_structural_coverage(
    document: CanonicalDocument, graph: StructuralGraph
) -> list[str]:
    """Prove the graph lost nothing, returning one message per problem.

    Checked mechanically on every build because it is cheap and because the
    failure it catches is silent: a coverage report computed over a graph that
    is already missing elements would confidently report full coverage.
    """

    problems: list[str] = []
    element_ids = {element.element_id for element in document.elements}

    missing = element_ids - set(graph.nodes)
    if missing:
        problems.append(f"{len(missing)} canonical element(s) absent from the graph")

    extra = set(graph.nodes) - element_ids
    if extra:
        problems.append(f"{len(extra)} graph node(s) not present in the canonical document")

    dangling = {
        endpoint
        for edge in graph.edges
        for endpoint in (edge.source, edge.target)
        if endpoint not in graph.nodes and not endpoint.startswith("#/")
    }
    if dangling:
        problems.append(f"{len(dangling)} edge endpoint(s) reference unknown nodes")

    return problems
