"""Tests for the Docling → canonical document conversion boundary.

The invariants under test are the ones that make evidence trustworthy:

* every recorded offset slices back to exactly the text it claims;
* no text is invented, and table rows are never flattened into prose;
* identity is derived from content and structure, not from output order;
* a source with no usable text layer stops explicitly instead of looking like
  a short policy document.

Most tests drive a stub Docling document so they run in milliseconds and
without the optional dependency. Two integration tests run the real converter
against the sample DOCX files and are skipped when the extra is absent.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from importlib import metadata
from pathlib import Path

import pytest

from policy_platform.contracts.element_identity import is_valid_element_id
from policy_platform.infrastructure.docling.converter import (
    DoclingConversionError,
    convert_document,
)

SOURCE_HASH = "c" * 64
SAMPLES = Path(__file__).resolve().parents[2] / "samples" / "source-documents"


# --------------------------------------------------------------------------
# Stub Docling document
# --------------------------------------------------------------------------


@dataclass
class _Bbox:
    l: float = 10.0  # noqa: E741 - mirrors Docling's attribute name
    t: float = 100.0
    r: float = 200.0
    b: float = 80.0
    coord_origin: str = "BOTTOMLEFT"


@dataclass
class _Prov:
    page_no: int = 1
    bbox: _Bbox | None = field(default_factory=_Bbox)


@dataclass
class _Text:
    text: str
    label: str = "text"
    self_ref: str = "#/texts/0"
    prov: list[_Prov] = field(default_factory=list)


@dataclass
class _Cell:
    text: str
    start_row_offset_idx: int
    start_col_offset_idx: int
    row_span: int = 1
    col_span: int = 1
    column_header: bool = False


@dataclass
class _TableData:
    table_cells: list[_Cell]


@dataclass
class _Table:
    data: _TableData
    self_ref: str = "#/tables/0"
    prov: list[_Prov] = field(default_factory=list)
    label: str = "table"


@dataclass
class _Size:
    width: float = 612.0
    height: float = 792.0


@dataclass
class _Page:
    size: _Size = field(default_factory=_Size)


class _StubDocument:
    def __init__(
        self,
        texts: list[_Text],
        tables: list[_Table] | None = None,
        pages: dict[int, _Page] | None = None,
        levels: list[int] | None = None,
    ) -> None:
        self.texts = texts
        self.tables = tables or []
        self.pages = pages or {}
        self._levels = levels or [1] * len(texts)

    def iterate_items(self):
        for item, level in zip(self.texts, self._levels):
            yield item, level


class _StubConverter:
    def __init__(self, document: _StubDocument) -> None:
        self._document = document

    def convert(self, _source: str):
        return type("Result", (), {"document": self._document})()


def _convert(document: _StubDocument, **kwargs):
    return convert_document(
        "fixture.docx",
        source_hash=SOURCE_HASH,
        converter=_StubConverter(document),
        **kwargs,
    )


# --------------------------------------------------------------------------


class TestOffsetIntegrity:
    def test_every_fragment_resolves(self) -> None:
        """The invariant the whole evidence chain rests on."""

        document = _convert(
            _StubDocument(
                [
                    _Text("Policy Title", label="title", self_ref="#/texts/0"),
                    _Text("Employees must apply in writing.", self_ref="#/texts/1"),
                    _Text("Approval is required.", self_ref="#/texts/2"),
                ]
            )
        )
        assert document.verify_fragments() == []

    def test_offsets_slice_back_to_element_text(self) -> None:
        document = _convert(
            _StubDocument([_Text("First clause."), _Text("Second, longer clause here.")])
        )
        for element in document.elements:
            fragment = element.source_fragments[0]
            page_text = document.page_text(fragment.page)
            assert page_text[fragment.start_offset : fragment.end_offset] == element.text

    def test_unicode_text_offsets_resolve(self) -> None:
        """Multi-byte characters must not desynchronise character offsets."""

        document = _convert(
            _StubDocument([_Text("Übergabe erfolgt — nach §5 Abs. 2."), _Text("Naïve café façade.")])
        )
        assert document.verify_fragments() == []


class TestNoFabrication:
    def test_table_cells_keep_verbatim_text(self) -> None:
        """The legacy DOCX path rendered rows as "Tier: 2; Limit: 5000".

        That text appears nowhere in the source, so any passage quoted from it
        was fabricated by construction. Cells must stay verbatim.
        """

        table = _Table(
            _TableData(
                [
                    _Cell("Tier", 0, 0, column_header=True),
                    _Cell("Limit", 0, 1, column_header=True),
                    _Cell("2", 1, 0),
                    _Cell("5000", 1, 1),
                ]
            )
        )
        document = _convert(_StubDocument([], tables=[table]))
        texts = [e.text for e in document.elements]

        assert texts == ["Tier", "Limit", "2", "5000"]
        assert not any(";" in t for t in texts)
        assert document.verify_fragments() == []

    def test_table_cell_carries_position_and_headers(self) -> None:
        """Meaning that used to be flattened into prose is kept structurally."""

        table = _Table(
            _TableData(
                [
                    _Cell("Severity", 0, 0, column_header=True),
                    _Cell("SLA", 0, 1, column_header=True),
                    _Cell("P1", 1, 0),
                    _Cell("15 minutes", 1, 1),
                ]
            )
        )
        document = _convert(_StubDocument([], tables=[table]))
        sla = next(e for e in document.elements if e.text == "15 minutes")

        assert sla.table_cell is not None
        assert (sla.table_cell.row_index, sla.table_cell.column_index) == (1, 1)
        assert sla.table_cell.is_header is False
        assert sla.table_headers == ["Severity", "SLA"]

    def test_merged_cell_span_is_preserved(self) -> None:
        """A header spanning three columns qualifies all three."""

        table = _Table(
            _TableData([_Cell("Approval limits", 0, 0, col_span=3, column_header=True)])
        )
        document = _convert(_StubDocument([], tables=[table]))
        header = document.elements[0]

        assert header.table_cell is not None
        assert header.table_cell.column_span == 3

    def test_element_text_is_never_rewritten(self) -> None:
        source = "  Employees  must   apply.  "
        document = _convert(_StubDocument([_Text(source)]))
        assert document.elements[0].text == source.strip()
        assert document.elements[0].normalized_text is None


class TestIdentity:
    def test_ids_are_content_derived(self) -> None:
        document = _convert(_StubDocument([_Text("A clause."), _Text("Another clause.")]))
        assert all(is_valid_element_id(e.element_id) for e in document.elements)

    def test_inserting_an_element_does_not_shift_others(self) -> None:
        """The defect the ordinal scheme caused, verified at converter level."""

        before = _convert(_StubDocument([_Text("First."), _Text("Second.")]))
        after = _convert(
            _StubDocument(
                [
                    _Text("First."),
                    _Text("Newly detected header.", label="section_header"),
                    _Text("Second."),
                ],
                levels=[1, 1, 1],
            )
        )
        assert before.elements[0].element_id == after.elements[0].element_id

    def test_docling_self_ref_is_recorded_but_not_used_as_identity(self) -> None:
        """`self_ref` is assigned by output order and would violate the gate.

        It is still carried, because graph provenance resolves through it — but
        two elements whose only difference is their `self_ref` must share an
        identity, proving the reference plays no part in deriving it.
        """

        first = _convert(_StubDocument([_Text("A clause.", self_ref="#/texts/7")]))
        second = _convert(_StubDocument([_Text("A clause.", self_ref="#/texts/99")]))

        assert first.elements[0].self_ref == "#/texts/7"
        assert second.elements[0].self_ref == "#/texts/99"
        assert first.elements[0].element_id == second.elements[0].element_id

    def test_identical_repeated_cells_stay_distinct(self) -> None:
        table = _Table(
            _TableData([_Cell("N/A", 1, 0), _Cell("N/A", 2, 0), _Cell("N/A", 3, 0)])
        )
        document = _convert(_StubDocument([], tables=[table]))
        ids = [e.element_id for e in document.elements]
        assert len(set(ids)) == 3


class TestStructure:
    def test_section_is_carried_forward_from_headings(self) -> None:
        document = _convert(
            _StubDocument(
                [
                    _Text("2. Leave", label="section_header"),
                    _Text("Employees may take leave."),
                    _Text("Approval is required."),
                ],
                levels=[1, 1, 1],
            )
        )
        paragraphs = [e for e in document.elements if e.element_type == "paragraph"]
        assert all(p.section == "2. Leave" for p in paragraphs)

    def test_page_headers_are_classified_as_furniture(self) -> None:
        """Furniture must be identifiable so it can receive a deliberate
        coverage disposition rather than looking like an unexplained gap."""

        document = _convert(
            _StubDocument([_Text("Confidential", label="page_header"), _Text("A clause.")])
        )
        furniture = [e for e in document.elements if e.element_type == "furniture"]
        assert len(furniture) == 1
        assert furniture[0].is_non_normative

    def test_unknown_labels_are_kept_as_other_not_dropped(self) -> None:
        """Dropping unrecognised content would reduce coverage silently."""

        document = _convert(_StubDocument([_Text("Odd content", label="some_new_label")]))
        assert len(document.elements) == 1
        assert document.elements[0].element_type == "other"

    def test_bottom_left_geometry_is_recorded_faithfully(self) -> None:
        """A silently flipped highlight looks like a wrong extraction."""

        document = _convert(
            _StubDocument(
                [_Text("A clause.", prov=[_Prov(page_no=1)])],
                pages={1: _Page()},
            )
        )
        bbox = document.elements[0].source_fragments[0].bbox
        assert bbox is not None
        assert bbox.coord_origin == "bottom_left"
        assert bbox.page_width == 612.0


class TestFailureModes:
    def test_document_with_no_text_layer_is_flagged_unsupported(self) -> None:
        """The directive forbids adding OCR, so this must stop explicitly."""

        document = _convert(_StubDocument([]))
        assert document.fidelity == "unsupported_source"
        codes = {d.code for d in document.diagnostics}
        assert "unsupported_source" in codes
        assert document.has_errors

    def test_converter_failure_is_raised_as_platform_error(self) -> None:
        class _Failing:
            def convert(self, _source: str):
                raise ValueError("backend exploded")

        with pytest.raises(DoclingConversionError):
            convert_document("x.docx", source_hash=SOURCE_HASH, converter=_Failing())

    def test_missing_document_is_raised(self) -> None:
        class _Empty:
            def convert(self, _source: str):
                return type("Result", (), {"document": None})()

        with pytest.raises(DoclingConversionError):
            convert_document("x.docx", source_hash=SOURCE_HASH, converter=_Empty())


class TestProvenance:
    def test_conversion_provenance_is_recorded(self) -> None:
        document = _convert(_StubDocument([_Text("A clause.")]))
        assert document.conversion is not None
        assert document.conversion.converter == "docling"
        assert document.conversion.source_hash == SOURCE_HASH
        assert document.conversion.config_hash

    def test_config_hash_changes_when_configuration_changes(self) -> None:
        """A configuration change must be detectable even at the same version."""

        from policy_platform.infrastructure.docling import converter as module

        first = _convert(_StubDocument([_Text("A clause.")])).conversion
        original = module._LABEL_MAP["text"]
        module._LABEL_MAP["text"] = "other"
        try:
            second = _convert(_StubDocument([_Text("A clause.")])).conversion
        finally:
            module._LABEL_MAP["text"] = original

        assert first is not None and second is not None
        assert first.config_hash != second.config_hash


# --------------------------------------------------------------------------
# Integration against the real sample documents
# --------------------------------------------------------------------------


def _docling_installed() -> bool:
    try:
        metadata.distribution("docling")
    except metadata.PackageNotFoundError:
        return False
    return True


requires_docling = pytest.mark.skipif(
    not _docling_installed(), reason="optional 'graph' extra (docling) is not installed"
)


@requires_docling
@pytest.mark.parametrize(
    "filename",
    [
        "HR-Special-Leave-Policy-v1.0.docx",
        "IT-Security-Incident-Emergency-Access-Policy-v1.0.docx",
    ],
)
def test_real_documents_convert_with_resolvable_spans(filename: str) -> None:
    """End-to-end proof on the documents the directive names as fixtures."""

    document = convert_document(SAMPLES / filename, source_hash=SOURCE_HASH)

    assert document.verify_fragments() == []
    assert document.fidelity == "complete"
    assert len(document.elements) > 10
    assert all(is_valid_element_id(e.element_id) for e in document.elements)
    for element in document.elements:
        fragment = element.source_fragments[0]
        assert (
            document.page_text(fragment.page)[fragment.start_offset : fragment.end_offset]
            == element.text
        )


@requires_docling
def test_real_table_cells_are_not_flattened() -> None:
    document = convert_document(
        SAMPLES / "IT-Security-Incident-Emergency-Access-Policy-v1.0.docx",
        source_hash=SOURCE_HASH,
    )
    cells = [e for e in document.elements if e.element_type == "table_cell"]

    assert cells, "expected the severity table to produce cell elements"
    assert any(c.table_cell and c.table_cell.is_header for c in cells)
    assert all(c.table_headers for c in cells)


@requires_docling
def test_conversion_is_reproducible() -> None:
    """Same bytes plus same configuration must give the same identities.

    Without this, a re-ingest would look like a wholesale policy change.
    """

    path = SAMPLES / "HR-Special-Leave-Policy-v1.0.docx"
    first = convert_document(path, source_hash=SOURCE_HASH)
    second = convert_document(path, source_hash=SOURCE_HASH)

    assert [e.element_id for e in first.elements] == [e.element_id for e in second.elements]
    assert [p.raw_text for p in first.pages] == [p.raw_text for p in second.pages]
