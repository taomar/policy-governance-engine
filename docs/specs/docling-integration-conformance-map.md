# Docling Integration — Repository Conformance Map

**Directive:** `OPUS_DOCLING_GRAPH_END_TO_END_PLAN.md`, Phase 0.
**Purpose:** classify every area the directive touches as **preserve**, **adapt**, **replace**, or **missing**, so the integration extends what exists instead of building a parallel policy framework (directive §10, §12).

This document records the state of the platform *before* the Docling integration begins. It is the reference used to justify every later decision about whether a contract was extended or replaced.

---

## 1. Classification table

| # | Area | Current implementation | Class | Notes |
|---|---|---|---|---|
| 1 | Upload and source release | `api/routers/documents.py::upload_document`; `SourceDocument` → `DocumentVersion` carrying `content_hash`, `storage_path`, `mime_type`, with content-hash dedupe | **preserve** | Already an immutable source release keyed by SHA-256. Docling conversion attaches to this, it does not replace it. |
| 2 | Native-text parsers | `infrastructure/ingestion/document_ingestion.py` — pdfplumber (`ingest_pdf`) and python-docx (`ingest_docx`): column detection, boilerplate removal, hyphenation and cross-page joins, table reconstruction | **replace** (shadow during cutover) | Directive §1 and §4: Docling becomes the primary converter; the legacy parser survives only as a migration-QA shadow comparator and is then removed from the new-ingestion path. |
| 3 | Canonical document contracts | `contracts/canonical_document.py`: `CanonicalDocument`, `CanonicalPage`, `CanonicalElement`, `SourceFragment`, `SpanReference`, `IngestionDiagnostic` | **adapt** | Shape is compatible. Missing versus Phase 1: page geometry/bbox, Docling `self_ref` retention, list nesting depth, merged-cell lineage, caption↔target and footnote-marker↔note links, header/footer furniture as a first-class kind, and element-level normalized text held separately from raw text. |
| 4 | Canonical element identity | `element_id = f"E{n:06d}"`, assigned from output order in both ingest paths | **replace** ⚠ | Directive Phase 1 requires identity derived from source release plus structural location/content. A zero-tolerance gate forbids identity that depends on list order. `Clause.element_id` is `String(20)`, so a migration is required. Previously published releases keep their existing identifiers and are never recanonicalized (directive §4). |
| 5 | Text authority and verification | `CanonicalPage.raw_text` immutable; `CanonicalElement.text` derived from fragments through recorded `transformations`; `CanonicalDocument.verify_fragments()` proves every offset resolves | **preserve** (pattern), **adapt** (source) | This is already the guarantee the directive asks for (§5, §6). The work is to rebuild the same invariant on top of Docling output rather than to invent it. |
| 6 | Exact-span resolution | `infrastructure/passage_extractor.py`: `resolve_span`, `span_clause_refs`, `verify_verbatim`, `_normalize`; `PolicyPassage.text_origin="application_copied"` | **preserve** | Pointer-only selection with application-side copying already exists. Phase 5's core requirement is satisfied in principle; it needs extending to non-contiguous, role-tagged evidence. |
| 7 | Context assembly | `infrastructure/ai_extraction.py::_batch_clauses`, `_MAX_CHARS_PER_BATCH = 4000` — fixed character windows | **replace** | Phase 4 explicitly forbids feeding arbitrary fixed-size chunks into policy formulation. The module's own comment concedes the defect: "a document is walked in fixed-size windows, not one topic at a time". |
| 8 | Rule candidate contracts | `contracts/formulation.py`: `CanonicalPolicy`, `CanonicalPolicyRule`, `CanonicalEvidence`, `RuleFormulation`, `AmbiguityCode`, `ExtractionStatus` | **preserve / adapt** | Covers most of Phase 6. Gaps: explicit non-contiguous evidence roles, graph dependency references, and per-element coverage disposition. |
| 9 | Candidate persistence and cross-run identity | `CandidateRule` with `content_fingerprint`, `anchor_fingerprint`, `delta_status`, `baseline_candidate_id`, soft supersession via `superseded_at` | **preserve** | Cross-run identity is already solved. The directive's repeat-run stability requirement maps directly onto these fields. |
| 10 | Mapping snapshots | `infrastructure/formulation_mapping.py`; `DmnSemanticProjection`, `DmnMappingStatus`, `DmnRequirementCode` | **preserve / adapt** | Phase 7 requires the approved-snapshot membership check to be an enforced gate rather than advisory metadata; this must be verified. |
| 11 | DMN / FEEL projection | Contracts (`DmnDecision`, `DmnDecisionTable`, `DmnLiteralExpression`, `DmnProjection`); `parse_feel_unary_test`, `derive_condition` | **adapt** ⚠ | A FEEL unary-test *parser* exists. There is no compiler and no canonical-versus-DMN parity harness. Phase 7 and a zero-tolerance gate require both. |
| 12 | Relationship discovery | `infrastructure/correlation_agent.py`, `correlation_service.py`; `CorrelationRun`, `CorrelationFindingRow` | **preserve** | Graph edges enter this subsystem as additional candidates. No parallel relationship store. |
| 13 | Jobs, workers, retries | **None.** `infrastructure/extraction_progress.py` is an in-process dictionary with `_prune()`, and its own docstring states multi-worker deployment is unsupported. `OutboxMessage` exists but is annotated "not yet consumed" | **missing** ⚠ | Phase 9 assumes an existing job/workflow mechanism to extend. There is none, so durable stage execution is net-new work rather than an extension. |
| 14 | Review and approval APIs | 11 routers; `api/routers/candidate_rules.py` owns draft → review → approve → request-changes → override → bulk-review → publish | **preserve** | The extraction handoff must enter through this boundary. No second reviewer workbench, authority service, or approval engine (directive §12). |
| 15 | Web application | 68 components under `apps/web/src`, including `ReviewQueue`, `PolicyInspector`, `QualityPage`, `CorrelationPage`, `PolicyValidationLab`, `ExtractionProgressPanel`, `DocumentsPage`, `ComparePage` | **preserve / extend** | Phase 12 permits only extraction-specific additions to these existing surfaces. |
| 16 | Azure AI Search | `infrastructure/search/indexing.py` — best-effort, writes only `policy-authoring`, `status` hardcoded to `"draft"`, resource shared with roughly 4,760 unrelated documents; `policy-evidence` deliberately untouched | **adapt** ⚠ | Phase 10 requires two rigorously separated projections. The runtime approved-evidence projection does not exist, and there is no pre-activation verification or outbox-based publish. The shared-resource constraint is recorded in `docs/known-limitations.md`. |
| 17 | Publication and activation | `candidate_rules.py::publish_approved_candidates` → `ApprovedPolicyVersion`; `infrastructure/persistence/policy_version_import.py`; on-publish `PolicyTest` re-run | **preserve** | Add the new extraction gates to this flow; do not restructure it. |
| 18 | Evaluator | `evaluator/engine.py`, `precedence.py`, `conditions.py`, `facts.py` | **preserve** | Already evaluates approved canonical rules only, which is what Phase 11 requires. |
| 19 | Audit | `infrastructure/persistence/audit.py`, `AuditEvent` | **preserve** | Extend with extraction-stage events. |

