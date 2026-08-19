# Known limitations

What this build does not yet do, and what to know before relying on it. It
complements the [capability flows](capability-flows.md),
[testing guide](testing.md) and [configuration guide](configuration.md).

A note on what is *not* here. This page used to list absent infrastructure — no
queue, no broker, no worker runtime, no CI pipeline — as though each were a
defect. They are design decisions, and describing them as shortfalls made the
platform look unfinished in ways it is not. Those now sit under
[Deliberate scope](#deliberate-scope), stated as what the system does. What
remains below constrains whether the build is safe to rely on.

## Before relying on this build

| Limitation | Current behavior | Impact |
|---|---|---|
| No production authentication or authorization | There is no identity-provider integration or trusted user directory. Role-like request fields and development headers are not a security boundary. | Do not expose the current build to untrusted networks or users. |
| No tenant isolation | Policy data is not partitioned or authorized by organization. | Suitable only for a single trusted environment. |
| AI settings are not enforced at startup | The API starts with blank Azure settings. AI routes then return `503`, indexing returns `0`, and deterministic features keep working. | A deployment can look healthy while extraction is unavailable. Validate required settings before accepting traffic. |
| Documents are stored on the local filesystem | Uploads are written beside the API process. | Durability and backup are the operator's responsibility. |
| Indexing is best-effort | Clause indexing catches search failures, logs a warning and returns `0` so upload still succeeds. | A document can exist in PostgreSQL and be absent from the grounding index. |
| Model output is validated after generation | Calls request JSON and Pydantic validates the result, rather than constraining generation to a schema. | Invalid output causes a retry or an explicit failure before anything is persisted. |
| The verbatim check is anchored to the batch, not the page | `verify_verbatim` compares a passage against the text the agent was shown, which is built from stored clauses. | It proves the model copied. It cannot detect text that ingestion stored wrongly, because both sides of the comparison come from the same stored clauses. See [What the verbatim check proves](ai-assistance.md#what-the-verbatim-check-proves). |
| AI behavior is not verified against live services | Tests isolate the AI boundary; none call Azure OpenAI or Azure AI Search. | Retrieval relevance, index freshness and model behavior need validation in a real environment. |

## Deliberate scope

These are choices, not gaps. They are recorded so nobody re-derives them.

| Decision | How it works |
|---|---|
| Work runs in the request that starts it | Extraction and quality analysis are request-driven and can take minutes. The trade is visible: a restart interrupts the run, and progress is polled rather than streamed. |
| Lifecycle events are recorded, not broadcast | An outbox model persists what happened. Nothing consumes it yet, so a subscriber would be added against a table that already exists rather than a schema invented later. |
| Deployment is operator-triggered | The `azd`/Bicep kit is invoked by a person. Deployment automation belongs to the Azure phase, which is not finished. |
| Grounding is capability-specific | Ask AI and AI-proposed tests query the search index. Other calls ground on the source passage, selected rule, policy version or records their caller supplies. Do not assume every model call performs retrieval. See [How the AI is grounded](ai-assistance.md#how-the-ai-is-grounded). |
| Grounding is corpus-bounded | Answers come from uploaded documents and persisted policy data. That is the point: an answer traceable to a clause is worth more here than one drawn from the open web. |
| Retrieval calls the search service directly | There is no abstraction over it. Replacing the backend means changing the callers — accepted while there is one backend, because an interface with a single implementation states a generality nobody has tested. |

## Workflow boundaries

| Capability | Where it stops |
|---|---|
| Policy tests | Proposed, accepted or rejected, run on demand and rerun after publication. No edit-in-place or hard delete, no bulk run, no schedule or trigger, no candidate simulation before publish. |
| Change management | Version comparison identifies added, removed and changed rules and can narrate them. It does not open a change request or approval workflow around the diff. |
| Quality and conflict analysis | Deterministic checks plus AI review. There is no independent contradiction engine and no automatic conflict resolution. |
| Rule relationships | Curated in the UI; older sample data may not populate them. Heuristic grouping is display assistance, not authoritative metadata. |
| Attestations | Campaigns and acknowledgements are stored. Reminders, escalation delivery, directory integration and automatic re-attestation are not implemented. |
| Ownership and RACI | Metadata only. Contacts are not validated and do not drive routing, notification or publish gates. |
| Exceptions | Requests have a stored lifecycle; no notification or external approval integration. |
| Exports | JSON, JSONL and CSV point-in-time downloads. No subscription or scheduled delivery. |
| Index maintenance | Each indexing write reconciles that document version's entries against the store, so re-extraction no longer leaves orphans searchable. A project's **policy** index additionally records what it last built, reports whether that still matches the active published version, and can be rebuilt on demand from the project Overview. What is still missing is anything scheduled or automatic: nothing sweeps for stale indexes, and a project that published before this existed stays unindexed until someone rebuilds it. |

## Test coverage boundaries

The suite is strong around deterministic domain behavior and does not prove the
deployed system:

- no database or Alembic migration tests
- no FastAPI integration tests
- no browser or end-to-end tests
- no automated frontend test runner
- no performance, load, penetration or dependency-security tests
- no tests against live Azure OpenAI or Azure AI Search resources

See [Testing and scripts](testing.md#current-coverage-gaps) for the verified
inventory and commands.

## Structural debt

- **Routers issue SQL directly.** The repository layer exists so that query
  construction lives in one place, and it does not hold. **16** `session.execute`
  calls remain across **6** files under `api/`: `ai.py` (6), `documents.py` (5),
  `extraction.py` (1), `policy_sets.py` (2), `app.py` (1), `audit.py` (1).

  It was 20 across 7. The largest single instance — 133 lines of aggregation
  behind `/review-facets` — moved into
  `infrastructure/persistence/review_facets.py`, which took `candidate_rules.py`
  from three direct queries to none. Retiring the extraction-stages read endpoint
  (`c5c06de`) removed one more, taking `extraction.py` from two calls to one — the
  query went because the surface it served went, not because it was rewritten.

  This is containment, not a resolution. Each remaining call is small on its own,
  which is exactly why the pattern spread: no individual one looks like a
  decision. The cost is that this logic cannot be exercised without going through
  FastAPI, which is also why [no FastAPI integration tests](#test-coverage-boundaries)
  and this entry reinforce each other.

  These counts are checked by `tests/unit/test_documented_sql_debt_is_current.py`,
  so the paragraph above cannot drift from the code without failing the suite.

- **Stored rule fingerprints are written and never read.** `domain/models.py`
  defines `content_fingerprint` and `anchor_fingerprint` on the candidate rule,
  and explains in a comment why they are stored rather than computed on read:
  the comparison is against runs that may be months old, and recomputing would
  silently re-interpret history if the definition ever changed.

  The columns are written at insert time in
  `infrastructure/extraction/ai_extraction.py`. Nothing reads them. `diff_runs`
  (`infrastructure/projection/rule_delta.py`) recomputes both sides from the
  stored payloads, which is exactly the behaviour the comment gives a reason
  against. The guarantee is described, the storage that would provide it is
  paid for, and the consumer does not use it.

  The code is left alone deliberately: recomputation is not currently wrong, and
  changing which side of this contradiction wins is a decision about historical
  comparability, not a cleanup. What is recorded here is that **the comment is
  the more persuasive of the two and is the one that is false** — it states a
  property, gives a reason, and reads as settled, while the behaviour it
  describes lives in another module that a reader has no cause to open.

- **Opening the largest policy renders every rule at once.** The Review and
  Policies rule card draws a policy's whole body — each rule with its name and
  inline detail — into the DOM in a single render, with no pagination or
  windowing, so the largest measured policy (72 rules) is the heaviest single
  render the build performs. In a queue that cost is bounded: a list draws
  collapsed heads, and a card's full body only when a reviewer opens it, not for
  every card scrolled past. The completeness test in
  `apps/web/src/nothingIsBehindAClick.test.tsx` draws that whole policy and
  carries a deliberately generous time budget, so a slow render is recorded as
  cost rather than tripping a stopwatch and reporting rules that are all present
  as missing.

- **A corrected extraction artefact survives in records already extracted.**
  `infrastructure/extraction/quantity_projection.py` used to borrow a comparison
  from a number-bearing predicate for a bare magnitude, so a plain quantity such
  as `"Received 3 doses"` could be projected as an instruction
  (`"You required to Received 3 doses"`). It now refuses that — a bare magnitude
  states what the quantity *is*, not a test, so it takes the `NO_COMPARISON`
  refusal — fixed at source in `18ca0e4`. The fix is forward-looking: rules
  extracted before it keep the wrong text until their document is re-extracted,
  so the artefact can still be read on a live record even though the defect is
  closed. Every surviving instance is in the `ais-employee-handbook` set — none
  in the GMU corpus — and some have already been approved or published, which is
  the part that catches people. Re-extraction alone does not clear an approved or
  published record: the corrected draft has to be reviewed, approved and
  republished before it replaces the live one — a governance act, not a technical
  one, and the only thing that rewrites an existing record.

- **The bulk-selection counter names no unit.** On both the Review and Policies
  panes the selection counter reads `N selected` without naming that the unit is
  policies. It is kept identical on the two surfaces on purpose; if it gains a
  unit it should gain one on both at once rather than let one side drift from the
  other.

- **The Overview omits two provenance facts it cannot honestly evidence.** A
  rule's sequence position in the document (`source_elements` is an element key
  such as `p1-E000004`, not an ordinal) and its ingestion time
  (`DocumentVersion.created_at` exists, but neither the Review nor Policies
  surface loads `SourceDocument`) are left out rather than approximated. Each is
  cheap to add once a caller loads the document record; neither is worth a
  request on its own.

## Documentation gaps

- **ADRs are cited but absent.** `ADR-0011` (XACML Obligation vs Advice) is
  referenced from five places in the code and no `docs/adr/` directory exists.
  The decision itself is real and is described in [Standards](standards.md); the
  record was never committed.
- **RFC 9457 is not implemented.** API errors use FastAPI's default
  `{"detail": ...}` rather than `application/problem+json`. Adopting it would be
  a small change; until then it is not claimed.
