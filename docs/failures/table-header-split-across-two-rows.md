# A table header split across two rows, and three items that were not there

Four extraction items sat in the backlog with one line of description between
them: `interleaved-title`, `doses-defect`, `two-row-hdr`, `fact-cap`. This
records what each turned out to be. One was a real defect and is fixed; one is a
real defect that is **deliberately not fixed here**, with the argument; two do
not reproduce.

Method, because §4.5 says the method must be challengeable: all corpus evidence
was gathered through `docker exec psql` and through Python with
`PYTHONIOENCODING=utf-8`. None of it went through PowerShell's `ConvertTo-Json`,
which escapes non-ASCII and has already caused one agent in this project to
conclude there was no Arabic in a corpus that holds 75 Arabic clauses.

| item | still real? | outcome |
|---|---|---|
| `doses-defect` | yes | fixed, generically |
| `two-row-hdr` | yes, reproduced on GMU p30 | **refused on constraint 1** — design handed back |
| `interleaved-title` | no | does not reproduce |
| `fact-cap` | no | no defect in the deterministic path |

---

## 1. `doses-defect` — a comparison about one number asserted about another

This is another instance of §4.7: a phrase landing in the role next door.

`project_stated_quantity` owns one decision — does this threshold state a
*comparison*, or only a magnitude? `stated_comparison(*sources)` owns a
different one — bind a comparative to the number **nearest it, within one
source**. The seam called `stated_comparison(threshold, rule.predicate)` with
both sources at once. When the threshold carried no comparative, the call fell
through to the predicate and returned a comparative bound to the **predicate's**
number, which the caller then applied to the **threshold's** magnitude.

Reproduced with a synthetic rule: threshold `"3 doses"`, predicate
`"administered no later than 30 days after exposure"`. That compiled to
`administered-course-doses ≤ 3` — a limit the sentence never states. The "no
later than" caps the 30 days, not the dose count.

The fix reads the threshold alone, and falls back to the predicate only where
the predicate has no number of its own to govern, using the same numeric
detector `stated_comparison` already uses to place its boundary. No vocabulary,
no counts, no document specifics — so it survives Arabic, which a list of words
would not. The module already held the principle this restores: *a manufactured
rule is worse than an absent one*.

---

## 2. `two-row-hdr` — real, reproduced, and left alone on purpose

`_row_states_column_labels` decides, **from the string grid alone**, whether row
0 is the header. Its own docstring already names the case it mishandles: on a
page whose table has a two-row header, row 0 is half of one.

Reproduced on the GMU Staff Handbook, page 30, table 1:

```
row0 = ['Sl.\nNo.', 'Position', 'Itemization', '', '', '', '']
row1 = ['', '', 'Salary Range', 'Housing Allowance (Monthly)',
        'Ticket Allowance (for Expatriates)', 'Health Insurance',
        'End of Service Benefit …']
```

`Itemization` is a merged banner spanning columns 2–6; row 1 holds the real
sub-labels beneath it. The function accepts row 0 as the sole header, so **row 1
is emitted as a data row** — a phantom provision whose text is
`" |  | Salary Range | Housing Allowance… "`, carried under headers that are
empty for the very columns row 1 labels.

### Why it was not fixed here

The only signal available at that boundary is "row 0 has empties that row 1
fills". That is **indistinguishable** from a legitimate stub crosstab —
`['', 'Q1', 'Q2']` over a first data row `['North', '10', '20']` — where row 0
*is* the whole header and row 1 *is* data.

Telling the two apart requires knowing that `Itemization` is a cell **spanning
columns 2–6**. That is merged-cell geometry, and `table.extract()` discards it,
returning only strings.

So any string-only heuristic would have to be balanced between the two cases,
and the neighbouring constant `_MAX_HEADER_CELL_CHARS = 40` shows that balance
has already been struck against these two corpora — its comment says the bound
"sits between" one corpus's 24-character header and another's 58-character
content. Adding a second threshold tuned to keep both cases working **is**
tuning to the corpus, which constraint 1 forbids. And the failure would be in
the destructive direction: on a real crosstab it would merge away a genuine
first data row, which the function's own asymmetric-risk comment already refuses.

This is the same shape as `rotated-cell-content-loss.md`: a measured, real
content loss left in place because every in-scope alternative scored worse.

### The design that would fix it

Read pdfplumber's cell **geometry** in `_table_to_blocks` rather than only
`table.extract()`. Where a row-0 cell spans columns that the next row
sub-divides, treat rows 0–1 as one compound header, join banner and sub-label
per column (`Itemization · Salary Range`), and emit a
`table_header_spans_multiple_rows` diagnostic.

That keys on geometry, which every PDF table has, rather than on any document's
words — so it is domain-neutral. It is a structural change to ingestion and
needs an owner's decision, which is why it is written down rather than done.

---

## 3. `interleaved-title` — does not reproduce

Block ordering sorts by vertical position, which interleaves table rows into
body flow **by design**. The hypothesised defect was a title landing wrongly
relative to that interleave, which is reachable only through the multi-column
reading-order path.

Two independent measurements say it does not happen here:

- **Structural, over the live corpus:** across 351 heading, 603 list-item, 933
  paragraph and 314 table-row clauses, **zero** non-table clauses are sequenced
  strictly inside any table's row span. No heading interleaves into table rows
  anywhere in the extracted corpus.
- **At ingestion:** the `multi_column_layout` diagnostic never fires on either
  fixture, so the column-reordering path that could misplace a title is not
  reached by these documents at all.

Either it was already fixed, or the shorthand names a shape these documents do
not exhibit. If the document that motivated the note can be identified, this is
worth re-testing against it.

---

## 4. `fact-cap` — the deterministic path is clean

The live evidence:

- `policy_aggregate_limits` holds **0 rows**, so there are no combined caps to
  be mis-linked.
- Every rule-level `factComparison` cap — 7 of 7 — has its compared fact
  declared in `required_facts`. Linkage is intact.
- The exclusion that keeps a clause out of a fact identifier is working: a
  clause in `predicate` yields no fact, which is the behaviour its comment
  describes.

One live anomaly exists — an 85-character fact identifier — but it **cannot** be
produced by the current deterministic path, which caps a slug at 80 and adds no
suffix. It is stale data from an older route, not a defect in the code today.

The strongest reading of "fact-cap" matches a defect that has already been
fixed. Recovering what it originally meant needs whoever wrote the note.

---

## The lesson

Half of this batch was not there. Combined with the rest of the backlog audit —
where four of eight other items proved already done or named symbols that do not
exist — **the standing instruction is to verify a backlog item against the code
before spending anything on it.** A one-line backlog note ages badly, and this
repository now has two separate sessions' worth of evidence that it does.
