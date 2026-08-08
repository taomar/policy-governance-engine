---
name: design-business-agentic-systems
description: Discover a business operating model and then design, implement, refactor, or review the justified allocation of work among people, deterministic services, retrieval, LLM-assisted agents, bounded autonomous agents, and Microsoft Agent Framework workflows. Use for business-process discovery, agentic architecture, multi-agent design, autonomy decisions, agent rationalization, human-in-the-loop processes, cross-industry workflow automation, Azure OpenAI or MAF implementations, or whenever a repository must determine what should be an agent, what may act autonomously, and what must remain deterministic or human-owned before coding.
---

# Design Business Agentic Systems

## Objective

Understand the business before selecting agents. Derive the architecture from outcomes, actors, authority, decisions, data, exceptions, risk, and operating conditions. Do not start from a desired agent count, an organization chart, fashionable orchestration pattern, or a list of job titles.

Produce the smallest coherent system that can achieve the business outcome safely. The result may contain no autonomous agent, one agent, or several agents. Every selected agent and every granted autonomous action requires repository or business evidence.

Use Microsoft Agent Framework to combine typed workflows, deterministic executors, LLM agents, external systems, and human gates. Do not equate a MAF executor, workflow step, scheduled job, human role, or API adapter with an AI agent.

## Non-negotiable rules

1. Never invent the business process, policy, authority, source of truth, exception behavior, integration contract, or acceptable risk.
2. Never design agents before mapping the current and intended operating model.
3. Never create one agent per department, job title, policy, workflow step, data source, or backend system.
4. Never call a fixed sequence, timer, notification job, rules engine, search index, or API wrapper an autonomous agent.
5. Never use an LLM for a decision that is completely determined by trusted facts and explicit rules.
6. Never let an LLM create authority, authenticate a principal, grant access, approve its own action, calculate a binding amount, attest a physical event, or silently resolve an unresolved policy conflict.
7. Never grant autonomy merely because a task is multi-step. Require changing conditions, meaningful choice among safe actions, and a justified need to replan.
8. Never grant an agent broader data or tool access than the business capability requires.
9. Never rely on a prompt as an authorization, approval, policy, budget, or state-transition boundary.
10. Never allow an autonomous loop without a goal, action allowlist, budget, termination conditions, escalation rules, idempotency, and an accountable human owner.
11. Never hide uncertainty. Mark assumptions, unknowns, conflicting evidence, and decisions requiring a business owner.
12. Never fabricate Microsoft Agent Framework or provider APIs. Inspect installed versions and verify current official documentation before implementing version-sensitive code.

## Establish the task and evidence boundary

Determine whether the user requests discovery, architecture, review, implementation, or migration. Inspect the repository and supplied business artifacts before proposing topology or editing runtime code.

Locate and read the relevant subset of:

- process maps, policies, procedures, forms, decision tables, SLAs, controls, audit findings, and exception logs;
- user journeys, tickets, case histories, call transcripts, operational notes, and failure reports;
- roles, approval matrices, delegations, separation-of-duty rules, and organizational relationships;
- domain models, state machines, APIs, events, queues, schedulers, rules, search, prompts, agents, workflows, and integration adapters;
- sources of truth for identity, policy, money, inventory, capacity, entitlement, approvals, and operational state;
- current volumes, cycle time, wait time, rework, exception rate, error cost, and service objectives when available.

Trace actual read and write paths. Distinguish documented behavior from implemented behavior and observed operational behavior. If they differ, record all three and identify which owner must resolve the discrepancy.

Do not block an architecture assessment merely because metrics are missing. Use conditional conclusions and state what evidence would change the decision. Do not implement a security-, authority-, or data-boundary assumption when the missing choice materially changes the design.

## Complete business discovery before agent allocation

Build a business operating model containing:

