# Docling Integration — Operating Notes

Findings from bringing Docling and Docling Graph into the platform. These are measured behaviours, not expectations: each one was observed while running the real dependencies against the repository's sample documents.

---

## 1. Environment

### Extraction runs in a separate environment from the API

`docling` resolves to `docling-slim[standard]`, which installs `torch`, `torchvision`, `accelerate`, `rapidocr`, `scipy`, and `transformers`. The API runtime image is `python:3.11-slim` with pdfplumber and python-docx and must not carry that footprint.

The two environments also have a **hard dependency conflict**, so merging them is not merely undesirable:

| Package | API runtime | Extraction |
|---|---|---|
| `httpx` | `>=0.27,<0.28` (project pin) | `>=0.28` (required by `litellm`) |

The extraction dependencies are therefore an optional extra:

```bash
python -m venv .venv-graph
.\.venv-graph\Scripts\python.exe -m pip install "docling-graph==1.9.1"
```

### PDF conversion needs dynamo disabled on Windows

Docling's PDF pipeline runs layout models through torch. On Windows without a Visual C++ toolchain, `torch.compile` fails with `InvalidCxxCompiler: Compiler: cl is not found` and conversion aborts.

Set this before any PDF conversion:

```powershell
$env:TORCHDYNAMO_DISABLE = "1"
```

DOCX conversion does not touch torch and is unaffected.

### Measured conversion cost

| Source | Result | Time |
|---|---|---|
| `HR-Special-Leave-Policy-v1.0.docx` | 22 elements, 1 page | 0.3 s |
| `IT-Security-Incident-Emergency-Access-Policy-v1.0.docx` | 41 elements incl. 20 table cells | 0.1 s |
| `Workplace-Hardware-Provisioning-Policy-v3.2.docx` | 191 texts, 5 tables | 0.6 s |
| `HR-Guide-Policy-and-Procedure-Template.pdf` | 53 pages, 969 texts, 2 tables | **195 s** |

PDF conversion is roughly three orders of magnitude slower than DOCX because it runs layout inference per page. Any ingestion flow that converts PDF synchronously inside a request will time out; this is a direct input to the durable stage-execution work.

---

## 2. Upstream API notes

### `docling_graph.utils` does not exist in 1.9.1

The upstream README shows:

```python
from docling_graph.utils import edge
```

That module is not present in the released package. `edge` is a **template-local helper**: `docling_graph/templategen/snippets.py` emits its source into generated templates rather than exporting it. The public contract is the `json_schema_extra` convention it writes:

| Key | Meaning |
|---|---|
| `edge_label` | Relationship name for this field |
| `graph_reference` | Identity-only link, filled by the parent's own call |
| `reference_closed_catalog` | Targets form a closed catalog defined elsewhere |

`PolicyDocumentGraphV1` defines its own `edge()` helper against these keys, which keeps the template on the documented public convention with no dependency on package internals.

### `NodeCatalog.paths` is a method

`build_node_catalog(...)` returns a `NodeCatalog` whose `paths` is a **method**, not a property. `set(catalog.paths)` silently produces a set containing a bound method rather than failing, so a test written against it passes while asserting nothing. Use `{node.path for node in catalog.nodes}`.

This was caught by a compatibility test and is the reason the template is validated against Docling Graph's real catalog builder rather than against our own metadata.

### Validated template structure

`build_node_catalog(PolicyDocumentGraphV1)` resolves 11 candidate paths, all classified as entities, in this bottom-up fill order:

```
policy_units[].scope
policy_units[].conditions[]
policy_units[].exceptions[]
policy_units[].approvals[]
policy_units[].references[]
policy_units[].footnotes[]
policy_units[].tables[]
definitions[]
policy_units[]
process_steps[]
''                       (root)
```

Supporting material is filled before the units it governs, which is what makes attachment reliable.

---

## 3. Conversion behaviour

### DOCX has no pagination

