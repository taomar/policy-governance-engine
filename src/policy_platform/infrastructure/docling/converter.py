"""Docling conversion into the platform's canonical document contract.

This is the narrow boundary the integration directive calls for::

    convert(source_release) -> canonical_document_artifact

WHAT THIS MODULE IS RESPONSIBLE FOR
-----------------------------------
Docling produces a layout-aware document tree. The platform's evidence
guarantee, however, is built on something Docling does not provide: exactly one
authoritative raw-text string per page, with every element addressable as a
character range inside it. That property is what makes `resolve_span` a slice
rather than a search, and what `CanonicalDocument.verify_fragments()` proves.

So this module *constructs* the authoritative text from Docling's items in
reading order, and records each element's offsets into it. The raw text is
therefore derived from Docling's output but owned by the platform, and the
existing invariant holds by construction rather than by alignment: there is no
second text authority and no fuzzy matching between two parsers.

WHY THERE IS NO ALIGNMENT LAYER
-------------------------------
An earlier design considered keeping pdfplumber authoritative and aligning
Docling's chunk offsets onto it. The directive rules this out, and it is also
the more fragile option: two independent text streams that must agree forever
is a permanent source of drift. Building canonical text *from* Docling means
graph provenance resolves through Docling element references directly.

WHAT IT MUST NEVER DO
---------------------
No text is invented, repaired, reordered, or normalized into `text`. Every
canonical element's text is exactly the characters Docling extracted, and every
recorded offset resolves to those characters. Normalization, where useful for
matching, lives in the separate `normalized_text` field.

Table rows are *not* flattened into prose. The legacy DOCX path rendered a row
as "Tier: 2; Limit: 5000" — text that appears nowhere in the source, so any
passage quoted from it was fabricated by construction. Cells keep their exact
values and carry their position and merge span as structured data.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from policy_platform.contracts.canonical import canonical_hash
from policy_platform.contracts.canonical_document import (
    BoundingBox,
    CanonicalDocument,
    CanonicalElement,
    CanonicalPage,
    ConversionProvenance,
    ElementType,
    IngestionDiagnostic,
    SourceFragment,
    TableCellRef,
)
from policy_platform.contracts.element_identity import assign_element_ids

logger = logging.getLogger(__name__)

#: Joiner between elements in the constructed page text. A newline keeps the
#: raw text readable in a reviewer-facing view and makes offsets easy to reason
#: about, while never appearing inside an element's own text.
_ELEMENT_JOINER = "\n"

#: Docling label -> canonical element type. Anything unmapped becomes "other"
#: rather than being dropped: an unknown label is still document content, and
#: silently discarding it would reduce coverage without a diagnostic.
_LABEL_MAP: dict[str, ElementType] = {
    "title": "title",
    "section_header": "heading",
    "paragraph": "paragraph",
    "text": "paragraph",
    "list_item": "list_item",
    "caption": "caption",
    "footnote": "footnote",
    "page_header": "furniture",
    "page_footer": "furniture",
    "formula": "formula",
    "code": "code",
    "reference": "paragraph",
    "checkbox_selected": "paragraph",
    "checkbox_unselected": "paragraph",
}


class DoclingConversionError(RuntimeError):
    """Raised when Docling cannot produce a usable document."""


@dataclass
class _PendingElement:
    """One element before ids and offsets are assigned.

    Identity depends on the whole document (collision resolution needs every
    element), and offsets depend on the final page text, so both are applied in
    a second pass rather than incrementally.
    """

    element_type: ElementType
    text: str
    page: int
    section_path: list[str]
    sibling_index: int
    self_ref: str | None = None
    parent_ref: str | None = None
    list_level: int | None = None
    list_marker: str | None = None
    list_enumerated: bool | None = None
    table_id: str | None = None
    table_headers: list[str] | None = None
    table_cell: TableCellRef | None = None
    bbox: BoundingBox | None = None
    caption_for_ref: str | None = None

    def identity_inputs(self) -> dict[str, Any]:
        """The subset of fields that determine this element's canonical id."""

        inputs: dict[str, Any] = {
            "element_type": self.element_type,
            "text": self.text,
            "section_path": self.section_path,
            "sibling_index": self.sibling_index,
        }
        if self.table_id is not None:
            inputs["table_id"] = self.table_id
        if self.table_cell is not None:
            inputs["row_index"] = self.table_cell.row_index
            inputs["column_index"] = self.table_cell.column_index
        if self.list_level is not None:
            inputs["list_level"] = self.list_level
        return inputs


