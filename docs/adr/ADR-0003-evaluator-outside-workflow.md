# ADR-0003: Deterministic evaluator lives outside the MAF/worker boundary

## Status
Accepted

## Context
Section 5.4 and Section 15 require the deterministic evaluator to never call Azure
OpenAI, Azure AI Search, or use embeddings, and to depend only on approved structured
rules and facts. The workflow worker (Section 10.3, 11) is the boundary where
Microsoft Agent Framework orchestrates non-deterministic, AI-assisted stages.

## Decision
`policy_platform.evaluator` is a plain Python package with no dependency on
`policy_platform.worker` or the Microsoft Agent Framework SDK. The FastAPI app
(`policy_platform.api`) imports the evaluator directly for the runtime evaluation
endpoint (`POST /api/evaluations`). The worker package is reserved exclusively for
future MAF workflow hosting (ingestion, formalization, change-management,
publication workflows) and will *call into* the same evaluator package during the
publication workflow's "run golden/generated tests" step — the dependency direction
is worker → evaluator, never evaluator → worker.

## Rationale
This keeps the dependency direction correct: workflow orchestration depends on the
deterministic core; the deterministic core never depends on orchestration or AI
frameworks. This satisfies Section 11's requirement to separate workflow determinism
(stage ordering) from model determinism (semantic interpretation).

## Consequences
- **Positive:** the evaluator can be unit tested, versioned, and reused (e.g. by a
  future runtime API, a CLI, or an offline batch evaluator) without pulling in
  workflow or AI dependencies.
- **Negative:** none. This mirrors the source specification's explicit boundary.
