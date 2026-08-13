"""Guard: the upload seam must be able to keep table cells intact.

WHAT THIS PROTECTS
------------------
`document_extraction.extract_document` is the only place the platform decides
how an uploaded file becomes canonical elements, and for a long time it had no
decision to make: it called the legacy parser unconditionally, so the converter
that preserves cell structure — and every downstream stage built on it — was
unreachable in production.

The invariant these tests enforce is a general one, and it is worth stating
plainly because it is the whole reason cell-level parsing exists:

    A cell in a table means nothing on its own. "15 minutes", "denied", "£500"
    are values whose meaning lives in the column header above them and the row
    they sit in. So a parse that keeps cells must keep the *association* too,
    and that association must survive all the way to what the model reads.

Concretely, for a table of any shape: every body cell is emitted as its own
element carrying its row index, column index and header flag; the structural
graph links it to the header cell in its own column; and the reading plan hands
the model that header alongside the cell. When a parser flattens a row into one
pipe-joined string instead, all of that is destroyed before any later stage can
see it, and distinct values in distinct columns become indistinguishable.

These tests are therefore written against synthetic grids of several shapes,
not against any real document. They assert the rule, not an instance of it. The
measurements that first exposed the defect live in
`docs/specs/docling-integration-operating-notes.md`, where evidence belongs.

Deliberately written against `extract_document`, not against `convert_document`
or `run_extraction`. Those already have tests and both passed throughout the
period the capability was unreachable — testing them again would re-prove the
part that was never broken.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest

from policy_platform.contracts.reading_plan import build_reading_plan
from policy_platform.contracts.structural_graph import build_structural_graph
from policy_platform.infrastructure.ingestion import document_extraction
from policy_platform.infrastructure.settings import Settings

SAMPLES = Path(__file__).resolve().parents[2] / "samples" / "source-documents"
SOURCE_HASH = "b" * 64

#: Grid shapes exercised by the structural assertions, as (body_rows, columns).
#: Several shapes, so nothing can come to depend on a particular table having a
#: particular width, or on a header sitting in a particular place.
GRID_SHAPES = [(1, 2), (1, 5), (3, 3), (2, 4)]


# --------------------------------------------------------------------------
# Stub document, mirroring the shape used in test_docling_converter.py
# --------------------------------------------------------------------------


@dataclass
class _Text:
    text: str
    label: str = "text"
    self_ref: str = "#/texts/0"
    prov: list = field(default_factory=list)
    marker: str | None = None
    enumerated: bool = False


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
    prov: list = field(default_factory=list)
    label: str = "table"


class _StubDocument:
    def __init__(self, texts: list[_Text], tables: list[_Table]) -> None:
        self.texts = texts
        self.tables = tables
        self.pages: dict = {}

    def iterate_items(self):
        for item in self.texts:
            yield item, 1


class _StubConverter:
    def __init__(self, document: _StubDocument) -> None:
        self._document = document

    def convert(self, _source: str):
        return type("Result", (), {"document": self._document})()


def header_text(column: int) -> str:
    return f"Header {column}"


def body_text(row: int, column: int) -> str:
    """Unique per cell, so an assertion can always name the one it means."""

    return f"Body r{row} c{column}"


def _grid_converter(body_rows: int, columns: int) -> _StubConverter:
    """A table with one header row and `body_rows` body rows.

    The only structural claim baked in is the one the canonical model itself
    makes: a cell has a row index, a column index, and may be flagged a header.
    """

    cells = [
        _Cell(header_text(column), start_row_offset_idx=0, start_col_offset_idx=column, column_header=True)
        for column in range(columns)
    ]
    cells += [
        _Cell(body_text(row, column), start_row_offset_idx=row, start_col_offset_idx=column)
        for row in range(1, body_rows + 1)
        for column in range(columns)
    ]
    return _StubConverter(
        _StubDocument(
            texts=[_Text("Enclosing Section", label="section_header")],
            tables=[_Table(data=_TableData(cells))],
        )
    )


def _use_converter(monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    """Point the seam at one converter without touching the process environment.

    `get_settings` is `lru_cache`d and shared by every other test in the run, so
    mutating the environment and clearing the cache would leak into them.
    """

    settings = Settings(
        database_url="******localhost:5433/db",
        alembic_database_url="******localhost:5433/db",
        document_converter=name,
    )
    monkeypatch.setattr(document_extraction, "get_settings", lambda: settings)


#: A real, parseable document, used as the path for every structured-path call.
#:
#: The stub converter ignores it, so it has no effect while the seam works. It
#: matters when the seam is BROKEN: the legacy parser then receives a file it
#: can actually read and returns ordinary flattened elements, so these tests
#: fail on the claim — no cell, no header — instead of on a missing file.
#: Pointing this at a non-existent path made every failure a FileNotFoundError,
#: which is red for a reason that has nothing to do with table structure and
#: proves nothing about it.
FALLBACK_SOURCE = str(SAMPLES / "HR-Special-Leave-Policy-v1.0.docx")
FALLBACK_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _extract_grid(monkeypatch: pytest.MonkeyPatch, body_rows: int, columns: int):
    _use_converter(monkeypatch, "docling")
    return document_extraction.extract_document(
        FALLBACK_SOURCE,
        FALLBACK_MIME,
        document_id="guard-doc",
        source_hash=SOURCE_HASH,
        converter=_grid_converter(body_rows, columns),
    )


def _element_by_text(document, text: str):
    """Find the element carrying exactly this text.

    Raises as an assertion rather than a StopIteration so that a missing cell
    reads as the claim it violates. A bare `next()` would surface as an opaque
    iterator error, which is indistinguishable from the fixture being wrong.
    """

    matches = [element for element in document.elements if element.text == text]
    assert matches, (
        f"no element carries the text {text!r}: the cell did not survive as an "
        f"element of its own. Element types present: "
        f"{sorted({e.element_type for e in document.elements})}"
    )
    return matches[0]


class TestTheSeamCanReachTheStructuredParser:
    def test_the_default_is_the_legacy_parser(self) -> None:
        """The behaviour change is opt-in; the default must not move on its own."""

        settings = Settings(
            database_url="******localhost:5433/db",
            alembic_database_url="******localhost:5433/db",
        )
        assert settings.document_converter == "legacy"

    def test_an_unknown_converter_is_rejected_rather_than_coerced(self) -> None:
        """A typo must not resolve to the flattening parser in silence.

        A silent downgrade from a structured parse to a flattened one is the
        exact defect this seam exists to end, so it must not be reachable by
        misspelling a setting.
        """

        with pytest.raises(Exception):
            Settings(
                database_url="******localhost:5433/db",
                alembic_database_url="******localhost:5433/db",
                document_converter="docling ",
            )

    def test_the_legacy_setting_still_flattens_rows(self, monkeypatch) -> None:
        """The contrast that makes the rest of this file mean something.

        If this stopped being true the guard below would pass for a document
        that had lost its cells anyway. Uses a sample already shared with the
        converter and pipeline suites.
        """

        _use_converter(monkeypatch, "legacy")
        document = document_extraction.extract_document(
            str(SAMPLES / "HR-Special-Leave-Policy-v1.0.docx"),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )

        assert document.parser != "docling"
        assert not [e for e in document.elements if e.element_type == "table_cell"]

    @pytest.mark.parametrize(("body_rows", "columns"), GRID_SHAPES)
    def test_selecting_the_structured_parser_emits_one_element_per_cell(
        self, monkeypatch, body_rows: int, columns: int
    ) -> None:
        document = _extract_grid(monkeypatch, body_rows, columns)

        cells = [e for e in document.elements if e.element_type == "table_cell"]
        assert len(cells) == (body_rows + 1) * columns
        assert document.parser == "docling"
        # The flattened form must not reappear under a different label.
        assert not [e for e in document.elements if e.element_type == "table_row"]

    @pytest.mark.parametrize(("body_rows", "columns"), GRID_SHAPES)
    def test_every_cell_keeps_its_own_text_and_position(
        self, monkeypatch, body_rows: int, columns: int
    ) -> None:
        document = _extract_grid(monkeypatch, body_rows, columns)

        for row in range(1, body_rows + 1):
            for column in range(columns):
                cell = _element_by_text(document, body_text(row, column))
                assert cell.table_cell is not None
                assert (cell.table_cell.row_index, cell.table_cell.column_index) == (row, column)
                assert cell.table_cell.is_header is False

    @pytest.mark.parametrize(("body_rows", "columns"), GRID_SHAPES)
    def test_the_header_row_is_marked_as_header(
        self, monkeypatch, body_rows: int, columns: int
    ) -> None:
        document = _extract_grid(monkeypatch, body_rows, columns)

        headers = {
            e.text: e.table_cell
            for e in document.elements
            if e.table_cell is not None and e.table_cell.is_header
        }
        assert set(headers) == {header_text(column) for column in range(columns)}
        assert all(cell.row_index == 0 for cell in headers.values())

    def test_source_hash_namespaces_the_element_ids(self, monkeypatch) -> None:
        """Two documents containing the same sentence must not share ids."""

        _use_converter(monkeypatch, "docling")
        other = document_extraction.extract_document(
            FALLBACK_SOURCE,
            FALLBACK_MIME,
            document_id="guard-doc",
            source_hash="c" * 64,
            converter=_grid_converter(2, 3),
        )
        baseline = _extract_grid(monkeypatch, 2, 3)

        assert {e.element_id for e in baseline.elements}.isdisjoint(
            e.element_id for e in other.elements
        )

    def test_parse_problems_still_surface_through_ingestion_warnings(
        self, monkeypatch
    ) -> None:
        """The upload route reports diagnostics from whatever parser ran.

        A source with no text layer must still be reported as unusable rather
        than looking like a short policy document.
        """

        _use_converter(monkeypatch, "docling")
        empty = document_extraction.extract_document(
            FALLBACK_SOURCE,
            FALLBACK_MIME,
            source_hash=SOURCE_HASH,
            converter=_StubConverter(_StubDocument(texts=[], tables=[])),
        )

        codes = {d.code for d in document_extraction.ingestion_warnings(empty)}
        assert "unsupported_source" in codes


class TestTheHeaderReachesTheReader:
    """The point of keeping cells: a bare value must arrive with its column.

    Cell-level elements are only worth having if the association survives all
    the way to what the model reads. These assertions walk the same path an
    upload does — canonical document, structural graph, reading plan.
    """

    @pytest.mark.parametrize(("body_rows", "columns"), GRID_SHAPES)
    def test_the_graph_links_every_cell_to_the_header_of_its_own_column(
        self, monkeypatch, body_rows: int, columns: int
    ) -> None:
        """The general rule, asserted over every cell rather than a chosen one.

        Not "some header is attached" — the header of *that cell's* column, so
        that values sitting side by side stay distinguishable.
        """

        document = _extract_grid(monkeypatch, body_rows, columns)
        graph = build_structural_graph(document)

        kinds = {edge.kind for edge in graph.edges}
        assert "table_cell_of" in kinds
        assert "header_for" in kinds

        for row in range(1, body_rows + 1):
            for column in range(columns):
                cell = _element_by_text(document, body_text(row, column))
                headers = {
                    graph.nodes[i].text
                    for i in graph.sources(cell.element_id, "header_for")
                    if i in graph.nodes
                }
                assert headers == {header_text(column)}

    @pytest.mark.parametrize(("body_rows", "columns"), GRID_SHAPES)
    def test_the_reading_plan_hands_each_cell_its_column_header(
        self, monkeypatch, body_rows: int, columns: int
    ) -> None:
        """The association must survive planning, not just graph construction.

        This is the assertion that would have caught the original defect: the
        graph edges are what `reading_plan._add_table_context` consumes, and a
        cell that reaches the model without its column header is a cell whose
        meaning has been thrown away.
        """

        document = _extract_grid(monkeypatch, body_rows, columns)
        graph = build_structural_graph(document)
        plan = build_reading_plan(document, graph)

        for row in range(1, body_rows + 1):
            for column in range(columns):
                cell = _element_by_text(document, body_text(row, column))
                unit = next(u for u in plan.units if cell.element_id in u.target_element_ids)
                attached = {
                    graph.nodes[c.element_id].text
                    for c in unit.context
                    if c.reason == "table_header"
                    and cell.element_id in graph.targets(c.element_id, "header_for")
                }
                assert attached == {header_text(column)}

    @pytest.mark.parametrize(("body_rows", "columns"), GRID_SHAPES)
    def test_cells_sharing_a_row_are_told_apart_by_their_headers(
        self, monkeypatch, body_rows: int, columns: int
    ) -> None:
        """The regression in one assertion.

        When a row is flattened, every value in it arrives as one string and
        the distinct decisions it encodes collapse into one. Distinct headers
        per column are exactly what keeps them distinct.
        """

        document = _extract_grid(monkeypatch, body_rows, columns)
        graph = build_structural_graph(document)
        plan = build_reading_plan(document, graph)

        for row in range(1, body_rows + 1):
            attached: dict[str, str] = {}
            for column in range(columns):
                cell = _element_by_text(document, body_text(row, column))
                unit = next(u for u in plan.units if cell.element_id in u.target_element_ids)
                headers = [
                    graph.nodes[c.element_id].text
                    for c in unit.context
                    if c.reason == "table_header"
                    and cell.element_id in graph.targets(c.element_id, "header_for")
                ]
                assert len(headers) == 1, f"{cell.text} has headers {headers}"
                attached[cell.text] = headers[0]

            # One header per column, all different: the row is still readable
            # as several values rather than one run-together string.
            assert len(set(attached.values())) == columns

    @pytest.mark.parametrize(("body_rows", "columns"), GRID_SHAPES)
    def test_the_reading_plan_also_hands_each_cell_its_row_label(
        self, monkeypatch, body_rows: int, columns: int
    ) -> None:
        """A cell needs its row as well as its column to be interpretable.

        Which cell counts as the row's label is the platform's own rule, not
        this test's assumption: `reading_plan._add_table_context` treats the
        leftmost cell of a row as its label and deliberately does not pull the
        remaining siblings, because a whole table in every cell's context is a
        sliding window under another name.

        Accepts the label either as context or as a co-target, because the
        planner supplies it as a target when a small table chunks into a single
        unit. Both mean the reader has it, which is the property that matters;
        pinning the route would make this fail on table size alone.
        """

        document = _extract_grid(monkeypatch, body_rows, columns)
        graph = build_structural_graph(document)
        plan = build_reading_plan(document, graph)

        for row in range(1, body_rows + 1):
            label = _element_by_text(document, body_text(row, 0))
            for column in range(1, columns):
                cell = _element_by_text(document, body_text(row, column))
                unit = next(u for u in plan.units if cell.element_id in u.target_element_ids)
                as_context = {
                    c.element_id for c in unit.context if c.reason == "table_row_label"
                }
                assert label.element_id in as_context | set(unit.target_element_ids), (
                    f"{cell.text} reached the reader without its row label"
                )


class TestNoSecondExtractionPathIgnoresTheSetting:
    """Every helper that parses a document has to go through the seam.

    The seam is only a seam if it is the sole way in. A convenience wrapper
    that calls the parser directly reads as supported, but silently pins its
    callers to one converter regardless of configuration - which is the shape
    of the original defect, not a new one.
    """

    def test_the_clause_helper_honours_the_converter_setting(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """It must reach the selected converter, not the parser it used to call."""

        _use_converter(monkeypatch, "docling")
        seen: dict[str, object] = {}
        real = document_extraction.extract_document

        def spy(storage_path, mime_type, **kwargs):
            seen["called"] = True
            seen.update(kwargs)
            kwargs.setdefault("converter", _grid_converter(1, 2))
            return real(storage_path, mime_type, **kwargs)

        monkeypatch.setattr(document_extraction, "extract_document", spy)

        clauses = document_extraction.extract_clauses(
            FALLBACK_SOURCE,
            FALLBACK_MIME,
            document_id="doc",
            source_hash=SOURCE_HASH,
        )

        assert seen.get("called"), (
            "extract_clauses did not route through extract_document, so the "
            "converter setting cannot reach it"
        )
        assert seen.get("source_hash") == SOURCE_HASH, (
            "the source hash was not forwarded to the seam, so element ids "
            "would be namespaced by an empty string"
        )
        texts = {c.text for c in clauses}
        assert header_text(1) in texts, (
            "the structured converter's cells did not reach the clause helper"
        )

    def test_the_structured_path_refuses_an_empty_namespace(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An empty source hash collides element ids across documents, silently."""

        _use_converter(monkeypatch, "docling")

        with pytest.raises(document_extraction.IngestionError) as raised:
            document_extraction.extract_document(
                FALLBACK_SOURCE,
                FALLBACK_MIME,
                document_id="doc",
                source_hash="",
                converter=_grid_converter(1, 2),
            )

        assert "source hash" in str(raised.value).lower()

    def test_the_default_converter_needs_no_hash(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The refusal belongs to the structured path only.

        The legacy parser does not namespace ids by the hash, so requiring one
        of every caller would be a behaviour change smuggled in beside a
        different fix.
        """

        _use_converter(monkeypatch, "legacy")
        clauses = document_extraction.extract_clauses(FALLBACK_SOURCE, FALLBACK_MIME)
        assert clauses, "the default path stopped returning clauses"