def _bbox_from_prov(prov: Any, page_size: Any) -> BoundingBox | None:
    """Translate a Docling provenance entry into the canonical geometry shape.

    Returns None rather than raising when geometry is absent or malformed:
    geometry is a reviewer convenience, and losing it must never cost the
    element itself.
    """

    box = getattr(prov, "bbox", None)
    if box is None:
        return None
    try:
        origin = getattr(box, "coord_origin", None)
        origin_name = getattr(origin, "value", None) or str(origin or "")
        return BoundingBox(
            left=float(box.l),
            top=float(box.t),
            right=float(box.r),
            bottom=float(box.b),
            page_width=float(page_size.width) if page_size is not None else None,
            page_height=float(page_size.height) if page_size is not None else None,
            coord_origin=(
                "bottom_left" if "bottom" in origin_name.lower() else "top_left"
            ),
        )
    except (AttributeError, TypeError, ValueError):
        return None


def _page_of(item: Any) -> int:
    """1-based page for an item, defaulting to 1.

    DOCX has no stored pagination — page breaks are decided by the renderer, not
    the file — so the whole document is modelled as one logical page, exactly as
    the legacy DOCX path did. Downstream consumers then need no special case.
    """

    prov = getattr(item, "prov", None) or []
    if prov:
        page_no = getattr(prov[0], "page_no", None)
        if isinstance(page_no, int) and page_no >= 1:
            return page_no
    return 1


def _label_of(item: Any) -> str:
    label = getattr(item, "label", None)
    return getattr(label, "value", None) or str(label or "")


def _collect_text_elements(document: Any) -> list[_PendingElement]:
    """Walk the Docling tree in reading order, building pending elements.

    Section path is carried forward from headings so every element knows which
    heading governs it. That is what later lets identity be structural, and what
    the reading plan uses instead of re-inferring hierarchy from prose.
    """

    pending: list[_PendingElement] = []
    section_path: list[str] = []
    sibling_counts: dict[tuple[str, str], int] = {}
    page_sizes = {no: getattr(page, "size", None) for no, page in (document.pages or {}).items()}

    for item, level in document.iterate_items():
        text = (getattr(item, "text", "") or "").strip()
        self_ref = getattr(item, "self_ref", None)
        label = _label_of(item)

        # Tables are handled separately: their cells carry position and merge
        # span, which a flat text walk would discard.
        if label == "table" or type(item).__name__ == "TableItem":
            continue
        if not text:
            continue

        element_type = _LABEL_MAP.get(label, "other")

        if element_type in ("title", "heading"):
            # `level` is Docling's nesting depth. Truncating to it keeps the
            # path correct when a document returns to a shallower heading.
            del section_path[max(level - 1, 0) :]
            section_path.append(text)
            current_path = list(section_path[:-1])
        else:
            current_path = list(section_path)

        key = ("/".join(current_path), element_type)
        sibling_index = sibling_counts.get(key, 0)
        sibling_counts[key] = sibling_index + 1

        page = _page_of(item)
        prov = (getattr(item, "prov", None) or [None])[0]

        marker = getattr(item, "marker", None)
        pending.append(
            _PendingElement(
                element_type=element_type,
                text=text,
                page=page,
                section_path=current_path,
                sibling_index=sibling_index,
                self_ref=self_ref,
                list_level=(level if element_type == "list_item" else None),
                list_marker=(str(marker) if element_type == "list_item" and marker else None),
                list_enumerated=(
                    bool(getattr(item, "enumerated", False))
                    if element_type == "list_item"
                    else None
                ),
                bbox=_bbox_from_prov(prov, page_sizes.get(page)) if prov is not None else None,
            )
        )

    return pending


