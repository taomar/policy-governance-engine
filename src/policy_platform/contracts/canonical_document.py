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
    "heading",
    "paragraph",
    "list",
    "list_item",
    "table",
    "table_row",
    "caption",
    "footnote",
    "other",
]

# Deterministic, code-performed canonicalizations. Recorded per element so the
# transformation from raw fragments to canonical text is always auditable and
# never implicit (spec section 30).
Transformation = Literal[
    "line_join_space",
    "line_break_hyphen_join",
    "cross_page_join",
    "table_cell_join",
]


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


class CanonicalDocument(BaseModel):
    """A fully ingested document: raw pages plus the ordered logical elements."""

    model_config = ConfigDict(extra="ignore")

    document_id: str
    page_count: int = Field(..., ge=0)
    pages: list[CanonicalPage] = Field(default_factory=list)
    elements: list[CanonicalElement] = Field(default_factory=list)
    parser: str = Field(..., description="Which parser produced the authoritative text.")
    diagnostics: list[IngestionDiagnostic] = Field(default_factory=list)

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

    def verify_fragments(self) -> list[str]:
        """Prove every recorded offset resolves to the text it claims.

        This is INVARIANT 4 and INVARIANT 5 checked mechanically rather than
        assumed. It is cheap, so it runs on every ingest: an offset that does
        not resolve makes an unverifiable extraction look verified, which is
        worse than having no provenance at all.
        """

        failures: list[str] = []
        by_page = {page.page: page.raw_text for page in self.pages}
        for element in self.elements:
            for fragment in element.source_fragments:
                raw = by_page.get(fragment.page)
                if raw is None:
                    failures.append(f"{element.element_id}: page {fragment.page} missing")
                    continue
                if raw[fragment.start_offset : fragment.end_offset] != fragment.text:
                    failures.append(
                        f"{element.element_id}: offsets "
                        f"{fragment.start_offset}:{fragment.end_offset} on page {fragment.page} "
                        "do not resolve to the recorded text"
                    )
        return failures


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
