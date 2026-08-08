# Business Discovery and Agent Allocation

## Contents

1. Discovery procedure
2. Operating-model artifacts
3. Atomic activity analysis
4. Allocation decision procedure
5. Autonomy qualification
6. Agent boundary and charter design
7. Microsoft Agent Framework execution mapping
8. Cross-industry domain profiles
9. Implementation and rollout
10. Verification and architecture review

## 1. Discovery procedure

### Establish the business question

Write one falsifiable outcome statement:

```text
For <beneficiary>, when <trigger>, enable <measurable outcome>
within <service objective>, while preserving <authority/control constraints>.
The process is complete only when <business invariant>.
```

Avoid outcomes such as “deploy multiple agents” or “automate the workflow.” Those are implementation preferences, not business results.

### Build an evidence register

For every source record:

| Field | Meaning |
| --- | --- |
| Evidence ID | Stable identifier |
| Type | Policy, process, code, schema, interview, ticket, log, metric, audit, or observation |
| Owner | Accountable source owner |
| Scope | Population, jurisdiction, product, unit, and dates |
| Authority | Normative, approved, draft, descriptive, historical, or unknown |
| Freshness | Effective date and last verified time |
| Supports | Business fact, activity, rule, risk, or pain point |
| Conflicts | Other evidence IDs that disagree |
| Confidence | Verified, partially verified, or unverified |

Do not treat the loudest stakeholder statement as authoritative. Reconcile policy, process documentation, code behavior, and operational evidence.

### Inspect the process from four views

1. **Normative view** — what policy and approved procedures require.
2. **System view** — what code, rules, integrations, and permissions currently enforce.
3. **Operational view** — what people actually do, including spreadsheets, email, workarounds, and unofficial escalations.
4. **Outcome view** — what succeeds or fails according to metrics, cases, complaints, and audits.

Record mismatches. A mismatch can reveal a policy defect, missing integration, bad user experience, control failure, or legitimate exception. Do not automatically encode either side.

### Discover actors by responsibility

For each actor establish:

- business responsibility and accountable outcome;
- authority granted and authority explicitly absent;
- resource and organizational scope;
- information they can see and change;
- decisions, approvals, attestations, and physical actions;
- delegation and escalation rules;
- separation-of-duty constraints;
- workload, queue, SLA, and replacement coverage.

Map company titles and groups to capability roles after discovering responsibilities. Do not branch runtime behavior on a title string.

### Discover decisions

For each decision ask:

- What question is answered?
- Is the result binding, advisory, or explanatory?
- Who owns the decision right?
- Which facts and policy releases apply?
- Can explicit logic determine it?
- What ambiguity or discretion remains?
- What is the consequence of error?
- Can the decision be appealed or reversed?
- What evidence must be preserved?

Decompose mixed decisions. An LLM may interpret a message, a service may calculate eligibility, and a human may approve an exception; these are three different activities.

### Discover variation and exceptions

Sample real cases when available. Classify variation as:

- missing or contradictory facts;
- natural-language, document, image, or speech variation;
- known deterministic branch;
- known exception requiring special authority;
- environmental change after work starts;
- novel situation with no approved rule;
- system or integration failure;
- human delay, rejection, reassignment, or dispute.

Only some of these justify LLM reasoning. Known branches belong in workflow logic. Integration failures need resilience. Novel authority gaps need human governance.

### Discover operational need for autonomy

Collect evidence for:

- cases that remain active over time;
- frequency and cost of manual monitoring;
- number and diversity of safe next actions;
- changes that invalidate an earlier plan;
- unstructured blocker notes or communications;
- time lost waiting for a coordinator to interpret and redirect work;
- escalation and abandonment patterns;
- actions already pre-authorized for the case owner;
- cost and reversibility of a wrong action.

Without these facts, autonomy remains an unproven hypothesis.

## 2. Operating-model artifacts

### Outcome and scope canvas

```text
Business outcome:
Beneficiary:
Trigger:
Start state:
Completion invariant:
In scope:
Out of scope:
Service objective:
Accountable owner:
Material risks:
Known jurisdictions/populations:
Evidence IDs:
Unknowns:
```

