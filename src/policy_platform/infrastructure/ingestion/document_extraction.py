"""Adapter from canonical document ingestion to the `Clause` persistence shape.

The parsing itself lives in `document_ingestion`, which builds a canonical
representation with cross-page reconstruction and exact source offsets. This
module exists only to project that representation onto the `ClauseData` shape
the upload route and repositories already speak, so the ingestion rework did
not have to ripple through the API layer.

WHY THE OLD IMPLEMENTATION WAS REPLACED
---------------------------------------
It parsed page by page and emitted paragraphs scoped to a single page, falling
back to fixed four-line groups when a page had no blank-line breaks. Both
choices turned a physical page boundary into a semantic one, so a rule could be
separated from its exception and a condition from its consequence before the
extractor ever saw them. It also rendered DOCX table rows as prose
("Tier: 2; Limit: 5000") — text that appears nowhere in the source, which meant
any passage quoted from a table was fabricated by construction.

One `ClauseData` is emitted per canonical element. A clause therefore now
corresponds to a logical unit a reader would recognise (a paragraph, a list
item, a table row) rather than to an artifact of pagination.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import sys
import unicodedata
from typing import Any

from policy_platform.contracts.canonical_document import (
    CanonicalDocument,
    IngestionDiagnostic,
    SourceFragment,
)
from policy_platform.infrastructure.ingestion.document_ingestion import (  # noqa: F401 - re-exported
    IngestionError,
    ingest_document,
)
from policy_platform.infrastructure.settings import get_settings


@dataclass
class ClauseData:
    clause_ref: str
    section: str | None
    page: int | None
    text: str
    element_id: str | None = None
    element_type: str | None = None
    source_fragments: list[dict] = field(default_factory=list)


def extract_clauses(
    storage_path: str,
    mime_type: str,
    *,
    document_id: str = "",
    source_hash: str = "",
) -> list[ClauseData]:
    """Parse a document into ordered clauses with full source provenance.

    Routes through `extract_document` rather than calling the legacy parser
    directly. It used to call `ingest_document`, which meant it walked around
    the one seam that decides how an upload is parsed: a caller reaching for
    this helper got the legacy parser no matter what the converter setting
    said, and nothing told them so. A second extraction path that ignores the
    setting is how the original defect spread, so there is no longer one.
    """

    document = extract_document(
        storage_path,
        mime_type,
        document_id=document_id,
        source_hash=source_hash,
    )
    return clauses_from_document(document)


def extract_document(
    storage_path: str,
    mime_type: str,
    *,
    document_id: str = "",
    source_hash: str = "",
    converter: Any | None = None,
) -> CanonicalDocument:
    """Return the full canonical document, for callers that need offsets/diagnostics.

    This is the one seam where the platform decides *how* an upload is parsed,
    so the converter choice lives here rather than in the route.

    WHY THIS IS SELECTABLE
    ----------------------
    The legacy parser emits one element per table row with the cells pipe-joined
    into a single string, so every value in a row arrives downstream as one
    undivided line and the distinct facts they encode become indistinguishable.
    Docling emits one element per *cell* with its row index, column index and
    header flag, which is what `structural_graph` turns into `header_for` edges
    and what `reading_plan._add_table_context` uses to tell a reader which
    column a bare value sits under.

    `source_hash` is the SHA-256 of the uploaded bytes and namespaces element
    ids, so the same sentence in two documents never collides. Callers on the
    structured path must pass the real hash.

    `converter` injects a Docling document converter, so a test can pin this
    seam's behaviour without a multi-minute layout-model run. It is ignored on
    the legacy path, which has no such dependency.

    NO SILENT FALLBACK
    ------------------
    If Docling is selected but cannot be imported or cannot convert, this
    raises. Quietly reverting to the legacy parser would downgrade a structured
    parse to a flattened one without anybody being told — the same invisible
    downgrade this seam exists to end.

    TEXT FIDELITY IS CHECKED FOR BOTH
    ---------------------------------
    Whichever converter runs, the result is checked for text captured as display
    glyphs rather than characters (see `detect_display_glyphs`) and a diagnostic
    is appended when it is found. Extraction itself is untouched by this: the
    elements and their text are exactly what the converter produced. The only
    difference is that a document with the defect now says so.
    """

    if get_settings().document_converter == "docling":
        document = _extract_with_docling(
            storage_path,
            document_id=document_id,
            source_hash=source_hash,
            converter=converter,
        )
    else:
        # Called exactly as before, with no extra arguments, so selecting the
        # default converter reproduces today's extraction byte for byte.
        document = ingest_document(storage_path, mime_type)

    # Checked here rather than in either parser: it is a property of the
    # extracted text, not of the thing that extracted it, and both converters
    # have been observed to produce it. One implementation at the seam means
    # neither path can be fixed while the other silently is not.
    glyphs = detect_display_glyphs(document)
    if glyphs is not None:
        document.diagnostics.append(glyphs)
    return document


#: Unicode decomposition tags that mark a codepoint as a *shaped form* of some
#: other character — the glyph a renderer chooses for a letter given its
#: neighbours, rather than the letter itself.
#:
#: This is read from the Unicode character database, so it is a statement about
#: codepoints and nothing else. There is deliberately no script list, no
#: language detection and no direction check: any script whose letters have
#: positional forms is covered the day Unicode says so, and a document in a
#: script that has none can never trip it.
_DISPLAY_GLYPH_TAGS = ("<isolated>", "<initial>", "<medial>", "<final>")


def _is_display_glyph(char: str) -> bool:
    return unicodedata.decomposition(char).startswith(_DISPLAY_GLYPH_TAGS)


def detect_display_glyphs(document: CanonicalDocument) -> IngestionDiagnostic | None:
    """Report text captured as display glyphs rather than as characters.

    Some extractors read a PDF's painted glyph stream and record what was drawn
    instead of what was written. The result still looks right to a human reading
    the rendered page, because the glyphs are the same ones the renderer chose —
    but the stored codepoints are presentation forms, not the characters the
    document contains, and the platform's promise that an attribute holds the
    source's words verbatim is quietly untrue for every such run.

    It is worse than an ordinary parse problem because it is invisible to the
    checks that would normally catch it: a verbatim comparison between a record
    and the canonical store compares one rendering against the same rendering
    and reports a match. Only a check against the *source's characters* can see
    it, which is why this fires at ingestion rather than at review.

    DETECTION, NOT REPAIR
    ---------------------
    Nothing is normalised, reordered or rewritten. A stored value that reads
    oddly is a defect a reviewer can see and weigh; a stored value silently
    rewritten into something the document does not literally contain is a defect
    nobody can see, and this product must never alter the words it attributes to
    a source. So this reports scale and location and stops there.

    Returns ``None`` when the document is clean, so a caller can append only
    when there is something to say.
    """

    affected_pages: set[int] = set()
    glyphs = 0
    letters = 0
    for element in document.elements:
        found = False
        for char in element.text:
            if char.isalpha():
                letters += 1
            if _is_display_glyph(char):
                glyphs += 1
                found = True
        if found:
            affected_pages.update(
                fragment.page
                for fragment in element.source_fragments
                if isinstance(fragment, SourceFragment)
            )

    if not glyphs:
        return None

    # Proportion of letters, so the figure means "how much of the writing is
    # affected" rather than being diluted by punctuation and whitespace.
    share = f"{glyphs / letters:.1%}" if letters else "unknown"
    pages = sorted(affected_pages)
    where = f"pages {pages[:20]}" if pages else "page numbers unavailable"
    return IngestionDiagnostic(
        code="display_glyphs_not_characters",
        # The document is usable and its structure is sound; what is not sound
        # is any claim that a quoted span reproduces the source's characters.
        severity="warning",
        detail=(
            f"{glyphs} characters ({share} of letters) are Unicode presentation forms — "
            f"display glyphs recorded in place of the characters they render ({where}). "
            "Text quoted from these regions reproduces how the document was drawn, not "
            "what it says, so a verbatim check against this text compares a rendering "
            "with itself and cannot detect the difference. No normalisation or "
            "reordering was applied: rewriting quoted text would replace a defect a "
            "reviewer can see with one nobody can."
        ),
    )


def _extract_with_docling(
    storage_path: str, *, document_id: str, source_hash: str, converter: Any | None
) -> CanonicalDocument:
    """Parse through Docling, failing loudly and diagnosably if it is absent.

    Docling ships in the optional `graph` extra. A runtime that selected it but
    does not have it installed is misconfigured, and the operator needs to be
    told which setting and which environment to look at — an ImportError
    surfacing from three modules down does not say that.

    An empty `source_hash` is refused for the same reason. Element ids are
    namespaced by it so that the same sentence in two documents never collides;
    an empty namespace puts every document in one bucket and the collision is
    silent, surfacing later as one document's element resolving to another's.
    A caller that has not been given the real hash is better stopped here.
    """

    if not source_hash:
        raise IngestionError(
            "the structured converter needs the document's source hash: element "
            "ids are namespaced by it, so extracting with an empty hash lets "
            "elements from different documents collide. Pass the SHA-256 of the "
            "uploaded bytes."
        )

    try:
        from policy_platform.infrastructure.docling.converter import convert_document
    except ImportError as exc:  # pragma: no cover - depends on the installed extra
        raise IngestionError(
            "DOCUMENT_CONVERTER=docling is selected but the Docling stack is not "
            f"importable in this interpreter ({sys.executable}): {exc}. Install the "
            "optional extra (`pip install -e .[graph]`) or set DOCUMENT_CONVERTER=legacy. "
            "Falling back to the legacy parser silently is deliberately not done: it "
            "would flatten table cells into rows without anyone being told."
        ) from exc

    return convert_document(
        storage_path,
        document_id=document_id,
        source_hash=source_hash,
        converter=converter,
    )


def clauses_from_document(document: CanonicalDocument) -> list[ClauseData]:
    clauses: list[ClauseData] = []
    for element in document.elements:
        clauses.append(
            ClauseData(
                clause_ref=_clause_ref(element.element_id, element.source_fragments),
                section=element.section,
                page=element.source_fragments[0].page if element.source_fragments else None,
                text=element.text,
                element_id=element.element_id,
                element_type=element.element_type,
                source_fragments=[fragment.model_dump() for fragment in element.source_fragments],
            )
        )
    return clauses


def _clause_ref(element_id: str, fragments: list[SourceFragment]) -> str:
    """A human-readable reference that still identifies exactly one element.

    Reviewers cite clauses to each other, so the reference needs to carry a page
    a reader can turn to. The element id is kept as the suffix because a page
    number alone is not unique, and spec section 25 requires an extraction to be
    identified by position rather than by its text.
    """

    if not fragments:
        return element_id
    pages = sorted({fragment.page for fragment in fragments})
    if len(pages) == 1:
        return f"p{pages[0]}-{element_id}"
    return f"p{pages[0]}-{pages[-1]}-{element_id}"


def ingestion_warnings(document: CanonicalDocument) -> list[IngestionDiagnostic]:
    return [d for d in document.diagnostics if d.severity in ("warning", "error")]