Docling reports `pages = 0` for DOCX because page breaks are decided by the renderer, not stored in the file. The canonical adapter models a DOCX as one logical page, matching the legacy behaviour, so downstream consumers need no special case. **Page-based anchoring is unusable for DOCX sources.**

### Table structure is fully exposed

Docling provides per-cell `start_row_offset_idx`, `start_col_offset_idx`, `row_span`, `col_span`, and `column_header`. This is what allows cells to keep their exact values while carrying their position and merge span structurally, instead of the legacy DOCX path's `"Tier: 2; Limit: 5000"` prose — text that appears nowhere in the source and therefore fabricated any passage quoted from it.

### PDF geometry uses a bottom-left origin

PDF provenance returns `CoordOrigin.BOTTOMLEFT`. Most renderers are top-left, so the origin is recorded on every bounding box. A silently flipped highlight looks to a reviewer like a wrong extraction.

### List enumeration labels are structure, not text

Docling strips the enumeration label from a list item's text and exposes it as `ListItem.marker` with an `enumerated` flag:

| | Text |
|---|---|
| Legacy | `"D. The outside employment should not embarrass the Foundation."` |
| Docling | `"The outside employment should not embarrass the Foundation."` + `marker="D."` |

Nothing is lost by the converter, but the label a reviewer cites ("Section 5.D") disappears unless captured explicitly. `CanonicalElement` therefore carries `list_marker` and `list_enumerated`, held separately from `text` so the text stays exactly what was extracted.

The marker is deliberately **excluded from element identity**: a converter upgrade that relabels `D.` as `4.` changes presentation, not the clause, and must not repoint stored spans.

Measured on the 53-page PDF: 146 list items carry a marker, 83 of them enumerated. The rest are bullets, which identify nothing and are unusable in a citation.

### Docling occasionally joins words without a space

At some line breaks Docling concatenates without a separator, producing tokens such as `SafetyAct`, `EmploymentStandards`, and `WorkSafe`. Seven such elements were found in the 53-page PDF.

These are **reported, never repaired**. Inserting a space would rewrite canonical text, which is exactly what INVARIANT 6 forbids: every character of an element must come from the source. A reviewer seeing a `suspected_missing_space` diagnostic can judge it; a silently corrected string cannot be audited, and the same heuristic would eventually corrupt a legitimate compound. The diagnostic is `info` severity and does not fail the document.

---

## 4. Shadow comparison results

Legacy parsers versus Docling across the sample corpus, measured by whether content tokens survived (`scripts/docling_shadow_report.py`):

| Document | Recall | Verdict |
|---|---|---|
| `HR-Special-Leave-Policy-v1.0.docx` | 1.0000 | no content loss |
| `IT-Security-Incident-Emergency-Access-Policy-v1.0.docx` | 1.0000 | no content loss |
| `Workplace-Hardware-Provisioning-Policy-v3.2.docx` | 1.0000 | no content loss |
| `Workplace-Hardware-Provisioning-Policy-v3.3.docx` | 1.0000 | no content loss |
| `HR-Guide-Policy-and-Procedure-Template.pdf` | 1.0000 | no content loss |

Docling additionally recovers content the legacy path dropped: table headers (`Severity`, `SLA`, `Escalation Contact`), and on the PDF it resolves 148 list items against the legacy parser's 88 and extracts 82 table cells where the legacy PDF path found no tables at all.

The comparison is token-based rather than string- or element-based because the two converters legitimately disagree about segmentation. Comparing element counts would report a large difference that means nothing, while comparing text alone would report a relocated list marker as loss.

---

## 5. Verified invariants

Confirmed by executing against the real sample documents:

- every canonical element's recorded offsets slice back to exactly its text (`verify_fragments()` returns empty for both DOCX samples);
- repeat conversion of the same bytes reproduces identical element identities and identical page text;
- the structural graph reports zero coverage problems on both samples (22 nodes / 63 edges, and 41 nodes / 156 edges including table and header edges);
- heading paths resolve through the document title to each leaf clause;
- every installed file of `docling-graph`, `docling-slim`, and `docling-core` matches the SHA-256 digest recorded at install time.