### Actor and authority matrix

| Actor/capability | May request | May decide | May approve | May execute | May attest | May override | Scope | Constraints |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |

Use “none” explicitly. Administrative access does not imply business approval authority.

### Source-of-truth matrix

| Business fact | Authoritative source | Projection/cache | Freshness rule | Verification | Access class | Failure behavior |
| --- | --- | --- | --- | --- | --- | --- |

If no authoritative source exists, mark the fact as asserted, inferred, or requiring human verification. Do not present an LLM inference as verified.

### State and event map

For each state define:

```text
stateId
entryConditions
permittedCommands
authorizedActors
eventsProduced
exitConditions
timers and SLA
compensation or cancellation
evidenceRequired
```

Events describe completed facts. Commands request a state change. Do not let free-form model output mutate state directly.

### Risk and control matrix

| Activity/action | Impact | Likelihood | Reversibility | Authority | Required controls | Human gate | Audit evidence |
| --- | --- | --- | --- | --- | --- | --- | --- |

Consider safety, financial, legal, regulatory, privacy, security, fairness, operational, and reputational impacts. Use the organization's approved classification when one exists.

## 3. Atomic activity analysis

### Activity record

```yaml
activityId: stable.business.capability.action
outcome: one observable business result
trigger: event or human request
accountableOwner: capability or named role
frequency: measured or unknown
inputs:
  - fact: value required
    source: authoritative source or assertion
    form: structured | text | document | image | audio
decisionRight: none | advisory | binding | approval | attestation
rules: policy/rule identifiers
outputs: typed facts, recommendations, commands, or events
sideEffects: external or domain mutations
variation: known branches and unstructured variation
changingConditions: events that can invalidate a plan
risk: impact, reversibility, and controls
latency: service objective
painPoint: supported current problem
evidence: evidence IDs
unknowns: unresolved facts
```

### Split and combine tests

Split an activity when any answer changes:

- Who has authority?
- Which source of truth applies?
- Is the output binding or advisory?
- What data sensitivity applies?
- What is the error impact?
- Is the action physical, digital, or communicative?
- What evaluation proves correctness?

Combine activities when they share one goal, owner, permission boundary, lifecycle, and evaluation and differ only through deterministic branches.

## 4. Allocation decision procedure

Classify every activity using this procedure. Record the first decisive gate and any supporting mechanisms.

### Gate A: human accountability

Keep the material act human-owned when it requires:

- approval or rejection by an accountable authority;
- legal, regulatory, employment, clinical, safety, or fiduciary discretion;
- negotiation or exception authority not codified in approved rules;
- physical inspection, receipt, custody, configuration, delivery, or attestation;
- a policy-mandated human review;
- a value judgment the organization has not delegated to automation.

An LLM can assemble evidence or summarize a case. It cannot impersonate the accountable person.

### Gate B: deterministic correctness

Use a deterministic component when:

- typed inputs and explicit logic determine the answer;
- arithmetic, dates, thresholds, calendars, eligibility, precedence, permissions, balances, stock, or state transitions are involved;
- replay must produce the same result for the same versioned facts;
- an invariant or constraint can be encoded and tested;
- a side effect requires exact preconditions.

Possible implementations include code, configuration, decision tables, a rules engine, SQL/query logic, optimization, a state machine, or a domain service. Select by ownership and complexity, not by AI branding.

### Gate C: retrieval or analytics

Use search, query, or analytics when the problem is primarily:

- locating exact policy or case evidence;
- filtering or ranking catalog items;
- aggregating records or calculating metrics;
- finding similar prior cases for advisory context;
- monitoring known SLA or state conditions.

Retrieval can support an agent but is not itself an agent. Search results do not make binding decisions.

### Gate D: LLM assistance

Use an LLM step when it materially improves:

- intent understanding from free language;
- candidate fact extraction from text, documents, images, or speech;
- clarification questions;
- semantic comparison or inconsistency detection;
- summarization for a specific audience;
- grounded explanation of a verified result;
- drafting communications or recommendations;
- interpretation of unstructured operational notes.

Require a typed output schema, provenance, validation, confidence/uncertainty behavior, and a deterministic or human consumer. Do not send more sensitive context than needed.