1. **Outcome and boundary** — trigger, beneficiary, value, completion condition, scope, and excluded work.
2. **Actors and accountability** — requester, beneficiary, case owner, approvers, operators, policy owners, system owners, and auditors.
3. **Authority and decision rights** — who may decide, approve, execute, override, attest, and review each material action.
4. **Information and systems of record** — required facts, provenance, freshness, confidence, access class, and authoritative source.
5. **Process and state** — happy path, branches, waits, deadlines, escalation, cancellation, compensation, and closure.
6. **Policies and constraints** — applicability, precedence, thresholds, exceptions, jurisdiction, effective dates, and human discretion.
7. **Variation and uncertainty** — unstructured inputs, ambiguity, changing conditions, exception families, and novel cases.
8. **Risk and controls** — financial, legal, safety, privacy, security, fairness, operational, and reputational impact.
9. **Operational economics** — volume, frequency, latency, manual effort, bottlenecks, error/rework, and expected value of automation.

Model both the current process and the intended process. Do not automate waste or preserve accidental manual behavior without examining why it exists.

Read [references/business-discovery-and-agent-allocation.md](references/business-discovery-and-agent-allocation.md) completely before classifying activities, proposing agents, defining autonomy, or implementing a business workflow.

## Decompose the process into atomic activities

Decompose by business responsibility rather than application screen or department. An activity must have one primary outcome, a clear input and output, and a clear accountable owner.

For every activity capture:

```text
activityId
businessOutcome
trigger and frequency
actor and accountableOwner
inputs and authoritativeSources
decisionRights
rules and policies
output and sideEffects
structured versus unstructured variation
known exceptions and changing conditions
impact and reversibility
latency and volume
current painPoint
evidence and openQuestions
```

Split an activity when its authority, data sensitivity, risk, lifecycle, or evaluation method changes. Keep activities together when they share one goal and only differ by ordinary deterministic branches.

## Classify each activity before naming agents

Assign one primary execution class and optional supporting classes:

| Class | Use when |
| --- | --- |
| Human-owned | A person must exercise accountable discretion, approve, attest, negotiate, or perform physical work |
| Deterministic service | Trusted facts and explicit logic can produce the correct result repeatably |
| Retrieval or analytics | The need is finding evidence, querying records, calculating metrics, or ranking candidates without delegated reasoning |
| LLM-assisted step | Language, document, image, or conversational interpretation is useful, but a caller or workflow owns the goal and next step |
| Supervised agent | An LLM may propose a plan or tool call, but a person or deterministic gate approves sensitive actions |
| Bounded autonomous agent | An LLM owns a durable delegated goal, observes changing conditions, chooses among allowlisted actions, replans, and stops or escalates within explicit limits |
| MAF workflow | The business process has known states, branches, waits, timers, retries, integrations, and human gates |

Use supporting classes rather than forcing one technology onto the whole activity. For example, an LLM may extract candidate facts, a deterministic service may verify and decide, a human may approve, and a MAF workflow may coordinate them.

Apply these gates in order:

1. If accountable human judgment, approval, legal authority, or physical attestation is required, keep that decision or act human-owned.
2. If typed facts and explicit logic determine the result, implement a deterministic service or rules component.
3. If the main need is evidence discovery or calculation, use search, retrieval, query, or analytics—not an agent.
4. If the main difficulty is unstructured understanding or explanation, use a bounded LLM step.
5. If the sequence and branches are knowable, use an explicit workflow even when some steps contain agents.
6. Consider autonomy only when the case has a durable goal, materially changing conditions, multiple valid next actions, and a real need for contextual replanning.
7. Reject autonomy when permissions, safe actions, budgets, stop conditions, evaluation, or accountable ownership cannot be specified.

The classification decision must cite observed evidence and at least one cheaper non-agent alternative. Do not use false numeric precision to conceal missing facts.

## Separate language reasoning from autonomy

Use this autonomy ladder:

