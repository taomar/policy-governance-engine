---
name: build-governed-policy-ingestion
description: Design, implement, refactor, or review governed ingestion systems that turn policy, procedure, standard, regulation, contract, entitlement, warranty, or process files into traceable policy releases, structured rule candidates, cross-policy comparisons, conflict cases, human review tasks, and approved search projections. Use when work involves document extraction, OCR or layout parsing, LLM-assisted policy understanding, policy normalization, amendment or version comparison, duplicate or collision detection, precedence ambiguity, reviewer workbenches, human-in-the-loop policy authoring, PostgreSQL policy catalogs, Blob source storage, Azure AI Search publication, or Microsoft Agent Framework ingestion workflows.
---

# Build Governed Policy Ingestion

## Objective

Build an authoring pipeline that converts one or more source files into an approved, immutable, fully traceable policy release without allowing an LLM, extractor, similarity score, or ingestion worker to create binding policy silently.

Produce three distinct representations:

| Representation | Role | Typical store |
| --- | --- | --- |
| Original source bundle | Immutable evidence of what was submitted; not automatically approved policy | Immutable Blob/object storage |
| Governed policy catalog | Authoritative metadata, approved clauses, relationships, and executable rules | PostgreSQL |
| Retrieval projection | Rebuildable discovery and evidence index | Azure AI Search |

Do not serialize one object blindly into all three stores. Preserve shared immutable identifiers and provenance while adapting each projection to its responsibility.

This skill governs policy authoring and publication. When present, also read:

- `.github/skills/build-policy-driven-agent-systems/SKILL.md` for runtime decisions, policy sets, agents, and actions;
- `.github/skills/build-policy-ai-search/SKILL.md` for production search schemas, embeddings, retrieval, and evaluation.

## Non-negotiable rules

1. Treat every extracted clause, definition, relationship, rule, date, scope, and precedence statement as a candidate until approved.
2. Require exact source provenance for every material candidate. A summary without a supporting source span is not publishable.
3. Never let the LLM decide document authority, precedence, legal effect, applicability, approval, or activation when approved metadata or human judgment is required.
4. Never equate semantic similarity with equivalence, conflict, supersession, or precedence.
5. Never let unresolved material conflicts enter an executable ruleset or runtime search index.
6. Never overwrite a published release. Create a new release and an explicit relationship such as `amends`, `supersedes`, `narrows`, or `adds_exception`.
7. Never recompute or rewrite historical decisions when a new release is published.
8. Never use free-form generated code or `eval` as an executable policy representation. Compile an approved typed rule model through deterministic code.
9. Never expose uploaded document instructions as system instructions or give the extraction model side-effecting tools.
10. Never claim complete extraction or conflict detection solely from model self-confidence. Evaluate against evidence, validators, comparison coverage, and reviewed test corpora.
11. Never guess version-sensitive Microsoft Agent Framework, Azure OpenAI, Document Intelligence, or Azure AI Search APIs. Inspect installed packages and current official documentation.
12. Never create or activate a runtime `PolicySet` during ingestion. Publish immutable `PolicyRelease` records; a deterministic runtime resolver later creates a case-pinned policy-set snapshot from all applicable releases.
13. Never model publication as one global active-policy pointer. Global policies, addenda, product rules, contractual terms, and approved exceptions may coexist; publish their scope and relationships for deterministic runtime resolution.

## Establish the task and authority boundary

For implementation work, inspect the repository before editing:

- language, frameworks, package versions, migrations, background-job mechanism, and deployment model;
- existing policy, document, search, workflow, approval, audit, and identity modules;
- current source-of-truth rules and every write path into legacy policy-version data;
- current Azure resources and configured model, extraction, embedding, and index capabilities;
- tenant boundaries, reviewer roles, separation-of-duty rules, and retention requirements.

Do not introduce a second policy framework when an authoritative domain model already exists. Extend or migrate it through explicit adapters and one-way authority.

