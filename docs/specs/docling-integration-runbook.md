# Docling Integration — Migration and Operating Runbook

How to enable, run, verify, and roll back the Docling extraction path. Every
number here was measured on this repository's sample corpus; nothing is
projected.

---

## 1. What is in place, and what is not

**Working and verified end to end:**

| Capability | State |
|---|---|
| Docling conversion → canonical document | working, exact-span verified |
| Deterministic element identity | working, replaces ordinal IDs |
| Deterministic structural graph | working, lossless |
| Graph-aware reading plan | working, exhaustive on all fixtures |
| Pointer-only evidence resolution | working |
| Per-element coverage accounting | working, 100% on all fixtures |
| Independent verification pass | working |
| Stage-recorded pipeline | working |
| Dependency integrity gate | working |
| DMN compile + parity harness | working, wired into verification |
| `PolicyDocumentGraphV1` template | validated against Docling Graph's catalog builder |
| Extraction API + web drawer | working, build and lint clean |

**Built but not exercised in this environment** — each needs a credential or
service that was not configured, so treat these as untested against the real
dependency:

| Component | Needs |
|---|---|
| Dense extraction (live model calls) | `AZURE_OPENAI_API_KEY` |
| Handoff submission | a policy set + candidate intake exercised end to end |
| Runtime Search projection | an Azure AI Search index |

**Verified against a live stack** (Postgres on 5433, API on 8010, UI on 5490):

- all migrations apply cleanly to a fresh database, including `extraction_stages`;
- the five extraction endpoints answer against a real uploaded document;
- CORS admits the configured UI origin and refuses an unlisted one;
- coverage reports 17/17 with zero unaccounted elements on the IT policy.

**Still to build:**

| Gap | Consequence |
|---|---|
| Worker/queue for conversion | PDF takes 195 s and cannot run in-request |
| Search publisher + activation flip | `verify_projection` exists; nothing calls it against a live index |

---

## 2. Enabling extraction

### Environment

Extraction runs in its own environment. This is not a preference: `litellm`
requires `httpx>=0.28` while the API pins `<0.28`, so the two cannot share one
interpreter.

```powershell
python -m venv .venv-graph
.\.venv-graph\Scripts\python.exe -m pip install -e ".[graph]"
```

### Configuration

Copy `.env.example` to `.env` and set:

```
AZURE_OPENAI_ENDPOINT=https://foundryfordevtarek.cognitiveservices.azure.com/
AZURE_OPENAI_API_KEY=<key>
AZURE_OPENAI_DEPLOYMENT=gpt-4o
DOCLING_GRAPH_ENABLED=true
DOCLING_GRAPH_MODEL=azure/gpt-4o
```

Dense extraction routes through LiteLLM at the platform's existing Azure OpenAI
deployment. There is deliberately no second endpoint: two model configurations
drift, and the resulting failure is a run extracted by a different model than
the one that was validated.

`DOCLING_GRAPH_ENABLED=false` leaves the deterministic pipeline fully
functional — a document can still be converted, structured, planned, coverage-proven
and verified. Only candidate discovery is skipped.

### Windows PDF prerequisite

```powershell
$env:TORCHDYNAMO_DISABLE = "1"
```

Without it, Docling's PDF pipeline fails with `InvalidCxxCompiler: Compiler: cl
is not found` on machines with no Visual C++ toolchain. DOCX is unaffected.

### Running the stack locally

```powershell
# 1. Database
docker start policy-postgres
$env:PYTHONPATH = "src"
.\.venv-graph\Scripts\python.exe -m alembic upgrade head

# 2. API. `--host ::` binds dual-stack, which matters more than it looks:
#    uvicorn defaults to 127.0.0.1 (IPv4 only), while browsers resolve
#    "localhost" to ::1 first. The result is every request failing as
#    "TypeError: Failed to fetch" while curl and the health check both pass,
#    because command-line clients prefer IPv4.
.\.venv-graph\Scripts\python.exe -m uvicorn policy_platform.api.app:app --host :: --port 8010

# 3. UI (separate shell)
cd apps/web; npm install; npm run dev
```

| Surface | URL |
|---|---|
| UI | `http://localhost:5490` |
| API | `http://localhost:8010` |
| OpenAPI | `http://localhost:8010/docs` |

**Ports and CORS live in `.env`, not in code.** `WEB_DEV_SERVER_PORT` sets the
port Vite binds to *and* the origin the API admits, so moving the UI is a
one-line change. `vite.config.ts` reads the same value with `strictPort`, which
means the dev server fails rather than silently moving to a port the API would
reject — a mismatch there presents as a broken backend, because the browser
blocks the request and the server logs nothing.

Set `CORS_ALLOWED_ORIGINS` explicitly for a deployed environment. An explicit
list is used verbatim and is never widened by the development range.

To verify CORS without a browser:

```powershell
curl.exe -s -i "http://localhost:8010/api/policy-sets" -H "Origin: http://localhost:5490"
# expect: access-control-allow-origin: http://localhost:5490

curl.exe -s -i "http://localhost:8010/api/policy-sets" -H "Origin: http://evil.example.com"
# expect: no access-control-allow-origin header at all
```

---

## 3. Verifying a deployment

Run these in order. Each is fast except the last.

```powershell
# 1. Dependency integrity — no upstream file may differ from its recorded hash
.\.venv-graph\Scripts\python.exe -m pytest tests/unit/test_dependency_provenance.py -q

# 2. Full unit suite
$env:PYTHONPATH="src"
.\.venv-graph\Scripts\python.exe -m pytest tests/unit -q

# 3. Apply the extraction-stages migration
alembic upgrade head

# 4. Fidelity against the legacy parsers (DOCX only, ~5s)
.\.venv-graph\Scripts\python.exe scripts/docling_shadow_report.py

# 5. Acceptance gates across the corpus (add --pdf for the full run, ~7 min)
.\.venv-graph\Scripts\python.exe scripts/docling_corpus_report.py --pdf --repeats 2

# 6. Web surfaces
cd apps/web; npm install; npm run build; npx oxlint
```

