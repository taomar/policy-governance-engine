# Docling Integration — Operating Notes

Findings from bringing Docling and Docling Graph into the platform. These are
measured behaviours, not expectations: each one was observed while running the
real dependencies against the repository's sample documents.

---

## 1. Environment

### Extraction runs in a separate environment from the API

`docling` resolves to `docling-slim[standard]`, which installs `torch`,
`torchvision`, `accelerate`, `rapidocr`, `scipy`, and `transformers`. The API
runtime image is `python:3.11-slim` with pdfplumber and python-docx and must not
carry that footprint.

The two environments also have a **hard dependency conflict**, so merging them
is not merely undesirable:

| Package | API runtime | Extraction |
|---|---|---|
| `httpx` | `>=0.27,<0.28` (project pin) | `>=0.28` (required by `litellm`) |

The extraction dependencies are therefore an optional extra:

```bash
python -m venv .venv-graph
.\.venv-graph\Scripts\python.exe -m pip install "docling-graph==1.9.1"
```

### PDF conversion needs dynamo disabled on Windows

Docling's PDF pipeline runs layout models through torch. On Windows without a
Visual C++ toolchain, `torch.compile` fails with `InvalidCxxCompiler: Compiler:
cl is not found` and conversion aborts.

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

PDF conversion is roughly three orders of magnitude slower than DOCX because it
runs layout inference per page. Any ingestion flow that converts PDF
synchronously inside a request will time out; this is a direct input to the
durable stage-execution work.

---

## 2. Upstream API notes

### `docling_graph.utils` does not exist in 1.9.1

The upstream README shows:

```python
from docling_graph.utils import edge
```

That module is not present in the released package. `edge` is a **template-local
helper**: `docling_graph/templategen/snippets.py` emits its source into generated
templates rather than exporting it. The public contract is the
`json_schema_extra` convention it writes:

| Key | Meaning |
|---|---|
| `edge_label` | Relationship name for this field |
| `graph_reference` | Identity-only link, filled by the parent's own call |
| `reference_closed_catalog` | Targets form a closed catalog defined elsewhere |

`PolicyDocumentGraphV1` defines its own `edge()` helper against these keys, which
keeps the template on the documented public convention with no dependency on
package internals.

### `NodeCatalog.paths` is a method

`build_node_catalog(...)` returns a `NodeCatalog` whose `paths` is a **method**,
not a property. `set(catalog.paths)` silently produces a set containing a bound
method rather than failing, so a test written against it passes while asserting
nothing. Use `{node.path for node in catalog.nodes}`.

This was caught by a compatibility test and is the reason the template is
validated against Docling Graph's real catalog builder rather than against our
own metadata.

### Validated template structure

`build_node_catalog(PolicyDocumentGraphV1)` resolves 11 candidate paths, all
classified as entities, in this bottom-up fill order:

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

Supporting material is filled before the units it governs, which is what makes
attachment reliable.

---

## 3. Conversion behaviour

### DOCX has no pagination

Docling reports `pages = 0` for DOCX because page breaks are decided by the
renderer, not stored in the file. The canonical adapter models a DOCX as one
logical page, matching the legacy behaviour, so downstream consumers need no
special case. **Page-based anchoring is unusable for DOCX sources.**

### Table structure is fully exposed

Docling provides per-cell `start_row_offset_idx`, `start_col_offset_idx`,
`row_span`, `col_span`, and `column_header`. This is what allows cells to keep
their exact values while carrying their position and merge span structurally,
instead of the legacy DOCX path's `"Tier: 2; Limit: 5000"` prose — text that
appears nowhere in the source and therefore fabricated any passage quoted from
it.

### PDF geometry uses a bottom-left origin

PDF provenance returns `CoordOrigin.BOTTOMLEFT`. Most renderers are top-left, so
the origin is recorded on every bounding box. A silently flipped highlight looks
to a reviewer like a wrong extraction.

### List enumeration labels are structure, not text

Docling strips the enumeration label from a list item's text and exposes it as
`ListItem.marker` with an `enumerated` flag:

| | Text |
|---|---|
| Legacy | `"D. The outside employment should not embarrass the Foundation."` |
| Docling | `"The outside employment should not embarrass the Foundation."` + `marker="D."` |

Nothing is lost by the converter, but the label a reviewer cites ("Section 5.D")
disappears unless captured explicitly. `CanonicalElement` therefore carries
`list_marker` and `list_enumerated`, held separately from `text` so the text
stays exactly what was extracted.

The marker is deliberately **excluded from element identity**: a converter
upgrade that relabels `D.` as `4.` changes presentation, not the clause, and
must not repoint stored spans.

Measured on the 53-page PDF: 146 list items carry a marker, 83 of them
enumerated. The rest are bullets, which identify nothing and are unusable in a
citation.

### Docling occasionally joins words without a space

At some line breaks Docling concatenates without a separator, producing tokens
such as `SafetyAct`, `EmploymentStandards`, and `WorkSafe`. Seven such elements
were found in the 53-page PDF.

These are **reported, never repaired**. Inserting a space would rewrite
canonical text, which is exactly what INVARIANT 6 forbids: every character of an
element must come from the source. A reviewer seeing a
`suspected_missing_space` diagnostic can judge it; a silently corrected string
cannot be audited, and the same heuristic would eventually corrupt a legitimate
compound. The diagnostic is `info` severity and does not fail the document.

---

## 4. Shadow comparison results

Legacy parsers versus Docling across the sample corpus, measured by whether
content tokens survived (`scripts/docling_shadow_report.py`):

| Document | Recall | Verdict |
|---|---|---|
| `HR-Special-Leave-Policy-v1.0.docx` | 1.0000 | no content loss |
| `IT-Security-Incident-Emergency-Access-Policy-v1.0.docx` | 1.0000 | no content loss |
| `Workplace-Hardware-Provisioning-Policy-v3.2.docx` | 1.0000 | no content loss |
| `Workplace-Hardware-Provisioning-Policy-v3.3.docx` | 1.0000 | no content loss |
| `HR-Guide-Policy-and-Procedure-Template.pdf` | 1.0000 | no content loss |

Docling additionally recovers content the legacy path dropped: table headers
(`Severity`, `SLA`, `Escalation Contact`), and on the PDF it resolves 148 list
items against the legacy parser's 88 and extracts 82 table cells where the
legacy PDF path found no tables at all.

The comparison is token-based rather than string- or element-based because the
two converters legitimately disagree about segmentation. Comparing element
counts would report a large difference that means nothing, while comparing text
alone would report a relocated list marker as loss.

---

## 5. Verified invariants

Confirmed by executing against the real sample documents:

- every canonical element's recorded offsets slice back to exactly its text
  (`verify_fragments()` returns empty for both DOCX samples);
- repeat conversion of the same bytes reproduces identical element identities
  and identical page text;
- the structural graph reports zero coverage problems on both samples
  (22 nodes / 63 edges, and 41 nodes / 156 edges including table and header
  edges);
- heading paths resolve through the document title to each leaf clause;
- every installed file of `docling-graph`, `docling-slim`, and `docling-core`
  matches the SHA-256 digest recorded at install time.
