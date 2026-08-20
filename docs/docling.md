# Docling — document conversion and graph discovery

Docling is how a PDF or DOCX becomes structured, offset-anchored elements the platform can point at. It replaces nothing about how policy is *decided*; it changes what the extraction has to read.

## The two packages

| Package | Pin | Role |
|---|---|---|
| `docling` | `2.118.0` | Converts PDF/DOCX to a structured document with layout, tables, headings and page geometry |
| `docling-graph` | `1.9.1` | Dense extraction over that document, producing a candidate graph of entities and relations |

Both are **exactly pinned**, not ranged. Conversion output is an input to every downstream identity and offset in the system, so a patch release that changes element ordering or text normalisation silently changes rule identity. See `infrastructure/docling/dependency_provenance.py` for the provenance record and why a range is not acceptable here.

## Deliberately optional

`docling` resolves to `docling-slim[standard]`, which pulls **torch, torchvision, accelerate and scipy**. Neither the API's startup nor its extraction path imports any of it — verified, not assumed — so the runtime image must not carry that footprint. Shipping it would make a policy decision service depend on a machine-learning stack it never calls.

There is a second, harder reason to keep it separate: `docling-graph` pulls `litellm`, which requires `httpx>=0.28`, while the API pins `httpx>=0.27,<0.28`. Installing the extra **resolves httpx above the API's own pin**. `pip check` reports nothing, because the constraint lives in an extra rather than in the installed distribution's metadata — so the divergence is silent.

```powershell
# Runs the API. Does not run the full test suite — 13 modules import
# Docling directly and fail at collection here.
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"

# Conversion work and the full test suite, at the cost of httpx 0.28
python -m venv .venv-graph
.\.venv-graph\Scripts\python.exe -m pip install -e ".[dev,graph]"
```

`scripts/run_api.ps1` prefers `.venv` and falls back to `.venv-graph`, so a checkout set up for conversion still runs the API without a second install.

## What conversion produces

| Concern | Module |
|---|---|
| Docling document → canonical elements | `infrastructure/docling/converter.py` |
| Deterministic structural graph | `infrastructure/docling/pipeline.py` |
| Graph run health and coverage gates | `infrastructure/docling/graph_runtime.py` |
| Verification pass | `infrastructure/docling/verification.py` |
| Shadow comparison against the legacy parser | `infrastructure/docling/shadow_comparison.py` |
| Handoff to the extraction boundary | `infrastructure/docling/handoff.py` |

Element identity is the platform's own, derived deterministically from verified source spans. **Docling display labels and graph ids are never reused** as identity — they are a vendor's presentation choice and would make rule identity depend on a library version.

## Two behaviours worth knowing

Both were found by shadow comparison against the previous parser, and both are **reported rather than repaired** — silently rewriting a document's text is how a citation stops matching its source.

- **List markers are structure, not text.** Docling strips `D.`, `H.` and similar into structural metadata. They are captured as `list_marker` / `list_enumerated` rather than lost.
- **Words occasionally join across line breaks** (`SafetyAct`). Flagged with a `suspected_missing_space` diagnostic. Never auto-corrected.

With both handled, recall against the corpus is `1.0000` across all documents — see [the corpus report](specs/docling-corpus-report.md).

## Running conversion

PDF conversion is slow enough to rule out doing it inside a request: roughly **195 seconds** for a PDF against **0.3 seconds** for a DOCX. Extraction is a background run with durable stages, not a synchronous call.

On Windows, PDF conversion needs `TORCHDYNAMO_DISABLE=1`; without it torch attempts a C++ compile and fails with `InvalidCxxCompiler: cl not found`.

## Graph discovery is a shadow, not an authority

`docling-graph` produces a `PolicyDocumentGraphV1` candidate — a versioned, domain-neutral template. It **enriches** the reading plan, context assembly and relationship candidates. It does not replace source spans, pointer-only selection, exact-span resolution, the canonical rule, mapping snapshots, canonical identities or the DMN/FEEL projection.

Provenance strength is recorded on every node and edge: `verbatim`, `observed`, `derived`, `unresolved`. Coverage gates fail a run that drops chunks or leaves material nodes unresolved, so a partial read is a failure rather than a quiet subset.

## Reference

| Document | Contents |
|---|---|
| [Runbook](specs/docling-integration-runbook.md) | How to run and verify a conversion |
| [Operating notes](specs/docling-integration-operating-notes.md) | Measured behaviour and environment quirks |
| [Conformance map](specs/docling-integration-conformance-map.md) | What was preserved, adapted, replaced |
| [Corpus report](specs/docling-corpus-report.md) | Recall and coverage across the document corpus |
| [Shadow comparison](specs/docling-shadow-comparison-report.md) | Docling against the previous parser |
| [Handoff](specs/docling-integration-handoff.md) | Replication guide |
