# The running path

**What this build actually executes, end to end, named by the symbols that
implement it.**

This page exists because of a specific failure. `docs/failures/` records it in
full: nine extraction stages were designed, built, tested and shown in the
interface, and production reaches two of them. Nothing was broken. Every file a
reader opened contained working code, every test passed, and the gap was
invisible from any single document — including the documents describing the
design, all of which were accurate about what had been built and silent about
what was connected.

So this page is written from the other direction: from the two production entry
points outward, following what calls what. It is not a design. Where a
capability exists but nothing on this path calls it, that is stated here rather
than left for someone to discover.

**How to read it.** Every step names the symbol that implements it. If you
cannot find the symbol, the step is not real and this page is wrong — report it
rather than working around it. Paths are relative to `src/policy_platform/`.

For why the system is shaped this way, read [Architecture](architecture.md). For
what the pipeline was designed to be, read the specifications under `docs/specs/`
and the status header on the ingestion specification. For what happened when the
two diverged, read
[the failure record](failures/designed-pipeline-and-running-pipeline.md).

---

## Two entry points

Everything below hangs off exactly two HTTP calls. There is no queue, no worker
and no scheduler: each runs inside the request that starts it, which is a
[recorded decision](known-limitations.md#deliberate-scope), not an omission.

| Entry point | Router symbol | What it produces |
|---|---|---|
| `POST /api/documents/upload` | `api/routers/documents.py::upload_document` | An immutable document version and its clauses |
| `POST /api/ai/policy-sets/{key}/documents/{document_version_id}/extract` | `api/routers/ai.py::extract_with_ai` | Candidate rules for review |

---

## Path 1 — upload becomes clauses

`upload_document` runs these in order. Clause extraction is wrapped in a
`try/except` that records `extraction_error` and still returns `200`: a document
whose parse failed is stored, and the caller is told, rather than the upload
being lost.

| # | Step | Symbol |
|---|---|---|
| 1 | SHA-256 the bytes; reject an identical version with `409` | `upload_document` |
| 2 | Write the bytes beside the API process | `upload_document` |
| 3 | Parse, at the one seam that decides how | `infrastructure/ingestion/document_extraction.py::extract_document` |
| 4 | Check the text for glyphs stored as display forms | `infrastructure/ingestion/document_extraction.py::detect_display_glyphs` |
| 5 | Project canonical elements onto the persistence shape | `infrastructure/ingestion/document_extraction.py::clauses_from_document` → `ClauseData` |
| 6 | Report parse problems to the caller | `infrastructure/ingestion/document_extraction.py::ingestion_warnings` |
| 7 | Insert the clauses | `ClauseRepository.bulk_create` |
| 8 | Commit | `upload_document` |
| 9 | Index and reconcile, best-effort | `infrastructure/search/indexing.py::index_clauses_best_effort` |

### The converter seam

Step 3 is the only place the platform decides how an upload is parsed.
`extract_document` reads `document_converter` from
`infrastructure/settings.py` and either calls `ingest_document`
(`infrastructure/ingestion/document_ingestion.py`) or the structured path. If
the structured stack is selected and cannot run, it raises. It does not fall
back, because a silent downgrade from a structured parse to a flattened one is
the invisible change this seam was built to end.

`extract_clauses` in the same module routes through `extract_document` rather
than calling `ingest_document` directly, so there is no second parsing path that
ignores the setting.

Text fidelity is checked for whichever converter ran, because it is a property
of the extracted text rather than of the thing that extracted it.

### Step 9 is best-effort in both halves

`index_clauses_best_effort` swallows its own failures and returns `0`, so a
search outage cannot fail an upload. After a successful write it calls
`infrastructure/search/reconciliation.py::reconcile_version_index`, which
removes index entries under this document version that no clause accounts for.
That sweep has its own `try/except`, so a failed reconcile cannot make a
successful upload report zero.

The consequence to hold on to: a document can exist in PostgreSQL and be absent
from the search index, and nothing on this path will say so.

---

## Path 2 — clauses become candidate rules

`extract_with_ai` calls
`infrastructure/extraction/ai_extraction.py::extract_candidate_rules`. This is
the long one — tens of remote calls over tens of minutes.

### Before the loop

| # | Step | Symbol |
|---|---|---|
| 1 | Load the policy set and document version | `PolicySetRepository.get_by_key` |
| 2 | Load the clauses in document order | `ClauseRepository.list_by_document_version` |
| 3 | Open a run row | `ExtractionRunRepository.create` |
| 4 | Group clauses into batches by running character count | `infrastructure/extraction/ai_extraction.py::_batch_clauses` |

`_batch_clauses` fills to `_MAX_CHARS_PER_BATCH` in stored order. A document is
therefore walked in fixed-size windows rather than one topic at a time, and a
batch boundary can fall between a rule and its exception.

### Per batch

Each batch is persisted and committed on its own. These runs are long, so an
all-or-nothing transaction would discard every finished batch on a late failure.

| # | Step | Symbol |
|---|---|---|
| 5 | Render the batch for the agent | `infrastructure/extraction/ai_extraction.py::_render_batch` |
| 6 | Select policy-bearing spans and copy them | `PassageExtractorAgent.extract` |
| 7 | Check the model copied rather than composed | `infrastructure/extraction/passage_extractor.py::verify_verbatim` |
| 8 | Repair a passage that points at a real clause but transcribes it imperfectly | `infrastructure/extraction/passage_extractor.py::resolve_span` |
| 9 | Render the kept passages as the formulator's source | `infrastructure/extraction/ai_extraction.py::_render_passages` |
| 10 | Draft structured rules | `PolicyFormulatorAgent.formulate` |
| 11 | Map the reply onto canonical rules deterministically | `infrastructure/extraction/formulation_mapping.py` |
| 12 | Retire the previous run's unreviewed candidates — **on the first batch that yields rules** | `infrastructure/extraction/ai_extraction.py::_supersede_prior_candidates` |
| 13 | Insert this batch's candidates and commit | `CandidateRuleRepository.create` |

`_render_batch` is the entire contract between the document and the model:
`clause_ref`, an optional `section` on its own line, and the clause text. No
structural graph, no table headers, no reading plan.

Step 12 fires once per run, in the same transaction as the first batch's
inserts, so the queue never holds both runs at once. Its timing is
load-bearing and is discussed under [What can still go wrong](#what-can-still-go-wrong).

### After every batch

| # | Step | Symbol |
|---|---|---|
| 14 | Link rules sharing a `group_label` | `infrastructure/extraction/formulation_mapping.py::_group_labels`, applied in `extract_candidate_rules` |
| 15 | Link what the document's structure establishes | `discover_structural_relationships` |
| 16 | Link by normative role | `discover_semantic_role_relationships` |
| 17 | Link records cut out of one decision | `discover_split_decision_relationships` |
| 18 | Link a record to the wording it depends on | `discover_referent_relationships` |
| 19 | Link a governing stem to the clauses completing it | `discover_enumeration_relationships` |
| 20 | Report stems whose extent the document does not state | `stems_needing_adjudication` |
| 21 | Ask the model about what structure could not resolve | `infrastructure/extraction/continuation_adjudicator.py::discover_continuations` |
| 22 | Re-read every drafted rule against the source it cites | `infrastructure/quality/policy_faithfulness.py::validate_rules` |
| 23 | Classify this run against the previous one | `infrastructure/extraction/ai_extraction.py::_classify_run_delta` |
| 24 | Close the run | `ExtractionRunRepository.mark_completed` |

Steps 15 to 20 are in `infrastructure/correlation/relationship_discovery.py`.
Only `confirmed` edges reach `related_rule_ids`; a candidate edge is recorded
for a reviewer and never written into a field consumers read as established
fact.

Step 21 is the only model call in this group, and its output is held to the same
standard as everything else: the model must quote the parent's own promise, the
quote is checked verbatim against the source, and only a verified quote produces
a `confirmed` edge.

Step 22 reports; it does not gate. It used to mark rules for review, which made
the interface argue with itself — a rule shown complete also carrying a flag
demanding attention — and made the flag meaningless by firing on most of the
corpus. Whether the extractor is behaving is a question about the run.

Steps 15 to 22 are each wrapped so a failure cannot cost the run its rules,
which are the expensive part.

---

## What is reachable but read-only

These endpoints run in production and are correct. None of them feeds
extraction. The distinction matters because a capability that is displayed looks
identical, from the interface, to one that is used.

| Endpoint | Router symbol | Reads |
|---|---|---|
| `GET /{document_version_id}/canonical` | `api/routers/extraction.py::get_canonical_document` | Clauses, rebuilt |
| `GET /{document_version_id}/structure` | `api/routers/extraction.py::get_structural_graph` | The structural graph |
| `GET /{document_version_id}/reading-plan` | `api/routers/extraction.py::get_reading_plan` | `contracts/reading_plan.py::build_reading_plan` |
| `GET /{document_version_id}/coverage` | `api/routers/extraction.py::get_coverage` | The same reading plan |
| `GET /{document_version_id}/stages` | `api/routers/extraction.py::list_extraction_stages` | Recorded stage rows |

`build_reading_plan` is genuinely reached in production, by the two endpoints
that display it. It never reaches a model. The coverage report is truthful about
a plan that nothing extracts from.

`_canonical_from_clauses` (`api/routers/extraction.py`) rebuilds pages with
`raw_text=""`, which is why fragment offsets cannot be resolved against what it
returns.

## What has no production caller

`infrastructure/docling/pipeline.py::run_extraction` defines the nine designed
stages. Nothing under `src/policy_platform` calls it; it is invoked from
`tests/unit/test_docling_pipeline.py` and `scripts/docling_corpus_report.py`.

This is stated here so that a reader comparing the nine stages against the
twenty-four steps above does not assume the two lists describe the same run.
`tests/unit/test_the_running_path_is_the_documented_path.py` fails if that
stops being true, so this paragraph cannot quietly become false.

---

## What can still go wrong

Stated because each is a live property of the path above, not a historical note.

**A failing batch costs coverage, and the run says so.** A batch whose agent
fails is appended to `skipped` and the run continues. `mark_completed` is called
with `coverage_complete=not skipped`, so a run that passed over material is
closed as `completed_with_gaps` rather than `completed`. That distinction is
load-bearing: the completed status is used as a trustworthiness predicate when
a later run is compared against this one.

**Superseding fires before the run can fail.** Step 12 runs on the first batch
that yields rules; steps 14 to 24 run at the end. A run that supersedes and then
fails leaves the reviewer with *fewer* records than before, plus a failed run.
Retrying transient remote failures (`infrastructure/ai/openai_client.py`) closed
the most common way in, but the ordering itself is unchanged, and any late
failure still has this shape.

**The verbatim check is anchored to the batch, not the page.** Step 7 compares
the model's output against step 5's rendering, which is built from stored clause
text. It proves the model copied. It cannot prove the stored text matches the
source document. See
[What the verbatim check proves](ai-assistance.md#what-the-verbatim-check-proves).

**Search can silently diverge.** Step 9 swallows its failures by design.

---

## Keeping this page true

The failure this page exists to prevent was not caused by carelessness. It was
caused by every individual document being accurate about the part it described.
Prose alone cannot hold that.

`tests/unit/test_the_running_path_is_the_documented_path.py` therefore checks
two things this page claims:

1. Every symbol named in a step exists at the module named beside it.
2. `run_extraction` still has no caller under `src/policy_platform`.

The second is the interesting one. It is not a check that the code is right —
wiring `run_extraction` into production would be an improvement. It is a check
that **this page notices**, so the claim cannot rot into a confident falsehood
while everyone reads it and believes it.

What the test cannot check is whether a step was *added* to the running path and
left out of this page. Nothing detects an omission, which is why this page is
written from the call path rather than from memory, and should be re-derived the
same way when it is next revised.