### Gate E: explicit workflow

Use a MAF workflow or another workflow/state-machine mechanism when the process needs:

- known sequencing or conditional branches;
- parallel independent reads;
- approvals or information waits;
- deadlines, timers, escalation, retry, and compensation;
- durable continuation across process restarts;
- typed routing between people, agents, services, and integrations.

A workflow remains the authoritative control plane even if several steps invoke LLM agents.

### Gate F: autonomous-agent candidacy

An activity is only a candidate for bounded autonomy when all are true:

1. It has a durable delegated business goal, not merely a single transformation.
2. Conditions can change after the initial plan.
3. Several context-dependent next actions can be valid.
4. Choosing the next action requires semantic reasoning that explicit rules cannot economically cover.
5. The agent can observe the needed state through authorized, typed tools.
6. Every permitted action can be enumerated, authorized, validated, audited, and made idempotent.
7. Risk limits, budgets, stop conditions, and escalation targets are explicit.
8. Wrong actions are reversible, compensatable, low impact, or human-gated.
9. An accountable business owner accepts operational responsibility.
10. Evaluations can measure task success, policy compliance, tool correctness, and safe escalation.
11. Expected business value exceeds the simpler workflow or supervised alternative.

If any mandatory condition fails, use `L1_ASSISTIVE`, `L2_SUPERVISED_ACTION`, workflow logic, or human handling.

### Common false positives for autonomy

Do not create an autonomous agent merely to:

- send scheduled reminders;
- poll a status and follow a known branch;
- route by a finite status code;
- call several APIs in a fixed order;
- calculate eligibility or price;
- look up a manager or approver;
- reserve stock or funds;
- translate or summarize one document;
- approve on behalf of a manager, buyer, policy owner, clinician, or regulator;
- make the architecture appear multi-agent.

These are schedulers, executors, services, workflows, LLM steps, or human tasks.

### Allocation record

| Activity | Primary class | Supporting classes | Autonomy level | Evidence | Why LLM | Why autonomy | Simpler alternative | Rejection/selection reason | Owner |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |

Do not leave “Why autonomy” blank for an `L3_BOUNDED_AUTONOMY` allocation.

## 5. Autonomy qualification

### Assign autonomy per action

For every tool/action used by an LLM, assign one:

| Mode | Runtime treatment |
| --- | --- |
| `READ_ONLY_AUTOMATIC` | Authorized read may execute automatically within data scope |
| `DRAFT_ONLY` | Produce a proposal; no external mutation |
| `RULE_GATED_AUTOMATIC` | Execute only after deterministic preconditions and low-risk policy allow it |
| `HUMAN_APPROVAL_REQUIRED` | Pause and require an authenticated authorized decision |
| `HUMAN_EXECUTION_REQUIRED` | Create a task for physical or accountable human work |
| `PROHIBITED` | Never expose the action to the agent |

An agent can therefore be `L3` for case coordination while individual high-impact actions remain human-gated or prohibited.

### Required autonomous envelope

Define:

```yaml
goal:
caseScope:
humanOwner:
allowedObservations:
allowedActions:
actionModes:
policySetBinding:
authorizationContext:
timeBudget:
tokenAndCostBudget:
maxIterations:
maxConsecutiveFailures:
communicationLimits:
financialOrResourceLimits:
completionConditions:
pauseConditions:
escalationConditions:
forbiddenOutcomes:
idempotencyStrategy:
compensationStrategy:
auditEvents:
```

Enforce the envelope outside the model. The model may choose among valid actions; it may not widen the envelope.

### Promotion ladder

Promote one action class at a time:

1. **Offline evaluation** — replay representative historical and synthetic cases.
2. **Shadow** — observe live inputs and compare recommendations without acting.
3. **Advisory** — show recommendations to an operator.
4. **Supervised execution** — prepare tool calls that require approval.
5. **Bounded automatic execution** — enable only proven low-risk actions.

Define rollback criteria before promotion. Model accuracy alone is insufficient; verify business outcomes, authorization, policy compliance, and safe escalation.

## 6. Agent boundary and charter design

