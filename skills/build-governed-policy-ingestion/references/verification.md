# Verification and quality gates

## Contents

1. Verification strategy
2. Golden corpus
3. Intake and layout tests
4. Semantic extraction tests
5. Comparison and conflict tests
6. Reviewer workflow tests
7. Rule compilation tests
8. Publication and consistency tests
9. Security and privacy tests
10. Resilience and performance tests
11. Model and prompt change gates
12. Definition of done

## Verification strategy

Test each stage independently and the complete publication path end to end. Separate deterministic correctness, model-assisted quality, reviewer effectiveness, and operational reliability.

Do not report one aggregate “accuracy” number. A high average can hide critical failures such as missed prohibitions, lost exceptions, wrong dates, inaccessible evidence, or unresolved conflicts.

Assign explicit owners and thresholds to each quality gate. Policy owners approve semantic relevance and conflict judgments; engineering owns schema, integrity, security, resilience, and publication correctness.

## Golden corpus

Maintain a versioned, policy-owner-reviewed corpus containing:

- native PDF, DOCX, HTML, text, and supported images;
- scanned and low-quality documents;
- multi-column pages, headers, footers, signatures, and handwritten annotations when in scope;
- simple and merged-cell tables with units and footnotes;
- one-file policies and multi-file bundles with annexes and addenda;
- exact duplicates and formatting variants;
- paraphrases and reorganized but equivalent releases;
- amendments, supersessions, narrowing, widening, and added exceptions;
- direct, procedural, temporal, scope, authority, and definition conflicts;
- ambiguous, incomplete, unsigned, draft, and versionless sources;
- cross-references, broken references, circular definitions, and external authorities;
- multiple languages and right-to-left text when in scope;
- prompt-injection and adversarial document content;
- material with no executable rules;
- documents intentionally outside the policy domain.

Annotate exact spans, clause boundaries, semantic classes, normalized rules, relationships, conflicts, approved precedence outcomes, and expected review routing. Use synthetic content when real sources cannot be retained safely.

Keep training/tuning material, development evaluation, and final holdout sets separate when models or prompts are optimized against the corpus.

## Intake and layout tests

Verify:

- immutable storage version and SHA-256 integrity;
- deterministic bundle-manifest hashing;
- MIME and extension mismatch handling;
- malware/quarantine flow;
- exact duplicate detection and idempotent submission;
- attachment ordering and parent-child relationships;
- page count, reading order, headings, paragraphs, lists, tables, cells, footnotes, and coordinates;
- merged table-cell reconstruction and units;
- source span round-trip from database to rendered page;
- missing, duplicated, rotated, or blank pages;
- OCR uncertainty preservation;
- cancellation, timeout, retry, and replay without duplicate artifacts.

Do not mark layout extraction complete when normative pages or table context are missing.

## Semantic extraction tests

Measure separately:

- clause segmentation precision, recall, and boundary quality;
- semantic classification by type;
- exact provenance/span correctness;
- field precision and recall for dates, scope, authority, actors, actions, modalities, outcomes, thresholds, units, evidence, approvals, and exceptions;
- definition extraction and dependency closure;
- cross-reference resolution rate and correctness;
- normalized rule schema validity;
- negation and modality preservation;
- inclusive/exclusive boundary correctness;
- table, footnote, annex, and exception attachment correctness;
- abstention on absent or ambiguous values;
- false assertion rate for unsupported fields;
- consistency across repeated runs where stability is required.

Score material fields more severely, but retain per-field and per-policy-family results. Model self-confidence is not a ground-truth label.

Create adversarial pairs such as:

```text
may / must
eligible / not eligible
more than 6 / at least 6
5 business days / 5 calendar days
request date / incident date
manager approval / HR director approval
all employees / permanent employees
unless approved / if approved
```

## Comparison and conflict tests

For each relationship class, include positive, negative, and difficult near-neighbor examples.

Measure:

- comparison-candidate recall before semantic classification;
- clause alignment precision and recall;
- atomic difference correctness;
- relationship classification precision and recall;
- conflict recall, especially for critical conflicts;
- false conflict rate;
- definition-drift detection;
- temporal and scope-overlap correctness;
- witness-scenario validity;
- comparison coverage reporting;
- correct escalation when authority or precedence is missing;
- refusal to treat similarity as equivalence or precedence.

Test collisions caused only by:

- one negation;
- one boundary operator;
- one changed unit, currency, calendar, or rounding rule;
- an altered definition with unchanged rule text;
- a footnote or exception;
- different event-date anchors;
- overlapping regional/global scope;
- a grandfathering or transition clause;
- an inaccessible external reference.

Require zero known silent publication of critical unresolved conflicts in the release test suite. This is a release gate, not a claim that all real-world conflicts can be detected automatically.

## Reviewer workflow tests

Verify:

- queue filters and authorization;
- exact source and comparison evidence rendering;
- stale review revision rejection;
- claim, release, delegation, reassignment, and escalation;
- request-for-information and resume;
- material edits create a new revision and invalidate required approvals;
- reason codes and notes are required appropriately;
- dual approval and separation of duties;
- rejection, withdrawal, and resubmission;
- SLA timeout and durable resume after restart;
- optimistic concurrency under competing reviewers;
- no model or service account can approve as a human;
- complete append-only audit history;
- notifications do not leak sensitive content;
- accessibility behavior for keyboard, screen reader, zoom, table, and right-to-left views when in scope.