Capture source-supplied metadata separately from extracted claims. Require an authorized owner to establish missing authority facts such as owner, document type, approval state, effective period, jurisdiction, and relationship to existing policies.

## Use an explicit ingestion workflow

Model ingestion as a durable, resumable workflow with typed stage outputs. Use deterministic executors for file handling, persistence, comparison, validation, publication, and status changes. Use constrained LLM agents only for bounded interpretation tasks.

Use this logical sequence:

1. **Register request** — create an ingestion job, correlation ID, tenant, requested policy domain, submitter, and idempotency key.
2. **Capture source bundle** — store every file and manifest immutably; calculate hashes; retain filenames, media types, order, locale, and attachment relationships.
3. **Validate intake** — scan content, verify supported formats, detect exact duplicates, enforce size and access limits, and quarantine failures.
4. **Extract layout** — recover pages, reading order, paragraphs, headings, lists, tables, cells, footnotes, headers, signatures, figures, and coordinates.
5. **Build canonical document model** — normalize layout without losing page/block/cell lineage; preserve both original text and normalized text.
6. **Map the document** — identify candidate document purpose, authority statements, dates, scope, definitions, annexes, cross-references, and normative regions.
7. **Extract policy semantics** — create clause, definition, rule, evidence, approval, exception, calculation, and process candidates with source spans.
8. **Resolve internal references** — connect defined terms, tables, footnotes, annexes, exceptions, and referenced clauses; flag broken or external references.
9. **Normalize candidates** — convert material statements into typed, domain-neutral semantics and optional domain extensions.
10. **Validate deterministically** — enforce schemas, units, dates, identifiers, evidence coverage, logical consistency, and compile-time rule restrictions.
11. **Find comparison candidates** — retrieve existing releases that may overlap by tenant, domain, authority, scope, dates, entities, products, definitions, and semantic similarity.
12. **Compare deeply** — run metadata, text, definition, rule-logic, process-graph, and impact diffs.
13. **Classify relationships and conflicts** — create evidence-backed suggestions and unresolved review cases; do not choose precedence silently.
14. **Route human review** — create risk-based tasks with complete review packets and separation-of-duty controls.
15. **Apply review decisions** — persist structured edits, reasons, relationships, approvals, and re-review requirements as append-only events.
16. **Compile and test rules** — compile only approved candidates; run generated and curated boundary, exception, overlap, and regression tests.
17. **Freeze the release** — materialize approved clauses and rules into an immutable `PolicyRelease` with a content fingerprint; do not resolve a case-specific policy set here.
18. **Publish projections** — commit a publication request through a transactional outbox; index approved content idempotently; verify completeness.
19. **Activate safely** — make the release eligible for deterministic policy-set resolution only after all mandatory readiness gates pass.
20. **Retain and monitor** — preserve every artifact, review, superseded release, index generation, evaluation result, and rollback route.

Do not collapse these stages into one long model call or one web request.

## Preserve independent status dimensions

Avoid a single overloaded status. Track at least:

```text
intakeStatus: RECEIVED | VALIDATED | QUARANTINED | FAILED
extractionStatus: PENDING | RUNNING | COMPLETE | NEEDS_REVIEW | FAILED
comparisonStatus: PENDING | COMPLETE | BLOCKED | FAILED
reviewStatus: NOT_REQUIRED | PENDING | IN_REVIEW | CHANGES_REQUESTED | APPROVED | REJECTED
rulesStatus: NOT_APPLICABLE | CANDIDATE | VALIDATED | FAILED
searchStatus: NOT_READY | PENDING | INDEXED | VERIFIED | FAILED
lifecycleStatus: DRAFT | APPROVED | SCHEDULED | PUBLISHED | RETIRED | WITHDRAWN
```

Define a deterministic readiness policy. A typical executable release cannot be published unless source integrity is verified, required reviews are approved, material conflicts are resolved, executable rules validate, and the runtime search projection is verified. Adapt gates by content type; explanatory material need not have executable rules.