---

## 6. The upload seam, and what selecting Docling measured

Until this was wired, `convert_document` had no production caller. Uploads went through `document_extraction.extract_document`, which called the legacy parser unconditionally, so the cell-level structure the rest of the pipeline is built on was unreachable outside tests and scripts.

`DOCUMENT_CONVERTER` (`legacy` | `docling`, default `legacy`) now selects the converter at that seam. It is distinct from `DOCLING_GRAPH_ENABLED`, which selects a model-driven dense-extraction backend and is a different concern.

### Measured on a 27-page bilingual HR handbook

Its last seven pages are a "Table of Violations and Penalties" whose columns are `1st Time / 2nd Time / 3rd Time / 4th Time`.

| | legacy | docling |
|---|---|---|
| elements | 522 | 797 |
| pages covered | 27/27 | 27/27 |
| `table_cell` | 0 | 540 |
| `table_row` | 91 | 0 |
| `table_cell_of` edges | 0 | 540 |
| `header_for` edges | 0 | 324 |
| reading-plan units | 157 | 192 |
| token recall vs the other | — | 6179/6196 (99.7%) |

The 17 token occurrences Docling has fewer of are all from a repeated copyright footer. On every substantive term Docling has more, and both parsers surface the same 9 quantified prose provisions, so the prose body does not regress.

Each escalation cell now carries its own column header: the four sanctions on offence row 1 of page 21 resolve to `1st Time`, `2nd Time`, `3rd Time` and `4th Time` respectively, which is what makes them four decisions rather than one.

### Two limits worth knowing before the default is flipped

- **Continuation tables carry no header.** Docling models each page's grid as its own table, and the appendix repeats its header only on pages 21 and 24. So 319 of 487 body cells (65.5%) get a `header_for` edge; on pages 22 and 27 none do. The cells and their column indices are still present and correct — only the association to a header printed on an earlier page is missing.
- **`merged_with` never fires.** `_add_table_edges` emits it by looking for a same-row cell in each column a span covers, but Docling represents a spanned region as one cell and emits nothing for the covered columns. The edge kind is currently unreachable from a Docling parse.

## 7. Text fidelity: display glyphs, and which converter reads in logical order

A second measurement on the same source, independent of table structure, found a defect that neither the table work nor the existing diagnostics could see.

Some PDF text extraction records the *painted glyph stream* rather than the characters the document contains. The stored codepoints are then Unicode presentation forms — the shaped glyph a renderer selected for a letter given its neighbours — and, depending on the extractor, the sequence may be the order the glyphs were painted rather than the order they are read in.

This is a general text-extraction defect. It affects any script whose letters have positional forms, and it affects an otherwise English document that quotes a single term in one of them. It is not a language feature and must not be treated as one.

### Why it survived every existing check

The platform promises that an attribute holds the source's words verbatim. A verbatim check compares a record against the canonical store — but when the canonical store holds glyphs, both sides hold the same glyphs and the check reports a match. A fidelity measurement taken this way read 92.6% while every affected span was wrong.

`rtl_script_detected` did not fire either. Its predicate is `bidirectional(char) in ("R","AL")`, which does match presentation forms, but it is gated on those characters exceeding 20% of all letters. On a bilingual document the affected script was 13.3% of letters, so the one diagnostic aimed near this problem stayed silent precisely because the document was mixed. It is also the wrong signal: it fires on correctly-encoded right-to-left text and says nothing about whether characters were preserved.

### Measured, same source, same run

| | legacy | docling |
|---|---:|---:|
| presentation-form codepoints | 5124 | 5586 |
| standard-block codepoints | 60 | 55 |
| elements carrying display glyphs | 68/522 (13.0%) | 283/797 (35.5%) |
| affected pages | 21–27 | 21–27 |
| character sequence | **visual** | **logical** |

Order was established with four probes, taking known logical strings and testing membership in each parser's NFKC-normalised output. All four appear in the Docling output and none in the legacy output; all four *reversed* appear in the legacy output and none in the Docling output.