Evaluate reviewer assistance with real reviewers where possible:

- time to correct resolution;
- percentage of suggestions accepted, edited, or rejected;
- critical findings missed before and after assistance;
- reviewer disagreement and escalation rate;
- source-view usage and evidence verification;
- cognitive load and usability feedback.

Do not optimize only for task completion time.

## Rule compilation tests

Verify:

- only approved candidates compile;
- operator and fact vocabularies are allowlisted;
- arbitrary code, SQL, tool calls, and unsafe expressions are rejected;
- deterministic output for the same verified facts and release set;
- three-valued handling of missing facts;
- every threshold boundary;
- every branch and exception;
- date, calendar, time-zone, currency, unit, and rounding behavior;
- overlapping rule detection and approved precedence;
- generated tests cannot approve themselves;
- approved regression tests remain pinned to the release;
- rule IDs and evidence references round-trip to exact clauses.

Use mutation testing when practical: change operators, values, negation, and branches and verify that tests fail.

## Publication and consistency tests

Verify:

- release freeze and content fingerprint stability;
- no update path for frozen/published release content;
- catalog plus outbox atomicity;
- outbox retries and duplicate delivery;
- stable search IDs and idempotent upsert;
- partial indexing failure leaves the release non-publishable;
- count, hash, release, clause, ACL, and lineage verification;
- draft and rejected content cannot appear in runtime retrieval;
- exact evidence lookup by `policyReleaseId + clauseId`;
- blue/green or equivalent projection rollback;
- embedding/chunking changes create projection versions without changing policy meaning;
- activation occurs only after configured gates;
- scheduled activation handles effective dates correctly;
- retirement prevents new applicability without deleting historical evidence;
- historical policy sets and decisions remain unchanged;
- empty-database migration and populated-schema upgrade;
- backfill collisions, orphaned references, and deterministic re-runs.

Inject failures between every cross-service step to confirm safe recovery.

## Security and privacy tests

Test:

- malicious instructions embedded in files, OCR layers, metadata, tables, and images;
- extractor isolation from action tools and privileged APIs;
- unsupported file, archive bomb, oversized input, and decompression limits;
- tenant and document-level access control at every stage;
- unauthorized comparison candidates and search results;
- source URI and signed-link leakage;
- sensitive data minimization in prompts, logs, traces, queues, and notifications;
- role and policy-domain authorization;
- separation-of-duty bypass attempts;
- forged reviewer identity or callback;
- replayed approval response and idempotency;
- stale or tampered source spans and hashes;
- secret and credential handling;
- retention, legal hold, withdrawal, and deletion behavior.

Treat prompts, model outputs, extracted text, and search results as untrusted data at rendering and integration boundaries.

## Resilience and performance tests

Test:

- burst uploads and large bundles;
- extraction and model throttling;
- queue backlog and reviewer SLA behavior;
- bounded concurrency by tenant and provider;
- retry storms and poison messages;
- workflow restart while awaiting review;
- database, object storage, model, document analysis, queue, and search outages;
- stage checkpoint restoration;
- cancellation and operator replay;
- duplicate messages and out-of-order events;
- cost and token budgets;
- database query and comparison-set performance as catalog size grows;
- index publication time and activation lag;
- telemetry cardinality and sensitive-content suppression.

Define service-level objectives for intake acknowledgment, extraction completion, review routing, publication, and recovery. Human wait time should not consume active compute.

## Model and prompt change gates

Treat changes to model deployment, prompt, structured-output schema, ontology, extraction algorithm, OCR/layout provider, or comparison logic as versioned pipeline changes.

Before rollout:

1. Run deterministic contract tests.
2. Run the full golden corpus.
3. Compare per-field and per-conflict regressions to the approved baseline.
4. Review changed critical outputs manually.
5. Run shadow extraction on representative new bundles when permitted.
6. Record cost, latency, abstention, and review-routing changes.
7. Approve the rollout and preserve rollback configuration.

Do not overwrite old extraction outputs. Do not silently reprocess published releases into new semantics. A new pipeline may create a new analysis or search projection; changing approved policy meaning requires a new governed release.

## Definition of done

Do not call the ingestion system production-ready until:

- store authority and trust boundaries are explicit;
- all contracts are typed and versioned;
- every approved material field has verified provenance;
- published releases and review decisions are immutable;
- critical unresolved conflicts block publication;
- reviewer authorization, concurrency, separation of duties, and durable resume are tested;
- rule compilation and policy boundaries are deterministic and covered;
- outbox, projection verification, activation, rollback, and replay are tested;
- runtime search excludes drafts and supports exact evidence;
- representative extraction and conflict metrics meet owner-approved thresholds;
- prompt-injection, tenant isolation, privacy, and retention controls are validated;
- deployed Azure integrations and installed SDK signatures are verified;
- operational dashboards, alerts, runbooks, ownership, and cost limits exist;
- remaining limitations and manual responsibilities are documented honestly.
