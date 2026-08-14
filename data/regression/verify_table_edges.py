"""The two `_add_table_edges` flaws, reproduced on a table shaped like the GMU one.

Claims made in docs/failures/rotated-cell-content-loss.md should be checkable,
so this builds the compensation table's geometry and reads the edges actually
emitted. No PDF, no model, no database — just the graph builder.

Table shape (the GMU compensation table, simplified):

      col0        col1      col2     col3      col4          col5
  r0  [ Staff Compensation (merged header, columns 1-5)              ]
  r1  Grade       Basic     HRA      Transport EOS           Notes
  r2  Grade 1     ...       ...      ...       [ As per the UAE      ]
  r3  Grade 2     ...       ...      ...       [ Labour Law          ]
  ...                                          [ (row_span = 7)      ]
  r8  Grade 7     ...       ...      ...       [                     ]
"""
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from policy_platform.contracts.structural_graph import (  # noqa: E402
    CanonicalDocument,
    CanonicalElement,
    TableCellRef,
    build_structural_graph,
)

TABLE = "tbl-compensation"
_order = iter(range(1, 500))


def elem(eid, text, **kw):
    return CanonicalElement(
        element_id=eid,
        element_type=kw.pop("element_type", "table_cell"),
        logical_order=next(_order),
        text=text,
        **kw,
    )


def cell(eid, row, col, text, *, header=False, colspan=1, rowspan=1):
    return elem(
        eid,
        text,
        table_id=TABLE,
        table_cell=TableCellRef(
            row_index=row,
            column_index=col,
            is_header=header,
            column_span=colspan,
            row_span=rowspan,
        ),
    )


elements = [
    elem(TABLE, "Compensation", element_type="table"),
    # r0: a merged banner header across columns 1-5
    cell("r0c1", 0, 1, "Staff Compensation", header=True, colspan=5),
    # r1: the real column headers
    *[
        cell(f"r1c{c}", 1, c, name, header=True)
        for c, name in enumerate(["Grade", "Basic", "HRA", "Transport", "EOS", "Notes"])
    ],
    # r2..r8: seven grade rows; the EOS column is one merged cell spanning them
    *[cell(f"r{r}c0", r, 0, f"Grade {r - 1}") for r in range(2, 9)],
    *[cell(f"r{r}c1", r, 1, "5000") for r in range(2, 9)],
    cell("eos", 2, 4, "As per the UAE Labour Law", rowspan=7),
]

graph = build_structural_graph(
    CanonicalDocument(
        document_id="gmu-handbook", page_count=45, parser="probe", elements=elements
    )
)
print("=== edges emitted, by kind ===")
for k, n in sorted(Counter(e.kind for e in graph.edges).items()):
    print(f"  {k:<20} {n}")

print("\n=== FLAW 1: does the row-spanning cell reach the rows it covers? ===")
print("  The cell declares row_span=7, covering grade rows r2..r8.")
for e in [e for e in graph.edges if "eos" in (e.source, e.target)]:
    print(f"    {e.source} -> {e.target}  [{e.kind}]")
linked = {e.target for e in graph.edges if e.source == "eos"} | {
    e.source for e in graph.edges if e.target == "eos"
}
grade_rows = {f"r{r}c0" for r in range(2, 9)}
print(f"\n  grade rows covered by the span : {len(grade_rows)}")
print(
    f"  grade rows the graph connects  : {len(linked & grade_rows)} "
    f"{sorted(linked & grade_rows) or '(none)'}"
)
print("  => row geometry emits no edges at all. `_covered_columns` exists;")
print("     there is no `_covered_rows` counterpart, so a provision merged down")
print("     a column is structurally attached to nothing below its first row.")

print("\n=== FLAW 2: how far does the merged banner header reach? ===")
merged = [e for e in graph.edges if e.kind == "merged_with"]
print(f"  merged_with edges emitted: {len(merged)}")
for src, n in Counter(e.source for e in merged).items():
    print(f"    from {src}: {n} targets -> {sorted(e.target for e in merged if e.source == src)}")
banner = sorted(e.target for e in merged if e.source == "r0c1")
body = [t for t in banner if not t.startswith("r1")]
print(
    f"\n  the banner heads the 5 header cells beneath it; it also claims "
    f"{len(body)} body cells: {body}"
)
print("  => headers are filed by column only. `headers_by_column` has no row")
print("     band, and the sole row guard drops headers *below* the cell, so a")
print("     banner in row 0 is attached to every cell in its columns for the")
print("     whole table however many row bands the table has.")
