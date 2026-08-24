# Microsoft services

## Implemented

### Azure OpenAI

Used for:

- passage selection and rule formulation;
- quality and correlation analysis;
- rewrite and comparison narrative;
- policy-test proposal and Ask AI;
- clause/query embeddings.

The application calls chat and embedding REST endpoints through `httpx`. Responses are validated before persistence or display.

References:

- [Azure OpenAI REST API](https://learn.microsoft.com/rest/api/microsoft-foundry/azureopenai/)
- [Embeddings](https://learn.microsoft.com/azure/foundry/openai/how-to/embeddings)
- [Quotas and limits](https://learn.microsoft.com/azure/ai-foundry/openai/quotas-limits)

### Azure AI Search

Used for clause-level hybrid keyword/vector retrieval. The application writes platform-owned clause documents and filters reads to platform document IDs.

References:

- [Load documents](https://learn.microsoft.com/azure/search/search-how-to-load-search-index)
- [Vector search](https://learn.microsoft.com/azure/search/vector-search-overview)
- [Hybrid search](https://learn.microsoft.com/azure/search/hybrid-search-overview)

### TypeScript

The React frontend is written in TypeScript and type-checked by `npm run build`.

## Design alignment

The platform follows responsible-AI principles through:

- explicit human approval before publication;
- source provenance and citations;
- separation of deterministic and AI findings;
- schema/reference validation;
- no model in the runtime decision path.

This is design alignment, not certification.

References:

- [Responsible AI in Azure Well-Architected](https://learn.microsoft.com/azure/well-architected/ai/responsible-ai)
- [AI security best practices](https://learn.microsoft.com/azure/security/fundamentals/ai-security-best-practices)

## Pending

| Area | Status |
|---|---|
| Microsoft Entra authentication and server-side RBAC | Pending |
| Managed identity for OpenAI/Search/PostgreSQL | Pending |
| Retry, backoff, and circuit breaker policies | Pending |
| Application Insights code-level instrumentation | Pending |
| Live Azure deployment validation | Pending |

See [Known limitations](known-limitations.md).

## Not used

- Microsoft Agent Framework;
- Semantic Kernel;
- Microsoft.Extensions.AI;
- Foundry Agent Service / Foundry IQ.

The current fixed request-driven workflows use explicit FastAPI services and PostgreSQL state. Reconsider an agent framework only if the product needs resumable multi-agent workflows, dynamic tool routing, or framework-managed checkpoints.