---

## 2. Conflicts between the directive and the current implementation

These are the points where the directive assumes something the repository does not provide. Each one is real work, not a naming difference.

1. **Ordinal element identity (row 4).** Canonical element IDs are currently assigned from output order. A zero-tolerance acceptance gate states that no canonical identity may depend on model-local labels, filenames, or list order. Resolving this requires a new derivation function and an Alembic migration widening `Clause.element_id`, while leaving already-published releases untouched.

2. **No job or worker system (row 13).** Phase 9 says to use the repository's existing job/worker patterns. The only progress mechanism is an in-memory dictionary that documents its own unsuitability for multi-worker deployment, and the outbox table is unconsumed. Durable, restartable, idempotent stage execution must be built.

3. **No runtime Search projection (row 16).** Phase 10 requires a rigorously separated approved/runtime projection whose unit is one approved atomic rule. Today there is a single best-effort draft projection into a shared index. The runtime projection, its verification, and its activation gate do not exist.

4. **No DMN parity harness (row 11).** Phase 7 and a zero-tolerance gate require that every supported projection compiles and that canonical-versus-DMN scenario parity is tested. Only a unary-test parser exists.

5. **Dependency footprint.** `docling` resolves to `docling-slim[standard]`, which pulls `torch`, `torchvision`, `accelerate`, `rapidocr`, and `scipy`. The application currently runs on a `python:3.11-slim` image with pdfplumber and python-docx. The extraction path must therefore be isolated from the API runtime image until a deployment decision is made.

---

## 3. Dependency provenance and immutability approach

The directive requires exact, immutable upstream snapshots with recorded SHA-256 manifests and a separate mutable-runtime allowlist.

This is satisfied through standard Python packaging rather than by copying upstream source trees:

- **Immutability of code.** Wheels published to PyPI are immutable artifacts. Each installed distribution carries a `.dist-info/RECORD` file containing a SHA-256 digest for every installed file. Verifying installed files against `RECORD`, together with a pinned version, proves that no upstream file has been edited, patched, or regenerated in place.
- **Provenance.** The PyPI JSON API publishes the artifact digest, upstream project URL, license, and version for every release, and these are recorded at pin time.
- **Mutable runtime.** Environment files, configuration instances, generated outputs, caches, and run artifacts remain mutable and are listed explicitly, exactly as the directive requires.

This approach is equivalent in guarantee to a vendored snapshot with a hand-built manifest, is verifiable with standard tooling, and avoids importing roughly 200 MB of upstream tests and documentation that the manifest would otherwise have to cover.

**Pinned versions**

| Project | Version | Upstream |
|---|---|---|
| `docling-graph` | `1.9.1` | https://github.com/docling-project/docling-graph |
| `docling` | resolved transitively, `>=2.105.0,<3.0.0` | https://github.com/docling-project/docling |

Both are MIT licensed.

---

## 4. Consequences for the integration

- The platform's existing invariants — immutable raw text, offset-verified fragments, pointer-only selection, application-side copying — are **stronger** than the directive assumes and are preserved as-is. The Docling work rebuilds them on a new conversion source; it does not weaken or duplicate them.
- The genuinely missing subsystems are durable job execution, the runtime Search projection, and DMN parity. These are the largest new-build items and are sequenced accordingly.
- Element identity is the one place where existing behaviour actively violates an acceptance gate and must be changed rather than extended.