Both scripts exit non-zero on failure, so they are usable as CI gates.

### Expected results

| Check | Expected |
|---|---|
| Unit tests | 912 passed |
| Shadow comparison | 5 documents, 1.0000 token recall, zero content loss |
| Corpus report | 5 documents PASS, 100% coverage, zero blockers, runs identical |
| Web build | `tsc -b` and `vite build` clean, oxlint clean |

---

## 4. Measured performance

| Source | Elements | Conversion |
|---|---|---|
| `HR-Special-Leave-Policy-v1.0.docx` | 22 | 0.12 s |
| `IT-Security-Incident-...docx` | 41 | 0.11 s |
| `Workplace-Hardware-...v3.2.docx` | 280 | 0.6 s |
| `HR-Guide-...Template.pdf` (53 pages) | 782 | **~195 s** |

PDF conversion is roughly three orders of magnitude slower than DOCX because it
runs layout inference per page. **Any ingestion flow that converts PDF
synchronously inside a request will time out.** This is the single hardest
constraint on the durable-job work.

---

## 5. Cutover

The directive permits the legacy parser to run in shadow mode for migration QA
only, then requires its removal from the new-ingestion path.

1. **Shadow.** Run `docling_shadow_report.py` on the real corpus. Cutover is
   blocked while any document reports content loss.
2. **Enable.** Point new ingestion at `convert_document`. Old releases keep their
   existing canonical artifacts and ordinal element IDs — the directive forbids
   silently recanonicalizing them, and `is_legacy_element_id` exists so both
   forms resolve side by side.
3. **Observe.** Watch `suspected_missing_space` diagnostics and coverage
   verdicts on newly ingested documents.
4. **Remove.** Once the gates hold on production documents, drop the legacy
   parser from the new-ingestion path only.

### Rollback

Re-point ingestion at `document_extraction.extract_document`, and
`alembic downgrade -1` if the stages table is unwanted. Nothing else needs
undoing: the Docling path is additive, alters no existing table, and previously
ingested releases are untouched by either direction of the switch.

---

## 6. Operating diagnostics

| Code | Severity | Meaning | Action |
|---|---|---|---|
| `unsupported_source` | error | No native text layer | Reject. The directive forbids adding OCR. |
| `suspected_missing_space` | info | Words joined at a line break (`SafetyAct`) | Review. Text is never repaired — rewriting it would violate INVARIANT 6. |
| `duplicate_element` | info | Two elements identical in type, position and text | Usually a repeated table row. Verify it is not a converter emitting twice. |

### Gate findings

| Finding | Severity | Meaning |
|---|---|---|
| `dropped_chunks` | blocker | Content was lost during discovery |
| `skeleton_batches_failed` | blocker | A batch could not be split or retried far enough |
| `unaccounted_elements` | blocker | An element was never considered |
| `unresolved_elements` | warning | Deliberately marked unclassifiable |
| `weak_provenance` | warning | Candidates lack verbatim location |
| `synthetic_parents`, `orphan_nodes` | warning | Graph structure needs review |

A blocker means the package asserts something untrue and cannot be reviewed into
correctness. A warning means it is honest but uncertain, which is what the
review workbench is for.

---

## 7. Failure triage

**Conversion fails.** Check the `docling_converted` stage detail. `cl is not
found` means `TORCHDYNAMO_DISABLE=1` is unset. `unsupported_source` means an
image-only PDF, which is out of scope.

**`canonical_artifact_frozen` fails.** Fragments do not resolve. This should be
impossible — canonical text is constructed from the elements themselves — so
treat it as a converter regression and do not accept the run.

**`context_units_assembled` fails.** The reading plan is not exhaustive; some
targetable element belongs to no unit. Check for an element type missing from
`_TARGETABLE`.

**`verification_completed` fails on coverage.** An element received no
disposition. Inspect `coverage.unaccounted_element_ids` — a class of element the
run does not know how to classify usually indicates a new document shape.

**Dependency integrity fails.** An upstream file differs from its installed
hash. Do not patch it. Reinstall the pinned version; if the difference persists,
treat it as a supply-chain event.

**The UI shows "TypeError: Failed to fetch" while the API health check passes.**
Almost always a bind-address mismatch rather than a CORS problem. Browsers
resolve `localhost` to `::1` (IPv6) first, while uvicorn defaults to `127.0.0.1`
(IPv4 only) — so command-line clients succeed and the browser does not. Confirm
with:

```powershell
curl.exe -s -o NUL -w "v4=%{http_code}`n" http://127.0.0.1:8010/health
curl.exe -s -o NUL -w "v6=%{http_code}`n" "http://[::1]:8010/health"
```

If v4 succeeds and v6 fails, restart the API with `--host ::`. A genuine CORS
failure looks different: the response arrives but carries no
`access-control-allow-origin` header.

---

## 8. Invariants that must not regress

1. Every canonical element's offsets slice back to exactly its text.
2. No canonical identity depends on a display label, filename, list position or
   graph node ID.
3. Evidence text is copied by the application, never accepted from a model.
4. Canonical text is never rewritten to repair a converter artifact.
5. Every canonical leaf receives exactly one coverage disposition.
6. Upstream Docling code is never edited, patched or monkey-patched.
7. Re-running extraction on identical bytes yields identical identities and the
   same idempotency key.

Each is covered by at least one test. A change that breaks one should fail the
suite rather than reach review.
