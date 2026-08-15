"""A row of a table is told what its columns are called — and nothing more.

The parser that runs emits whole `table_row` elements: a row's values arrive
pipe-joined into one string, and its column labels arrive as a separate list of
strings held on the row. There are no cell coordinates, so nothing records
which value sits under which label.

That leaves exactly one true thing to say, and these tests pin both halves of
it:

* **say the names**, because a row rendered as values alone reads as a sentence
  with punctuation rather than as a row of a grid; and
* **refuse the pairing**, because pairing by position would be a confident,
  well-formed, wrong attribution — worse than saying nothing.

A third rule is pinned as hard as the other two: **absence stays absent.** A
row from a grid where no row evidenced itself as the header says nothing at
all. It does not say that its labels are unavailable.

Every fixture here is a synthetic grid. No document, domain, language or count
from any real corpus appears, and the shapes are parameterised so no single
layout can be the thing that passes.
"""
from __future__ import annotations

import pytest

from policy_platform.contracts.canonical_document import CanonicalDocument, CanonicalElement
from policy_platform.contracts.reading_plan import (
    build_reading_plan,
    render_table_columns,
    table_column_names,
)
from policy_platform.contracts.structural_graph import build_structural_graph
from policy_platform.domain.models import Clause
from policy_platform.infrastructure.extraction.ai_extraction import (
    _column_marker,
    _rendered_size,
    _render_batch,
)

#: Deliberately varied so no one shape can be what makes the suite pass.
GRID_SHAPES = [(1, 2), (2, 3), (3, 4), (4, 2)]

VALUE_SEPARATOR = " | "


def _labels(columns: int) -> list[str]:
    return [f"Column {index}" for index in range(columns)]


def _row_text(row: int, columns: int) -> str:
    return VALUE_SEPARATOR.join(f"v{row}c{index}" for index in range(columns))


def _grid_document(
    rows: int,
    columns: int,
    *,
    headers: list[str] | None,
    document_id: str = "DOC",
) -> CanonicalDocument:
    """A heading followed by `rows` table rows of one table."""

    elements = [
        CanonicalElement(
            element_id="E000000",
            element_type="heading",
            logical_order=0,
            text="A section",
        )
    ]
    for row in range(rows):
        elements.append(
            CanonicalElement(
                element_id=f"E{row + 1:06d}",
                element_type="table_row",
                logical_order=row + 1,
                text=_row_text(row, columns),
                section="A section",
                table_id="T1",
                table_headers=headers,
            )
        )
    return CanonicalDocument(
        document_id=document_id,
        page_count=1,
        parser="synthetic",
        elements=elements,
    )


def _clause(
    sequence: int,
    text: str,
    *,
    element_type: str = "table_row",
    headers: list[str] | None = None,
    section: str | None = None,
) -> Clause:
    return Clause(
        sequence=sequence,
        clause_ref=f"C{sequence:04d}",
        element_id=f"E{sequence:06d}",
        element_type=element_type,
        text=text,
        section=section,
        table_id="T1" if element_type == "table_row" else None,
        table_headers=headers,
    )


# --- The names are said ------------------------------------------------------


@pytest.mark.parametrize("rows,columns", GRID_SHAPES)
def test_a_planned_row_is_told_its_column_names(rows: int, columns: int) -> None:
    document = _grid_document(rows, columns, headers=_labels(columns))
    plan = build_reading_plan(document, build_structural_graph(document))

    named = {
        element_id: names
        for unit in plan.units
        for element_id, names in unit.table_columns.items()
    }

    assert named, "a row of a table with stated column labels was told nothing"
    assert all(names == _labels(columns) for names in named.values())


@pytest.mark.parametrize("rows,columns", GRID_SHAPES)
def test_every_targeted_row_is_told_and_not_just_the_first(
    rows: int, columns: int
) -> None:
    """A capability that reaches only the first row of a grid is not one."""

    document = _grid_document(rows, columns, headers=_labels(columns))
    plan = build_reading_plan(document, build_structural_graph(document))

    targets = {eid for unit in plan.units for eid in unit.target_element_ids}
    told = {eid for unit in plan.units for eid in unit.table_columns}

    assert told == targets


def test_the_order_the_table_stated_is_preserved() -> None:
    """Reordering labels would be an editorial act on attributed material."""

    stated = ["Third-stated", "First-stated", "Second-stated"]
    assert table_column_names(stated) == stated


# --- The pairing is refused --------------------------------------------------


@pytest.mark.parametrize("rows,columns", GRID_SHAPES)
def test_the_rendered_line_refuses_positional_pairing(
    rows: int, columns: int
) -> None:
    """The one thing a reader must not conclude is stated, not left implied."""

    line = render_table_columns(_labels(columns))
    assert "not" in line and "position" in line


def test_column_names_are_not_rendered_with_the_separator_the_values_use() -> None:
    """Two lists joined the same way invite the reading the marker denies."""

    line = render_table_columns(["Alpha", "Beta"])
    assert VALUE_SEPARATOR not in line


@pytest.mark.parametrize("rows,columns", GRID_SHAPES)
def test_the_rendered_line_does_not_claim_to_name_every_column(
    rows: int, columns: int
) -> None:
    """The names shown are ones the table has, not necessarily all of them.

    Labels that name nothing are dropped, and a grid whose column names are
    printed across more than one line yields only the line the parser read as
    the header. A reader told these *are* the columns could conclude that a row
    carrying more values than there are names is malformed. Stating membership
    costs a word and keeps the sentence true.
    """

    line = render_table_columns(_labels(columns))
    assert "include" in line


def test_nothing_here_pairs_a_label_to_a_value() -> None:
    """The marker names columns; it never claims a value belongs to one."""

    columns = 3
    line = render_table_columns(_labels(columns))
    for value in _row_text(0, columns).split(VALUE_SEPARATOR):
        assert value not in line


