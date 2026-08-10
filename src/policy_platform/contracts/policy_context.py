"""Context-preserving ingestion contracts: source elements, windows, coverage.

These contracts sit between the canonical document (``contracts.canonical_document``)
and the two extraction agents. They exist because the previous pipeline turned a
document into fixed 4,000-character windows that ignored every structural
boundary the document actually had — so a table row could be separated from its
headers, a consequence from the lead-in that qualified it, and a rule from the
exception directly attached to it. What a reviewer reads as one coherent
provision arrived at the model as two unrelated fragments.

Three ideas are modelled here, and all three are deliberately **domain
neutral**. Nothing in this module knows what an employee, a device, an invoice,
an article of law or a control objective is. It knows only that documents have
sections, paragraphs, lists, tables, footnotes and references, and that a policy
statement is interpreted against neighbouring text:

1. :class:`SourceElement` — one ordered, addressable unit of a document, with
   the structural identity (section path, table identity, row index, references)
   that the persisted ``Clause`` row now carries.
2. :class:`PolicyContextUnit` — a *window*: the elements this unit is
   responsible for extracting (``target_element_ids``) plus the elements
   supplied purely so the target can be understood (``context_element_ids``).
   Keeping the two lists separate is what stops interpretation context from
   being cited as evidence — a rule may only ever quote its target.
3. :class:`CoverageManifest` — proof that every element of the document received
   a disposition. Retrieval, ranking and embedding similarity are all allowed to
   *propose*; none of them may cause a source region to silently disappear, so
   coverage is asserted mechanically rather than assumed.

Vocabulary note: "target" and "context" are used throughout instead of "policy"
and "background" because a window's target is whatever region the pipeline is
currently responsible for, regardless of whether it turns out to contain a rule.
A window whose target contains no policy still consumes its elements and records
``non_policy`` — that is a *result*, not a gap.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

#: What happened to one source element by the end of an extraction run.
#:
#: * ``policy_target`` — the element was inside some window's target region and
#:   was offered to the extractor as policy-bearing candidate text.
#: * ``interpretation_context`` — the element was supplied to help interpret a
#:   target but was never itself a target. Definitions, table headers and
#:   governing lead-ins usually land here *in addition to* being a target in
#:   their own window; the manifest records the strongest disposition an element
#:   reached, so this value means "context only, nowhere a target".
#: * ``non_policy`` — the element was processed and judged to carry no policy
#:   (a title page, a revision-history row, a page footer that survived
#:   boilerplate stripping).
#: * ``unresolved`` — the element was reached but could not be dispositioned:
#:   its window failed, the model call errored, or the run stopped early. This
#:   is the value that must never be silently absent, because "we never got to
#:   it" and "there was nothing there" are completely different facts.
CoverageDisposition = Literal[
    "policy_target",
    "interpretation_context",
    "non_policy",
    "unresolved",
]

#: Ordering used when an element is reached more than once. A single element can
#: be a target in one window and context in another; the manifest keeps the
#: strongest claim so "was this ever extracted?" has one answer.
_DISPOSITION_RANK: dict[str, int] = {
    "unresolved": 0,
    "non_policy": 1,
    "interpretation_context": 2,
    "policy_target": 3,
}


def stronger_disposition(left: CoverageDisposition, right: CoverageDisposition) -> CoverageDisposition:
    """Return whichever disposition makes the stronger claim about an element."""

    return left if _DISPOSITION_RANK[left] >= _DISPOSITION_RANK[right] else right


class SourceElement(BaseModel):
    """One ordered, addressable unit of a document, structurally described.

    This is the assembler's input. It is intentionally a *projection* rather
    than a second copy of ``CanonicalElement``: the assembler runs over persisted
    ``Clause`` rows during extraction and over freshly parsed canonical elements
    in tests, and both must produce identical windows. Anything either source
    cannot supply is optional.

    ``section_path`` is the ordered heading hierarchy above this element
    (``["4. Replacement", "4.1 Faulty equipment"]``). The single ``section``
    string the platform carried before could not distinguish "a sibling
    paragraph under the same subsection" from "a paragraph in a different part
    of the document that happens to share a heading name", which is precisely
    the judgement window assembly needs.
    """

    model_config = ConfigDict(extra="ignore")

    element_id: str = Field(..., description="Stable identity within the document.")
    #: The platform's own addressing label (``p3-E000016``). Carried so a window
    #: can be rendered with the exact identifier the agents echo back.
    element_ref: str = ""
    element_type: str = "paragraph"
    order: int = Field(0, ge=0, description="Position in the document's total order.")
    text: str = ""
    section: str | None = None
    section_path: list[str] = Field(default_factory=list)
    page: int | None = None

    # --- table identity -------------------------------------------------
    table_id: str | None = None
    table_headers: list[str] | None = None
    #: 0-based position of this row within its table's data rows.
    table_row_index: int | None = None
    #: The row's cell values, unjoined. Preserved because "Standard laptop,
    #: 14-inch" is a cell value and "General office | Standard laptop, 14-inch |
    #: On request, manager approval | USD 1,150" is a rendering of a row; a rule
    #: formulated from the second without the first has no column semantics.
    table_cells: list[str] | None = None

    # --- explicit relationships stated by the document itself ------------
    #: Section/clause labels this element explicitly points at ("see section
    #: 11", "Article 74"). Extracted lexically, never invented.
    references: list[str] = Field(default_factory=list)
    #: Footnote markers attached to this element, and footnote identities this
    #: element *is*. Both directions are needed: a table row cites a footnote,
    #: and the footnote element must be able to find its table.
    footnote_refs: list[str] = Field(default_factory=list)
    #: Heading depth the document itself declares. Authoritative over textual
    #: numbering when present.
    outline_level: int | None = None

    @property
    def is_table_row(self) -> bool:
        return self.table_id is not None and self.element_type in {"table_row", "table"}

    @property
    def is_heading(self) -> bool:
        return self.element_type == "heading"

    @property
    def sizing_length(self) -> int:
        """Character cost of including this element in a window.

        The constant covers the addressing marker and section label the renderer
        adds around the text. Kept as a property so window sizing has exactly
        one definition rather than one per call site.
        """

        return len(self.text) + 40


class ContextReason(BaseModel):
    """Why one element was pulled into a window as context rather than target.

    Recorded per element, not per window, because a reviewer asking "why is this
    paragraph attached to that rule?" needs an answer that names *this*
    paragraph. The vocabulary is structural and domain neutral.
    """

    model_config = ConfigDict(extra="ignore")

    element_id: str
    reason: Literal[
        "section_lead_in",
        "section_sibling",
        "table_headers",
        "table_sibling_row",
        "table_caption",
        "footnote",
        "list_parent",
        "explicit_reference",
        "window_overlap",
        "definition",
        "preceding_paragraph",
        "following_paragraph",
    ]
    detail: str = ""


class PolicyContextUnit(BaseModel):
    """One target region plus the context needed to interpret it.

    Replaces the fixed character batch. The unit owns its targets exclusively —
    every element appears in exactly one unit's ``target_element_ids`` — while
    context is shared freely, which is what produces overlap at semantic
    boundaries instead of hard cuts. Two consecutive units covering §4 and §4.1
    therefore both see the general replacement lead-in, and the clause that used
    to be stranded at a batch boundary is now interpretable from either side.

    ``window_start_order``/``window_end_order`` are the inclusive bounds of the
    whole window (targets *and* context) in document order, so a reviewer can
    reconstruct exactly which region of the source the model was shown.
    """

    model_config = ConfigDict(extra="ignore")

    unit_id: str
    document_id: str = ""
    target_element_ids: list[str] = Field(default_factory=list)
    context_element_ids: list[str] = Field(default_factory=list)
    context_reasons: list[ContextReason] = Field(default_factory=list)

    #: The deepest heading path common to every target. Empty for a unit whose
    #: targets straddle sections (which the assembler avoids but does not forbid
    #: — a table larger than one window has to split somewhere).
    section_path: list[str] = Field(default_factory=list)
    #: Set when every target belongs to one table, so a formulator can be told
    #: "these are rows of one table" rather than inferring it from prose.
    table_id: str | None = None
    table_headers: list[str] | None = None

    window_start_order: int = 0
    window_end_order: int = 0
    #: Sum of ``sizing_length`` over targets and context. Recorded so a
    #: reviewer can see why a unit was split without re-deriving the sizing.
    window_chars: int = 0
    #: Units this one overlaps by sharing context. Purely informational, but it
    #: is the fastest way to answer "which other window saw this paragraph?".
    overlaps_unit_ids: list[str] = Field(default_factory=list)

    @property
    def element_ids(self) -> list[str]:
        """Every element in the window, targets first, without duplicates.

        Deliberately **not** document order: this is the membership list, used
        for set operations and overlap detection. Anything that needs the window
        as the model sees it — rendering it, or resolving a span reference by
        slicing a contiguous range — must sort by ``SourceElement.order``
        instead. Conflating the two lets a span be stated against one ordering
        and resolved against another, which silently stitches a target together
        with an unrelated context paragraph.
        """

        seen: set[str] = set()
        ordered: list[str] = []
        for element_id in [*self.target_element_ids, *self.context_element_ids]:
            if element_id not in seen:
                seen.add(element_id)
                ordered.append(element_id)
        return ordered


class ElementCoverage(BaseModel):
    """The disposition one source element reached, and why."""

    model_config = ConfigDict(extra="ignore")

    element_id: str
    disposition: CoverageDisposition = "unresolved"
    #: Machine-readable justification, e.g. ``"window_target"``,
    #: ``"window_failed"``, ``"no_policy_passage"``. Free-form on purpose: the
    #: closed vocabulary that matters is the disposition itself.
    reason: str = ""
    unit_ids: list[str] = Field(default_factory=list)


class CoverageManifest(BaseModel):
    """Every element of one document, with the disposition it reached.

    The manifest is the mechanical form of "no source region disappears
    silently". It is built from the assembler's own element list — not from
    whatever the model happened to return — so a model that ignores half a
    window produces ``unresolved`` entries rather than an absence nobody can
    see.
    """

    model_config = ConfigDict(extra="ignore")

    document_id: str = ""
    elements: list[ElementCoverage] = Field(default_factory=list)

    def counts(self) -> dict[str, int]:
        totals = {key: 0 for key in _DISPOSITION_RANK}
        for entry in self.elements:
            totals[entry.disposition] = totals.get(entry.disposition, 0) + 1
        return totals

    @property
    def total_elements(self) -> int:
        return len(self.elements)

    def unresolved_element_ids(self) -> list[str]:
        return [entry.element_id for entry in self.elements if entry.disposition == "unresolved"]

    def is_exhaustive(self, element_ids: list[str]) -> bool:
        """True when the manifest has an entry for every supplied element id."""

        covered = {entry.element_id for entry in self.elements}
        return all(element_id in covered for element_id in element_ids)


class ExtractionContextManifest(BaseModel):
    """The full window plan for one extraction run, persisted with the run.

    Kept as a run artefact rather than recomputed on read: the assembler is
    deterministic, but its *inputs* (the clause rows) can be re-extracted, and a
    reviewer asking "what did the model actually see for this rule?" months
    later needs the answer the run used, not the answer today's document would
    produce.
    """

    model_config = ConfigDict(extra="ignore")

    document_id: str = ""
    assembler_version: str = ""
    max_window_chars: int = 0
    #: The clause generation these element ids belong to. Element ids restart at
    #: `E000001` in every generation, so a manifest without this becomes
    #: ambiguous the moment its document is re-ingested: `E000012` would name
    #: different text than it did when the run executed.
    clause_generation: int | None = None
    units: list[PolicyContextUnit] = Field(default_factory=list)
    coverage: CoverageManifest = Field(default_factory=CoverageManifest)

    def unit_by_id(self, unit_id: str) -> PolicyContextUnit | None:
        for unit in self.units:
            if unit.unit_id == unit_id:
                return unit
        return None