## Extract in evidence-preserving passes

Do not ask one model to “understand the policy” and accept one opaque answer. Use hierarchical passes whose outputs are persisted and independently validated:

### Pass 1: Document map

Extract candidate document type, purpose, authority statements, policy family, version language, effective dates, jurisdictions, populations, products, owners, approvals, defined-term regions, appendices, and references.

### Pass 2: Structural clauses

Segment semantic units using document structure. Keep rules with their qualifiers, exceptions, table headers, footnotes, and definitions. Assign stable candidate IDs and exact spans.

### Pass 3: Clause semantics

Classify each unit as definition, applicability, obligation, prohibition, permission, entitlement, calculation, procedure, evidence requirement, approval, exception, discretion, guidance, conflict, or non-normative text.

### Pass 4: Normalized rules and processes

Represent rule candidates using typed fields for actor, subject, action, object, modality, conditions, exceptions, outcome, amount, unit, currency, calendar, scope, dates, evidence requirements, approval requirements, and cited spans. Represent processes as typed steps, guards, actors, timers, approvals, failure paths, and postconditions.

### Pass 5: Cross-reference closure

Resolve terms and references against the same bundle and catalog. Record unresolved, circular, ambiguous, versionless, or inaccessible references. Never silently substitute a semantically similar target.

### Pass 6: Independent verification

Check candidate assertions against source spans, tables, units, negation, exceptions, footnotes, page continuity, and output schemas. For high-risk material, use a separate verification pass or reviewer rather than asking the original extraction call to approve itself.

Read [references/extraction-contracts.md](references/extraction-contracts.md) before implementing schemas, persistence, prompts, or APIs.

## Constrain LLM policy analysis

Use Azure OpenAI structured outputs with a versioned JSON Schema when supported by the configured deployment. Validate again in application code.

For every extracted field, require:

- a value or explicit `unknown`;
- one or more immutable source-span IDs;
- extraction method and run ID;
- uncertainty and ambiguity reasons;
- dependencies on definitions, tables, footnotes, or other clauses;
- whether the value was explicit, derived deterministically, or inferred by the model.

Treat model-reported confidence as one signal, not a calibrated probability. Compute routing signals from evidence presence, OCR quality, parser/model agreement, schema validity, cross-reference closure, deterministic consistency checks, comparison coverage, materiality, and prior evaluation results.

Prefer abstention over forced extraction. A model must be able to return `unknown`, `ambiguous`, `conflicting_source`, and `needs_review`.

Keep model prompts free of policy authority. The prompt may define the extraction ontology and output contract; it may not declare which source wins unless that precedence is already approved catalog data.

Record model deployment, model/version where available, prompt-template version, schema version, temperature and other relevant parameters, input artifact hashes, output, validation results, latency, and token usage. Reprocessing creates a new `ExtractionRun`; it never mutates an old run.

## Normalize without destroying meaning

Use a stable core ontology and permit versioned domain extensions. Do not hard-code one HR, hardware, warranty, finance, or legal schema into the platform.

Normalize:

- actors, subjects, resources, actions, and outcomes;
- modalities such as must, must not, may, is entitled to, and requires approval;
- Boolean conditions and explicitly grouped alternatives;
- thresholds with inclusive/exclusive boundaries;
- units, currencies, rounding, calendars, time zones, and date anchors;
- applicability dimensions and exclusions;
- exceptions and exception-to-exception relationships;
- evidence and approval requirements;
- definitions and synonyms;
- precedence or amendment statements explicitly present in the source.

Keep original wording beside normalized semantics. Do not erase qualifiers during normalization. Do not convert uncertainty into a default value.

## Compare against the full applicable catalog

Do not compare only against the latest similarly named file. Build a candidate comparison set using deterministic metadata filters first and lexical/vector discovery second.

Compare at six levels:

1. **Identity and authority** — policy family, issuer, approval state, jurisdiction, owner, and source type.
2. **Temporal and applicability** — effective dates, event-date anchors, populations, entities, regions, products, contracts, and exceptions.
3. **Text and structure** — inserted, removed, moved, or rewritten clauses, tables, definitions, annexes, and footnotes.
4. **Semantic rules** — condition trees, modalities, thresholds, outcomes, evidence, approvals, and exception logic.
5. **Process behavior** — actors, ordering, branches, timers, escalation, and side effects.
6. **Impact** — test cases or authorized representative scenarios whose outcomes change.

Use embeddings to discover possible overlap and paraphrase. Use normalized semantics and deterministic analysis to establish concrete differences. Require human judgment for authority, interpretation, unresolved ambiguity, or material conflicts.

Read [references/collision-and-diff.md](references/collision-and-diff.md) before implementing comparison, conflict detection, precedence, or impact analysis.

## Distinguish difference from conflict

Classify relationships with evidence rather than a binary “same/different” label. Support at least:

```text
EXACT_DUPLICATE
FORMATTING_ONLY
SEMANTICALLY_EQUIVALENT
ADDITIVE
CLARIFYING
NARROWING
WIDENING
AMENDS
SUPERSEDES
ADDS_EXCEPTION
PARTIAL_OVERLAP
DEFINITION_DRIFT
TEMPORAL_OVERLAP
DIRECT_CONFLICT
PROCEDURAL_CONFLICT
AUTHORITY_OR_PRECEDENCE_UNKNOWN
AMBIGUOUS
UNRELATED
```

A difference becomes a conflict only when applicable statements cannot be satisfied or resolved together for at least one relevant scenario, or when their authority/precedence cannot be established safely. Preserve the witness scenario and exact conflicting spans.

Block automatic publication for material direct conflicts, missing precedence, authority uncertainty, ambiguous effective dates, unresolved definition drift, broken material references, or low-confidence material extraction.

## Build a reviewer workbench, not an approval button

Make human judgment efficient without hiding evidence. Every review task must show:

- original document pages with highlighted source spans and table context;
- normalized clause and rule candidates;
- extracted dates, scopes, authority, relationships, and uncertainty;
- side-by-side existing and candidate clauses;
- textual, semantic, rule-tree, and impact differences;
- why the task was created and what publication gate it blocks;
- affected policy definitions and overlapping releases;
- generated boundary tests and representative outcome changes;
- complete prior review history, comments, assignments, and approvals.

Permit authorized reviewers to accept, edit, reject, mark non-normative, split, merge, relink evidence, map definitions, declare release relationships, establish approved precedence, request clarification, delegate, or escalate. Require reason codes and notes for material judgments.

Treat a material reviewer edit as a new revision requiring revalidation and, when required, second approval. Preserve who changed what, when, why, and from which source evidence.

Read [references/review-workbench.md](references/review-workbench.md) before implementing human-in-the-loop APIs, UI, roles, queues, or audit records.

## Use risk-based human routing

Do not require identical review effort for every clause, and do not auto-approve merely because confidence is high.

Route using configurable factors:

- binding versus explanatory content;
- financial, legal, safety, employment, access, or customer impact;
- new entitlement, prohibition, threshold, deadline, exception, or approval requirement;
- conflict severity and number of potentially affected policies;
- extraction uncertainty and OCR/table quality;
- scope breadth and expected case volume;
- authority and precedence completeness;
- whether behavior changes in impact tests;
- regulatory, contractual, privacy, or separation-of-duty requirements.

Allow low-risk, non-normative, unchanged material to be batch-reviewed only when governance permits. Require named policy-owner approval for executable rules and stronger approval for configured high-risk classes.

## Persist a complete lineage model

Use PostgreSQL as the transactional authority unless the repository has an established alternative that satisfies equivalent constraints. Separate immutable artifacts from mutable workflow projections.

Model concepts equivalent to:

