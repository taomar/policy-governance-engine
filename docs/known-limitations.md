# Known limitations

This page describes current product and engineering limits. It complements the
[capability flows](capability-flows.md), [testing guide](testing.md) and
[configuration guide](configuration.md).

## Product and deployment readiness

| Limitation | Current behavior | Impact |
|---|---|---|
| AI requirements are not enforced at startup | Azure OpenAI and a grounding/search layer are required for the intended product, but the API can start with blank Azure settings. AI routes then return `503`, indexing returns `0`, and deterministic features remain available. | A deployment can appear healthy while core product capabilities are unavailable. Production deployment should validate required Azure settings before accepting traffic. |
| No production authentication or authorization | The application has no identity-provider integration or trusted user directory. Role-like request fields and development headers are not a security boundary. | Do not expose the current build to untrusted networks or users. |
| No tenant isolation | Policy data is not partitioned or authorized by organization. | The current build is suitable only for a single trusted environment. |
| Local document storage | Uploaded documents are stored on the local filesystem. | Horizontal scaling, durable cloud storage, backup and disaster recovery are not implemented. |
| Long-running work executes in the API process | Extraction and quality analysis are request-driven and can take minutes. There is no job queue, scheduler or worker runtime. | Restarts interrupt work; clients receive no durable job identifier or incremental progress stream. |
| No event publisher | An outbox model exists, but no process publishes messages to a broker. | Downstream systems cannot subscribe to policy lifecycle changes. |
| Limited operational telemetry | Application logs exist, but distributed tracing, production dashboards, alerting and service-level objectives are not defined. | Diagnosing latency and dependency failures requires manual investigation. |
| No CI/CD pipeline | A validated interactive `azd`/Bicep deployment kit exists, but no pipeline invokes it automatically. | Build, test, policy checks and deployment remain operator-triggered. |

## AI and grounding

| Limitation | Current behavior | Impact |
|---|---|---|
| Best-effort indexing | Clause indexing catches Azure AI Search failures, logs a warning and returns `0` so document upload can still succeed. | A document can exist in PostgreSQL and local storage but be absent from the grounding index. |
| No index reconciliation | There is no scheduled freshness check, repair job or complete re-index workflow. | Search results can become stale after re-extraction or source replacement. |
| Direct Azure AI Search coupling | Retrieval callers construct Azure AI Search requests directly. There is no retrieval interface. | Replacing the grounding backend requires code changes in each caller. |
| Foundry IQ is not integrated | No Foundry IQ knowledge base, knowledge source or Foundry Agent Service connection exists. | Foundry IQ can become an alternative grounding implementation only after an adapter and citation mapping are added. |
| Grounding is capability-specific | Ask AI and AI-proposed policy tests query Azure AI Search. Other AI capabilities use the source passage, selected rule, policy version or database records supplied by their caller. | Do not assume every model call performs retrieval-augmented generation. See [How the AI is grounded](ai-assistance.md#how-the-ai-is-grounded). |
| No external web grounding | The platform grounds against uploaded documents and persisted policy data, not public web sources. | Answers are limited to the organization's loaded policy corpus and selected records. |
| Structured output is validated after generation | Model calls request JSON-object output and Pydantic validates the result. They do not use schema-constrained structured output for every request. | Invalid model output can require retry or produce an explicit failure before persistence. |
| No automated live-service evaluation | Unit tests mock or isolate AI boundaries; they do not call Azure OpenAI or Azure AI Search. | Retrieval relevance, index freshness, filter correctness and model behavior require separate environment validation. |

## Workflow limitations

| Capability | Current limitation |
|---|---|
| Policy tests | Tests can be proposed, accepted or rejected, run on demand and rerun after publication. There is no edit-in-place or hard-delete endpoint, bulk "run all" action, schedule, CI trigger or candidate-version simulation before publish. |
| Change management | Version comparison identifies added, removed and changed rules and can generate an AI narrative. It does not create a durable change request or approval workflow around the diff. |
| Quality and conflict analysis | Quality combines deterministic checks with AI review. There is no independent contradiction engine or automatic conflict resolution. |
| Rule relationships | Relationship fields can be curated in the UI, but older sample data may not populate them. Heuristic grouping is display assistance, not authoritative policy metadata. |
| Attestations | Campaigns and acknowledgements are stored, but reminders, escalation delivery, directory integration and automatic re-attestation after a new release are absent. |
| Ownership and RACI | Ownership fields are metadata only. Contacts are not validated and do not drive routing, notifications or publish gates. |
| Exceptions | Exception requests have a stored lifecycle, but no notification or external approval integration exists. |
| Exports | JSON, JSONL and CSV are point-in-time downloads. There is no subscription, scheduled delivery or event stream. |

## Test coverage boundaries

The current automated suite is strong around deterministic domain behavior but
does not prove the complete deployed system:

- no database or Alembic migration tests
- no FastAPI integration tests
- no browser or end-to-end tests
- no automated frontend test runner
- no performance, load, penetration or dependency-security tests
- no tests against live Azure OpenAI or Azure AI Search resources

See [Testing and scripts](testing.md#current-coverage-gaps) for the
verified module-level inventory and commands.
