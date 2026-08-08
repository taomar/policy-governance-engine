# Goal-Anchored Conversational Architecture Contract

This reference defines the reusable architecture for natural conversational detours that preserve, progress, pause, and resume business goals. It is domain-independent: service requests, purchasing, onboarding, claims, bookings, support incidents, and applications are examples, not core orchestration concepts.

## Architectural Separation

Keep four state domains distinct:

1. **Conversation history**: what people and agents said.
2. **Goal state**: validated facts, candidate facts, current step, missing information, pending request, and pending action.
3. **Domain grounding**: approved documents, product data, policies, and live system records.
4. **Execution state**: external actions, approvals, idempotency, compensation, and workflow checkpoints.

The LLM manages language and interpretation. The Goal Manager owns objective state. Task workflows own progression. Deterministic code owns rules and transitions. External systems remain authoritative.

## Logical Components

### Conversation Supervisor

The only user-facing agent:

- receives every message;
- obtains a compact active-goal summary;
- invokes typed turn interpretation;
- calls grounded tools or bounded specialists;
- sends candidate updates and corrections to the Goal Manager;
- requests workflow progression;
- composes one natural response;
- retains the active goal through detours;
- never mutates validated state or executes sensitive actions directly.

### Turn Interpreter

Use machine-consumed structured output or an equivalently typed function-tool contract. A turn may contain multiple updates, questions, corrections, and one control intent.

```json
{
  "field_updates": [
    {
      "field": "string",
      "value": {},
      "source_text": "string",
      "confidence": 0.0
    }
  ],
  "questions": [
    {
      "text": "string",
      "relationship": "goal_related | adjacent | unrelated",
      "requires_grounding": true
    }
  ],
  "corrections": [
    {
      "field": "string",
      "new_value": {},
      "source_text": "string"
    }
  ],
  "control_intent": "none | continue | pause | resume | switch_goal | cancel | confirm | reject",
  "candidate_new_goal_type": null,
  "needs_clarification": false,
  "clarification_reason": null
}
```

Rules:

- values remain candidates until validated;
- retain source message and source text;
- never invent missing values;
- confidence never authorizes critical data;
- process questions and information in the same turn;
- corrections replace prior candidates through versioned updates;
- detect goal switching without abandoning the active goal.

### Goal Manager

Persist goals independently of conversation history.

```json
{
  "goal_id": "string",
  "goal_type": "string",
  "version": 1,
  "status": "created | collecting | waiting | ready | confirming | executing | paused | completed | cancelled | failed",
  "current_step": "string",
  "confirmed_fields": {},
  "candidate_fields": {},
  "missing_fields": [],
  "pending_user_request": null,
  "pending_action": null,
  "workflow_checkpoint": null,
  "created_at": "timestamp",
  "updated_at": "timestamp"
}
```

Responsibilities:

- create, load, pause, resume, cancel, and fail goals;
- validate candidates through the registered handler;
- compute missing data deterministically;
- avoid re-asking confirmed information;
- apply corrections with version and audit history;
- retain one active goal and several paused/completed goals;
- require explicit replacement rather than silent overwrite;
- enforce optimistic concurrency;
- produce compact supervisor context;
- never reconstruct authority from transcript prose.

### Goal Handler Registry

Core orchestration must not know domain field names or business rules. Each goal handler supplies equivalents of:

```text
create_goal(initial_context)
validate_updates(current_state, proposed_updates)
apply_updates(current_state, validated_updates)
determine_missing_fields(current_state)
determine_next_step(current_state)
build_user_request(current_state)
preview_action(current_state)
execute_action(confirmed_state)
cancel(current_state)
```

Each handler declares:

- state schema;
- required and optional fields;
- validation and transition rules;
- grounding sources;
- allowed read and write tools;
- confirmation policy;
- completion criteria;
- cancellation and compensation behavior.

### Knowledge and Specialist Layer

Ordinary information detours do not transfer conversational ownership.

Use:

- deterministic/live read tools;
- approved-document retrieval or context providers;
- focused agents-as-tools when genuine reasoning is needed.

A specialist receives minimal context, returns a bounded answer, cannot mutate goals, cannot call transaction tools unless explicitly authorized, and reports missing grounding. Use handoff only when a specialist must own several conversational turns.

### Task Workflow

Model each business process as controlled Microsoft Agent Framework workflow components when appropriate:

- deterministic executors for validation, policy, transitions, and writes;
- agent executors only for language or genuine reasoning;
- conditional edges;
- structured workflow state;
- the installed-version request/response mechanism for human input;
- checkpoints and durable execution for long-running work;
- optional workflow-as-agent composition when it simplifies supervisor integration.

Do not model interactive data collection as a fixed sequential multi-agent pipeline.

### Response Composer

Normally compose in this order:

1. Answer current questions directly.
2. Acknowledge recorded or corrected information.
3. Explain validation problems without blaming the person.
4. State important workflow consequences.
5. Ask the next best missing question.

Do not append a robotic return-to-task phrase. Ask only for missing information and prefer one focused question.

## Deterministic Routing Policy