### Boundary decision

Group LLM activities into one agent when they share:

- one delegated goal and termination condition;
- one case or conversation lifecycle;
- compatible data classification and access scope;
- the same tool permission ceiling;
- the same accountable owner and escalation path;
- a coherent evaluation suite.

Split agents when they require:

- different authorities or data isolation;
- different high-risk tools;
- different domain evidence and evaluation;
- runtime case behavior versus policy/content authoring;
- independent lifecycle or scale characteristics;
- a security boundary that should not rely on prompting.

Do not split solely for personas, tone, departments, titles, tables, or microservices.

### Agent charter template

```yaml
agentId:
purpose:
businessOutcome:
supportedActivities:
humanOwner:
trigger:
termination:
autonomyLevel:
autonomyByAction:
inputs:
  trusted:
  untrusted:
contextPolicy:
dataScopes:
tools:
  read:
  write:
forbiddenToolsAndActions:
decisionDependencies:
policyBinding:
outputContracts:
memory:
budgets:
stopConditions:
escalations:
idempotency:
compensation:
audit:
evaluations:
evidenceAndRationale:
```

### Topology review

For every proposed agent ask:

- Can a deterministic executor replace it?
- Can a single bounded LLM call replace a durable agent?
- Can an existing agent safely absorb the activities?
- Does splitting reduce a real permission, data, ownership, or evaluation risk?
- Does the agent have a business goal rather than a technical component name?
- What observable condition would cause removal or merger of the agent?

Record rejected agents. Rationalization is part of the architecture, not a failure to be agentic.

## 7. Microsoft Agent Framework execution mapping

### Recommended control shape

```text
trusted trigger
  -> authenticate and establish case scope
  -> deterministic fact snapshot
  -> LLM interpretation only where needed
  -> deterministic verification and decisions
  -> explicit typed workflow routing
  -> authenticated human request/response gates
  -> bounded agent stage only where qualified
  -> authorized idempotent command tools
  -> reconciliation and immutable audit
```

### Workflow ownership

The workflow owns:

- typed stage sequencing and routing;
- retries, timeouts, external waits, checkpoints, and resume;
- human information and approval requests;
- action preconditions and compensation routing;
- correlation between case, task, agent run, and command.

The domain application owns:

- authoritative case and business state;
- identity, authorization, policies, approvals, money, resources, and custody;
- immutable decision and action records;
- idempotency and outbox/inbox records.

The agent owns only:

- its bounded delegated reasoning goal;
- selection among currently allowed actions;
- structured proposals, explanations, or communications;
- explicit uncertainty and escalation.

### Dynamic orchestration selection

Use:

- **single agent** when one charter covers the reasoning safely;
- **sequential agents** only when distinct charters produce staged reasoning artifacts;
- **concurrent agents** only when independent perspectives add measurable value and aggregation is defined;
- **handoff** for conversational transfer between genuine domains or permission boundaries;
- **group chat or manager orchestration** only for open-ended collaborative reasoning where no binding side effect follows without deterministic validation and authorization.

Do not use dynamic orchestration to resolve policy authority, choose approvers, approve transactions, or bypass a known state machine.

### Tool contract

Every side-effecting tool should require:

```text
principal/case authorization context
caseId and expectedRevision
validated typed arguments
policy or decision reference when applicable
approval reference when required
idempotencyKey
action budget and scope
```

Return typed success, conflict, validation, authorization, policy, unavailable, retryable, and permanent-failure results. Never rely on prose to decide whether a command succeeded.

## 8. Cross-industry domain profiles

### Profile contract

```yaml
profileId:
version:
jurisdictions:
vocabulary:
outcomes:
actorsAndCapabilities:
organizationRelationships:
caseTypes:
factSchemas:
evidenceTypes:
sourcesOfTruth:
policySubjectsAndPrecedence:
deterministicDecisionInterfaces:
statesAndEvents:
taskTypes:
actionsAndCompensations:
humanDecisionAndAttestationPoints:
riskClasses:
dataRestrictions:
serviceObjectives:
evaluationSuites:
integrationAdapters:
```

### What transfers across industries

