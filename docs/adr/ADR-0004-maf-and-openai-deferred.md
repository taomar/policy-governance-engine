# ADR-0004: Microsoft Agent Framework and Azure OpenAI integration are deferred

## Status
Accepted (documented gap, not a silent omission)

## Context
The full specification (Sections 11, 12, and Phases 2–4 of Section 32) requires
Microsoft Agent Framework graph workflows and Azure OpenAI structured-output agents
for ingestion, formalization, change management, and reviewer assistance. This is a
large, independently deployable subsystem requiring live Azure resources, API keys,
and the `agent-framework` / `openai`/`azure-ai-*` Python packages configured against
a real Azure OpenAI deployment — none of which exist in this local session.

Per the engineering behavior rules (Section 33): "Do not create placeholder
implementations and call them complete" and "Do not fabricate Azure SDK APIs."

## Decision
This build phase implements **Phase 1 (Foundation)** and **Phase 5 (Deterministic
execution)** from Section 32 in full for the local environment:
- Domain model, database, policy-set management foundation.
- Canonical policy package, deterministic evaluator, runtime evaluation API, result
  hashes.

Phases 2 (document processing/search), 3 (MAF + Azure OpenAI formalization), 4
(governance/HITL), 6 (change management), and 7 (production hardening) are **not
implemented** in this pass. `policy_platform.worker` exists as a real, runnable
Python process (asyncio-based) with no fabricated MAF calls inside it — it is an
honest placeholder, not a fake implementation of workflow behavior.

## Rationale
Building a correct, testable deterministic core first is the highest-value,
lowest-risk slice: it is the piece the entire platform's trust model depends on
(Section 35 quality gate: "No LLM participates in the final runtime rule
calculation"). Fabricating MAF/Azure OpenAI wiring without the actual packages,
Azure resources, and API keys available in this local-only session would violate
the explicit instruction not to fabricate SDK APIs.

## Consequences
- **Positive:** what is delivered is real, runnable, and tested — not a stub dressed
  up as complete.
- **Negative:** the end-to-end acceptance scenario (Section 28) is **not** achievable
  yet; specifically steps 7–14 (extraction workflow, HITL review pause/resume) are
  out of scope this phase.
- **Migration path:** when the `agent-framework` Python package and Azure OpenAI
  resource credentials are available, implement `policy_platform.worker` executors
  per Section 11 behind the same interfaces already reserved in
  `policy_platform.infrastructure` (documented in `docs/known-limitations.md`).
