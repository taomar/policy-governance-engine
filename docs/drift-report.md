# Documentation drift report

_Branch: taomar-microsoft-policy-queue-and-backlog._

This is a verify-before-rewrite audit of the 26 reference documents under
`docs/` — every top-level `docs/*.md` except `docs/HANDOVER.md`, which is owned
elsewhere, and `docs/failures/`, the failure record. Each material claim was
checked against the code, the database, or the live API surface. A document that
is old but still true was left untouched; needless churn is its own drift.

## Method and evidence sources

- API surface: `create_app().openapi()`, asserted by
  `tests/unit/test_documented_api_surface_is_current.py`.
- Database: the `policy-postgres` container, database `policy_platform_advtool`.
- Code: direct reads under `src/policy_platform/` and `apps/web/src/`.
- Table set: `Base.metadata.tables` introspection.

## Summary

- 26 documents checked.
- 3 documents corrected: architecture.md, data-model.md, configuration.md.
- 23 documents verified accurate and left unchanged.
- More than 150 material claims checked; 8 corrected.

## Per-document verdict

| Document | Verdict | Basis |
|---|---|---|
| ai-assistance.md | Accurate | Stage 2 canonical plus DMN projection and grounding match the code |
| api.md | Accurate | Headline and all 13 tag counts pass the surface test |
| architecture.md | Corrected | Sub-package count, router count, reconciler scope |
| azure-deployment-options.md | Accurate | Service and SKU choices verified |
| azure-deployment.md | Accurate | Steps and resource names verified |
| azure-operations.md | Accurate | Runbook steps verified |
| azure-prerequisites.md | Accurate | Tooling and role list verified |
| capability-flows.md | Accurate | Flow boundaries match code; one flag below |
| configuration.md | Corrected | Web dev port, CORS range, reconciler scope |
| data-model.md | Corrected | Mapped-table count and three undocumented tables |
| docling.md | Accurate | Module paths verified |
| extraction-run-coverage.md | Accurate | Run-completion constants verified |
| frameworks.md | Accurate | Versions verified against the manifest and compose |
| how-we-work.md | Accurate | Methodology modules verified |
| known-limitations.md | Accurate | Debt counts are test-guarded |
| microsoft-technologies.md | Accurate | Product mapping verified |
| policy-standards-research.md | Accurate | External-standard summary; one flag below |
| README.md | Accurate | Document links resolve |
| relationships.md | Accurate | Grouping helper verified |
| repair-passes.md | Accurate | Pass modules and scripts verified |
| running-path.md | Accurate | Call-path names verified |
| security-roadmap.md | Accurate | Posture items verified |
| standards.md | Accurate | Representation modules verified; SBVR scope is disclaimed in text |
| testing.md | Accurate | Mutation and skip totals are test-guarded; one flag below |
| user-guide.md | Accurate | Route table and inspector placement match the recorded changes |
| workflows.md | Accurate | Lifecycle and route table match; flags below |

## Corrections, with evidence

### architecture.md

1. **Sub-package count.** Line 57 states "eleven sub-packages". The
   `src/policy_platform/infrastructure/` tree carries fourteen directories with an
   `__init__.py`: aggregates, ai, `assembly/`, assistants, `consolidation/`,
   correlation, docling, extraction, ingestion, persistence, policy_tests,
   projection, quality, search. The `prompts/` directory carries no `__init__.py`
   and is not a package. Corrected to "fourteen"; the layer table gains a row for
   `assembly/` (grouping rules into policies, with provision history and the
   rule-name and topic-label lookups) and one for `consolidation/` (collapsing
   records emitted more than once into a single record).
2. **Router count.** Line 58 states "ten routers". `api/app.py` registers twelve
   through `include_router`: policy_sets, candidate_rules, evaluations,
   documents, ai, notes, policy_tests, audit, policy_exceptions,
   policy_attestations, policy_payload, extraction. Corrected to "twelve".
3. **Reconciler scope.** Lines 122-124 describe the startup sweep over any
   interrupted run. `api/app.py` filters on `owner_kind == OWNER_API`, so the
   sweep now touches only runs the API itself started and leaves foreign runs
   alone. Prose corrected to state the owner scoping.

### data-model.md

- **Mapped-table count.** Line 3 states "26 tables". `Base.metadata.tables`
  introspects to 29. The three not listed are `extraction_stages`
  (`ExtractionStage`, `domain/models.py`), `candidate_rule_names`
  (`CandidateRuleName`, `domain/models.py`), and `provision_topic_labels`
  (`ProvisionTopicLabel`, `domain/models.py`). Corrected to "29"; the three rows
  were added under "Extraction and review". The Mermaid diagram is a curated
  subset and was left alone.

### configuration.md

- **Web dev server port.** Line 28 lists `WEB_DEV_SERVER_PORT` as `5174`. The
  `.env.example` default is `5490`. Corrected.
- **CORS dev port range.** The same line notes a range ending at 5179.
  `infrastructure/settings.py` sets `cors_dev_port_range` to a range ending at
  5180. Corrected.
- **Reconciler scope.** Lines 190-192 carry the same unscoped-sweep wording as
  architecture.md, and were corrected the same way from `api/app.py`.

## Aggregate Limits — flagged for your decision, not changed

`policy_aggregate_limits` holds zero rows and the feature is being retired, but
another change is in flight, so nothing here was deleted. These are the places
the feature is described, for you to decide:

| Document | Lines |
|---|---|
| api.md | 31 |
| architecture.md | 77, 228 |
| capability-flows.md | 86, 95, 200 |
| data-model.md | 20, 37, 97 |
| policy-standards-research.md | 15, 16, 39, 72 |
| testing.md | 35, 80 |
| user-guide.md | 98, 309, 353 |
| workflows.md | 92, 108, 124, 150 |

Line numbers for architecture.md and data-model.md are as of this analysis; the
corrections above add rows to both, so their later lines shift down by a few.

## Reported to you, not edited

`docs/HANDOVER.md` and `docs/failures/` are owned elsewhere. Nothing in them was
found wrong during this pass. Route vocabulary follows
`docs/failures/route-vocabulary-and-framing.md`.

## Claims checked versus changed

More than 150 material claims were checked across the 26 documents. Eight were
corrected, in three documents. The other 23 documents were already true and were
left as they were.
