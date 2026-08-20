# Docling Integration — Handoff Summary

**Branch:** `taomar-microsoft-advancedtooling` **Base commit:** `bcb4f7a` on `main` **20 commits · 56 files · +13,097 lines · 912 Python tests + clean web build**

All 16 directive deliverables are implemented. Everything is additive: no existing module was rewritten, and the one migration only creates a new table. Reverting is a branch drop plus one `alembic downgrade`.

---

## 1. Replicate by cherry-picking, in order

```bash
git cherry-pick 7c4e213   # deps pinned + canonical contracts extended
git cherry-pick 3cc54d5   # Docling -> canonical converter
git cherry-pick ccaed15   # deterministic structural graph
git cherry-pick ae4c0fa   # PolicyDocumentGraphV1 template
git cherry-pick a1ceb0c   # graph run health + coverage gates
git cherry-pick 9c8bf23   # list markers + join diagnostics (closes PDF gate)
git cherry-pick fde4a9e   # graph-aware context assembly
git cherry-pick c9b904f   # evidence resolution + Foundry runtime
git cherry-pick 61cae62   # extraction package + handoff boundary
git cherry-pick 47d5527   # verification pass + end-to-end pipeline
git cherry-pick 9597e34   # corpus report + coverage gate fix
git cherry-pick c4867fd   # runbook
git cherry-pick 2c73acb   # this handoff summary
git cherry-pick 8c849ea   # DMN compile + parity harness
git cherry-pick fd8b622   # idempotent handoff adapter
git cherry-pick be642e1   # review vs runtime Search projections
git cherry-pick 4077e41   # durable extraction stages (+ migration)
git cherry-pick 33a8434   # extraction API surface
git cherry-pick 8a2cfa3   # web extraction detail drawer
```

Each commit is self-contained and leaves the suite green, so the sequence can be stopped at any point.

---

## 2. New files

### Contracts — `src/policy_platform/contracts/`
| File | Purpose |
|---|---|
| `element_identity.py` | Content+structure-derived element IDs, replacing ordinal `E000001` |
| `structural_graph.py` | Deterministic LLM-free graph, 10 edge kinds, coverage verification |
| `policy_document_graph.py` | `PolicyDocumentGraphV1` extraction template |
| `graph_run.py` | Run config, health stats, coverage report, gate evaluation |
| `reading_plan.py` | Graph-aware context units (replaces fixed windows) |
| `evidence_resolution.py` | Pointer-only spans, exact-span resolution, coverage accounting |
| `extraction_package.py` | Versioned package + application handoff boundary |

### Infrastructure — `src/policy_platform/infrastructure/`
| File | Purpose |
|---|---|
| `docling/dependency_provenance.py` | Pins `docling-graph==1.9.1`; verifies files against `RECORD` SHA-256 |
| `docling/converter.py` | `convert(source_release) -> canonical artifact` |
| `docling/graph_runtime.py` | Dense-extraction config against `foundryfordevtarek` |
| `docling/verification.py` | Independent pass: hard failures vs reviewable conditions |
| `docling/pipeline.py` | One-file, stage-recorded extraction pipeline |
| `docling/shadow_comparison.py` | Legacy-vs-Docling fidelity measurement |
| `docling/handoff.py` | Idempotent submission into the existing candidate-intake |
| `dmn_parity.py` | FEEL compile + canonical-vs-DMN parity harness |
| `search/projection.py` | Review vs runtime Search projections + pre-activation verification |
| `extraction_stage_repository.py` | Durable stage persistence |

### API and web
- `api/routers/extraction.py` — five read-only GET endpoints (canonical, structure, reading plan, stages, coverage)
- `apps/web/src/components/ExtractionInsightDrawer.tsx` + `extractionApi` in `api.ts`

### Database
- `alembic/versions/e7f4a9c2b615_extraction_stages_table.py` — creates `extraction_stages`; additive and reversible

### Scripts, docs, tests
- `scripts/docling_shadow_report.py`, `scripts/docling_corpus_report.py` — both exit non-zero on failure, usable as CI gates
- `docs/specs/docling-integration-{conformance-map,operating-notes,runbook,handoff}.md`
- `docs/specs/docling-{shadow-comparison,corpus}-report.md` — generated evidence
- 18 test modules under `tests/unit/`

---

## 3. Modified files (all additive)

| File | Change |
|---|---|
| `contracts/canonical_document.py` | Added geometry, merged-cell lineage, list depth + **marker**, caption/footnote links, `self_ref`, `normalized_text`, `ConversionProvenance`, `fidelity`; extended `ElementType` |
| `contracts/extraction_package.py` | Added `dmn_decisions` so verification can compile and prove parity |
| `domain/models.py` | Added `ExtractionStage` (new table only) |
| `api/app.py` | Registered the extraction router |
| `infrastructure/settings.py` | Added `docling_graph_enabled`, `docling_graph_model`, `graph_extraction_enabled` |
| `pyproject.toml` | Optional extra `graph = ["docling-graph==1.9.1"]`; `aiosqlite` for dev |
| `apps/web/src/api.ts` | Added `extractionApi` + its types |
| `apps/web/src/components/DocumentsPage.tsx` | Added the "Extraction detail" action |
| `.env.example`, `.gitignore` | Foundry endpoint (no key); `.venv-graph/` |

