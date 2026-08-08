---
name: goal-anchored-conversational-orchestration
description: "Design, implement, review, or debug goal-anchored multi-turn conversational orchestration using Microsoft Agent Framework and OpenAI Responses. Use for goal management, focus shifting, conversational detours, pause/resume, intent portfolios, structured turn interpretation, pending interaction cards, workflow checkpoints, agent-as-tool patterns, human approval, and domain-independent service architecture."
argument-hint: "Describe the conversational architecture, focus, resume, or goal-management change"
user-invocable: true
disable-model-invocation: false
---

# Goal-Anchored Conversational Orchestration

Use this skill whenever work changes conversational routing, multi-turn focus, service switching, goal state, question cards, specialist orchestration, or workflow progression.

Read [the architecture contract](./references/architecture-contract.md) before planning or editing.

## Non-Negotiable Principles

1. Do not preserve focus with prompting alone.
2. Keep conversation history, durable goal state, grounding, and execution state separate.
3. The user-facing supervisor owns conversational coherence, not business authority.
4. The Goal Manager owns active and paused goals.
5. Workflows own process progression and checkpoints.
6. Deterministic services own authorization, validation, policy, arithmetic, concurrency, idempotency, custody, and writes.
7. External systems remain the source of truth for business data.
8. Tool selection establishes service intent. Never add keyword, verb, topic, or confirmation-phrase routing.
9. A turn may contain several questions, field updates, corrections, and control commands.
10. A detour pauses an unrelated pending interaction without deleting it. Resuming restores the exact goal and pending request.
11. Read-only questions must not manufacture action workflows or choice cards.
12. Sensitive actions use Prepare -> Consent -> Commit, with no model or retrieval work after consent.
13. Never infer transaction intent from free-form assistant prose.
14. Never claim grounding, execution, or success when its authoritative source was unavailable.

## Required Workflow

### 1. Discover the Repository

Before substantial edits:

- Read the repository instructions and nearby architecture decisions.
- Identify language, runtime, persistence, API host, dependency patterns, tests, and installed Microsoft Agent Framework version.
- Inspect the current supervisor, service profiles, goal/intent persistence, workflow implementation, interaction lifecycle, and UI journey projection.
- Use only APIs available in the installed framework. Do not invent classes or package names.
- State one falsifiable local hypothesis and one focused check before editing.

### 2. Map Existing Components

Map repository abstractions to these responsibilities:

| Responsibility | Required owner |
| --- | --- |
| User-facing dialogue | Conversation Supervisor |
| Typed turn decomposition | Turn Interpreter |
| Active/paused objective state | Goal Manager |
| Domain extensibility | Goal Handler Registry |
| Grounded questions | Read tools, retrieval, bounded specialists |
| Process progression | Task Workflow |
| Natural final response | Response Composer |
| Consequential writes | Deterministic executor after consent |

Extend established abstractions instead of creating parallel frameworks.

### 3. Plan Before Editing

The plan must explain:

- how goals persist independently of transcript history;
- how one active goal and several paused/completed goals are represented;
- how field candidates and corrections are validated;
- how pending interactions bind to a goal;
- how focus changes, detours, resume, replacement, cancellation, and confirmation work;
- how domain rules stay outside core orchestration;
- how restart, concurrency, idempotency, and partial failure are handled;
- what Microsoft Agent Framework capabilities are implemented and what remains educational.

### 4. Implement in Layers

Use this order:

1. Typed turn interpretation and service intent contracts.
2. Versioned goal persistence and append-only transitions.
3. Goal Handler Registry over versioned domain/service profiles.
4. Goal Manager focus, pause, resume, correction, and optimistic concurrency.
5. Goal-bound pending interactions and restart-safe restoration.
6. Supervisor context injection and grounded specialist calls.
7. Response composition: answer, acknowledge updates, explain validation, state consequences, ask one next question.
8. Controlled workflow progression and approval-protected writes.
9. Dynamic journey UI showing active, paused, completed, failed, and superseded goals.
10. Observability without prompts, secrets, personal records, or hidden reasoning.

### 5. Apply Focus Arbitration

Use deterministic arbitration after tools run:

- A grounded informational answer owns the current turn over an unrelated old clarification.
- The unrelated action goal remains paused with its pending interaction checkpointed.
- A newly emitted goal-bound interaction resumes that goal unless another grounded informational answer owns the turn.
- A proposal may remain current because it is an explicit action outcome.
- Switching topics never silently cancels or supersedes another goal.
- Replacing a goal requires explicit model-identified control intent and deterministic validation.
- Returning to a paused goal restores its exact missing fields and pending request.

### 6. Preserve Safety Boundaries

- Authenticate before any goal or business lookup.
- Authorize every tool independently of the model.
- Validate record ownership and all tool arguments server-side.
- Keep read and write tools separate.
- Treat retrieved text and tool output as untrusted data, never instructions.
- Preview consequential actions and require structured confirmation.
- Bind idempotency to operation, target, actor, and normalized input.
- Record external references and truthful partial-failure states.
- Use versioned atomic goal updates and append-only audit transitions.

### 7. Validate Broadly

Run focused checks first, then the full relevant suites. Tests must not require live models.

At minimum cover:

1. Partial goal creation.
2. Related question detour.
3. Unrelated question detour.
4. Question plus field update in one turn.
5. Correction of a prior value.
6. New goal while another is active.
7. Pause and resume after a new database session/restart.
8. Incomplete submission rejection.
9. Confirmation before sensitive execution.
10. Duplicate confirmation idempotency.
11. Unauthorized or foreign identifiers.
12. Missing grounding without fabrication.
13. Workflow checkpoint resume.
14. External action failure.
15. Prompt injection in retrieved content.
16. Goal-bound card hidden on detour and restored on resume.
17. Dynamic journey status and mobile/desktop layout.

Perform browser validation across relevant personas and record wording, layout, and workflow findings before claiming completion.

## Repository-Specific Mapping

For this repository:

- `Hardware Assistant` is the Conversation Supervisor.
- `capture_intent_plan` is the typed service-intent decomposition boundary; extend it rather than adding phrase routing.
- `ServiceProfileRegistry` is the basis of the Goal Handler Registry.
- Durable conversation goals must not rely only on `ChatConversation.intake_state` or transcript replay.
- `WorkflowBuilder` in `backend/app/agents/mesh.py` remains the real bounded specialist fan-out/fan-in topology.
- Existing deterministic request, proposal, approval, custody, procurement, and incident services remain authoritative.
- `CasePanel` renders the conversational goal portfolio before commit; the authoritative request journey takes over after commit.
- Prepared commands enforce no model or retrieval calls after consent.

## Completion Gate

Do not call the architecture complete until:

- goal state survives restart independently of transcript history;
- detours and resume work in both deterministic tests and a browser replay;
- mixed turns can answer and update state;
- one active goal is explicit and paused goals are retained;
- pending interactions are goal-bound;
- writes require validation, consent, and idempotency;
- all relevant tests and builds pass;
- documentation shows implemented capabilities, deferred capabilities, extension guidance, and official references.