| Level | Meaning |
| --- | --- |
| `L0_NO_LLM` | Human, deterministic, retrieval, or workflow implementation only |
| `L1_ASSISTIVE` | LLM interprets, drafts, summarizes, or explains during a bounded invocation; no side effect |
| `L2_SUPERVISED_ACTION` | LLM proposes an action or plan; an authorized person or deterministic gate confirms sensitive execution |
| `L3_BOUNDED_AUTONOMY` | Agent pursues a durable case goal and may execute pre-authorized, allowlisted, reversible or compensatable actions within limits |
| `PROHIBITED` | LLM involvement is not acceptable for this activity or data boundary |

Autonomy is not a property of an agent name. Assign it per action. One agent may read autonomously, draft without approval, send low-risk reminders within limits, require approval for a supplier message, and be prohibited from approving spend.

## Derive agent boundaries from the business

Create an agent only when one or more activities require LLM reasoning and share a coherent:

- delegated business goal;
- context and lifecycle;
- permission ceiling and tool set;
- data-access boundary;
- risk and human owner;
- evaluation criteria.

Combine activities when those dimensions align. Split them when authority, sensitive data, runtime lifecycle, tool permissions, domain expertise, or evaluation materially differ. Keep authoring/governance agents separate from runtime case agents.

For every proposed agent produce an `AgentCharter` with:

```text
agentId and businessPurpose
supportedActivityIds
trigger and termination
autonomyByAction
trustedInputs and untrustedInputs
allowedTools and allowedDataScopes
allowedActions and forbiddenActions
policy and decisionDependencies
humanOwner and escalationTargets
budgets, deadlines, loop and concurrencyLimits
stop, pause and fallbackConditions
state and memoryBoundary
idempotency and compensation
auditEvents
quality, safety and businessEvaluations
evidenceJustification
```

An agent without a complete charter is a design hypothesis, not an implementation target.

## Map the design to Microsoft Agent Framework

Use an explicit typed MAF workflow for authoritative business processes. MAF documentation distinguishes dynamic, LLM-driven agent steps from predefined workflows; preserve that distinction in the implementation.

Map components as follows:

| Business allocation | MAF/application implementation |
| --- | --- |
| Deterministic activity | Typed executor or domain-service call |
| LLM-assisted activity | Agent executor with validated structured output |
| Human decision or information | Request/response human-in-the-loop gate backed by an authenticated application task |
| Long-running case | Durable workflow/checkpoint plus authoritative domain state |
| Bounded autonomous activity | Agent loop contained inside a workflow stage with action policy, budgets, stop conditions, and escalation |
| External side effect | Least-privilege idempotent command tool behind authorization and policy enforcement |
| Known timing or escalation | Workflow timer, event, or scheduler |

Keep authoritative business state in the domain database. MAF state stores execution continuation and agent session context, not the sole record of approvals, money, custody, entitlements, or completed work.

Use multi-agent orchestration patterns only when the selected agents have real distinct reasoning responsibilities. Do not choose sequential, concurrent, handoff, group-chat, or manager patterns before the agent charters exist. Avoid dynamic manager orchestration on binding approval, policy, financial, safety, or fulfillment paths unless a deterministic envelope controls every material action.

## Generalize through domain profiles

Keep the discovery and allocation method cross-industry. Put industry semantics in a typed `DomainProfile`, not only in prompts.

A profile defines:

- domain vocabulary, outcomes, actors, capabilities, and organization relationships;
- request, case, fact, evidence, and resource schemas;
- sources of truth and integration contracts;
- policy subjects, decision services, precedence, and human-discretion points;
- business states, events, tasks, actions, compensation, and closure invariants;
- risk classes, approval rules, data restrictions, and evaluation suites;
- jurisdiction, locale, language, currency, calendar, retention, and accessibility requirements.

Examples include hardware fulfillment, HR leave, travel, access provisioning, procurement, insurance claims, facilities, and public-service cases. Reuse the method, contracts, and controls; do not assume that roles, state machines, authorities, or acceptable autonomy transfer unchanged between industries.

