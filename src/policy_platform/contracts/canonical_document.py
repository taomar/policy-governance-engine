"""Canonical document representation (PDF ingestion architecture spec, section 7).

The deterministic intermediate representation that sits between a raw PDF and
every downstream consumer (policy extraction, chat grounding, quality
evaluation). Two representations are stored side by side per spec section 6:

* ``CanonicalPage.raw_text`` — the authoritative parser output, never rewritten.
  It exists for auditability and verbatim validation.
* ``CanonicalElement`` — the *logical* view, in which physical page fragments
  that clearly belong to one paragraph/list/table have been reconnected.

The critical invariant (spec section 10, INVARIANT 6) is that reconnection may
only ever *concatenate source fragments in their original order*. No component
in this module — and no model downstream of it — may introduce a word that was
not in the PDF. Every ``CanonicalElement.text`` is therefore reconstructible
from its ``source_fragments`` plus a recorded, deterministic list of
``transformations``.

``SourceFragment`` offsets are page-relative and index into
``CanonicalPage.raw_text`` for that page, so "where did this sentence come
from" is answerable by slicing, not by searching. Spec section 25: source
position — not text — is the identity of an extraction, because the same
sentence can legitimately appear more than once in a document.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ElementType = Literal[
    "title",
    "heading",
    "paragraph",
    "list",
    "list_item",
    "table",
    "table_row",
    "table_cell",
    "caption",
    "footnote",
    "furniture",
    "formula",
    "code",
    "other",
]

#: Element kinds that carry no policy text of their own and exist only to
#: describe the document itself. Spec section 55 / INVARIANT 9 requires every
#: canonical element to receive a coverage disposition; separating furniture
#: here is what lets "this page header was not extracted as policy" be a
#: *deliberate* disposition rather than an unexplained gap.
NON_NORMATIVE_TYPES: frozenset[str] = frozenset({"furniture", "caption"})

# Deterministic, code-performed canonicalizations. Recorded per element so the
# transformation from raw fragments to canonical text is always auditable and
# never implicit (spec section 30).
Transformation = Literal[
    "line_join_space",
    "line_break_hyphen_join",
    "cross_page_join",
    "table_cell_join",
]


class BoundingBox(BaseModel):
    """Where a fragment sits on the rendered page, in PDF points.

    Geometry is *additive provenance*: it lets a reviewer see a highlighted
    span on the rendered page instead of trusting a character offset they
    cannot check by eye. It is deliberately never used for identity or for
    text reconstruction — a converter upgrade may legitimately shift a box by
    a fraction of a point, and no stored span may break because of that.

    Optional throughout, because DOCX has no stored pagination and therefore no
    geometry at all (see `ingest_docx`).
    """

    model_config = ConfigDict(extra="ignore")

    left: float
    top: float
    right: float
    bottom: float
    page_width: float | None = None
    page_height: float | None = None
    #: Which corner ``top``/``bottom`` are measured from. PDF-native geometry is
    #: bottom-left origin; most renderers are top-left. Recording it prevents a
    #: silently flipped highlight, which looks like a wrong extraction.
    coord_origin: Literal["top_left", "bottom_left"] = "top_left"


class TableCellRef(BaseModel):
    """A table cell's position and span within its table.

    Merged cells are the reason this exists. A merged header covering three
    columns means the value beneath each of those columns is qualified by it;
    flattening that into prose loses the qualification, and inventing prose to
    express it fabricates source text. Recording the span instead keeps both
    the exact cell text and its true scope.
    """

    model_config = ConfigDict(extra="ignore")

    row_index: int = Field(..., ge=0)
    column_index: int = Field(..., ge=0)
    row_span: int = Field(default=1, ge=1)
    column_span: int = Field(default=1, ge=1)
    is_header: bool = False
    #: Set on every cell covered by a merge to the ``element_id`` of the cell
    #: that owns the merged region, so lineage survives without duplicating text.
    merged_into: str | None = None


class SourceFragment(BaseModel):
    """A contiguous run of characters on one physical page.

    ``text`` is redundant with ``raw_text[start_offset:end_offset]`` by
    construction; it is stored anyway so a fragment stays self-describing in
    logs, API payloads, and test failures without needing the whole page.
    """

    model_config = ConfigDict(extra="ignore")

    page: int = Field(..., description="1-based physical page number.")
    start_offset: int = Field(..., ge=0, description="Inclusive offset into that page's raw_text.")
    end_offset: int = Field(..., ge=0, description="Exclusive offset into that page's raw_text.")
    text: str = Field(..., description="Exact characters at that span.")
    bbox: BoundingBox | None = Field(
        default=None,
        description="Rendered position, when the source format exposes geometry.",
    )


class CanonicalElement(BaseModel):
    """One logical block: a heading, paragraph, list item, or table row.

    An element may span pages — that is the entire point of the canonical
    layer. ``source_fragments`` then carries one entry per page it touches
    (spec section 8), which is what makes cross-page verbatim validation
    possible (spec section 27).
    """

    model_config = ConfigDict(extra="ignore")

    element_id: str = Field(..., description="Stable within a document, e.g. 'E000001'.")
    element_type: ElementType
    logical_order: int = Field(..., ge=0, description="Position in the document's total order.")
    text: str = Field(..., description="Canonical text, derived only from source_fragments.")
    section: str | None = Field(
        default=None,
        description="Heading this element sits under, carried forward until the next heading.",
    )
    source_fragments: list[SourceFragment] = Field(default_factory=list)
    transformations: list[Transformation] = Field(
        default_factory=list,
        description="Deterministic joins applied when building text from fragments.",
    )
    table_id: str | None = Field(
        default=None,
        description="Set on table/table_row elements so rows of one table stay identifiable.",
    )
    table_headers: list[str] | None = Field(
        default=None,
        description="Column headers for a table_row, preserved rather than flattened into prose.",
    )

    # --- Structural lineage (Docling integration, directive Phase 1) --------
    # The legacy parsers emitted a flat, ordered list: structure was implied by
    # position and by `section` alone. That is enough to read a document top to
    # bottom, but not enough to answer "which heading governs this list item",
    # "which table does this row belong to", or "what does this footnote
    # qualify" — all of which the extraction reading plan depends on. These
    # fields carry that structure explicitly so it never has to be re-inferred
    # from prose.

    parent_element_id: str | None = Field(
        default=None,
        description="Structural parent (section for a paragraph, table for a row, list for an item).",
    )
    list_level: int | None = Field(
        default=None,
        ge=0,
        description="0-based nesting depth for list/list_item elements.",
    )
    list_marker: str | None = Field(
        default=None,
        description=(
            "Enumeration label a list item is printed with ('D.', '1.', a bullet glyph). "
            "Held separately from `text` because converters treat it as structure and "
            "strip it, yet reviewers cite clauses by it ('Section 5.D')."
        ),
    )
    list_enumerated: bool | None = Field(
        default=None,
        description=(
            "Whether the marker is an ordered label rather than a bullet. A bullet "
            "identifies nothing, so only enumerated markers are usable in a citation."
        ),
    )
    table_cell: TableCellRef | None = Field(
        default=None,
        description="Position and merge span, set on table_cell elements.",
    )
    caption_for: str | None = Field(
        default=None,
        description="element_id of the table/figure this caption describes.",
    )
    footnote_marker: str | None = Field(
        default=None,
        description="Marker text ('1', '*') linking a footnote to its reference site.",
    )
    references_footnote_ids: list[str] = Field(
        default_factory=list,
        description="element_ids of footnotes whose markers appear in this element.",
    )
    self_ref: str | None = Field(
        default=None,
        description=(
            "Converter-native element reference (Docling '#/texts/57'). Carried so graph "
            "provenance can resolve back to this element. Never used as identity: it is "
            "assigned by output order and would violate the identity gate."
        ),
    )
    normalized_text: str | None = Field(
        default=None,
        description=(
            "Derived comparison/matching form. May be used for embeddings, labels, dedupe "
            "and diffing; must never be substituted for `text` when producing evidence."
        ),
    )

    @property
    def is_non_normative(self) -> bool:
        """True for structural furniture that carries no policy of its own."""

        return self.element_type in NON_NORMATIVE_TYPES

    @property
    def pages(self) -> list[int]:
        """Distinct pages this element touches, in order."""

        seen: list[int] = []
        for fragment in self.source_fragments:
            if fragment.page not in seen:
                seen.append(fragment.page)
        return seen

    @property
    def spans_pages(self) -> bool:
        return len(self.pages) > 1


class CanonicalPage(BaseModel):
    """The raw source representation for one page (spec section 6A).

    Never rewritten after ingestion. Spec section 28 requires exactly one
    authoritative text representation for downstream exact matching; this is
    it. Any later "cleanup" of this string invalidates every offset already
    recorded against it, so it must be treated as immutable.
    """

    model_config = ConfigDict(extra="ignore")

    page: int = Field(..., ge=1)
    raw_text: str
    removed_boilerplate: list[str] = Field(
        default_factory=list,
        description="Header/footer lines dropped from the logical flow but retained here for provenance.",
    )
    visual_order_raw_text: str | None = Field(
        default=None,
        description=(
            "The parser's own output for this page in the order the page paints it, before "
            "reading order was recovered. Present only when the two differ, which happens when "
            "the page contains a run written in a right-to-left script. Recorded so the "
            "recovery stays auditable against the source; raw_text remains the single "
            "authoritative representation and offsets are recorded against it alone."
        ),
    )


class IngestionDiagnostic(BaseModel):
    """A problem observed while ingesting, surfaced rather than swallowed.

    Spec INVARIANT 9: failures cannot silently reduce document coverage. An
    uploaded file can be a scan with no text layer, an encrypted PDF, a
    multi-column layout, or right-to-left script — each of which degrades
    extraction in a way that looks like "the document just had little policy
    content" unless it is reported explicitly.
    """

    model_config = ConfigDict(extra="ignore")

    code: str = Field(..., description="Stable machine-readable identifier, e.g. 'no_text_layer'.")
    severity: Literal["info", "warning", "error"] = "warning"
    page: int | None = None
    detail: str = ""


class ConversionProvenance(BaseModel):
    """Which converter, at which version and configuration, produced a document.

    Directive Phase 1 requires the conversion configuration to be versioned so
    the same source can be reprocessed as a *new* extraction release without
    mutating an older one. Without this, two canonical artifacts built months
    apart are indistinguishable, and a span that no longer resolves cannot be
    explained as "the converter changed" rather than "the evidence was wrong".

    ``config_hash`` is a canonical hash over the effective conversion options,
    so a configuration change is detectable even when versions are unchanged.
    """

    model_config = ConfigDict(extra="ignore")

    converter: str = Field(..., description="Converter identity, e.g. 'docling' or 'pdfplumber'.")
    converter_version: str | None = None
    #: Versions of every dependency whose behaviour can change the output.
    component_versions: dict[str, str] = Field(default_factory=dict)
    config_hash: str | None = Field(
        default=None,
        description="Canonical hash of the effective conversion configuration.",
    )
    #: SHA-256 of the original uploaded bytes. Ties this artifact to exactly one
    #: immutable source release, so a re-upload cannot silently reuse it.
    source_hash: str | None = None


#: How much of the source the converter believes it actually recovered.
#: ``degraded`` means text was obtained but something was lost or uncertain;
#: ``unsupported_source`` means the input has no usable native text layer at
#: all. The directive forbids adding a text-recognition subsystem, so that case
#: must stop explicitly rather than produce a near-empty document that looks
#: like a short policy.
FidelityStatus = Literal["complete", "degraded", "unsupported_source"]


#: Why a recorded fragment does or does not equal the slice its offsets delimit.
#:
#: ``resolved``            the slice is exactly the recorded text.
#: ``span_not_isolating``  every recorded character is present at the declared
#:                         offsets, in order, but interleaved with characters
#:                         belonging to a *different* element. The evidence is
#:                         real and correctly located; a single (start, end)
#:                         pair simply cannot express it. This happens wherever
#:                         a parser emits two adjacent cells' characters in one
#:                         run, which a two-column table does by construction.
#: ``whitespace_only``     the same non-space characters in the same order, but
#:                         the whitespace differs. Treated as a failure: it is a
#:                         real deviation from the source and nothing has yet
#:                         shown it to be harmless.
#: ``text_absent``         characters the fragment claims are not there, or the
#:                         slice contains characters belonging to no element at
#:                         all, meaning content was dropped. A data error.
#: ``page_missing``        the fragment names a page the document does not have.
FragmentResolution = Literal[
    "resolved",
    "span_not_isolating",
    "whitespace_only",
    "text_absent",
    "page_missing",
]

#: The resolutions that mean the recorded text does not resolve to its offsets.
#: ``span_not_isolating`` is deliberately absent: reporting it as a failure is
#: an overclaim, because the text *is* at the offsets given.
UNRESOLVED_FRAGMENT_RESOLUTIONS: frozenset[str] = frozenset(
    {"whitespace_only", "text_absent", "page_missing"}
)


class FragmentFinding(BaseModel):
    """One fragment's verification verdict together with the reason it reached.

    ``verify_fragments`` answers "did this resolve"; this answers "and why
    not", which is the difference between a data error and a limit of the
    two-offset representation. Reporting the second as the first raises an
    error on correctly-ingested content, and an error that fires on healthy
    input trains its reader to ignore it.
    """

    model_config = ConfigDict(extra="ignore")

    element_id: str
    page: int
    start_offset: int
    end_offset: int
    resolution: FragmentResolution
    detail: str = ""

    @property
    def resolves(self) -> bool:
        return self.resolution not in UNRESOLVED_FRAGMENT_RESOLUTIONS


def _classify_fragment_text(
    text: str,
    raw: str,
    start_offset: int,
    end_offset: int,
    element_id: str,
    spans: list[tuple[int, int, str]],
) -> tuple[FragmentResolution, str]:
    """Decide why ``text`` differs from ``raw[start_offset:end_offset]``.

    Two questions are asked, and both must pass before a difference is excused.

    1. Is every non-space character of the recorded text present in the window,
       in order? If not, the fragment claims text the source does not have.
    2. Are the window's remaining characters claimed by a *different* element?
       If not, this fragment silently dropped content.

    Question 2 is what makes the check safe. An ordered-subsequence test alone
    is far too weak to excuse anything: "shall pay" is an ordered subsequence
    of "shall not pay", so a dropped negation would look identical to an
    interleaved table column. Requiring the skipped characters to belong to a
    named neighbour distinguishes them, because dropped content belongs to
    nobody.
    """

    wanted = [character for character in text if not character.isspace()]
    if not wanted:
        return (
            "text_absent",
            "the fragment records no text, but its offsets delimit source characters",
        )

    matched = 0
    skipped: list[int] = []
    for offset in range(start_offset, end_offset):
        character = raw[offset]
        if character.isspace():
            continue
        if matched < len(wanted) and character == wanted[matched]:
            matched += 1
        else:
            skipped.append(offset)

    if matched < len(wanted):
        return (
            "text_absent",
            f"{len(wanted) - matched} of {len(wanted)} recorded characters are not "
            "present at these offsets",
        )

    if not skipped:
        return (
            "whitespace_only",
            "the same characters in the same order, but the whitespace differs",
        )

    neighbours = {
        owner
        for offset in skipped
        for span_start, span_end, owner in spans
        if owner != element_id and span_start <= offset < span_end
    }
    unclaimed = [
        offset
        for offset in skipped
        if not any(
            owner != element_id and span_start <= offset < span_end
            for span_start, span_end, owner in spans
        )
    ]
    if unclaimed:
        return (
            "text_absent",
            f"{len(unclaimed)} source characters between these offsets belong to no "
            "element, so content was dropped rather than shared",
        )

    return (
        "span_not_isolating",
        f"every recorded character is present at these offsets, interleaved with "
        f"{len(skipped)} characters belonging to "
        f"{', '.join(sorted(neighbours))}, so no single span can isolate it",
    )


class CanonicalDocument(BaseModel):
    """A fully ingested document: raw pages plus the ordered logical elements."""

    model_config = ConfigDict(extra="ignore")

    document_id: str
    page_count: int = Field(..., ge=0)
    pages: list[CanonicalPage] = Field(default_factory=list)
    elements: list[CanonicalElement] = Field(default_factory=list)
    parser: str = Field(..., description="Which parser produced the authoritative text.")
    diagnostics: list[IngestionDiagnostic] = Field(default_factory=list)
    conversion: ConversionProvenance | None = Field(
        default=None,
        description="Versioned record of how this artifact was produced.",
    )
    fidelity: FidelityStatus = Field(
        default="complete",
        description="Whether the converter recovered the source completely.",
    )

    def page_text(self, page: int) -> str:
        for candidate in self.pages:
            if candidate.page == page:
                return candidate.raw_text
        raise KeyError(f"page {page} not in document {self.document_id}")

    def element_by_id(self, element_id: str) -> CanonicalElement:
        for element in self.elements:
            if element.element_id == element_id:
                return element
        raise KeyError(f"element {element_id} not in document {self.document_id}")

    @property
    def has_errors(self) -> bool:
        return any(diagnostic.severity == "error" for diagnostic in self.diagnostics)

    def verify_fragments_detailed(self) -> list[FragmentFinding]:
        """Verify every fragment and record *why* each one reached its verdict.

        ``verify_fragments`` reports what failed. This reports what happened,
        including the successes, so a caller can tell a data error from a
        fragment whose evidence is correctly located but shares its character
        range with a neighbouring element.
        """

        by_page = {page.page: page.raw_text for page in self.pages}
        spans_by_page: dict[int, list[tuple[int, int, str]]] = {}
        for element in self.elements:
            for fragment in element.source_fragments:
                spans_by_page.setdefault(fragment.page, []).append(
                    (fragment.start_offset, fragment.end_offset, element.element_id)
                )

        findings: list[FragmentFinding] = []
        for element in self.elements:
            for fragment in element.source_fragments:
                raw = by_page.get(fragment.page)
                if raw is None:
                    findings.append(
                        FragmentFinding(
                            element_id=element.element_id,
                            page=fragment.page,
                            start_offset=fragment.start_offset,
                            end_offset=fragment.end_offset,
                            resolution="page_missing",
                            detail=f"page {fragment.page} is not in this document",
                        )
                    )
                    continue

                if raw[fragment.start_offset : fragment.end_offset] == fragment.text:
                    resolution: FragmentResolution = "resolved"
                    detail = ""
                else:
                    resolution, detail = _classify_fragment_text(
                        fragment.text,
                        raw,
                        fragment.start_offset,
                        fragment.end_offset,
                        element.element_id,
                        spans_by_page.get(fragment.page, []),
                    )

                findings.append(
                    FragmentFinding(
                        element_id=element.element_id,
                        page=fragment.page,
                        start_offset=fragment.start_offset,
                        end_offset=fragment.end_offset,
                        resolution=resolution,
                        detail=detail,
                    )
                )
        return findings

    def fragments_with_shared_spans(self) -> list[FragmentFinding]:
        """Fragments whose evidence is correct but whose span cannot isolate it.

        Not a failure, and deliberately not silent: ``resolve_span`` returns the
        whole slice, so a reviewer following this element's evidence sees the
        neighbouring element's characters mixed in. That is worth reporting and
        is not worth refusing the document over.
        """

        return [
            finding
            for finding in self.verify_fragments_detailed()
            if finding.resolution == "span_not_isolating"
        ]

    def shared_span_diagnostics(self) -> list[IngestionDiagnostic]:
        """Report shared spans so removing the false error does not create silence.

        Severity is ``info``, not ``warning``: nothing is wrong with the
        document or with the extraction. What a reader needs to know is narrower
        and specific — that following one element's evidence link will show a
        neighbouring element's characters too, because the source interleaves
        them and a character range cannot separate them.
        """

        shared = self.fragments_with_shared_spans()
        if not shared:
            return []
        first = shared[0]
        return [
            IngestionDiagnostic(
                code="fragment_span_not_isolating",
                severity="info",
                page=first.page,
                detail=(
                    f"{len(shared)} element(s) share a character range with a neighbour, "
                    "so following their evidence shows both elements' text. The recorded "
                    f"text itself is present and correct at the offsets given. First: "
                    f"{first.element_id} on page {first.page}."
                ),
            )
        ]

    def verify_fragments(self) -> list[str]:
        """Prove every recorded offset resolves to the text it claims.

        This is INVARIANT 4 and INVARIANT 5 checked mechanically rather than
        assumed. It is cheap, so it runs on every ingest: an offset that does
        not resolve makes an unverifiable extraction look verified, which is
        worse than having no provenance at all.

        A fragment whose characters are all present at the offsets given, but
        interleaved with a neighbouring element's, is *not* reported here. Its
        offsets do resolve to its text; what fails is the assumption that a
        character range holds one element's content, which a multi-column table
        breaks by construction. See ``fragments_with_shared_spans``.
        """

        return [
            f"{finding.element_id}: "
            + (
                f"page {finding.page} missing"
                if finding.resolution == "page_missing"
                else (
                    f"offsets {finding.start_offset}:{finding.end_offset} on page "
                    f"{finding.page} do not resolve to the recorded text"
                )
            )
            for finding in self.verify_fragments_detailed()
            if not finding.resolves
        ]


class SpanReference(BaseModel):
    """What the extraction model is allowed to return (spec sections 25, 44).

    The model identifies *where* a policy is, never *what it says* — the
    application then copies the text out of the canonical document itself.
    This is a stronger guarantee than instructing a model to be verbatim and
    checking afterwards: text the model never emits cannot be fabricated.
    """

    model_config = ConfigDict(extra="ignore")

    start_element: str = Field(..., description="element_id where the passage begins.")
    end_element: str = Field(..., description="element_id where the passage ends (inclusive).")
    classification: Literal["POLICY", "POLICY_AMBIGUOUS"] = "POLICY"
    ambiguity_note: str | None = None
    source_quality: str | None = Field(
        default=None,
        description="Flag for OCR damage or truncation observed in the source, never repaired.",
    )
