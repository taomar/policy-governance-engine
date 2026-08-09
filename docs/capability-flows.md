# Capability flows

One diagram per implemented capability, with a short note on what triggers it,
which components take part, what it produces, and where the deterministic /
probabilistic line sits.

Read [Architecture](architecture.md) first for the system shape; this page is the
per-feature detail. For the technologies these flows run on, see
[Frameworks and technologies](frameworks.md). For which test modules defend each
capability below, see the
[active test capability groups](testing.md#active-test-capability-groups) in
[Testing and scripts](testing.md); for how the AI-touching flows get their
context, see [How the AI is grounded](ai-assistance.md#how-the-ai-is-grounded).

**How to read the diagrams**

- **Deterministic** steps are plain Python — same input, same output, no model.
- **Probabilistic** steps call Azure OpenAI and are always advisory. Azure
  OpenAI and a grounding/search layer are required for these flows to run at
  all; without them the flow returns `503` rather than degrading silently.
- **Human** steps are the gates: nothing probabilistic reaches a published
  version without one.
- Dotted arrows are best-effort: they can fail without failing the flow.

Anything below labelled *hidden* is fully implemented in backend and frontend but
deliberately not surfaced in the current navigation. Anything labelled *not
implemented* is not diagrammed as if it exists.

---

## 1. Navigation and UI-to-API invocation

**Purpose.** Show how a user reaches a capability and how the browser reaches the
backend. **Trigger:** opening the web app.

```mermaid
flowchart LR
    User(["Reviewer / Manager / Operator"])

    subgraph Shell["App shell — apps/web/src/App.tsx"]
        Dash["Dashboard"]
        Proj["Projects"]
        Inbox["Document Inbox"]
        Eval["Evaluate"]
        Att["My Attestations<br/>(hidden)"]
        Ask["Ask AI drawer<br/>(only when AI enabled)"]
    end

    subgraph Workspace["Project workspace — ProjectWorkspace.tsx"]
        direction LR
        A1["Author: Overview · Documents · Review"]
        A2["Publish: Policies · Aggregate Limits · Compare"]
        A3["Assure: Quality · Tests · Regression"]
        A4["Operate: Decision Log"]
        A5["Hidden: Correlation · Exceptions · Attestations"]
    end

    Client["Typed HTTP client<br/>apps/web/src/api.ts"]
    API["FastAPI routers<br/>src/policy_platform/api/routers"]

    User --> Shell
    Proj --> Workspace
    Shell --> Client
    Workspace --> Client
    Ask --> Client
    Client -- "JSON over HTTP, VITE_API_BASE_URL" --> API
```

**Components.** `App.tsx` holds page state in memory — there is no router
library and no URL routing. `ProjectWorkspace.tsx` owns the tab strip, grouped
Author → Publish → Assure → Operate. `api.ts` is the single typed client for the
whole backend surface.

**Outputs / state.** None persisted client-side except the "acting as" identity
in `localStorage` (`ActorContext.tsx`).

**Human control.** Every write in the app is an explicit user action; nothing
polls-and-writes.

**Limitations.** `my-attestations`, and the `correlation` / `exceptions` /
`attestations` tabs, are filtered out of both the rendered menu and the
navigation guard, so they cannot be reached in the UI even though their APIs
work. There is no deep-linking: a browser refresh returns to the Dashboard.

---

## 2. Document ingestion and clause extraction

**Purpose.** Turn an uploaded PDF/DOCX into stable, offset-anchored `Clause`
rows. **Trigger:** `POST /api/documents/upload` from **Documents** or the
**Document Inbox**.

```mermaid
sequenceDiagram
    participant UI as Web app
    participant R as documents router
    participant FS as data/documents/
    participant ING as document_ingestion
    participant EX as document_extraction
    participant DB as PostgreSQL
    participant IDX as search/indexing

    UI->>R: multipart upload (title, owner, optional project)
    R->>R: SHA-256 content hash
    alt identical hash already stored
        R-->>UI: 409 duplicate content
    else new content
        R->>FS: write file
        R->>DB: SourceDocument + immutable DocumentVersion
        R->>ING: layout-aware parse
        ING->>ING: reconstruct text from word geometry,<br/>stitch across page breaks, detect tables/headings
        ING-->>R: CanonicalDocument + IngestionDiagnostic[]
        R->>EX: adapt to persistence shape
        R->>DB: Clause rows (offsets, page, section, sequence)
        R-)IDX: embed + upload clauses (best effort)
        R-->>UI: clause_count, clauses_indexed, diagnostics
    end
```

**Deterministic vs probabilistic.** Entirely deterministic. No model is involved
in parsing — that is the point: offsets are exact *by construction* because the
ingester builds the canonical page string itself.

**Outputs.** A `DocumentVersion` (content hash + storage path) and its `Clause`
rows; `ingestion_diagnostics` in the response when coverage is degraded.

**Limitations.** Clause extraction failure is caught and reported as
`extraction_error` rather than failing the upload. A scan with no text layer
produces diagnostics, not silent emptiness. Files are written to the local
filesystem with no scanning or encryption — Azure Blob Storage is not
implemented.

---

## 3. AI-assisted extraction: source passages to candidate rules

**Purpose.** Draft structured candidate rules from a document version.
**Trigger:** `POST /api/ai/policy-sets/{key}/documents/{document_version_id}/extract`
(the **Extract with AI** action).

```mermaid
flowchart TD
    Start["Extraction run created<br/>extraction_runs: pending"]
    Batch["Batch clauses by character budget<br/>ai_extraction._batch_clauses"]
    S1["Stage 1 — passage extractor<br/>passage_extractor.py"]
    V{"verify_verbatim()<br/>contiguous substring of source?"}
    Drop["Discard passage, record skip"]
    S2["Stage 2 — policy formulator<br/>policy_formulator.py"]
    Map["Deterministic derivation<br/>formulation_mapping.py"]
    Exec{"trusted_config supplies<br/>every required fact path?"}
    MEx["machine_executable = true"]
    NEx["machine_executable = false<br/>requirement codes retained"]
    Persist[("candidate_rules<br/>review_status = candidate")]
    Delta["Classify vs previous run<br/>rule_delta.py: new / continued / changed"]
    Prog["extraction_progress<br/>in-memory, polled by the UI"]

    Start --> Batch --> S1 --> V
    V -- no --> Drop
    V -- yes --> S2 --> Map --> Exec
    Exec -- yes --> MEx --> Persist
    Exec -- no --> NEx --> Persist
    Persist --> Delta
    Batch -.-> Prog
```

**Why two agents.** Scanning ("where does a policy statement start and stop")
and formulating ("what does it mean as data") have different failure modes.
Splitting them makes Stage 1's output verifiable by string containment.

**Deterministic boundary.** Identifier generation, rule-type/effect mapping and
condition compilation are plain Python. The FEEL-expression parser is strict: an
expression it does not fully understand yields *no* condition rather than a
guess. The untouched formulation payload is kept on every candidate.

**Outputs.** `candidate_rules` rows (never published), an `extraction_runs`
record, and per-rule delta status.

**Limitations.** Long-running — tens of model calls. Progress is in-memory
telemetry, not a source of truth. Prior candidates are superseded only once the
new run has rules to replace them, so a run that fails every batch cannot leave a
reviewer with less than they started with. An API restart marks in-flight runs
`failed` and keeps rules already committed.

---

## 4. Evidence, provenance and verbatim verification

**Purpose.** Guarantee every published rule can be traced back to the exact
source text. **Trigger:** implicit in extraction, publish, and evaluation.

```mermaid
flowchart LR
    Src["Source file<br/>data/documents/"]
    DV[("document_versions<br/>content_hash")]
    Cl[("clauses<br/>page, section, offsets")]
    P["Stage 1 passage<br/>must be a substring"]
    Chk{"verify_verbatim()"}
    Cand[("candidate_rules<br/>CanonicalRule.evidence")]
    Ev[("evidence_references<br/>written at publish")]
    Rule[("approved_rules")]
    Resp["EvaluationResponse.evidence_references<br/>document_version_id#clause_id"]

    Src --> DV --> Cl --> P --> Chk
    Chk -- fail --> X["Dropped, recorded as skipped"]
    Chk -- pass --> Cand --> Rule
    Cand --> Ev --> Rule
    Rule --> Resp
```

**Deterministic boundary.** The verbatim check is a normalised string
containment test in Python — a model's assurance about its own output is not
accepted as evidence. `policy_version_import.py` writes `evidence_references`
at publish time so the clause linkage survives approval.

**Outputs.** `evidence_references` rows; evidence IDs on satisfied rules in
every evaluation response.

**Limitations.** Verification proves the quote is real, not that it was the
*right* quote to pick. Evidence for a rule nobody curated is only as good as the
clause boundaries ingestion produced.

---

## 5. Human review and the candidate lifecycle

**Purpose.** The governance gate. **Trigger:** the **Review** tab, or the
candidate-rules endpoints directly.

```mermaid
stateDiagram-v2
    [*] --> candidate: AI extraction or manual draft
    candidate --> candidate: edit, or apply an AI rewrite
    candidate --> approved: approve
    candidate --> rejected: reject
    candidate --> needs_changes: request changes
    needs_changes --> candidate: revise
    approved --> published: publish a version
    rejected --> [*]
    published --> [*]
    candidate --> superseded: re-extraction replaces it
```

```mermaid
sequenceDiagram
    participant UI as Review tab
    participant R as candidate_rules router
    participant Repo as CandidateRuleRepository
    participant AUD as audit
    participant DB as PostgreSQL

    UI->>R: GET review-facets (documents, runs, delta, counts)
    UI->>R: GET candidate-rules (filtered)
    UI->>R: PUT candidate-rules/{id} — edit
    UI->>R: POST .../review — approve or reject
    alt manager-only action
        UI->>R: POST .../request-changes or .../override
        R->>R: actor_role must be policy_manager, else 403
    end
    UI->>R: POST .../bulk-review — many at once
    R->>Repo: persist decision, reviewer, revision
    R->>AUD: record_audit_event
    R->>DB: commit
    R-->>UI: updated candidate(s)
```

**Human control.** This *is* the human control point. Every decision records the
reviewer and a timestamp; `request-changes` and `override` require the
`policy_manager` role.

**Outputs.** Updated `candidate_rules` rows plus `audit_events`.

**Limitations.** The role check reads `actor_role` from the request body. It is a
local-trust convention, trivially spoofable, and is not authentication.

---

## 6. Publishing, versioning and release

**Purpose.** Turn approved candidates into an immutable, evaluable version.
**Trigger:** `POST /api/policy-sets/{key}/publish`.

```mermaid
sequenceDiagram
    participant UI as Web app
    participant R as candidate_rules router
    participant VR as ApprovedPolicyVersionRepository
    participant IMP as policy_version_import
    participant TR as policy_test_execution
    participant DB as PostgreSQL

    UI->>R: POST /publish (effective dates, approver)
    R->>VR: load current active version
    Note over R: merge — carry forward every existing rule,<br/>newly approved candidates add or supersede by rule_id
    R->>R: snapshot current draft aggregate limits
    R->>IMP: import_approved_policy_version(...)
    IMP->>DB: approved_policy_versions + approved_rules +<br/>rule_exceptions + approved_aggregate_limits + evidence_references
    R->>DB: mark candidates published, write audit event, commit
    R-)TR: re-run every active policy test against the new version
    TR->>DB: append policy_test_runs (trigger = on_publish)
    R-->>UI: new version
```

**Outputs / state changes.** A new `approved_policy_versions` row (exactly one
active per policy set), its full rule snapshot, and a fresh set of test runs.

**Deterministic boundary.** Fully deterministic. No model participates in a
publish.

**Versioning.** `version_number` is a monotonically increasing integer, unique
per policy set. Semantic versioning is **not** implemented — there is no
major/minor/patch semantics anywhere in the schema or API.

**Limitations.** The on-publish test re-run is best-effort: the publish is
already committed, so a failure there is logged and surfaced through the tests'
own history rather than failing the request. Publishing requires at least one
approved, unpublished candidate (`409` otherwise).

---

## 7. Deterministic policy evaluation

**Purpose.** Produce a decision from facts. **Trigger:** `POST /api/evaluations`
(the **Evaluate** page), the policy-test runner, the aggregate-limit preview, and
the AI scenario engine — all through the same function.

```mermaid
flowchart TD
    Req["EvaluationRequest<br/>policy set + optional version pin + facts"]
    Pkg["approved_policy_version_to_package()<br/>mappers.py"]
    Canon["canonicalize_facts()"]
    Win["Filter rules by effective window"]
    Ord["order_rules_by_precedence()<br/>8 dimensions, rule_id tiebreak"]
    PerRule["Per-rule evaluation"]
    Tgt{"Scope / Target match?"}
    NA["NOT_APPLICABLE<br/>scope_mismatch:dimension"]
    IND["INDETERMINATE<br/>missing_facts listed"]
    Cond["Interpret condition AST<br/>20 allowlisted operators"]
    Exc["Evaluate rule exceptions"]
    Comb["Combining algorithm<br/>allow/require_action vs deny,<br/>precedence-ordered first-applicable"]
    Agg["Aggregate limits<br/>DMN Collect + SUM"]
    Hash["canonical_hash() — stable SHA-256"]
    Resp["EvaluationResponse"]
    Log[("evaluations — append-only")]

    Req --> Pkg --> Canon --> Win --> Ord --> PerRule --> Tgt
    Tgt -- mismatch --> NA
    Tgt -- fact absent --> IND
    Tgt -- match --> Cond --> Exc --> Comb --> Agg --> Hash --> Resp --> Log
```

**Deterministic boundary.** `evaluator/` imports nothing from `infrastructure/`.
No database, no network, no model — enforced by module structure and unit tests.

**Outputs.** Overall status
(`SATISFIED` / `NOT_SATISFIED` / `NOT_APPLICABLE` / `INDETERMINATE` / `ERROR`),
outcome, per-rule results with `overridden_by`, triggered exceptions, aggregate
breaches, advice notes, evidence references, and a stable `result_hash`. Every
call appends an `evaluations` row.

**Human control.** None needed at decision time — that is the design. Control was
exercised earlier, at approval and publish.

**Limitations.** Missing facts always yield `INDETERMINATE` with the exact list,
never a guess. Supersession precedence resolves direct pairs but not every
multi-hop chain. The engine surfaces an aggregate breach but does not decide a
remediation.

---

## 8. Policy tests: definition, review and execution

**Purpose.** Pin worked examples as regression tests against the evaluator.
**Trigger:** the **Tests** tab, `POST /api/policy-tests/policy-sets/{key}`
(manual), `.../propose` (AI), `.../{test_id}/run`, or a publish.

```mermaid
stateDiagram-v2
    [*] --> pending_review: AI proposes a test
    [*] --> active: a human writes a test
    pending_review --> active: accept — is_active becomes true
    pending_review --> rejected: reject — row kept for history
    active --> retired: is_active set to false
    rejected --> [*]
    retired --> [*]
```

```mermaid
sequenceDiagram
    participant UI as Tests tab
    participant R as policy_tests router
    participant PROP as ai_test_proposal
    participant EXEC as policy_test_execution
    participant ENG as evaluator.test_runner
    participant DB as PostgreSQL

    opt AI proposal
        UI->>R: POST /propose
        R->>PROP: draft scenarios grounded in the active version
        PROP-->>R: validated test definitions
        R->>DB: persist as pending_review, is_active = false
    end
    UI->>R: POST /{test_id}/review (accept or reject)
    UI->>R: POST /{test_id}/run
    R->>EXEC: resolve version, build package
    EXEC->>ENG: run_policy_test(case, package)
    Note over ENG: calls the real evaluator, then diffs<br/>every expectation — collects all mismatches
    ENG-->>EXEC: PASS / FAIL + explanation
    EXEC->>DB: append policy_test_runs (immutable)
    R-->>UI: run result
```

**Deterministic vs probabilistic.** AI may *propose*; only
`evaluator/test_runner.py` ever *executes*. `ai_test_proposal.py` is forbidden
by design from importing the evaluator.

**Outputs.** `policy_tests` rows (mutable — a QA artifact), and append-only
`policy_test_runs` recording the version each run targeted, the trigger
(`manual` / `on_publish`), the expected assertions snapshot and its hash.

**Limitations.** No hard delete or edit of an existing test (retire and
re-create), no "run all now" bulk action, and no scheduled execution — every run
is manual or publish-triggered.

---

## 9. Blind validation batches (Regression tab)

**Purpose.** Generate sealed scenarios for a chosen subset of published policies,
run them blind, then reveal. **Trigger:** the **Regression** tab →
`POST /api/policy-tests/policy-sets/{key}/validation-batches`.

```mermaid
flowchart LR
    S1["1 · Select policies<br/>from one published version"]
    S2["2 · Generate & seal<br/>AI drafts N scenarios per policy;<br/>expectation_hash committed"]
    Guard{"Exactly N per selected policy?"}
    Fail["422 — refine selection or guidance"]
    S3["3 · Run blind<br/>real evaluator, expectations hidden"]
    S4["4 · Reveal & preserve<br/>batch marked executed"]
    Runs[("policy_test_runs<br/>append-only")]

    S1 --> S2 --> Guard
    Guard -- no --> Fail
    Guard -- yes --> S3 --> S4
    S3 --> Runs
```

**Why sealed.** Committing an `expectation_hash` before execution means the
expected answer cannot be quietly adjusted after seeing the engine's result.

**Deterministic boundary.** Scenario *generation* is probabilistic; execution and
pass/fail are not. Execution is restricted to the reviewer-selected rule subset
so unrelated rules cannot turn the package `INDETERMINATE`.

**Limitations.** Batches run against a published version — running a suite
against a candidate version *before* publishing is not implemented.

---

## 10. Quality analysis, findings and inspection

**Purpose.** Answer "are these policies actually any good?" for both a published
version and pre-publish candidates. **Trigger:** the **Quality** tab →
`GET /api/ai/policy-sets/{key}/quality` or `.../candidates/quality`.

```mermaid
flowchart TD
    Scope{"Scope"}
    Pub["Active published version<br/>approved_policy_version_to_package"]
    Cand["Unpublished candidates<br/>candidate + approved statuses"]
    Det["Deterministic checks<br/>ai_quality._deterministic_findings"]
    D1["duplicate ids · conflicting effects · expired rules"]
    D2["definitions with a decision effect · eligibility polarity"]
    D3["degenerate predicates · non-blocking ambiguity"]
    D4["machine executability · review backlog · invalid payloads"]
    AI["AI review pass<br/>source = ai_review"]
    Norm["Validate & normalise<br/>every referenced rule id must exist"]
    Merge["Findings tagged by source"]
    Run[("quality_runs — immutable,<br/>with methodology_version")]
    Drawer["Finding drawer<br/>QualityFindingDrawer.tsx"]
    Tests["Failing policy tests surfaced alongside"]

    Scope --> Pub --> Det
    Scope --> Cand --> Det
    Det --> D1 & D2 & D3 & D4 --> Merge
    Det --> AI --> Norm --> Merge
    Merge --> Run --> Drawer
    Tests --> Drawer
```

**Inspection and remediation.** The finding drawer resolves each finding against
the exact version it was raised on, explains the category in plain language, and
drills through to the affected policies and their source evidence. Remediation
itself is ordinary editing: fix the candidate or publish a corrected version,
then re-run and compare against the persisted history. There is **no** finding
disposition field for quality findings — persisted runs are the mechanism for
showing a fix stuck.

**Deterministic boundary.** Deterministic findings are exact by construction. AI
findings are judgement, explicitly framed as *potential* issues needing human
confirmation, and any finding referencing an unknown rule ID is rejected whole.

**Outputs.** A `quality_runs` row with the full findings payload, the rule count,
whether AI review was used, and the methodology version.

**Limitations.** A candidate-scope run over hundreds of rules is a single
long-running request with no incremental progress. Historic candidate-scope runs
do not snapshot the mutable candidate payload, so a later-superseded candidate is
reported as an unresolved reference rather than reconstructed.

---

## 11. Cross-rule correlation (hidden tab)

**Purpose.** Find rules that contradict, overlap, duplicate, supersede or
specialise one another. **Trigger:** `POST /api/ai/policy-sets/{key}/correlate`.
The **Correlation** tab is implemented but hidden in this phase; the API is
callable.

```mermaid
flowchart TD
    Load["Load latest revision per rule<br/>candidate + approved + needs_changes + published"]
    Group["Deterministic grouping<br/>correlation_agent.group_rules_for_comparison"]
    Sem["Bounded concurrency<br/>GROUP_CONCURRENCY = 3"]
    Agent["Model classifies the relationship<br/>within one small group only"]
    Dedupe["Deduplicate by finding identity"]
    Chunk["Commit every PERSIST_CHUNK_GROUPS groups"]
    Run[("correlation_runs")]
    Find[("correlation_findings + disposition")]

    Load --> Group --> Sem --> Agent --> Dedupe --> Chunk --> Run --> Find
```

```mermaid
stateDiagram-v2
    [*] --> open: finding recorded
    open --> accepted: real, will be acted on
    open --> dismissed: not a real problem
    open --> resolved: underlying rules changed
    accepted --> resolved: fix published
    dismissed --> [*]
    resolved --> [*]
```

**Division of labour.** The application decides **which rules to compare**; the
model decides only **what the relationship is**. Exhaustive pairwise comparison
is arithmetically impossible on a large set — roughly a million pairs at 1,400
rules — so grouping must be deterministic and cheap.

**Outputs.** A `correlation_runs` row and `correlation_findings` rows, each
carrying a reviewer disposition (`open`, `accepted`, `dismissed`, `resolved`)
with the deciding actor, timestamp and notes. Setting a disposition also writes
an audit event, because "someone decided this was not a real problem" is a claim
an auditor needs attributed.

**Limitations.** Rejected rules are excluded deliberately. Findings are scoped to
a run, so they remain statements about the rules as they stood. Long runs commit
in chunks so a failure costs minutes, not hours.

---

## 12. Search: indexing and retrieval

**Purpose.** Ground AI answers in the organisation's own clauses. **Trigger:**
document upload (write side); Ask AI and test-scenario grounding (read side).
Requires `AZURE_SEARCH_*` configuration — this is the platform's mandatory
grounding layer, not an add-on, and the full grounding path is documented in
[How the AI is grounded](ai-assistance.md#how-the-ai-is-grounded).

```mermaid
sequenceDiagram
    participant UP as Upload flow
    participant IDX as search/indexing
    participant AOAI as Azure OpenAI embeddings
    participant SRCH as Azure AI Search
    participant CHAT as ai_chat / ai_test_proposal

    UP->>IDX: clauses for one document version
    IDX->>AOAI: embed(texts)
    AOAI-->>IDX: vectors
    IDX->>SRCH: mergeOrUpload, batches of 100,<br/>key = documentVersionId_clauseId
    Note over IDX: failures are logged and swallowed —<br/>an upload never fails on a search outage

    CHAT->>AOAI: embed(question)
    CHAT->>SRCH: hybrid query — keyword + body_vector,<br/>filtered to our own document ids
    SRCH-->>CHAT: top hits with clause metadata
```

**Scoping.** The shared index also holds unrelated documents from another system.
Every write uses this platform's own `SourceDocument` UUID as `policy_id`, and
every read filters to the set of those IDs, so the two data sets cannot mix. The
client never creates or alters an index schema.

**Outputs.** Indexed clause documents; retrieved hits surfaced as provenance
chips in the UI.

**Limitations.** Best-effort by design: an indexing failure is logged and
swallowed, so a document can be fully usable and still invisible to retrieval.
Only the authoring index is written; the evidence index is untouched. Retrieval
failure degrades Ask AI to rules-only grounding rather than erroring. Automated
coverage is limited to the index-key contract
([`test_search_indexing.py`](../tests/unit/test_search_indexing.py)) — no test
contacts Azure AI Search. Full register:
[grounding limitations](ai-assistance.md#grounding-limitations-and-failure-modes).

---

## 13. Ask AI: grounded chat

**Purpose.** Answer plain-English questions about policy, citing what it used.
**Trigger:** the global **Ask AI** drawer, or `POST /api/ai/ask`. Also reachable
per-rule from the Review tab.

```mermaid
sequenceDiagram
    participant UI as Ask AI drawer
    participant R as ai router
    participant CHAT as ai_chat
    participant SRCH as Azure AI Search
    participant DB as PostgreSQL
    participant AOAI as Azure OpenAI (fast deployment)

    UI->>R: POST /api/ai/ask (question, optional policy set, optional focus rule)
    R->>CHAT: ask(...)
    opt focus rule given
        CHAT->>DB: load that candidate + same-group siblings
    end
    opt search configured
        CHAT->>SRCH: hybrid retrieval over our clauses
    end
    opt policy set given
        CHAT->>DB: active version's approved rules
    end
    CHAT->>AOAI: JSON-mode chat with assembled CONTEXT
    AOAI-->>CHAT: {groups[].facts[], reflection}
    CHAT-->>UI: verbatim fact groups + AI reflection + source chips
```

**Structured output contract.** The response schema forces a split between facts
copied character-for-character from context and the model's own synthesis, so a
reader can always tell which is which. This is JSON *object* mode
(`response_format: {"type": "json_object"}`), not JSON-Schema-constrained
structured outputs.

**Human control.** Advisory only. Nothing the chat says changes any record.

**Limitations.** Runs on the fast deployment for latency. If search or the rules
lookup fails, it answers from whatever context it did assemble and says so.
Retrieval is filtered to all of this platform's documents rather than to the
named policy set. There is no unit test for `ai_chat.ask` — see
[Testing and scripts](testing.md#active-test-capability-groups).

---

## 14. Aggregate limits

**Purpose.** Express a ceiling that spans several rules — "these leave types
together cannot exceed 70 days a year". **Trigger:** the **Aggregate Limits**
tab.

```mermaid
flowchart TD
    Elig["GET .../aggregate-limits/eligibility<br/>aggregate_eligibility.py"]
    Prop["POST .../aggregate-limits/propose<br/>ai_aggregate_proposal.py"]
    Draft["Create / update / delete draft<br/>policy_aggregate_limits"]
    Prev["POST .../aggregate-limits/preview<br/>aggregate_preview.py"]
    RealEng["Splices the draft into the active package<br/>and calls the REAL evaluator"]
    Pub["Publish snapshots the full draft list<br/>into approved_aggregate_limits"]
    Runtime["Evaluator reports aggregate_breaches"]

    Elig --> Draft
    Prop -.-> Draft
    Draft --> Prev --> RealEng
    Draft --> Pub --> Runtime
```

**Why eligibility and preview exist.** The engine skips a contribution silently
when a rule is not SATISFIED, was overridden, or its amount fact is missing or
non-numeric. Eligibility tells the author which rules can contribute *before*
they build the cap; preview runs the real evaluator rather than re-implementing
the arithmetic.

**Deterministic boundary.** Eligibility, preview and enforcement are all
deterministic. Only the *proposal* is probabilistic.

**Limitations.** Aggregate limits have no per-item review step — they are
policy-set configuration a manager maintains directly. The evaluator surfaces a
breach; it does not decide which contributing rule gets curtailed.

---

## 15. Version compare and change explanation

**Purpose.** Show exactly what changed between two published versions, and why a
candidate was flagged as changed. **Trigger:** the **Compare** tab
(`GET /api/ai/policy-sets/{key}/compare`) and the Review tab's change explainer
(`GET /api/ai/candidate-rules/{id}/explain-change`).

```mermaid
flowchart LR
    subgraph Det["Deterministic — always produced"]
        A["Load both persisted snapshots"]
        B["Rule-level diff<br/>added · removed · changed · unchanged"]
        C["Field-level deltas"]
    end
    subgraph Prob["Probabilistic — optional narrative"]
        D["Model narrates the already-correct diff"]
    end
    A --> B --> C --> D
    C --> Out["Diff shown even when AI is off or fails"]
    D --> Out
```

**Deterministic boundary.** The diff is never asked of the model; the model only
explains it. `rule_delta.py` provides the same guarantee for extraction runs, and
`rule_change_explainer.py` narrates that diff for one candidate.

**Limitations.** Comparison is read-only and on demand. There is no persistent
change-request/approval workflow wrapped around a diff.

---

## 16. Exceptions and waivers (hidden tab)

**Purpose.** Track a human-requested, time-bounded waiver of a rule for one
case. Distinct from the rule-level `exceptions` field the evaluator applies
automatically. **Trigger:** `POST /api/policy-exceptions/policy-sets/{key}`. The
**Exceptions** tab is implemented but hidden in this phase.

```mermaid
stateDiagram-v2
    [*] --> pending: composer or reviewer requests a waiver
    pending --> granted: policy manager grants, with optional expiry
    pending --> denied: policy manager denies
    granted --> expired: expiry_date passes — computed, not stored
    denied --> [*]
    expired --> [*]
```

**Deterministic vs probabilistic.** Fully human and deterministic. No AI, and the
evaluator does not read `policy_exceptions` — a granted waiver is a governance
record, not an automatic runtime carve-out.

**Limitations.** No multi-level approval chain, no notification on request or
expiry.

---

## 17. Employee attestations (hidden surfaces)

**Purpose.** Track each person's obligation to acknowledge a specific published
version. **Trigger:** a manager launching a campaign
(`POST /api/policy-attestations/policy-sets/{key}/campaigns`); an employee
searching for their own items. Both the **My Attestations** page and the project
**Attestations** tab are implemented but hidden in this phase.

```mermaid
stateDiagram-v2
    [*] --> pending: manager assigns a version to a person with a due date
    pending --> acknowledged: employee acknowledges, optional notes
    pending --> overdue: due_date passes — computed at read time
    overdue --> acknowledged: late acknowledgement
    acknowledged --> [*]
```

**Human control.** Campaign creation is manager-only (`403` otherwise).
Acknowledgement is self-service with no login — an employee finds their items by
name or identifier, because there is no identity system to key off.

**Outputs.** `policy_attestations` rows bound to a specific
`approved_policy_versions` row; status is computed, never stored.

**Limitations.** No reminder or escalation delivery, no automatic re-attestation
cascade when a new version is published, and no personnel directory — assignees
are free-text name/email captured per campaign.

---

## 18. Outputs: exports, decision log and audit trail

**Purpose.** Get governed data out of the platform, and prove what happened.
**Trigger:** export buttons in the Policies and Review tabs; the **Decision Log**
tab; `GET /api/audit-events`.

```mermaid
flowchart TD
    subgraph Files["Downloadable files"]
        E1["GET /api/policy-sets/{key}/versions/{id}/export<br/>?format=json|jsonl|csv"]
        E2["GET /api/policy-sets/{key}/candidate-rules/export<br/>?format=json|jsonl|csv"]
        E3["Policies tab client-side JSONL<br/>selected or all rules"]
    end
    subgraph Reads["Read APIs and UI history"]
        L1["GET /api/evaluations/policy-sets/{key} — decision log"]
        L2["GET /api/evaluations/{id} — full facts + response"]
        L3["GET /api/audit-events — immutable trail"]
        L4["Quality / correlation / test run history"]
    end
    Ser["export.py — verbatim re-serialisation,<br/>CSV nests structures as JSON cells, UTF-8 BOM"]
    Cons["Downstream: spreadsheets, archives,<br/>other systems, evidence packs"]

    E1 --> Ser
    E2 --> Ser
    Ser --> Cons
    E3 --> Cons
    Reads --> Cons
```

**Deterministic boundary.** Export is a verbatim structural re-serialisation of
persisted data. No field is summarised or reworded.

**Also readable, not shown above.** Free-form `notes` attached to any governed
entity (`GET`/`POST`/`DELETE /api/notes`) carry rationale and sign-off remarks.
They are collaboration context rather than evidence — unlike the tables above,
a note can be deleted by its author.

**Limitations.** Exports are point-in-time downloads, not a subscription or feed.
`outbox_messages` is modelled but no publisher consumes it, so there is no event
stream. There is no scheduled or automated export.

---

## Not diagrammed

These are named in the codebase or backlog but are **not implemented**, so no
diagram claims them:

- Microsoft Agent Framework / graph-workflow orchestration —
  `src/policy_platform/worker/` is an empty reserved package and no MAF
  dependency or workflow runtime exists. The current explicit, request-driven
  services do not need a framework-managed agent graph.
- Transactional outbox publishing — table only, no publisher.
- Authentication, multi-tenancy, and any identity provider integration.
- CI/CD pipeline. The prepared `azd`/Bicep path is operator-invoked, not automated delivery.
- Notification, reminder or escalation delivery of any kind.
- Scheduled or event-triggered runs — every flow above is request-driven.

See [Known limitations](known-limitations.md) for the full register.
