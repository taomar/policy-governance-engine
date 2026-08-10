# Docling Integration — Handoff Summary

**Branch:** `taomar-microsoft-advancedtooling`
**Base commit:** `bcb4f7a` on `main`
**12 commits · 39 files · +9,259 lines · 775 unit tests passing**

Everything is additive. No existing module was rewritten, no table was altered,
no migration was added. Reverting is a single branch drop.

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
```

Each commit is self-contained and leaves the suite green, so the sequence can be
stopped at any point.

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

### Infrastructure — `src/policy_platform/infrastructure/docling/`
| File | Purpose |
|---|---|
| `dependency_provenance.py` | Pins `docling-graph==1.9.1`; verifies files against `RECORD` SHA-256 |
| `converter.py` | `convert(source_release) -> canonical artifact` |
| `graph_runtime.py` | Dense-extraction config against `foundryfordevtarek` |
| `verification.py` | Independent pass: hard failures vs reviewable conditions |
| `pipeline.py` | One-file, stage-recorded extraction pipeline |
| `shadow_comparison.py` | Legacy-vs-Docling fidelity measurement |

### Scripts, docs, tests
- `scripts/docling_shadow_report.py`, `scripts/docling_corpus_report.py` — both exit non-zero on failure, usable as CI gates
- `docs/specs/docling-integration-{conformance-map,operating-notes,runbook}.md`
- `docs/specs/docling-{shadow-comparison,corpus}-report.md` — generated evidence
- 13 test modules under `tests/unit/`

---

## 3. Modified files (all additive)

| File | Change |
|---|---|
| `contracts/canonical_document.py` | Added geometry, merged-cell lineage, list depth + **marker**, caption/footnote links, `self_ref`, `normalized_text`, `ConversionProvenance`, `fidelity`; extended `ElementType` |
| `infrastructure/settings.py` | Added `docling_graph_enabled`, `docling_graph_model`, `graph_extraction_enabled` |
| `pyproject.toml` | Added optional extra `graph = ["docling-graph==1.9.1"]` |
| `.env.example` | Foundry endpoint + graph settings (no key) |
| `.gitignore` | `.venv-graph/` |

**No changes** to: routers, repositories, `domain/models.py`, evaluator, search, or any DMN contract.

---

## 4. Setup in the target fork

```powershell
python -m venv .venv-graph
.\.venv-graph\Scripts\python.exe -m pip install -e ".[graph]"
$env:TORCHDYNAMO_DISABLE = "1"   # Windows without a C++ toolchain; PDF only
```

`.env`:
```
AZURE_OPENAI_ENDPOINT=https://foundryfordevtarek.cognitiveservices.azure.com/
AZURE_OPENAI_API_KEY=<key>
AZURE_OPENAI_DEPLOYMENT=gpt-4o
DOCLING_GRAPH_ENABLED=false      # deterministic pipeline works fully without it
DOCLING_GRAPH_MODEL=azure/gpt-4o
```

**Extraction must use its own venv** — not a preference: `litellm` requires
`httpx>=0.28` while the API pins `<0.28`.

---

## 5. Verification (expected results)

```powershell
$env:PYTHONPATH="src"
.\.venv-graph\Scripts\python.exe -m pytest tests/unit -q                        # 775 passed
.\.venv-graph\Scripts\python.exe scripts/docling_shadow_report.py               # exit 0
.\.venv-graph\Scripts\python.exe scripts/docling_corpus_report.py --pdf --repeats 2   # exit 0
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

## 8. Not built — verify before promising these

Found absent during Phase 0; the directive assumes they exist:

| Gap | Consequence |
|---|---|
| Durable job/worker system | PDF takes **195 s** — cannot convert in-request |
| DMN compile + parity harness | Only a FEEL unary-test *parser* exists |
| Runtime approved Search projection | Only draft `policy-authoring`; `status` hardcoded `"draft"` |
| Candidate-intake handoff adapter | Package is produced but not submitted |

Also unexercised here: live dense extraction (no API key), persistence (no Postgres), and Search.

---

## 9. Invariants covered by tests

1. Every element's offsets slice back to exactly its text.
2. No identity depends on a display label, filename, list position or graph node ID.
3. Evidence text is copied by the application, never accepted from a model.
4. Canonical text is never rewritten to repair a converter artifact.
5. Every canonical leaf gets exactly one coverage disposition.
6. Upstream Docling code is never edited or patched.
7. Identical bytes yield identical identities and the same idempotency key.
