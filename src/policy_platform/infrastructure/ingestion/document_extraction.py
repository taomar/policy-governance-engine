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


def extract_clauses(storage_path: str, mime_type: str) -> list[ClauseData]:
    """Parse a document into ordered clauses with full source provenance."""

    document = ingest_document(storage_path, mime_type)
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
    into a single string. A penalty matrix whose columns are "1st Time / 2nd
    Time / 3rd Time / 4th Time" therefore arrives downstream as one undivided
    line, and the four distinct decisions it encodes collapse into one. Docling
    emits one element per *cell* with its row index, column index and header
    flag, which is what `structural_graph` turns into `header_for` edges and
    what `reading_plan._add_table_context` uses to tell a reader which column a
    bare value sits under.

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
    """

    if get_settings().document_converter == "docling":
        return _extract_with_docling(
            storage_path,
            document_id=document_id,
            source_hash=source_hash,
            converter=converter,
        )
    # Called exactly as before, with no extra arguments, so selecting the
    # default converter reproduces today's behaviour byte for byte.
    return ingest_document(storage_path, mime_type)


def _extract_with_docling(
    storage_path: str, *, document_id: str, source_hash: str, converter: Any | None
) -> CanonicalDocument:
    """Parse through Docling, failing loudly and diagnosably if it is absent.

    Docling ships in the optional `graph` extra. A runtime that selected it but
    does not have it installed is misconfigured, and the operator needs to be
    told which setting and which environment to look at — an ImportError
    surfacing from three modules down does not say that.
    """

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
