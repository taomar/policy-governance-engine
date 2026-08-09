# Microsoft technologies and references

The Microsoft services and patterns this platform touches, and official
Microsoft documentation for each. Every external link on this page is
Microsoft first-party.

Each entry states the relationship honestly:

- **Implemented** — the code calls this service or applies this pattern today.
- **Aligned** — the implementation resembles the guidance and was informed by
  it, but this is not a compliance claim.
- **Deferred / not used** — named elsewhere in the repository, but the code does
  not use it.

> Nothing on this page asserts certification, compliance, or adoption of a
> Microsoft programme. Where the repository merely *resembles* guidance, it says
> so.

---

## Azure OpenAI — implemented

**How it is used here.** Two chat deployments and one embedding deployment,
called over REST with `httpx` from
[`infrastructure/ai/openai_client.py`](../src/policy_platform/infrastructure/ai/openai_client.py).
Chat drives extraction, quality review, correlation classification, rewrite,
compare narrative, test proposal and Ask AI. Embeddings drive clause indexing and
query vectors. Configuration is the `AZURE_OPENAI_*` block in `.env`; it is
**required** for the product, and with it blank every AI route returns `503` and
the platform runs in a degraded diagnostic mode.

| Reference | Relationship |
|---|---|
| [Chat completions REST reference](https://learn.microsoft.com/rest/api/microsoft-foundry/azureopenai/chat) | **Implemented** — the exact request shape the client builds, including `max_completion_tokens` and `response_format`. |
| [Embeddings REST reference](https://learn.microsoft.com/rest/api/microsoft-foundry/azureopenai/embeddings) | **Implemented** — `embed()` posts a batch of texts and reorders results by `index`. |
| [Generate embeddings with Azure OpenAI](https://learn.microsoft.com/azure/foundry/openai/how-to/embeddings) | **Aligned** — batching and dimension configuration (`AZURE_OPENAI_EMBEDDING_DIMENSIONS`, default 3072). |
| [Structured outputs](https://learn.microsoft.com/azure/foundry/openai/how-to/structured-outputs) | **Aligned, not adopted.** The platform uses JSON *object* mode (`response_format: {"type": "json_object"}`) plus Pydantic validation of the parsed result, not JSON-Schema-constrained structured outputs. The shape is enforced by prompt contract and re-validated in code; moving to schema-constrained outputs is a natural upgrade, not a current behaviour. |
| [Quotas and limits](https://learn.microsoft.com/azure/ai-foundry/openai/quotas-limits) | **Relevant context** — correlation bounds concurrency to 3 in-flight group calls and commits in chunks partly for this reason. No formal rate-limit handling is implemented. |

---

## Azure AI Search — implemented

**How it is used here.** Azure AI Search is this platform's **mandatory
grounding layer**, integrated directly — clause-level retrieval through
[`search/indexing.py`](../src/policy_platform/infrastructure/search/indexing.py)
(write) and
[`search/search_client.py`](../src/policy_platform/infrastructure/search/search_client.py)
(read). Writes are `mergeOrUpload` batches of 100. Reads are hybrid queries
combining a keyword `search` term with a `vectorQueries` entry over
`body_vector`, filtered to this platform's own document IDs. The client never
creates or alters an index schema. The full path — sources, fields, scoping,
retrieval parameters and failure behaviour — is documented in
[How the AI is grounded](ai-assistance.md#how-the-ai-is-grounded).

| Reference | Relationship |
|---|---|
| [Load data into a search index](https://learn.microsoft.com/azure/search/search-how-to-load-search-index) | **Implemented** — push model via the Documents - Index REST API. |
| [Add, update or delete documents (REST)](https://learn.microsoft.com/rest/api/searchservice/addupdate-or-delete-documents) | **Implemented** — the `@search.action` values `mergeOrUpload` and `delete` are exactly what the client sends. |
| [Vector search overview](https://learn.microsoft.com/azure/search/vector-search-overview) | **Implemented** — vector queries over an embedding field. |
| [Hybrid search overview](https://learn.microsoft.com/azure/search/hybrid-search-overview) and [how to query](https://learn.microsoft.com/azure/search/hybrid-search-how-to-query) | **Implemented** — the retrieval call is a hybrid query, not vector-only. |
| [Generate embeddings for vector queries](https://learn.microsoft.com/azure/search/vector-search-how-to-generate-embeddings) | **Implemented** — the query is embedded with the same deployment used at index time. |
| [Security filters for trimming results](https://learn.microsoft.com/azure/search/search-security-trimming-for-azure-search) | **Aligned in shape only.** The `policy_id` filter isolates this platform's documents from unrelated data sharing the same index. It is a data-scoping measure, **not** a security or per-user access control — there is no identity to trim by. |
| [Retrieval-augmented generation in Azure AI Search](https://learn.microsoft.com/azure/search/retrieval-augmented-generation-overview) | **Aligned** — the app-orchestrated RAG shape described there (app embeds the query, queries the index, assembles context, calls the model) is exactly what `ai_chat.py` and `ai_test_proposal.py` do. |

---

## Microsoft Foundry IQ not integrated architectural alternative

**Status in this repository: not wired in.** There is no Foundry IQ knowledge
base, no knowledge source, no agent, and no Foundry Agent Service call anywhere
in the code. The only retrieval client is `AzureSearchClient`, which builds
Azure AI Search REST request bodies by hand.

Foundry IQ is listed here because the platform's **grounding layer is
mandatory** while its *implementation* is a choice. Foundry IQ — knowledge bases
composed of knowledge sources, with agentic query planning and citations —
could satisfy that mandatory layer, and would replace the hand-rolled
embed-then-query-then-assemble sequence in `ai_chat.py` and `ai_test_proposal.py`
with a managed retrieval surface. It is **not a drop-in backend today**: adopting
it requires an adapter behind a retrieval interface that does not yet exist,
plus a decision about how the platform's `policy_id` scoping maps onto knowledge
sources, and about how citations map onto the existing verbatim-fact contract.

| Reference | Relationship |
|---|---|
| [What is Foundry IQ](https://learn.microsoft.com/azure/foundry/agents/concepts/what-is-foundry-iq) | **Not implemented** — the candidate target for the mandatory grounding layer. |
| [Foundry IQ components and workflow](https://learn.microsoft.com/azure/foundry/agents/concepts/what-is-foundry-iq#components) | **Not implemented** — knowledge bases and knowledge sources have no counterpart in this codebase. |
| [Create a knowledge base (agentic retrieval)](https://learn.microsoft.com/azure/search/agentic-retrieval-how-to-create-knowledge-base) | **Not implemented** — the platform queries a plain index directly instead. |
| [Connect a Foundry IQ knowledge base to Foundry Agent Service](https://learn.microsoft.com/azure/foundry/agents/how-to/foundry-iq-connect) | **Not implemented** — there is no agent service in this architecture; AI capabilities are direct FastAPI endpoints. |
| [Connect an Azure AI Search index to Foundry agents](https://learn.microsoft.com/azure/foundry/agents/how-to/tools/ai-search) | **Not implemented** — the existing `policy-authoring` index would be the natural connection point if this route were taken. |
| [Foundry IQ FAQ](https://learn.microsoft.com/azure/foundry/agents/concepts/foundry-iq-faq) | **Background** — indexed knowledge sources refresh on an indexer schedule, which is the freshness model the current best-effort indexing does not have. |
| [Information retrieval in RAG solutions](https://learn.microsoft.com/azure/architecture/ai-ml/guide/rag/rag-information-retrieval) | **Aligned in shape** — the retrieval concerns described there (hybrid search, filtering, chunk quality) are the ones this platform handles manually. |

Nothing in this section should be read as a claim that the platform supports
Foundry IQ. It does not, and no code path would change if a Foundry IQ resource
were provisioned.

---

## Responsible AI and human oversight — aligned

**How it relates.** The platform's central rule is that no model participates in
a runtime decision. Models draft, classify and narrate; humans approve;
deterministic Python decides. Concretely: extracted rules land as `candidate` and
require an explicit approval; AI-proposed tests start `pending_review` and cannot
run until accepted; rewrites are suggestions until a human applies them; quality
and correlation findings are advisory evidence carrying a human disposition; and
Stage 1 passages are re-verified in code rather than trusted.

| Reference | Relationship |
|---|---|
| [Responsible AI in the Well-Architected Framework](https://learn.microsoft.com/azure/well-architected/ai/responsible-ai) | **Aligned** — human oversight and clear provenance of model output. Content-safety operationalisation described there is **not** implemented here. |
| [Responsible AI — concepts](https://learn.microsoft.com/azure/machine-learning/concept-responsible-ai) | **Aligned** — transparency and accountability principles are visible in how findings are labelled `deterministic` vs `ai_review`. |
| [Securing AI applications](https://learn.microsoft.com/azure/security/fundamentals/ai-security-best-practices) | **Partially aligned.** Prompts are reviewable files, model output is schema-validated, and rule IDs the model invents are rejected. Not done: content filtering, abuse monitoring, or any threat-model review. |
| [MCSB — AI-5: Ensure human in the loop](https://learn.microsoft.com/security/benchmark/azure/mcsb-v2-artificial-intelligence-security) | **Aligned** — every model output is a draft or an observation behind an explicit human gate; see [AI assistance](ai-assistance.md#human-review-is-the-gate). |

Grounding is part of this posture: model answers are constrained to context the
application assembled from the organisation's own records, with verbatim
excerpts re-verified in code. See
[How the AI is grounded](ai-assistance.md#how-the-ai-is-grounded) and its
[limitations](ai-assistance.md#grounding-limitations-and-failure-modes).

This is alignment in design, not a compliance statement. No responsible-AI
assessment, red-team exercise or content-safety configuration has been performed.

---

## Microsoft Agent Framework — not used

`src/policy_platform/worker/` is an empty reserved package. There is no
`agent-framework` dependency, import, workflow graph, checkpoint store or MAF
tool-registration layer anywhere in the code. Human review is implemented
through persisted domain states and explicit FastAPI endpoints.

| Reference | Relationship |
|---|---|
| [Agent Framework overview](https://learn.microsoft.com/agent-framework/overview/) | **Not used.** The current fixed, request-driven service flows do not require an agent runtime. |
| [Workflows: human in the loop](https://learn.microsoft.com/agent-framework/workflows/human-in-the-loop) | **Not used.** The platform achieves human-in-the-loop through persisted review states and explicit endpoints rather than workflow checkpoints and request/response pairs. There is no pause/resume-as-a-workflow semantics here. |

For the current architecture, adopting MAF would duplicate orchestration already
expressed clearly in application services. It becomes relevant if the product
needs resumable multi-agent workflows, dynamic tool routing, parallel branches,
cross-process checkpoints or framework-managed human pause/resume.

Semantic Kernel and `Microsoft.Extensions.AI` are likewise **not used** — see
[Frameworks and technologies](frameworks.md#proposed-deferred-or-explicitly-not-used).

---

## Reliability patterns — mostly gaps, listed honestly

Outbound calls to Azure OpenAI and Azure AI Search use `httpx` timeouts only.
There is **no** retry policy, exponential backoff, jitter, or circuit breaker.
Some AI services retry after a *schema-validation* failure, which is prompt
correction rather than transient-fault handling.

What *is* implemented is graceful degradation: search indexing failures are
logged and swallowed so an upload never fails on a downstream outage; retrieval
failure degrades Ask AI to rules-only grounding; the on-publish test re-run
cannot fail an already-committed publish.

| Reference | Relationship |
|---|---|
| [Retry pattern](https://learn.microsoft.com/azure/architecture/patterns/retry) | **Not implemented** — the intended direction for the outbound clients. |
| [Transient fault handling](https://learn.microsoft.com/azure/architecture/best-practices/transient-faults) and [Well-Architected guidance](https://learn.microsoft.com/azure/well-architected/design-guides/handle-transient-faults) | **Not implemented** — no retry-aware client wrapper exists. |
| [Circuit Breaker pattern](https://learn.microsoft.com/azure/architecture/patterns/circuit-breaker) | **Not implemented.** |
| [Transactional Outbox pattern](https://learn.microsoft.com/azure/architecture/databases/guide/transactional-outbox-cosmos) | **Modelled only.** The `outbox_messages` table exists; no publisher consumes it. The Microsoft article is Cosmos DB-specific; the pattern, not the implementation, is what this table anticipates. |

---

## Identity and secrets — gaps, listed honestly

The platform has **no authentication**. The "acting as" switcher is a name and
role in browser `localStorage`, and the `policy_manager` check reads a field from
the request body. Azure credentials are API keys in a git-ignored `.env`.

| Reference | Relationship |
|---|---|
| [Keyless connections with Microsoft Entra ID](https://learn.microsoft.com/azure/developer/ai/keyless-connections) | **Not implemented** — the documented direction for replacing the API-key configuration. |
| [Application secrets guidance](https://learn.microsoft.com/azure/well-architected/security/application-secrets) | **Partially aligned** — secrets are externalised to `.env` and read in exactly one module, but there is no vault, rotation or managed identity. |

Microsoft Entra ID integration is listed as not implemented in
[Known limitations](known-limitations.md). The dev auth stub must be replaced
before any non-local deployment.

---

## TypeScript — implemented

The frontend is written in TypeScript (`~6.0`) and type-checked as part of
`npm run build` via `tsc -b`. Microsoft maintains the language.

| Reference | Relationship |
|---|---|
| [Build JavaScript applications with TypeScript](https://learn.microsoft.com/training/paths/build-javascript-applications-typescript/) | **Implemented** — the language is a direct dependency; the linked material is introductory background rather than a pattern this repository follows. |

---

## Not Microsoft, listed for completeness

Several standards this platform follows are not Microsoft's: OASIS XACML 3.0,
OMG DMN and FEEL, OpenAPI, JSON Schema, ISO 37301 and ISO 27001, and Open Policy
Agent's decision-log concept. They are covered in
[`policy-standards-research.md`](policy-standards-research.md) and summarised in
the [root README](../README.md#standards-and-design-principles).