@pytest.mark.parametrize("rows,columns", GRID_SHAPES)
def test_being_told_the_names_builds_no_table_structure(
    rows: int, columns: int
) -> None:
    """Naming columns is not cell structure and must not be mistaken for it."""

    document = _grid_document(rows, columns, headers=_labels(columns))
    graph = build_structural_graph(document)

    cell_edges = [e for e in graph.edges if e.kind in {"table_cell_of", "header_for", "merged_with"}]
    assert cell_edges == []
    assert graph.table_cells == {}


# --- Absence stays absent ----------------------------------------------------


@pytest.mark.parametrize("rows,columns", GRID_SHAPES)
def test_a_headerless_row_is_told_nothing_at_all(rows: int, columns: int) -> None:
    document = _grid_document(rows, columns, headers=None)
    plan = build_reading_plan(document, build_structural_graph(document))

    assert all(unit.table_columns == {} for unit in plan.units)


def test_a_headerless_row_gets_no_line_rather_than_a_line_saying_so() -> None:
    """"Labels unavailable" is a sentence about this system, not the document."""

    assert render_table_columns(None) == ""
    assert table_column_names(None) == []


def test_an_empty_label_list_is_also_silence() -> None:
    assert render_table_columns([]) == ""


def test_a_label_that_is_only_whitespace_names_nothing_and_is_dropped() -> None:
    assert table_column_names(["Named", "   ", ""]) == ["Named"]


def test_a_header_row_of_entirely_blank_labels_stays_silent() -> None:
    assert render_table_columns(["", "  ", "\t"]) == ""


def test_a_label_printed_across_lines_is_kept_on_one() -> None:
    """A newline inside the marker would break the one-line addressing format.

    Collapsing whitespace for display changes no word and drops none; the
    stored label is untouched.
    """

    collapsed = table_column_names(["Serial\nNumber"])
    assert collapsed == ["Serial Number"]
    assert "\n" not in render_table_columns(["Serial\nNumber"])


def test_a_non_row_element_is_told_nothing() -> None:
    document = CanonicalDocument(
        document_id="DOC",
        page_count=1,
        parser="synthetic",
        elements=[
            CanonicalElement(
                element_id="E000000",
                element_type="paragraph",
                logical_order=0,
                text="Prose states its own subject.",
            )
        ],
    )
    plan = build_reading_plan(document, build_structural_graph(document))
    assert all(unit.table_columns == {} for unit in plan.units)


# --- The text a model is actually given -------------------------------------


@pytest.mark.parametrize("rows,columns", GRID_SHAPES)
def test_the_batch_a_model_reads_carries_the_column_names(
    rows: int, columns: int
) -> None:
    """The reading plan is a reviewer's artefact; this is the model's input.

    Pinned separately because a correct answer that reaches only an inspection
    endpoint is this project's signature failure, not a fix.
    """

    labels = _labels(columns)
    batch = [_clause(row, _row_text(row, columns), headers=labels) for row in range(rows)]

    rendered = _render_batch(batch)

    for label in labels:
        assert label in rendered
    assert rendered.count(render_table_columns(labels)) == rows


def test_a_headerless_row_adds_nothing_to_what_a_model_reads() -> None:
    text = _row_text(0, 3)
    unchanged = _render_batch([_clause(0, text, headers=None)])
    assert unchanged.splitlines()[-1] == text
    assert len(unchanged.splitlines()) == len(
        _render_batch([_clause(0, text, element_type="paragraph")]).splitlines()
    )


def test_prose_in_a_batch_is_rendered_exactly_as_before() -> None:
    """Nothing that is not a row of a table may change shape."""

    prose = _clause(0, "Employees shall report incidents promptly.", element_type="paragraph")
    rendered = _render_batch([prose])
    assert rendered == f"[clause_ref={prose.clause_ref}]\n{prose.text}"


def test_the_row_text_itself_is_passed_through_untouched() -> None:
    """The marker is added around the text; it never edits it."""

    text = _row_text(0, 4)
    rendered = _render_batch([_clause(0, text, headers=_labels(4))])
    assert text in rendered


def test_the_marker_sits_on_its_own_line_above_the_row() -> None:
    """The addressing format is one identifier per line; this keeps it so."""

    text = _row_text(0, 2)
    rendered = _render_batch([_clause(0, text, headers=_labels(2))])
    lines = rendered.splitlines()
    assert lines[-1] == text
    assert lines[-2] == render_table_columns(_labels(2))


# --- What it costs to say it -------------------------------------------------


def test_the_added_line_is_charged_against_the_batch_budget() -> None:
    """An unbudgeted addition would let a batch overrun the window it was packed for."""

    labels = _labels(4)
    text = _row_text(0, 4)
    with_labels = _rendered_size(_clause(0, text, headers=labels))
    without = _rendered_size(_clause(0, text, headers=None))

    assert with_labels - without == len(render_table_columns(labels))


def test_a_clause_with_no_column_names_costs_exactly_what_it_did_before() -> None:
    """Charging every clause for a line most never carry would shrink batches for nothing."""

    prose = _clause(0, "Some text.", element_type="paragraph")
    assert _column_marker(prose) == ""
    assert _rendered_size(prose) == len(prose.text) + 40


@pytest.mark.parametrize("rows,columns", GRID_SHAPES)
def test_what_is_charged_is_what_is_rendered(rows: int, columns: int) -> None:
    """The estimate must not drift from the text it is estimating."""

    labels = _labels(columns)
    batch = [_clause(row, _row_text(row, columns), headers=labels) for row in range(rows)]
    rendered = _render_batch(batch)

    assert len(rendered) <= sum(_rendered_size(c) for c in batch)