- authoritative `PolicyDefinition` and immutable `PolicyRelease` records;
- `SourceBundle`, `SourceAsset`, and `SourceSpan`;
- `IngestionJob` and immutable `ExtractionRun`;
- `ClauseCandidate`, `DefinitionCandidate`, `RuleCandidate`, and `ProcessCandidate`;
- approved `PolicyClause`, `PolicyDefinitionTerm`, `PolicyRule`, and `PolicyProcess`;
- `PolicyRelationship`, `PolicyComparison`, `ConflictCase`, and `ImpactRun`;
- `ReviewTask`, `ReviewRevision`, `ReviewDecision`, and `Approval`;
- `IndexProjection`, `OutboxEvent`, and append-only `AuditEvent`.

Reuse an existing legacy identifier only after proving one-to-one semantic and type compatibility. Do not keep two writable sources of truth. Make compatibility models read-only and remove them through a measured cutover.

Keep large layout and extraction payloads in immutable object storage when appropriate; retain hashes, typed summaries, and lineage in PostgreSQL. Never store only a pointer to an unversioned mutable object.

Treat `PolicySet` as a separate runtime concept owned by the deterministic applicability resolver. Ingestion may report how a candidate release could affect representative policy sets, but it must not persist a policy set as the publication unit. Search evidence remains identified by `policyReleaseId + clauseId`; a runtime policy set contains the ordered applicable release IDs.

## Publish through staged projections

PostgreSQL, Blob Storage, and Azure AI Search do not share a transaction. Use an outbox-driven saga:

1. Freeze the approved release and insert `PolicyPublicationRequested` in one database transaction.
2. Have an idempotent worker create the search projection using stable `policyReleaseId + clauseId + projectionVersion` identities.
3. Index drafts only into a separately secured review index when reviewer search is required.
4. Keep draft, rejected, future-unapproved, and unresolved-conflict content out of the runtime index.
5. Verify expected counts, hashes, lineage, authorization fields, and exact-evidence retrieval.
6. Record a verified `IndexProjection` and update readiness through a new transaction.
7. Activate the release only through the deterministic catalog/resolver after all gates pass.

Search is a derived projection. Rebuild it from approved catalog data and immutable source artifacts. Changing the embedding model or chunking implementation creates a new projection version, not a new policy release unless policy meaning changed.

## Integrate Microsoft Agent Framework deliberately

Use an explicit MAF workflow for long-running extraction and human review when the repository uses MAF and benefits from durable pause/resume behavior.

Prefer typed executors for:

- source storage and hashing;
- layout/OCR calls;
- schema validation and persistence;
- comparison-set construction;
- deterministic diffs and rule compilation;
- review-task creation and authorization;
- outbox publication and index verification.

Use constrained agents for:

- document mapping;
- semantic clause extraction;
- normalized rule proposals;
- cross-reference suggestions;
- comparative explanations;
- reviewer-facing summaries and proposed test cases.

Use MAF request/response human-in-the-loop to pause without occupying a worker. Persist the authoritative review task outside conversation history. Resume by verified task and workflow IDs with optimistic concurrency and authorization checks.

Do not use dynamic group chat as the authoritative ingestion path. Multiple extraction agents may provide independent candidates, but deterministic reconciliation and human gates control publication.

## Make the pipeline operationally safe

Require:

- idempotency keys derived from tenant, source-bundle hash, requested operation, and pipeline version;
- bounded retries, backoff, timeouts, cancellation, dead-letter handling, and operator replay;
- stage-level checkpoints so expensive extraction is not repeated unnecessarily;
- optimistic concurrency on review tasks and mutable catalog metadata;
- least-privilege identities and document-level authorization;
- encrypted storage, malware handling, retention, legal hold, and deletion policies where required;
- content/prompt-injection isolation and no extractor access to action tools;
- separate operational telemetry and immutable governance audit;
- cost, token, latency, retry, model, prompt, schema, and projection version telemetry without logging sensitive content by default.