| Turn behavior | Required result |
| --- | --- |
| Provides task information | Validate, store candidates/confirmed data, progress workflow |
| Related question | Ground and answer, retain goal, continue naturally |
| Information plus question | Process both in one turn |
| Correction | Versioned replacement after validation |
| Adjacent question | Answer according to policy, offer light continuation |
| Unrelated question | Answer/decline per product policy; retain goal |
| New goal | Pause old goal or request explicit replacement; never erase silently |
| Pause | Checkpoint and mark paused |
| Resume | Restore exact goal, step, missing fields, and pending request |
| Cancel | Confirm material consequences, then compensate deterministically |
| Submit | Block until validation and confirmation pass |
| Repeat confirmation | Return idempotent prior outcome; never repeat write |

## Microsoft Agent Framework Mapping

Verify every API against the installed version before use. Preferred conceptual mapping:

- `AIAgent`: Conversation Supervisor.
- OpenAI Responses-compatible client: model client.
- `AgentSession`: conversation-scoped model/session continuity.
- `AIContextProvider`: compact goal summary injection when supported by installed version.
- `WorkflowBuilder`, executors, and edges: controlled task/specialist workflows.
- Workflow state: typed executor exchange.
- `RequestPort` or `request_info()`: human input when supported by installed version.
- Agent-as-tool: bounded specialists.
- Workflow-as-agent: optional task workflow exposure.
- Middleware: authentication, authorization, validation, policy, and telemetry.
- Approval-required functions: sensitive writes.
- Checkpoints/Durable Extension: long-running recovery.

Context injection never authorizes goal mutation; Goal Manager methods do.

## OpenAI Integration

- Use structured outputs or typed function calls for machine-consumed interpretation.
- Use function tools for live reads, identifier validation, record retrieval, previews, and approved actions.
- Never parse assistant prose to trigger writes.
- Separate read and write tools.
- Use narrow write schemas and explicit descriptions.
- Require approval immediately before sensitive execution.
- Conversation APIs may preserve dialogue but never replace application-owned goal state.

## Safety and Execution Controls

- Authenticate before loading goals/business records.
- Authorize every tool independently.
- Validate owner, tenant, and record identifiers from authoritative context.
- Never expose another user's goals.
- Validate arguments server-side.
- Present an accurate action preview.
- Use object-bound idempotency.
- Record external action references and status.
- Handle timeout/partial failure without claiming success.
- Treat retrieval and tool output as untrusted data.
- Prevent prompt injection from changing permissions or policy.
- Use least privilege for connectors.

## Persistence Boundaries

Provide separate production abstractions for:

- conversation/session state;
- goal state;
- workflow checkpoints;
- audit events;
- external action/idempotency records.

In-memory adapters are acceptable only for local development. Goal updates are atomic and versioned. Restarting between turns must not lose focus or repeat completed work.

## Observability

Record safe structured telemetry for:

- conversation, goal, and goal type;
- workflow step;
- agent/executor/tool;
- tool result status;
- state transition;
- approval request/outcome;
- external action reference;
- latency/retry/error category.

Never log secrets, tokens, unnecessary personal data, raw prompts, or hidden reasoning. Operators must reconstruct behavior from durable facts rather than chain-of-thought.

## Testing Matrix

CI uses deterministic model/tool doubles. Test at least:

1. Partial goal start.
2. Related detour.
3. Question and update together.
4. Correction.
5. Unrelated detour.
6. Second goal.
7. Pause/resume after restart.
8. Incomplete submission.
9. Sensitive confirmation.
10. Duplicate confirmation.
11. Invalid/unauthorized identifiers.
12. Grounding unavailable.
13. Checkpoint resume.
14. External failure.
15. Retrieved prompt injection.
16. Multi-intent natural-language fixtures.
17. Pending card hidden on detour and restored on resume.
18. Browser journey and wording across roles.

## Documentation Deliverables

Document:

- implementation and extension interfaces;
- minimal goal-handler example;
- grounded read tool and approval-protected write tool;
- component and detour/resume sequence diagrams;
- local setup/build/test commands;
- assumptions and unimplemented production integrations;
- installed-version framework limitations;
- how to add a goal type without changing the supervisor.

## Completion Criteria

Complete only when the project builds, relevant tests pass, state survives restart, detours and resume work, mixed turns work, confirmed data is not repeatedly requested, goal replacement is explicit, sensitive writes require confirmation, idempotency prevents duplication, grounding failures remain truthful, domain rules remain outside core orchestration, and documentation distinguishes implemented from educational capabilities.

## Authoritative References

Check current pages and installed package APIs before implementation:

- [Microsoft Agent Framework overview](https://learn.microsoft.com/en-us/agent-framework/overview/)
- [Microsoft Agent Framework workflows](https://learn.microsoft.com/en-us/agent-framework/workflows/)
- [Context providers](https://learn.microsoft.com/en-us/agent-framework/agents/conversations/context-providers)
- [Workflow state](https://learn.microsoft.com/en-us/agent-framework/workflows/state)
- [Human in the loop](https://learn.microsoft.com/en-us/agent-framework/workflows/human-in-the-loop)
- [Agents as tools](https://learn.microsoft.com/en-us/agent-framework/journey/agents-as-tools)
- [Workflows as agents](https://learn.microsoft.com/en-us/agent-framework/workflows/as-agents)
- [OpenAI function calling](https://developers.openai.com/api/docs/guides/function-calling)
- [OpenAI structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs)
- [OpenAI conversation state](https://developers.openai.com/api/docs/guides/conversation-state)
