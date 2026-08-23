"""A table header split across two rows is one header, not a header and a row.

THE DEFECT THIS EXISTS TO PREVENT

`_row_states_column_labels` decides from the string grid alone whether row 0 is
the header. On a table whose header occupies two rows — a merged banner over the
sub-labels that divide it — row 0 is only half of one. It was accepted as the
whole header, so **row 1 was emitted as a data row**: a phantom provision whose
text is the sub-labels themselves, filed under headers that are empty for
exactly the columns it names.

Reproduced on the GMU staff handbook, page 30:

    row0 = ['Sl.\\nNo.', 'Position', 'Itemization', '', '', '', '']
    row1 = ['', '', 'Salary Range', 'Housing Allowance (Monthly)',
            'Ticket Allowance (for Expatriates)', 'Health Insurance',
            'End of Service Benefit …']

WHY IT WAS REFUSED ONCE, AND WHAT CHANGED

`docs/failures/table-header-split-across-two-rows.md` recorded this as real and
declined to fix it, correctly: read from the strings alone, "row 0 has empties
that row 1 fills" is indistinguishable from a legitimate stub crosstab, where
row 0 *is* the whole header and row 1 *is* data. Balancing a string heuristic
between those two cases is tuning to the corpus, which constraint 1 forbids, and
the failure would be destructive — on a real crosstab it would swallow a genuine
first data row.

That document also wrote down the fix: read the cell **geometry** pdfplumber
already returns, which every PDF table has and no document's words influence.
This file pins that behaviour.

WHAT IS ASSERTED

The tests below use the geometry measured from the reproduction case rather than
a guess at pdfplumber's API:

    row0 cells [(56,80), (80,156), (156,508), None, None, None, None]
    row1 cells [None, None, (156,209), (209,265), (265,380), (380,448), (448,508)]

The banner at column 2 covers x 156–508; row 1 divides that same span into five.
In an ordinary table each row-0 cell covers exactly one row-1 cell.

Measured over every PDF in the corpus: 84 tables with two or more rows, 4
flagged, and all 4 are the same GMU table in duplicate copies of that file — so
the rule is specific to the defect and fires on nothing else.
"""

from policy_platform.infrastructure.ingestion.document_ingestion import (
    _banner_columns,
    _join_header_rows,
)


class _Row:
    """The one thing this code reads from a pdfplumber row: its cells."""

    def __init__(self, cells):
        self.cells = cells


def _gmu_page_30_geometry() -> list[_Row]:
    """The reproduction case, measured from the real document."""
    return [
        _Row([(56, 0, 80, 10), (80, 0, 156, 10), (156, 0, 508, 10), None, None, None, None]),
        _Row(
            [
                None,
                None,
                (156, 10, 209, 20),
                (209, 10, 265, 20),
                (265, 10, 380, 20),
                (380, 10, 448, 20),
                (448, 10, 508, 20),
            ]
        ),
    ]


def test_a_banner_over_sub_divided_columns_is_recognised() -> None:
    banner = _banner_columns(_gmu_page_30_geometry())

    assert banner == {2: 5}, (
        "column 2's cell spans x 156-508, which row 1 divides into five; "
        f"got {banner}"
    )


def test_an_ordinary_table_has_no_banner() -> None:
    # Every row-0 cell covers exactly one row-1 cell: the shape of almost every
    # table in the corpus, and the case a string-only rule could not tell from
    # the one above.
    ordinary = [
        _Row([(10, 0, 50, 10), (50, 0, 90, 10), (90, 0, 130, 10)]),
        _Row([(10, 10, 50, 20), (50, 10, 90, 20), (90, 10, 130, 20)]),
    ]

    assert _banner_columns(ordinary) == {}


def test_a_stub_crosstab_is_not_mistaken_for_a_banner() -> None:
    """The case the refusal was written to protect.

    `['', 'Q1', 'Q2']` over `['North', '10', '20']` reads exactly like a two-row
    header in strings — row 0 has an empty that row 1 fills. Its geometry does
    not: each row-0 cell covers one row-1 cell, so nothing is flagged and the
    genuine first data row survives.
    """
    crosstab = [
        _Row([(10, 0, 60, 10), (60, 0, 110, 10), (110, 0, 160, 10)]),
        _Row([(10, 10, 60, 20), (60, 10, 110, 20), (110, 10, 160, 20)]),
    ]

    assert _banner_columns(crosstab) == {}


def test_a_single_row_table_has_no_banner() -> None:
    assert _banner_columns([_Row([(10, 0, 50, 10)])]) == {}


def test_a_row_of_only_empty_cells_has_no_banner() -> None:
    assert _banner_columns([_Row([(10, 0, 50, 10)]), _Row([None, None])]) == {}


def test_both_halves_of_a_split_label_are_kept_verbatim() -> None:
    assert _join_header_rows("Itemization", "Salary Range") == "Itemization · Salary Range"


def test_a_column_labelled_in_only_one_row_gains_no_separator() -> None:
    assert _join_header_rows("Position", "") == "Position"
    assert _join_header_rows("", "Health Insurance") == "Health Insurance"


def test_a_label_written_twice_is_one_label() -> None:
    # A banner that spans a single column repeats its own text in both rows.
    # "Position · Position" would be this code inventing emphasis the document
    # does not carry.
    assert _join_header_rows("Position", "Position") == "Position"
