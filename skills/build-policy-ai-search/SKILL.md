---
name: build-policy-ai-search
description: Design, implement, refactor, or review Azure AI Search, embeddings, vector search, hybrid retrieval, semantic ranking, policy indexing, access-controlled RAG, and exact policy evidence retrieval for governed AI and Microsoft Agent Framework systems. Use when a task involves making policies, procedures, standards, regulations, contracts, manuals, decision explanations, or process documents searchable and citable without allowing retrieval or an LLM to become the binding policy decision engine.
---

# Build Policy AI Search

## Objective

Build an access-controlled Azure AI Search layer that helps agents discover relevant policy knowledge and retrieve exact supporting evidence while preserving the boundary between probabilistic retrieval and deterministic policy enforcement.

Use this skill independently for retrieval-specific work. When `.github/skills/build-policy-driven-agent-systems/SKILL.md` exists and the task also includes decisions, approvals, workflow orchestration, exceptions, or actions, read and apply that skill as well.

## Non-negotiable boundary

Use Azure AI Search, embeddings and RAG for:

- semantic policy discovery;
- exact term, code and clause lookup;
- definitions and terminology;
- identifying potentially relevant sections;
- identifying candidate facts the intake process may need;
- retrieving procedures, guidance and exceptions;
- exact evidence and citations for an immutable decision;
- policy-authoring and analysis support.

Never use retrieval score, vector similarity, semantic ranker output or LLM interpretation as the authority for:

- policy applicability or precedence;
- selection of the binding policy release;
- eligibility or entitlement;
- threshold, date, calendar, currency or quantity calculations;
- approval or exception decisions;
- authorization;
- permission to execute an action.

Keep those responsibilities in deterministic services, metadata filters, authorization components, explicit workflows and authorized human gates.

## Establish the task mode

Determine whether the request is architecture, implementation, review, migration, indexing, query design or evaluation.

Before changing code:

1. Inspect the repository, language, package versions, deployment model and existing Azure resources.
2. Read the relevant source documents and schemas rather than relying on summaries.
3. Identify the authoritative policy source, versioning model, approval state and access classification.
4. Inspect existing index definitions, indexers, skillsets, vectorizers, embedding clients, query code and authorization logic.
5. Verify current Azure AI Search and Azure OpenAI APIs through official Microsoft documentation before generating version-sensitive code.
6. Do not invent an embedding deployment, model name, vector dimension, API version, index name, field name, semantic configuration or service capability.

If a required deployment or policy-authority decision is missing, state the exact blocker and keep the design configurable instead of fabricating a value.

## Use the retrieval architecture

Separate the solution into:

| Component | Responsibility |
| --- | --- |
| Canonical source | Store approved policy documents and source metadata |
| Publication pipeline | Extract, classify, chunk, enrich, embed and publish an immutable release |
| Azure AI Search index | Store searchable content, vectors, citations, applicability metadata and authorization metadata |
| Discovery retrieval | Find semantically or lexically relevant policy content during intake and exploration |
| Evidence retrieval | Fetch exact clauses referenced by an authoritative decision |
| Deterministic policy service | Make binding decisions and return rule and evidence identifiers |
| Explanation agent | Explain the immutable decision using authorized exact evidence |
| Audit and telemetry | Record release, query, filters, evidence IDs and operational behavior |

Do not collapse the canonical source, search index and executable ruleset into one representation.

## Build a governed publication pipeline

For each approved policy release:

1. Capture `policyId`, version, immutable `releaseId`, status, effective dates, scope, owner, approval metadata, source URI and source hash.
2. Extract headings, paragraphs, definitions, lists, tables, footnotes, annexes and cross-references.
3. Classify content such as definition, rule explanation, procedure, exception, evidence requirement, form instruction or FAQ.
4. Create semantic policy units with stable identifiers.
5. Preserve clause, section, table and page lineage.
6. Attach applicability and authorization metadata.
7. Generate embeddings only for fields intended for semantic retrieval.
8. Validate the output against the approved source.
9. Publish the search projection under the same `releaseId` used by the authoritative ruleset.
10. Activate the release through a controlled pointer or equivalent mechanism.
11. Retain previous releases for historical search, replay, rollback and audit.

Do not overwrite an active release in place. Prevent runtime queries from mixing chunks, vectors or metadata from different releases.

## Chunk by policy meaning

Prefer chunks that correspond to complete policy units:

- one definition and its scope;
- one rule with all qualifiers;
- one exception with its conditions;
- one procedure stage;
- one table with the header information necessary to interpret its rows;
- one evidence requirement;
- one FAQ answer linked to its authoritative clause.

Avoid separating:

- a rule from its exception;
- a table row from its headers and units;
- a clause from a material footnote;
- a defined term from the definition needed to interpret it;
- regional or population qualifiers from the rule they constrain.

When content must be split, store parent-child and cross-reference identifiers so retrieval can reconstruct the complete evidence unit.

Do not treat arbitrary fixed token chunking as the default when the document structure is available.

## Design the index explicitly

Use fields equivalent to the following and adapt them to repository conventions:

```json
{
  "id": "unique-search-record-id",
  "policyId": "stable-policy-id",
  "policyVersion": "human-readable-version",
  "policyReleaseId": "immutable-release-id",
  "clauseId": "stable-clause-id",
  "parentClauseId": null,
  "section": "section-title",
  "page": 0,
  "content": "authorized-policy-text",
  "contentVector": [],
  "contentType": "definition|rule_explanation|procedure|exception|evidence|faq",
  "effectiveFrom": null,
  "effectiveTo": null,
  "jurisdictions": [],
  "applicability": {},
  "status": "active",
  "authorizedPrincipals": [],
  "sensitivity": null,
  "sourceUri": "authoritative-source-location",
  "sourceHash": "source-document-hash"
}
```

Choose field attributes intentionally:

- make exact identifiers filterable and retrievable;
- make authorization and applicability fields filterable;
- make policy codes and clause identifiers searchable where useful;
- keep vector fields non-retrievable unless the application genuinely needs raw vectors;
- avoid making sensitive metadata searchable without a requirement;
- preserve stable IDs across re-indexing of the same immutable release.

Verify the configured vector dimension against the actual embedding deployment. Never guess it.

## Configure embeddings responsibly

Generate embeddings from the policy text used for semantic discovery. Optionally include a controlled combination of title, section path, defined terms and content when evaluation shows that it improves retrieval.

Do not embed:

- credentials or secrets;
- unauthorized content into a shared index without enforceable access metadata;
- unstable runtime values that belong in case state;
- executable rule state as a substitute for the rules engine;
- irrelevant boilerplate that reduces retrieval quality.

Select integrated vectorization or a custom embedding pipeline based on the existing platform:

- Prefer integrated vectorization when supported sources, operational simplicity and managed indexer behavior meet the requirements.
- Prefer a custom pipeline when extraction, table reconstruction, approval workflow, chunk control, release atomicity or custom enrichment requires application control.

Keep deployment names, endpoints, credentials and dimensions in validated configuration. Use managed identity where supported and appropriate.

Batch ingestion safely, observe service limits, handle throttling and make indexing idempotent. Record embedding configuration and content hashes so unchanged chunks need not be re-embedded unnecessarily.

## Use hybrid retrieval deliberately

Combine retrieval methods according to the query:

- **Keyword or lexical search:** exact policy codes, clause numbers, defined terms, product names and quoted wording.
- **Vector search:** paraphrases, synonyms, informal descriptions, multilingual or semantically related wording when supported and evaluated.
- **Hybrid search:** combine lexical precision with semantic recall for general policy questions.
- **Semantic ranking:** rerank an already authorized candidate set when configured and validated.
- **Exact lookup:** retrieve known `clauseId + policyReleaseId` evidence without semantic approximation.

Do not assume hybrid search is always better. Evaluate it against keyword-only and vector-only baselines using representative queries and policy-owner-approved relevance judgments.

## Implement two separate retrieval paths

### Discovery retrieval

Use discovery retrieval during intake, exploration and policy question answering.

It may identify:

- a likely policy domain;
- relevant definitions and sections;
- alternative terminology;
- facts that might be material;
- procedures or evidence requirements that may apply.

Use hybrid retrieval when justified. Treat the results as candidates, not decisions. If discovery retrieves conflicting releases or policies, do not let the agent resolve precedence silently.

### Exact evidence retrieval

After the deterministic decision service returns `policyReleaseId`, `matchedRuleIds` and `evidenceRefs`, retrieve the cited evidence by exact identifiers.

Require:

- exact `policyReleaseId` match;
- exact clause or evidence ID match;
- authorization checks;
- source URI, page and section metadata;
- failure when the referenced evidence cannot be found.

Do not silently replace missing exact evidence with the most semantically similar clause. Return an integrity error or human-review condition.

## Apply security and applicability filters first

Before content is returned to the application or model, enforce:

- authenticated caller identity;
- tenant boundary;
- document ACL or authorized-principal filter;
- sensitivity restrictions;
- exact policy release where known;
- approved policy status;
- effective-date rules;
- jurisdiction and legal entity;
- employee, customer, product or population applicability;
- business unit or organizational scope.

Do not retrieve broadly and trim unauthorized results after model exposure. Do not ask the model to enforce ACLs or applicability.

When using caches, include identity or authorization scope, policy release, query mode, filters and relevant configuration in the cache key. Never allow cached evidence to bypass current authorization.

## Integrate with Microsoft Agent Framework

Use a MAF context provider when automatic retrieval before a general explanatory agent invocation is appropriate.

Use an explicit Azure AI Search tool or deterministic retrieval executor for binding policy workflows. Make its inputs and outputs typed and auditable.

Use a request equivalent to:

```json
{
  "query": "user-or-system-query",
  "mode": "discovery|exact_evidence",
  "policyReleaseId": null,
  "clauseIds": [],
  "filters": {},
  "authorizationContext": "trusted-reference",
  "top": 5
}
```

Return an equivalent to:

```json
{
  "results": [
    {
      "searchRecordId": "record-id",
      "policyReleaseId": "release-id",
      "clauseId": "clause-id",
      "content": "authorized-policy-text",
      "section": "section",
      "page": 0,
      "sourceUri": "source",
      "retrievalMethod": "keyword|vector|hybrid|exact",
      "score": null
    }
  ],
  "appliedFilters": {},
  "warnings": []
}
```

Do not expose raw authorization tokens to the model. Do not let an agent alter trusted filters or broaden its authorization scope.

Keep the deterministic policy decision service separate. The explanation agent receives the immutable decision plus exact authorized evidence and may not revise the outcome.

## Make retrieval observable without leaking content

Record operational metadata such as:

- correlation and case ID;
- query mode;
- index and semantic configuration versions;
- embedding deployment identifier and version where available;
- policy release;
- filters applied;
- returned record and clause IDs;
- retrieval method, latency and result count;
- failure, throttling and retry status.

Do not log complete sensitive policy text, user queries, embeddings, prompts or tool payloads by default in production.

Keep search telemetry separate from the immutable policy decision audit. Link them through controlled identifiers.

## Evaluate retrieval independently

Build a policy-owner-reviewed test set that includes:

- exact terminology and policy codes;
- paraphrases and synonyms;
- vague and informal user wording;
- near-duplicate clauses;
- conflicting or superseded releases;
- definitions and cross-references;
- tables, qualifiers, exceptions and footnotes;
- multilingual queries when in scope;
- queries with no supported answer;
- unauthorized and cross-tenant queries.

Measure at least:

- recall at the configured result depth;
- precision or relevance at the configured result depth;
- exact evidence hit rate;
- citation correctness;
- unsupported-query abstention;
- authorization-filter correctness;
- release and applicability-filter correctness;
- latency, throttling and failure behavior.

Compare keyword-only, vector-only and hybrid retrieval. Do not claim quality from a few hand-selected demonstrations.

Add automated tests for:

- index schema and required fields;
- stable IDs and release consistency;
- embedding dimension and configuration validation;
- chunk lineage and table reconstruction;
- filter generation;
- document-level access control;
- exact evidence lookup;
- missing evidence integrity failures;
- injection content inside indexed documents;
- cache isolation;
- index rollback and re-publication;
- confirmation that retrieval cannot authorize an action.

## Review anti-patterns

Flag these as defects unless explicitly justified:

- putting complete policy files into every agent prompt;
- using vector similarity as policy applicability or eligibility;
- using semantic ranking to resolve precedence;
- using one unversioned index that overwrites policy history;
- indexing draft and active policies without enforceable filters;
- separating table rows from required headers or units;
- arbitrary chunking that loses qualifiers and exceptions;
- retrieving all content and relying on the model to discard unauthorized results;
- using discovery search after a decision when exact evidence IDs are available;
- silently substituting similar evidence when an exact clause is missing;
- hard-coding an embedding dimension or deployment without verification;
- evaluating only with model-generated queries and model-generated judgments;
- logging full queries, policy content, vectors or prompts in production;
- treating high retrieval scores as proof of correctness;
- calling the system compliant merely because responses include citations.

## Produce the required output

For architecture work, provide the relevant subset of:

1. Source and release assessment.
2. Publication and activation design.
3. Chunking and table-handling strategy.
4. Index schema with field attributes.
5. Embedding and vectorization design.
6. Keyword, vector, hybrid, semantic and exact-query design.
7. Discovery and exact-evidence retrieval flows.
8. Authorization, applicability and tenant-filter design.
9. MAF context-provider or explicit-tool integration.
10. Caching, failure, rollback, telemetry and cost considerations.
11. Retrieval evaluation dataset, metrics and tests.
12. Explicit assumptions, blockers and unverified service capabilities.

For implementation work:

- preserve repository conventions;
- isolate ingestion, indexing, query construction, authorization, MAF integration and evaluation modules;
- use typed configuration and contracts;
- add deterministic tests before claiming success;
- run the relevant formatter, build, unit, integration and retrieval evaluation commands;
- report exactly what was executed and what remains unverified.

Do not claim production readiness without approved sources, access-control validation, representative retrieval evaluation, operational ownership, rollback testing and security/privacy review.

## Current official references

Verify current capabilities and APIs with official documentation:

- Azure AI Search RAG: https://learn.microsoft.com/azure/search/retrieval-augmented-generation-overview
- Azure AI Search vector search: https://learn.microsoft.com/azure/search/vector-search-overview
- Azure AI Search hybrid search: https://learn.microsoft.com/azure/search/hybrid-search-overview
- Azure AI Search integrated vectorization: https://learn.microsoft.com/azure/search/vector-search-integrated-vectorization
- Azure AI Search document access control: https://learn.microsoft.com/azure/search/search-document-level-access-overview
- Microsoft Agent Framework RAG: https://learn.microsoft.com/agent-framework/agents/rag
- Microsoft Agent Framework context providers: https://learn.microsoft.com/agent-framework/agents/conversations/context-providers

Prefer official documentation and the repository's pinned dependency documentation over remembered APIs or generated examples. If documentation or deployed configuration cannot establish a capability, state the uncertainty rather than fabricating working code.