- the discovery procedure;
- authority and source-of-truth separation;
- activity allocation gates;
- autonomy envelope and action modes;
- agent charter and topology rules;
- workflow durability, HITL, idempotency, audit, and rollout patterns.

### What does not transfer automatically

- policy precedence and legal obligations;
- roles and approval authority;
- domain entities and completion invariants;
- acceptable risk and human discretion;
- state machines, compensations, evidence, retention, and integrations;
- whether a specific activity is suitable for autonomy.

Examples:

- Hardware may require stock reservation, serialized assets, custody, configuration, delivery, and return.
- HR leave may require balance calculation, date rules, coverage, manager/HR authority, and jurisdictional protections.
- Insurance may require coverage, claim evidence, adjuster authority, fraud controls, and regulated notices.
- Access provisioning may require resource ownership, privilege risk, expiry, attestation, and revocation.

Use these only to locate questions. Do not copy their workflows into another domain.

## 9. Implementation and rollout

### Repository execution sequence

1. Map owning modules and actual write paths.
2. Write or update business architecture artifacts close to the owning domain documentation.
3. Implement shared typed contracts without provider dependencies.
4. Implement deterministic policies, authorization, calculations, state transitions, and tool guards.
5. Implement authoritative persistence, audit, outbox/inbox, and idempotency.
6. Implement MAF workflow executors and human request/response handling.
7. Implement LLM agents last, consuming only typed tools and producing validated contracts.
8. Add observability linking business case, workflow, agent run, tool call, decision, approval, and action.
9. Seed representative business scenarios rather than toy prompts.
10. Roll out per action through the promotion ladder.

Do not create a second writable business model to accommodate agents. Adapt agents to the authoritative domain model.

### Architecture checkpoint

Before large runtime edits, present:

- current-state findings and unsupported assumptions;
- activity allocation matrix;
- selected and rejected agent hypotheses;
- autonomy-by-action matrix;
- MAF workflow and trust boundaries;
- concise file plan and migration risk.

Then implement in the same task when authorized and not blocked by a material business decision.

### Operational ownership

Assign owners for:

- business outcome and process;
- policies and decisions;
- identity and authorization;
- each agent charter and action policy;
- evaluation datasets and promotion approval;
- production monitoring, incident response, disable/rollback, and model/provider changes.

An agent without an operational owner must not enter autonomous mode.

## 10. Verification and architecture review

### Business-fit tests

- Does each selected agent address an evidenced language or coordination problem?
- Is the expected value measurable?
- Does a simpler workflow/service alternative perform adequately?
- Are current manual controls understood before removal?
- Are human workload and exception handling improved rather than displaced invisibly?

### Allocation tests

- Are deterministic decisions outside LLM control?
- Are human authority and physical attestations preserved?
- Is retrieval used for evidence rather than authority?
- Does every `L3` activity pass all autonomy candidacy conditions?
- Is autonomy assigned per action rather than per name?
- Are rejected agent ideas recorded with reasons?

### Agent tests

- Contract/schema adherence and groundedness;
- tool selection and argument correctness;
- refusal of prohibited actions;
- safe behavior with missing, contradictory, malicious, or stale inputs;
- progress detection, loop termination, and escalation;
- cross-tenant, cross-case, and cross-role isolation;
- prompt injection and tool-result injection resistance;
- stable behavior across supported model/configuration changes.

### Workflow and system tests

- typed routing and deterministic replay;
- duplicate commands, callbacks, and events;
- concurrency and expected-revision conflicts;
- retries, timeouts, restarts, checkpoints, and resume;
- human approval authenticity and stale-task rejection;
- compensation and cancellation;
- end-to-end reconciliation and immutable audit lineage.

### Production review questions

- What immediately disables each autonomous action?
- What happens when the model, search, policy service, source system, or integration is unavailable?
- Can operators see why the agent acted and which facts, policies, and permissions applied?
- Can a case be recovered without editing the database manually?
- Are cost, latency, token, action, and communication budgets enforced?
- Are drift and business outcome metrics reviewed by named owners?
- What evidence promotes, demotes, merges, or removes an agent?

Do not label the system production-ready while these answers are unknown for material actions.