On the appendix heading:

```
legacy  stored : <presentation forms>
legacy  NFKC   : تاءازجلاو تافلاخملا لوادج      <- normalises but reads backwards
legacy  NFKC[::-1] : جداول المخالفات والجزاءات   <- correct, only after reversing

docling stored : <presentation forms>
docling NFKC   : جداول المخالفات والجزاءات      <- correct, no reversal needed
```

So the two halves of the defect separate cleanly:

* **Character order** — legacy stores visual order; Docling stores logical order. Legacy output cannot be recovered by any order-preserving operation; restoring it would require reversing runs, which cannot be verified against the source and would corrupt text that is merely awkward.
* **Codepoint form** — both store presentation forms. This is recoverable in principle by NFKC, which maps each form to the character it renders, but that is a decision about altering quoted text and is deliberately not taken here.

Selecting Docling therefore fixes the unrecoverable half and leaves the recoverable half. That is a materially stronger argument for the cutover than table structure alone.

### The diagnostic

`document_extraction.detect_display_glyphs` is applied at the seam, after either converter returns, so neither path can be fixed while the other silently is not. It emits `display_glyphs_not_characters` at severity `warning` with the affected character count, the proportion of letters, and the affected pages.

The predicate is a Unicode-database property and nothing else: a codepoint is a display glyph when its compatibility decomposition tag is `<isolated>`, `<initial>`, `<medial>` or `<final>`. There is no script list, no language detection and no direction check, so any script Unicode gives positional forms is covered automatically and correctly-encoded text can never trip it. Verified silent on correctly-encoded Arabic, Hebrew, Farsi, Syriac, Thaana, Greek, CJK, Latin typographic ligatures and fullwidth forms; verified firing on display glyphs in any of them.

Nothing is normalised, reordered or rewritten. Detection only. A stored value that reads oddly is a defect a reviewer can see and weigh; a value silently rewritten into something the document does not literally contain is a defect nobody can see.

**Known limit.** This detects the presentation-form symptom, which is decidable from the character data. It does not detect visual ordering on its own — a parser that emitted standard codepoints in visual order would pass. In the sources measured the two travel together, and order is not decidable without language knowledge the ingestion layer deliberately does not have.

## 8. Which converter may be the default — settled by a paired control

The witness document stores its right-to-left runs in visual order. That makes it useless for the question that actually gates the cutover: does a converter change text that is already correct? On an already-reversed document, a converter that reverses everything looks like a fix.

Two controls were generated to answer it (`tests/fixtures/text-order/`, built by `make_controls.py`). Same characters, same embedded font, same `ToUnicode`, same geometry; the only difference is the order the glyphs are painted. Both were verified to carry standard codepoints and no presentation forms, so they measure order alone.

|                | paint order = logical | paint order = visual |
| -------------- | --------------------- | -------------------- |
| legacy parser  | preserved             | **reversed**         |
| docling        | **reversed**          | preserved            |

The results are exactly complementary. Neither converter inspects the direction evidence in the file; each applies a fixed policy. The legacy parser trusts paint order, which is correct only for producers that do no bidi layout. Docling reverses right-to-left runs, which is correct only for producers that do.

Two consequences.

**The default does not move.** Flipping it would not fix the fidelity defect; it would exchange one population of damaged documents for another, and the newly damaged population — correctly produced documents — is the one the platform is most likely to receive. The table-structure gains are real and remain available per document through `DOCUMENT_CONVERTER`.

**Cause C is now demonstrated, not merely read.** The left-to-right span sorts in the legacy parser were previously identified by inspection with no fixture to show them failing. The visual-order control is that fixture: the legacy parser returns it reversed. This is a defect in this codebase, independent of how any PDF encodes its text, and it is a text-direction defect rather than a language-specific one — the Hebrew and Arabic runs behave identically.

Neither result licenses a repair. Both converters would need to decide from per-run direction evidence rather than from a fixed assumption, and that is a change to what the extraction layer records, not a string transformation applied after the fact.