def _collect_table_elements(document: Any) -> list[_PendingElement]:
    """Emit one element per table cell, preserving position and merge span.

    A cell is the smallest unit whose text is genuinely verbatim. Emitting rows
    as joined prose would create text that is not in the document; emitting only
    the table would make a single rule's evidence the entire grid.
    """

    pending: list[_PendingElement] = []
    page_sizes = {no: getattr(page, "size", None) for no, page in (document.pages or {}).items()}

    for table_index, table in enumerate(document.tables or []):
        table_id = getattr(table, "self_ref", None) or f"#/tables/{table_index}"
        data = getattr(table, "data", None)
        if data is None:
            continue

        page = _page_of(table)
        prov = (getattr(table, "prov", None) or [None])[0]
        bbox = _bbox_from_prov(prov, page_sizes.get(page)) if prov is not None else None

        headers_by_column: dict[int, str] = {}
        for cell in getattr(data, "table_cells", []) or []:
            if getattr(cell, "column_header", False):
                headers_by_column[int(cell.start_col_offset_idx)] = (cell.text or "").strip()

        ordered_headers = [headers_by_column[k] for k in sorted(headers_by_column)]

        for cell in getattr(data, "table_cells", []) or []:
            text = (getattr(cell, "text", "") or "").strip()
            if not text:
                continue
            row_index = int(cell.start_row_offset_idx)
            column_index = int(cell.start_col_offset_idx)
            pending.append(
                _PendingElement(
                    element_type="table_cell",
                    text=text,
                    page=page,
                    section_path=[],
                    sibling_index=0,
                    self_ref=f"{table_id}/cell/{row_index}/{column_index}",
                    table_id=table_id,
                    table_headers=ordered_headers or None,
                    table_cell=TableCellRef(
                        row_index=row_index,
                        column_index=column_index,
                        row_span=int(getattr(cell, "row_span", 1) or 1),
                        column_span=int(getattr(cell, "col_span", 1) or 1),
                        is_header=bool(getattr(cell, "column_header", False)),
                    ),
                    bbox=bbox,
                )
            )

    return pending


def _build_pages(
    pending: list[_PendingElement],
) -> tuple[list[CanonicalPage], dict[int, list[tuple[int, int]]]]:
    """Construct authoritative page text and each element's offsets into it.

    This is the step that makes the platform's evidence guarantee hold by
    construction: an element's recorded range always slices back to its exact
    text, because the text was written into the page at that range.
    """

    by_page: dict[int, list[int]] = {}
    for index, element in enumerate(pending):
        by_page.setdefault(element.page, []).append(index)

    pages: list[CanonicalPage] = []
    offsets: dict[int, list[tuple[int, int]]] = {}

    for page_no in sorted(by_page):
        parts: list[str] = []
        cursor = 0
        for index in by_page[page_no]:
            text = pending[index].text
            start = cursor
            end = start + len(text)
            offsets[index] = [(start, end)]
            parts.append(text)
            cursor = end + len(_ELEMENT_JOINER)
        pages.append(CanonicalPage(page=page_no, raw_text=_ELEMENT_JOINER.join(parts)))

    return pages, offsets


#: A lowercase letter immediately followed by an uppercase one, where neither is
#: part of a longer run of capitals. Deliberately narrow: it must not fire on
#: legitimate compounds the document actually prints ("PolicyID", "eCommerce").
_SUSPECT_JOIN_RE = re.compile(r"(?<![A-Z])[a-z]{2,}[A-Z][a-z]{2,}")


def detect_join_anomalies(document: CanonicalDocument) -> list[IngestionDiagnostic]:
    """Report words that look like two words joined without a space.

    Docling occasionally concatenates across a line break with no separator,
    producing tokens such as ``SafetyAct`` where the source printed "Safety Act"
    on two lines. Three such tokens were observed in ~2,490 on a 53-page PDF.

    This is *reported, never repaired*. Inserting a space would rewrite the
    canonical text, which is the one thing INVARIANT 6 forbids: every character
    of an element must come from the source. A reviewer seeing the diagnostic
    can judge it; a silently "fixed" string cannot be audited at all, and the
    same heuristic would eventually corrupt a legitimate compound.
    """

    diagnostics: list[IngestionDiagnostic] = []
    for element in document.elements:
        suspects = _SUSPECT_JOIN_RE.findall(element.text)
        if not suspects:
            continue
        fragment = element.source_fragments[0] if element.source_fragments else None
        diagnostics.append(
            IngestionDiagnostic(
                code="suspected_missing_space",
                severity="info",
                page=fragment.page if fragment else None,
                detail=(
                    f"{element.element_id}: {sorted(set(suspects))[:5]} may be words joined "
                    "without a space at a line break; text is left exactly as extracted"
                ),
            )
        )
    return diagnostics


