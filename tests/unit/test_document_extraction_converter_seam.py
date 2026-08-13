"""Guard: the upload seam must be able to keep table cells intact.

WHAT THIS PROTECTS
------------------
`document_extraction.extract_document` is the only place the platform decides
how an uploaded file becomes canonical elements, and for a long time it had no
decision to make: it called the legacy parser unconditionally, so the Docling
converter — and every downstream stage built on the cell-level structure it
produces — was unreachable in production.

That is not a cosmetic difference. Measured on a 27-page HR handbook whose
final seven pages are a "Table of Violations and Penalties":

  * the legacy parser produced 91 `table_row` elements and zero `table_cell`
    ones, and the structural graph contained zero `header_for`,
    `table_cell_of` and `merged_with` edges;
  * a row whose four columns are "1st Time / 2nd Time / 3rd Time / 4th Time"
    reached the model as one pipe-joined line, and the four distinct sanctions
    it encodes were extracted as a single record whose fact identifier was
    "written-warning-one-1-day-deduction-two-2-days-deduction-..." — a fact no
    real case could ever supply.

So these tests assert the property that failure destroyed: on the structured
path a cell survives as a cell, keeps its row and column, knows which cell is
its header, and arrives in the reading plan *with that header attached*. A
future change that quietly routes uploads back through row flattening fails
here rather than in a reviewer's judgement six weeks later.

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


# --------------------------------------------------------------------------
# Stub Docling document, mirroring the shape used in test_docling_converter.py
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


#: The shape that broke: an offence described in column 0, then one sanction
#: per escalation tier. Only the header row carries `column_header`.
_PENALTY_HEADERS = ["Violation", "1st Time", "2nd Time", "3rd Time", "4th Time"]
_PENALTY_ROW = [
    "Departing from work more than 15 minutes early without permission",
    "10% deduction",
    "25% deduction",
    "One (1) day deduction",
    "Two (2) days deduction",
]


def _penalty_table_converter() -> _StubConverter:
    cells = [
        _Cell(text, start_row_offset_idx=0, start_col_offset_idx=column, column_header=True)
        for column, text in enumerate(_PENALTY_HEADERS)
    ]
    cells += [
        _Cell(text, start_row_offset_idx=1, start_col_offset_idx=column)
        for column, text in enumerate(_PENALTY_ROW)
    ]
    return _StubConverter(
        _StubDocument(
            texts=[_Text("Table of Violations and Penalties", label="section_header")],
            tables=[_Table(data=_TableData(cells))],
        )
    )


def _use_converter(monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    """Point the seam at one converter without touching the process environment.

    `get_settings` is `lru_cache`d and shared by every other test in the run, so
    mutating the environment and clearing the cache would leak into them.
    """

    settings = Settings(
        database_url="postgresql://u:p@localhost:5433/db",
        alembic_database_url="postgresql://u:p@localhost:5433/db",
        document_converter=name,
    )
    monkeypatch.setattr(document_extraction, "get_settings", lambda: settings)


def _extract_penalty_table(monkeypatch: pytest.MonkeyPatch):
    _use_converter(monkeypatch, "docling")
    return document_extraction.extract_document(
        "penalties.pdf",
        "application/pdf",
        document_id="guard-doc",
        source_hash=SOURCE_HASH,
        converter=_penalty_table_converter(),
    )


class TestTheSeamCanReachTheStructuredParser:
    def test_the_default_is_the_legacy_parser(self) -> None:
        """The behaviour change is opt-in; the default must not move on its own."""

        settings = Settings(
            database_url="postgresql://u:p@localhost:5433/db",
            alembic_database_url="postgresql://u:p@localhost:5433/db",
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
                database_url="postgresql://u:p@localhost:5433/db",
                alembic_database_url="postgresql://u:p@localhost:5433/db",
                document_converter="docling ",
            )

    def test_the_legacy_setting_still_flattens_rows(self, monkeypatch) -> None:
        """The contrast that makes the rest of this file mean something.

        If this stopped being true the guard below would pass for a document
        that had lost its cells anyway.
        """

        _use_converter(monkeypatch, "legacy")
        document = document_extraction.extract_document(
            str(SAMPLES / "HR-Special-Leave-Policy-v1.0.docx"),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )

        assert document.parser != "docling"
        assert not [e for e in document.elements if e.element_type == "table_cell"]

    def test_selecting_docling_emits_one_element_per_cell(self, monkeypatch) -> None:
        document = _extract_penalty_table(monkeypatch)

        cells = [e for e in document.elements if e.element_type == "table_cell"]
        assert len(cells) == len(_PENALTY_HEADERS) + len(_PENALTY_ROW)
        assert document.parser == "docling"
        # The flattened form must not reappear under a different label.
        assert not [e for e in document.elements if e.element_type == "table_row"]

    def test_a_penalty_cell_keeps_its_own_text_and_position(self, monkeypatch) -> None:
        document = _extract_penalty_table(monkeypatch)

        third_time = next(e for e in document.elements if e.text == "One (1) day deduction")
        assert third_time.table_cell is not None
        assert (third_time.table_cell.row_index, third_time.table_cell.column_index) == (1, 3)
        assert third_time.table_cell.is_header is False

    def test_the_escalation_header_row_is_marked_as_header(self, monkeypatch) -> None:
        document = _extract_penalty_table(monkeypatch)

        headers = {
            e.text: e.table_cell
            for e in document.elements
            if e.table_cell is not None and e.table_cell.is_header
        }
        assert set(headers) == set(_PENALTY_HEADERS)
        assert all(cell.row_index == 0 for cell in headers.values())

    def test_source_hash_namespaces_the_element_ids(self, monkeypatch) -> None:
        """Two documents containing the same sentence must not share ids."""

        _use_converter(monkeypatch, "docling")
        other = document_extraction.extract_document(
            "penalties.pdf",
            "application/pdf",
            document_id="guard-doc",
            source_hash="c" * 64,
            converter=_penalty_table_converter(),
        )
        baseline = _extract_penalty_table(monkeypatch)

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
            "scanned.pdf",
            "application/pdf",
            source_hash=SOURCE_HASH,
            converter=_StubConverter(_StubDocument(texts=[], tables=[])),
        )

        codes = {d.code for d in document_extraction.ingestion_warnings(empty)}
        assert "unsupported_source" in codes


class TestTheHeaderReachesTheReader:
    """The point of keeping cells: a bare value must arrive with its column.

    Cell-level elements are only worth having if the association survives all
    the way to what the model reads. These assertions walk the same path the
    upload does — canonical document, structural graph, reading plan.
    """

    def test_the_graph_associates_each_cell_with_its_column_header(
        self, monkeypatch
    ) -> None:
        document = _extract_penalty_table(monkeypatch)
        graph = build_structural_graph(document)

        kinds = {edge.kind for edge in graph.edges}
        assert "table_cell_of" in kinds
        assert "header_for" in kinds

        third_time = next(e for e in document.elements if e.text == "One (1) day deduction")
        header_ids = set(graph.sources(third_time.element_id, "header_for"))
        headers = {graph.nodes[i].text for i in header_ids if i in graph.nodes}
        assert headers == {"3rd Time"}

    def test_the_reading_plan_gives_a_penalty_cell_its_column_and_row_label(
        self, monkeypatch
    ) -> None:
        """"One (1) day deduction" states nothing on its own.

        Its meaning is entirely in the column that says which offence number it
        punishes and the row that says which offence it is. Without both, four
        escalating sanctions read as one.
        """

        document = _extract_penalty_table(monkeypatch)
        graph = build_structural_graph(document)
        plan = build_reading_plan(document, graph)

        third_time = next(e for e in document.elements if e.text == "One (1) day deduction")
        unit = next(u for u in plan.units if third_time.element_id in u.target_element_ids)

        context = {(c.reason, graph.nodes[c.element_id].text) for c in unit.context}
        assert ("table_header", "3rd Time") in context

        # The offence itself may arrive as a target rather than as context when
        # the planner chunks a short table into one unit, so this asserts the
        # property that matters — the reader has it — not the route it took.
        row_label = next(e for e in document.elements if e.text == _PENALTY_ROW[0])
        assert row_label.element_id in unit.ordered_element_ids

    def test_each_tier_gets_a_different_header(self, monkeypatch) -> None:
        """The regression in one assertion.

        All four sanctions previously collapsed into a single record because
        nothing distinguished them. Four cells, four different headers, is
        precisely what makes them four decisions again.
        """

        document = _extract_penalty_table(monkeypatch)
        graph = build_structural_graph(document)
        plan = build_reading_plan(document, graph)

        seen: dict[str, str] = {}
        for sanction in _PENALTY_ROW[1:]:
            cell = next(e for e in document.elements if e.text == sanction)
            unit = next(u for u in plan.units if cell.element_id in u.target_element_ids)
            headers = [
                graph.nodes[c.element_id].text
                for c in unit.context
                if c.reason == "table_header"
                and cell.element_id
                in graph.targets(c.element_id, "header_for")
            ]
            assert len(headers) == 1, f"{sanction} has headers {headers}"
            seen[sanction] = headers[0]

        assert sorted(seen.values()) == ["1st Time", "2nd Time", "3rd Time", "4th Time"]
