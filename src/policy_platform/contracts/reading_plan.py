"""Graph-aware context assembly.

WHAT THIS REPLACES
------------------
Extraction currently walks a document in fixed 4,000-character windows
(``ai_extraction._batch_clauses``). The existing code says so itself: "a
document is walked in fixed-size windows, not one topic at a time". That is the
defect this module exists to remove.

A fixed window is wrong in both directions at once. It **splits** material that
belongs together — a rule on one side of a boundary and its exception on the
other, so the model sees an obligation that appears unconditional. And it
**joins** material that does not belong together — the tail of one section and
the head of the next, inviting a condition to be attached to the wrong rule.
Neither failure is visible in the output: both produce a confident, well-formed
rule that is simply wrong.

TARGET VERSUS CONTEXT
---------------------
Every unit distinguishes two roles:

* **target elements** may contain a policy statement, and are what the model is
  asked to extract from;
* **context elements** are needed to *interpret* the target and must never be
  copied into its evidence.

The separation is the point. A definition three sections away is essential for
reading a rule correctly, but quoting the definition as if it were the rule's
own text would misrepresent the source. Every context element therefore carries
a machine-readable reason for its inclusion, so a reviewer can see why the model
was shown it.

CLOSURE IS PROPOSED BY STRUCTURE, NOT BY GUESSWORK
--------------------------------------------------
Every dependency here is derived from the deterministic structural graph or
from an explicit textual cross-reference. Nothing is included because it merely
looks related, and nothing is included on the say-so of an LLM. Candidate graph
edges may later *propose* additional context, but they arrive marked as
candidates and do not silently become part of the closure.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from policy_platform.contracts.canonical_document import CanonicalDocument, CanonicalElement
from policy_platform.contracts.structural_graph import StructuralGraph

#: Why a context element was included. Recorded per element rather than per unit
#: because one unit routinely pulls context for several different reasons, and
#: "why is this here" is the first question a reviewer asks.
DependencyReason = Literal[
    "ancestor_heading",
    "list_parent",
    "list_sibling",
    "table_header",
    "table_row_label",
    "merged_header",
    "caption",
    "footnote",
    "continuation",
    "cross_reference",
    "definition",
    "preceding_context",
]

#: Element kinds that can carry an obligation. Headings and furniture are
#: excluded as *targets* but remain available as context: a heading scopes a
#: rule, it does not state one.
_TARGETABLE = frozenset({"paragraph", "list_item", "table_cell", "other", "formula", "code"})

#: "Section 4.2", "clause 7", "paragraph 3.1(a)". Deliberately requires an
#: explicit keyword: bare numbers appear constantly in policy text ("within 5
#: days"), and treating them as references would pull unrelated material in.
_CROSS_REFERENCE_RE = re.compile(
    r"\b(?:section|clause|paragraph|article|appendix|schedule|annex|part)\s+"
    r"(\d+(?:\.\d+)*(?:\([a-z]\))?|[A-Z](?:\.\d+)*)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ContextElement:
    """One supporting element, with the reason it was pulled in."""

    element_id: str
    reason: DependencyReason
    #: True when a candidate graph edge proposed this rather than deterministic
    #: structure. Kept distinct so unverified suggestions never masquerade as
    #: structural fact.
    is_candidate: bool = False


@dataclass
class ContextUnit:
    """One coherent reading unit handed to extraction.

    ``ordered_element_ids`` presents targets and context in original document
    order. Reading order is preserved because policy text is written to be read
    forwards: an exception usually follows the rule it modifies, and shuffling
    them changes what a reader — human or model — concludes.
    """

    unit_id: str
    target_element_ids: list[str]
    context: list[ContextElement] = field(default_factory=list)
    heading_path: list[str] = field(default_factory=list)

    @property
    def context_element_ids(self) -> list[str]:
        return [c.element_id for c in self.context]

    @property
    def ordered_element_ids(self) -> list[str]:
        seen = set(self.target_element_ids) | set(self.context_element_ids)
        return [eid for eid in self._document_order if eid in seen]

    #: Populated by the assembler; kept private so callers use the properties.
    _document_order: list[str] = field(default_factory=list, repr=False)

    def reasons_for(self, element_id: str) -> list[DependencyReason]:
        return [c.reason for c in self.context if c.element_id == element_id]


@dataclass
class ReadingPlan:
    """The complete set of context units for one document.

    A plan is only useful if it is exhaustive: a unit-based reading that quietly
    omits a paragraph has the same effect as a parser that never extracted it.
    ``uncovered_target_ids`` makes that checkable rather than assumed.
    """

    document_id: str
    units: list[ContextUnit] = field(default_factory=list)
    uncovered_target_ids: list[str] = field(default_factory=list)

    @property
    def is_exhaustive(self) -> bool:
        return not self.uncovered_target_ids


def build_reading_plan(
    document: CanonicalDocument,
    graph: StructuralGraph,
    *,
    max_targets_per_unit: int = 4,
) -> ReadingPlan:
    """Group a document into graph-aware context units.

    Units are formed within a section, never across one: a section boundary is
    the document's own statement that the subject changed, and it is the only
    boundary that is meaningful rather than arbitrary. ``max_targets_per_unit``
    bounds unit size for models with limited context, and splits only *within* a
    section so the bound never silently reintroduces the arbitrary cut this
    module exists to remove.
    """

    by_id = {element.element_id: element for element in document.elements}
    order = [element.element_id for element in sorted(document.elements, key=lambda e: e.logical_order)]
    definitions = _definition_index(document)

    units: list[ContextUnit] = []
    covered: set[str] = set()

    for group in _group_by_section(document, graph):
        for chunk in _chunk(group, max_targets_per_unit):
            unit = _build_unit(
                targets=chunk,
                document=document,
                graph=graph,
                by_id=by_id,
                definitions=definitions,
                order=order,
                index=len(units),
            )
            units.append(unit)
            covered.update(chunk)

    targetable = [eid for eid in order if _is_targetable(by_id[eid])]
    return ReadingPlan(
        document_id=document.document_id,
        units=units,
        uncovered_target_ids=[eid for eid in targetable if eid not in covered],
    )


def _is_targetable(element: CanonicalElement) -> bool:
    if element.element_type not in _TARGETABLE:
        return False
    if element.is_non_normative:
        return False
    # A column header labels values rather than stating a rule; it is pulled in
    # as context for the cells beneath it instead.
    if element.table_cell is not None and element.table_cell.is_header:
        return False
    return bool(element.text.strip())


def _group_by_section(
    document: CanonicalDocument, graph: StructuralGraph
) -> list[list[str]]:
    """Partition targetable elements by their nearest governing heading."""

    groups: list[list[str]] = []
    current_key: tuple[str, ...] | None = None

    for element in sorted(document.elements, key=lambda e: e.logical_order):
        if not _is_targetable(element):
            continue
        key = tuple(graph.heading_path(element.element_id))
        if key != current_key:
            groups.append([])
            current_key = key
        groups[-1].append(element.element_id)

    return [g for g in groups if g]


def _chunk(items: list[str], size: int) -> list[list[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)] or [[]]


def _definition_index(document: CanonicalDocument) -> dict[str, str]:
    """Map a defined term to the element defining it.

    Detection is deliberately conservative — an explicit definitional phrasing —
    because a false definition link pulls unrelated text into a rule's context
    and can change how the rule reads.
    """

    index: dict[str, str] = {}
    pattern = re.compile(
        r'^["\u201c]?([A-Z][\w \-/]{2,40})["\u201d]?\s+(?:means|shall mean|is defined as)\b'
    )
    for element in document.elements:
        match = pattern.match(element.text.strip())
        if match:
            index[match.group(1).strip().casefold()] = element.element_id
    return index


def _build_unit(
    *,
    targets: list[str],
    document: CanonicalDocument,
    graph: StructuralGraph,
    by_id: dict[str, CanonicalElement],
    definitions: dict[str, str],
    order: list[str],
    index: int,
) -> ContextUnit:
    context: dict[tuple[str, str], ContextElement] = {}

    def add(element_id: str, reason: DependencyReason) -> None:
        if element_id in targets or element_id not in by_id:
            return
        context.setdefault((element_id, reason), ContextElement(element_id, reason))

    heading_ids = graph.heading_path(targets[0]) if targets else []
    for heading_id in heading_ids:
        add(heading_id, "ancestor_heading")

    for target in targets:
        _add_list_context(target, graph, add)
        _add_table_context(target, graph, add)
        _add_reference_context(target, graph, add)
        _add_continuation_context(target, graph, add)
        _add_definition_context(by_id[target], definitions, add)

    _add_preceding_context(targets, order, by_id, graph, add)

    return ContextUnit(
        unit_id=f"{document.document_id}:U{index:04d}",
        target_element_ids=list(targets),
        context=sorted(context.values(), key=lambda c: (order.index(c.element_id), c.reason)),
        heading_path=[by_id[h].text for h in heading_ids if h in by_id],
        _document_order=order,
    )


def _add_list_context(target: str, graph: StructuralGraph, add) -> None:
    """Pull the list preamble and sibling items.

    A sub-item is frequently unreadable alone ("(c) except where (a) applies"),
    and siblings routinely enumerate alternatives to one condition.
    """

    for parent in graph.sources(target, "list_child"):
        add(parent, "list_parent")
        for sibling in graph.targets(parent, "list_child"):
            add(sibling, "list_sibling")


def _add_table_context(target: str, graph: StructuralGraph, add) -> None:
    """Pull headers, merged headers, the row label and the caption for a cell.

    A cell reading "15 minutes" states nothing on its own; its meaning lives
    entirely in the column header and the row label that frame it.

    Only the row's *label* is included, not every sibling cell. Pulling the whole
    table would put all 94 cells of a large table into the context of each one,
    which is a sliding window wearing a different name — and the row above is
    rarely relevant to the row below.
    """

    for header in graph.sources(target, "header_for"):
        add(header, "table_header")
    for merged in graph.sources(target, "merged_with"):
        add(merged, "merged_header")

    for table_id in graph.targets(target, "table_cell_of"):
        for caption in graph.sources(table_id, "caption_for"):
            add(caption, "caption")

        node = graph.nodes.get(target)
        row = _row_of(graph, target)
        if node is None or row is None:
            continue
        for sibling in graph.sources(table_id, "table_cell_of"):
            if sibling == target:
                continue
            if _row_of(graph, sibling) != row:
                continue
            # The leftmost cell of a row is conventionally its label ("P1",
            # "Standard tier"); the rest are peer values that do not explain it.
            if _column_of(graph, sibling) == 0:
                add(sibling, "table_row_label")


def _row_of(graph: StructuralGraph, element_id: str) -> int | None:
    cell = graph.table_cells.get(element_id)
    return cell.row_index if cell else None


def _column_of(graph: StructuralGraph, element_id: str) -> int | None:
    cell = graph.table_cells.get(element_id)
    return cell.column_index if cell else None


def _add_reference_context(target: str, graph: StructuralGraph, add) -> None:
    for footnote in graph.targets(target, "footnote_marker_to_note"):
        add(footnote, "footnote")


def _add_continuation_context(target: str, graph: StructuralGraph, add) -> None:
    """Follow continuation edges in both directions.

    Half a sentence is not a rule, and the missing half is exactly where the
    qualifying clause tends to sit.
    """

    for nxt in graph.targets(target, "continues_on"):
        add(nxt, "continuation")
    for previous in graph.sources(target, "continues_on"):
        add(previous, "continuation")


def _add_definition_context(
    element: CanonicalElement, definitions: dict[str, str], add
) -> None:
    lowered = element.text.casefold()
    for term, element_id in definitions.items():
        if term in lowered:
            add(element_id, "definition")


def _add_preceding_context(
    targets: list[str],
    order: list[str],
    by_id: dict[str, CanonicalElement],
    graph: StructuralGraph,
    add,
) -> None:
    """Include the immediately preceding element within the same section.

    A rule's stated scope is very often the sentence just before it ("The
    following applies to full-time employees:"). One element is deliberate:
    widening this turns targeted context into a sliding window, which is the
    behaviour being replaced.

    Skipped for table cells. Their meaning comes from the header and row label,
    which are already attached explicitly; the cell that happens to precede one
    in reading order is a peer value that explains nothing.
    """

    if not targets:
        return
    first = targets[0]
    if by_id[first].table_cell is not None:
        return
    position = order.index(first)
    if position == 0:
        return
    previous = order[position - 1]
    if by_id[previous].table_cell is not None:
        return
    if graph.heading_path(previous) == graph.heading_path(first):
        add(previous, "preceding_context")


def find_cross_references(text: str) -> list[str]:
    """Return explicit section references mentioned in `text`.

    Exposed separately because cross-reference closure needs a resolution step
    against the document's own numbering, which belongs to the caller that has
    the section index — not here.
    """

    return [match.group(1) for match in _CROSS_REFERENCE_RE.finditer(text)]