Make every stage rerunnable from immutable inputs. Retries must not duplicate releases, review tasks, outbox events, or search chunks.

## Verify before claiming completion

Read and apply [references/verification.md](references/verification.md) when designing tests, reviewing an implementation, changing prompts/models/schemas, or declaring a release ready.

At minimum, test:

- clean native documents, scans, tables, footnotes, annexes, and multiple-file bundles;
- exact duplicates, paraphrases, amendments, narrowing, widening, exceptions, temporal overlaps, and direct conflicts;
- negation, inclusive/exclusive thresholds, units, currencies, calendars, date anchors, and definition changes;
- multilingual and right-to-left documents when in scope;
- missing pages, poor OCR, broken references, prompt injection, unauthorized files, and cross-tenant access;
- review concurrency, reassignment, escalation, rejection, material edits, dual approval, timeout, and resume;
- outbox retries, partial index failure, verification failure, rollback, replay, and no runtime exposure of drafts;
- historical decisions remaining pinned and unchanged after publication.

Maintain a policy-owner-reviewed golden corpus. Measure extraction, provenance, comparison, conflict, review, and publication quality separately. Do not hide critical false negatives inside an aggregate score.

## Produce implementation artifacts

For architecture work, produce the relevant subset of:

1. Trust boundaries and store responsibilities.
2. Ingestion state machine and failure/recovery paths.
3. Canonical document, extraction, normalized rule, comparison, review, publication, and audit contracts.
4. LLM pass design, structured-output schemas, provenance, uncertainty, and injection controls.
5. Policy catalog and immutable lineage model.
6. Difference, relationship, collision, precedence, and impact-analysis design.
7. Human review roles, queues, APIs, and reviewer-workbench design.
8. MAF workflow with typed messages, checkpoints, and HITL requests.
9. Blob/PostgreSQL/AI Search consistency, outbox, idempotency, activation, rollback, and replay design.
10. Security, observability, evaluation corpus, quality gates, and operational ownership.

For implementation work:

- inspect and extend owning modules rather than adding parallel frameworks;
- define domain contracts before service-specific adapters;
- keep extraction candidates distinct from approved policy entities;
- isolate object storage, document analysis, model inference, catalog, comparison, review, rule compilation, search publication, and MAF adapters;
- implement one vertical slice with a representative policy bundle and a deliberate collision;
- add migrations, deterministic backfill, indexes, constraints, and rollback plans;
- test empty-database and populated-database upgrades;
- run focused tests first, then the repository's complete verification suite;
- report exactly what was executed and what requires deployed-resource validation.

Do not stop after scaffolding or a plan when implementation is requested, unless blocked by missing authority, credentials, source documents, or a decision only the user can make.

## Current official references

Verify version-sensitive behavior with current official sources:

- Azure AI Document Intelligence layout: https://learn.microsoft.com/azure/ai-services/document-intelligence/prebuilt/layout
- Document Intelligence RAG and semantic structure: https://learn.microsoft.com/azure/ai-services/document-intelligence/concept/retrieval-augmented-generation
- Azure OpenAI structured outputs: https://learn.microsoft.com/azure/foundry/openai/how-to/structured-outputs
- Microsoft Agent Framework workflows: https://learn.microsoft.com/agent-framework/workflows/
- MAF human-in-the-loop: https://learn.microsoft.com/agent-framework/workflows/human-in-the-loop
- MAF durable extension: https://learn.microsoft.com/agent-framework/integrations/durable-extension
- Azure AI Search RAG: https://learn.microsoft.com/azure/search/retrieval-augmented-generation-overview
- Azure AI Search hybrid search: https://learn.microsoft.com/azure/search/hybrid-search-overview
- Azure Database for PostgreSQL: https://learn.microsoft.com/azure/postgresql/overview

Prefer installed package documentation and current official Microsoft documentation over remembered API signatures. Keep integrations behind typed ports when deployed configuration is unavailable.
