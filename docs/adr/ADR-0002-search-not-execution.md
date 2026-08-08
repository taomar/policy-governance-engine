# ADR-0002: Search and RAG are excluded from the runtime evaluation path

## Status
Accepted

## Context
Section 5.1 and Section 15 require that Azure AI Search (and any retrieval/RAG
mechanism) never determines a transactional result. Runtime deterministic evaluation
must operate exclusively on approved, versioned, structured rules and structured
facts.

## Decision
`policy_platform.evaluator` has **zero imports** of any search, HTTP, or AI SDK, and
zero imports from `policy_platform.infrastructure` or `policy_platform.worker`. It
depends only on the Python standard library and `policy_platform.contracts` (plain
Pydantic data models with no I/O). It accepts only:
- An immutable, already-approved canonical policy package (a Pydantic model, however
  it was loaded — the loading mechanism is irrelevant to the evaluator itself).
- A structured fact bag (`dict[str, Any]`), canonicalized before evaluation.

Search and AI concerns are confined to ingestion/formalization adapters in
`policy_platform.infrastructure` (to be added in a later phase) and must never be
imported by `policy_platform.evaluator` or `policy_platform.domain`. This is checked
mechanically: the evaluator package's only internal dependency is `contracts`.

## Rationale
Enforcing this as a **module dependency boundary** (no import path exists from
evaluator to any network-capable module) makes the rule structurally impossible to
violate by accident, not just a documented convention.

## Consequences
- **Positive:** deterministic replay and result-hash stability (Section 27.5) are
  guaranteed by construction.
- **Negative:** none identified; this is a hard constraint from the source
  specification with no legitimate exception.