def convert_document(
    storage_path: str | Path,
    *,
    document_id: str = "",
    source_hash: str = "",
    converter: Any | None = None,
) -> CanonicalDocument:
    """Convert one source release into a canonical document artifact.

    `source_hash` is the SHA-256 of the uploaded bytes and is the identity
    namespace for every element id, so the same sentence in two documents never
    collides. It is required in practice; an empty value is accepted only so
    tests can build fixtures without a stored file.
    """

    path = Path(storage_path)
    if converter is None:  # pragma: no cover - exercised via integration runs
        from docling.document_converter import DocumentConverter

        converter = DocumentConverter()

    try:
        result = converter.convert(str(path))
    except Exception as exc:  # noqa: BLE001 - surfaced as a typed platform error
        raise DoclingConversionError(f"cannot convert {path.name}: {exc}") from exc

    document = getattr(result, "document", None)
    if document is None:
        raise DoclingConversionError(f"conversion of {path.name} produced no document")

    pending = _collect_text_elements(document) + _collect_table_elements(document)

    diagnostics: list[IngestionDiagnostic] = []
    if not pending:
        # The directive forbids adding a text-recognition subsystem, so a source
        # with no usable native text layer must stop explicitly rather than look
        # like a short policy document.
        diagnostics.append(
            IngestionDiagnostic(
                code="unsupported_source",
                severity="error",
                detail=(
                    "no native text layer was recovered; image-only sources are not supported"
                ),
            )
        )

    element_ids, collisions = assign_element_ids(
        source_hash or path.name, [p.identity_inputs() for p in pending]
    )
    for collision in collisions:
        diagnostics.append(
            IngestionDiagnostic(code="duplicate_element", severity="info", detail=collision)
        )

    pages, offsets = _build_pages(pending)
    ref_to_id = {p.self_ref: element_ids[i] for i, p in enumerate(pending) if p.self_ref}

    elements: list[CanonicalElement] = []
    for index, item in enumerate(pending):
        start, end = offsets[index][0]
        elements.append(
            CanonicalElement(
                element_id=element_ids[index],
                element_type=item.element_type,
                logical_order=index,
                text=item.text,
                section=(item.section_path[-1] if item.section_path else None),
                source_fragments=[
                    SourceFragment(
                        page=item.page,
                        start_offset=start,
                        end_offset=end,
                        text=item.text,
                        bbox=item.bbox,
                    )
                ],
                table_id=item.table_id,
                table_headers=item.table_headers,
                table_cell=item.table_cell,
                list_level=item.list_level,
                list_marker=item.list_marker,
                list_enumerated=item.list_enumerated,
                self_ref=item.self_ref,
                parent_element_id=ref_to_id.get(item.parent_ref) if item.parent_ref else None,
                caption_for=ref_to_id.get(item.caption_for_ref) if item.caption_for_ref else None,
            )
        )

    canonical = CanonicalDocument(
        document_id=document_id or path.stem,
        page_count=len(pages),
        pages=pages,
        elements=elements,
        parser="docling",
        diagnostics=diagnostics,
        conversion=_provenance(source_hash),
        fidelity="unsupported_source" if not pending else "complete",
    )

    # Reported after the document exists so each diagnostic can name the element
    # it concerns. Never repaired: rewriting the text to "fix" a join would
    # violate the rule that every character comes from the source.
    canonical.diagnostics.extend(detect_join_anomalies(canonical))

    # Cheap, and the failure it catches is the dangerous kind: an offset that
    # does not resolve makes an unverifiable extraction look verified.
    failures = canonical.verify_fragments()
    if failures:
        raise DoclingConversionError(
            f"canonical fragments do not resolve for {path.name}: {failures[:3]}"
        )

    return canonical


def _provenance(source_hash: str) -> ConversionProvenance:
    """Record which converter version and configuration produced an artifact."""

    versions = _component_versions()
    return ConversionProvenance(
        converter="docling",
        converter_version=versions.get("docling"),
        component_versions=versions,
        config_hash=canonical_hash(
            {"element_joiner": _ELEMENT_JOINER, "label_map": dict(sorted(_LABEL_MAP.items()))}
        ),
        source_hash=source_hash or None,
    )


def _component_versions() -> dict[str, str]:
    from importlib import metadata

    versions: dict[str, str] = {}
    for name in ("docling", "docling-core", "docling-slim", "docling-graph"):
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            continue
    return versions