Use a domain-specific skill alongside this skill when one exists. The domain skill supplies terminology and invariants; this skill determines the execution allocation and agent topology.

## Execute in the repository

For implementation work, follow this order:

1. Inspect dependencies, write paths, business artifacts, runtime topology, and installed MAF/provider APIs.
2. Produce the current-state operating model, open questions, activity map, and allocation matrix.
3. Produce the proposed operating model, agent charters, autonomy-by-action matrix, trust boundaries, and MAF workflow.
4. State the evidence, benefit hypothesis, cheaper alternative, and disconfirming test for every agent.
5. Define typed domain, decision, workflow, agent, action-policy, approval, task, and audit contracts.
6. Implement authoritative services and tool boundaries before agent prompts.
7. Implement the explicit workflow and human tasks before enabling autonomous actions.
8. Implement LLM steps with structured outputs, grounded context, minimal permissions, and model-independent interfaces.
9. Enable autonomy by action in shadow, advisory, supervised, and then bounded modes only after evidence supports promotion.
10. Add business, deterministic, workflow, security, agent, resilience, migration, and operational tests.
11. Run focused tests and then the complete relevant suite. Report verified and unverified boundaries exactly.

Extend existing abstractions rather than creating a parallel agent platform. Preserve historical decisions and workflow lineage. Use compatibility adapters for controlled migrations instead of dual writable authority.

## Required design artifacts

Produce the relevant subset of:

1. Business outcome and scope statement.
2. Evidence inventory and unresolved business questions.
3. Current and intended operating-model maps.
4. Actor, authority, source-of-truth, and risk matrices.
5. Atomic activity catalog.
6. Activity allocation and autonomy-by-action matrix.
7. Rejected-agent alternatives and rationales.
8. Agent charters and tool/data permission matrix.
9. Typed MAF workflow with human and deterministic boundaries.
10. Domain profile and contracts.
11. Implementation, migration, evaluation, rollout, rollback, and operating-ownership plan.

Do not present agent names alone as an architecture.

## Verify the decision and the implementation

Verify both whether the chosen topology is justified and whether the implementation behaves safely.

At minimum test:

- representative happy, exception, ambiguous, conflicting, incomplete, and adversarial cases;
- deterministic replay for binding decisions and workflow transitions;
- structured-output validation and behavior when model confidence is low;
- tool authorization, tenant/data isolation, prompt injection, and excessive-agency attempts;
- action budgets, duplicate events, retries, timeouts, restarts, cancellation, and compensation;
- escalation when the agent cannot make progress or reaches a prohibited action;
- shadow comparisons against current human outcomes and operations;
- business metrics such as cycle time, wait time, rework, error, escalation, abandonment, and human workload;
- drift in inputs, policies, tools, models, and organizational conditions;
- removal of an agent whose measured value does not exceed its cost and risk.

Do not claim success from conversational examples or model evaluations alone. Binding business invariants and human accountability must also pass.

## Current official references

Verify current capabilities and exact APIs through official Microsoft sources and the repository's pinned packages:

- MAF workflows and agent/workflow distinction: https://learn.microsoft.com/agent-framework/workflows/
- MAF executors: https://learn.microsoft.com/agent-framework/workflows/executors
- MAF human-in-the-loop: https://learn.microsoft.com/agent-framework/workflows/human-in-the-loop
- MAF orchestration patterns: https://learn.microsoft.com/agent-framework/workflows/orchestrations/
- MAF durable extension: https://learn.microsoft.com/agent-framework/integrations/durable-extension
- MAF tool approvals: https://learn.microsoft.com/agent-framework/agents/tools/tool-approval

Keep provider-specific code behind typed adapters. If the installed API or external contract cannot be verified, keep the design at the interface level rather than fabricating an implementation.