**No changes** to: candidate-rule/review/approval/publication routers, repositories, evaluator, or any DMN contract.

---

## 4. Setup in the target fork

### Setup

```powershell
python -m venv .venv-graph
.\.venv-graph\Scripts\python.exe -m pip install -e ".[graph,dev]"
$env:TORCHDYNAMO_DISABLE = "1"   # Windows without a C++ toolchain; PDF only
```

Copy `.env.example` to `.env` and fill in the database URLs plus, if you want live extraction, `AZURE_OPENAI_API_KEY`.

**Extraction must use its own venv** — not a preference: `litellm` requires `httpx>=0.28` while the API pins `<0.28`.

### Ports and CORS

Both live in `.env`, not in code:

```
API_PORT=8010
WEB_DEV_SERVER_PORT=5490      # Vite binds here AND the API admits this origin
VITE_API_BASE_URL=http://localhost:8010
CORS_ALLOWED_ORIGINS=         # empty = derive; set explicitly when deployed
CORS_DEV_PORT_RANGE=5173-5180
```

`vite.config.ts` reads `WEB_DEV_SERVER_PORT` with `strictPort`, so the dev server fails rather than drifting onto a port the API would reject. That mismatch is worth preventing because it presents as a broken backend: the browser blocks the request and nothing appears in the server log.

---

## 5. Verification (expected results)

```powershell
$env:PYTHONPATH="src"
.\.venv-graph\Scripts\python.exe -m pytest tests/unit -q                        # 912 passed
.\.venv-graph\Scripts\python.exe scripts/docling_shadow_report.py               # exit 0
.\.venv-graph\Scripts\python.exe scripts/docling_corpus_report.py --pdf --repeats 2   # exit 0
cd apps/web; npm install; npm run build; npx oxlint                             # clean
```

| Document | Coverage | Blockers | Stability |
|---|---|---|---|
| HR-Special-Leave v1.0 | 14/14 | 0 | identical |
| IT-Security-Incident v1.0 | 32/32 | 0 | identical |
| Workplace-Hardware v3.2 | 202/202 | 0 | identical |
| Workplace-Hardware v3.3 | 206/206 | 0 | identical |
| HR-Guide PDF (53pp) | 619/619 | 0 | identical |

Shadow comparison: **1.0000 token recall on all 5, zero content loss.**

---

## 6. Decisions worth preserving

1. **Provenance via packaging metadata, not a vendored tree.** Cloning was measured — docling is ~202 MB, ~197 MB of it tests/docs. Wheels are immutable; `.dist-info/RECORD` carries a SHA-256 per file. `docling-slim` is verified explicitly because `docling` is a 5-file meta-package.
2. **No alignment layer.** Canonical text is built *from* Docling in reading order, so `verify_fragments()` holds by construction and there is never a second text authority.
3. **Element identity is content+structure derived.** The old ordinal scheme was globally unstable under a local change: one newly detected element renumbered everything after it, silently repointing published spans. Legacy IDs stay recognised — published releases are never recanonicalized.
4. **One model configuration.** Dense extraction routes through LiteLLM at the platform's existing Azure OpenAI deployment, so the two cannot drift.

---

## 7. Two real findings, both fixed

- **List markers stripped.** Docling holds `D.` as structure, not text — the label reviewers cite ("Section 5.D") was lost. Captured as `list_marker`/`list_enumerated`, excluded from identity so renumbering can't repoint spans. (146 markers on the PDF, 83 enumerated.)
- **Missing-space joins.** Docling occasionally emits `SafetyAct` across a line break. Reported as an `info` diagnostic, **never repaired** — rewriting canonical text would violate INVARIANT 6.

A third was caught by the corpus gate itself: 40 headings governing no content had no disposition. Fixed narrowly (headings only, confirmed empty by the graph) so the check that catches real loss still fires.

---

## 8. Built, but not exercised end to end here

All 16 deliverables exist, and the stack was run locally against Postgres.

**Verified live** (Postgres 5433, API 8010, UI 5490): all migrations apply to a fresh database including `extraction_stages`; the five extraction endpoints answer against a real uploaded document; CORS admits the configured origin and refuses an unlisted one; coverage reports 17/17 with zero unaccounted elements.

**Still untested against the real dependency**, because no credential was configured:

| Component | Needs |
|---|---|
| Dense extraction (live model calls) | `AZURE_OPENAI_API_KEY` |
| Handoff submission | a policy set exercised through candidate intake |
| Search projections | an Azure AI Search index |

Two follow-ups worth scheduling: a **worker/queue** for conversion (PDF takes 195 s, so it cannot run in-request), and the **publisher** that writes the runtime projection and flips activation after `verify_projection` passes.

### Local database note

The shared `policy_platform` database is stamped at a revision that does not exist on this branch, so migrations were applied to a separate `policy_platform_advtool` database rather than migrating another branch's working state. Point `DATABASE_URL` wherever is appropriate in the target fork.

---

## 9. Invariants covered by tests

1. Every element's offsets slice back to exactly its text.
2. No identity depends on a display label, filename, list position or graph node ID.
3. Evidence text is copied by the application, never accepted from a model.
4. Canonical text is never rewritten to repair a converter artifact.
5. Every canonical leaf gets exactly one coverage disposition.
6. Upstream Docling code is never edited or patched.
7. Identical bytes yield identical identities and the same idempotency key.
