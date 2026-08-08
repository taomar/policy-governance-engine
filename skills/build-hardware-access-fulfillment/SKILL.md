---
name: build-hardware-access-fulfillment
description: Design, implement, refactor, or review identity, organization hierarchy, user-group, application-role, authorization, approval, procurement, inventory, logistics, asset-custody, and human-fulfillment architecture for employee hardware support applications. Use when a repository handles laptop replacement, device or accessory requests, employee levels and entitlements, spending allowances, eligible catalog presentation, manager or budget approval, procurement approval, warehouse or logistics work, Microsoft Agent Framework human-in-the-loop workflows, organizational reporting lines, role restructuring, scoped access, delegation, separation of duties, or end-to-end hardware fulfillment.
---

# Build Hardware Access and Fulfillment

## Objective

Build a hardware-support system that can establish who a person is, where they sit in the organization, what they may access, which policies apply, what hardware or spend they are entitled to, who must approve, and which named human or scoped work queue owns each physical fulfillment step.

Keep identity, organizational facts, application permissions, policy eligibility, approval authority, and work assignment separate. Connect them through typed, audited decisions.

Do not begin by naming agents. First discover how this organization actually handles demand, policy, support, approval, procurement, inventory, configuration, delivery, custody, return, exceptions, and closure. Apply the cross-industry business/activity allocation method, then use this skill as the hardware domain profile.

When present, also read:

- `.github/skills/design-business-agentic-systems/SKILL.md` first, for business discovery, activity classification, agent boundaries, and autonomy-by-action decisions;
- `.github/skills/build-policy-driven-agent-systems/SKILL.md` for deterministic policy decisions and runtime policy sets;
- `.github/skills/build-governed-policy-ingestion/SKILL.md` for policy publication and conflict governance;
- `.github/skills/build-policy-ai-search/SKILL.md` for policy discovery and exact evidence retrieval.

## Non-negotiable rules

1. Never equate authentication identity, employment level, department, manager relationship, application role, policy entitlement, approval authority, and fulfillment assignment.
2. Never grant administrative access because a user has a senior job grade, high spending entitlement, or managerial title.
3. Never let an LLM determine authorization, eligibility, allowance balance, approval requirements, approval outcome, inventory allocation, or permission to execute a side effect.
4. Never enforce access only in the frontend, a prompt, or an agent instruction. Enforce it at every API, command, query, workflow-resume, and tool boundary.
5. Never branch on display names, email addresses, group names, or job-title strings. Use stable IDs, typed capabilities, scopes, and effective dates.
6. Never make “Admin” an implicit business approver. Administrative capability and business authority are separate assignments.
7. Never allow self-approval, self-assignment of privileged roles, or incompatible request/approve/purchase/issue/receive actions unless an explicit, audited exception permits it.
8. Never represent a required human approval or fulfillment action as an AI agent decision. Agents may prepare evidence and explanations; authenticated people approve and perform accountable work.
9. Never leave a fulfillment stage owned only by a status value. Assign it to an authorized user or scoped queue, then record claim, reassignment, completion, and custody.
10. Never let current organization changes rewrite historical approval plans, policy sets, decisions, or custody events.
11. Never infer that the latest manager, nearest manager, newest policy, or available device is automatically applicable. Use approved relationship and policy rules.
12. Never present inventory availability as entitlement, or entitlement as stock availability. Compute and explain both independently.
13. Never spend, reserve inventory, create procurement work, issue an asset, or close a request without idempotency and required approvals.
14. Never invent identity-provider, Microsoft Graph, Microsoft Agent Framework, procurement, inventory, or asset APIs. Inspect installed packages, configured integrations, and current official documentation.
15. Never assume that a requester assistant, policy agent, case coordinator, manager agent, procurement agent, or logistics agent is required. Derive every agent and its autonomy from the business activity analysis.

## Inspect the repository before restructuring

For implementation work, locate and map:

- authentication middleware, token parsing, session handling, seeded users, and identity-provider adapters;
- `User`, `Employee`, `Role`, `Group`, `Department`, `Manager`, `Level`, `Grade`, `CostCenter`, and permission models;
- every constructor, mutation, seed, import, and synchronization path for users, roles, managers, and groups;
- route guards, service checks, query filters, frontend visibility checks, and tool authorization;
- request, approval, inventory, procurement, logistics, asset, notification, audit, and MAF workflow modules;
- policy resolver, decision service, policy-set binding, catalog filtering, price, spend, and allowance logic;
- migrations, foreign keys, test fixtures, reporting queries, API contracts, and UI assumptions;
- actual external sources of identity, employment, manager, organization, budget, inventory, and asset truth.

Run a dependency and write-site scan before replacing a legacy `User.role`, group enum, manager field, or approval status. Preserve compatibility through a read-only adapter when necessary; do not maintain two writable authorization models.

For review-only requests, report concrete findings and risks without changing code. For implementation requests, provide a concise file plan and then edit, migrate, and verify in the same task unless genuinely blocked.

## Discover the hardware operating model before allocating agents

Use `design-business-agentic-systems` when it is available. Otherwise reproduce its essential procedure before designing the MAF topology:

1. Define the business outcome, trigger, completion invariant, scope, accountable owner, and service objective.
2. Map current and intended flows from request through policy decision, approvals, sourcing, fulfillment, custody, replacement return, and reconciliation.
3. Identify actual actors, capability roles, decision rights, sources of truth, policies, risks, volumes, delays, exception families, and system boundaries.
4. Decompose the flow into atomic activities with one outcome and owner each.
5. Classify each activity as human-owned, deterministic service, retrieval/analytics, LLM-assisted, supervised agent action, bounded autonomous agent, or workflow orchestration.
6. Assign autonomy per action and document allowed tools, prohibited actions, limits, stop conditions, escalation, and human ownership.
7. Group qualified LLM activities into agents only when their goal, lifecycle, data boundary, permission ceiling, owner, and evaluation align.

Produce an activity-allocation matrix and agent charters before implementing agents. Cite repository or business evidence, a simpler alternative, and the expected operational value for every agent. Missing evidence creates an explicit hypothesis or question, not an invented requirement.

The capability roles later in this skill are a reference catalog, not proof that the organization employs each role or needs a corresponding application role, queue, or agent. Map real responsibilities and separation-of-duty requirements to the smallest valid set.

## Separate the seven dimensions

Model these as distinct concerns:

| Dimension | Question | Authority example |
| --- | --- | --- |
| Authentication identity | Who signed in? | Microsoft Entra ID or configured local identity provider |
| Person and employment | Who is the employee and what is their employment context? | HR system or approved local employee registry |
| Organization relationship | Which positions, units, managers, and cost centers apply at the relevant date? | HR organizational source |
| Application authorization | What operations may this principal perform over which scope? | Role and permission assignments |
| Policy eligibility | What classes, limits, cycles, and exceptions apply? | Deterministic policy resolver and decision service |
| Approval authority | Who is authorized and required to approve this request? | Versioned approval rules plus organization and delegation facts |
| Work ownership | Which person or queue must carry out the next operational task? | Assignment and fulfillment services |

Read [references/identity-and-organization.md](references/identity-and-organization.md) before changing user, employment, position, department, manager, group-sync, or organization models.

## Model identity and organization explicitly

Use stable internal `personId`, `employmentId`, `positionId`, and external identity subject IDs. Do not use mutable email as a primary key.

Represent employment and organization data with effective intervals, including:

- legal entity, country, location, employment type, status, start/end dates;
- job family, job profile, grade or level, and worker type;
- position, department, business unit, cost center, and budget unit;
- primary manager, optional approved functional/dotted-line relationships, and relationship purpose;
- location/site and remote-work attributes relevant to device fulfillment;
- source system, synchronization timestamp, and data confidence/verification status.

Treat job grade or employee level as a policy attribute, not an application role. Treat “manager” as a relationship at an effective date, not merely a permanent role.

Support matrix organizations, multiple employments, temporary assignments, acting managers, vacancies, contractors, transfers, terminated users, circular-data errors, and missing managers. Define which manager relationship drives approval; do not silently use any available manager edge.

## Use scoped RBAC plus trusted attributes and relationships

Use application roles for broad capabilities and scope assignments for where they apply. Evaluate trusted attributes and relationships when the action depends on department, location, warehouse, cost center, direct-report chain, request ownership, or task assignment.

A role assignment should identify:

```text
principalId
roleDefinitionId
scopeType and scopeId
effectiveFrom and effectiveTo
assignmentSource
delegationId when applicable
grantedBy and approval evidence
```

Support scopes such as tenant, legal entity, business unit, department, cost center, site, warehouse, catalog, request category, and individual request or task.

Use deny-by-default authorization that returns an auditable decision containing principal, action, resource, scope, matched assignments, relationship checks, separation-of-duty checks, and reason codes. Cache only with identity, assignments, relationships, resource version, and expiration in the cache key.

Read [references/roles-and-authorization.md](references/roles-and-authorization.md) before implementing role definitions, permissions, scopes, approval authority, delegation, or separation of duties.

## Use capability roles, not organization-specific titles

Start from stable capabilities and map each company's job titles or directory groups to them. A person may hold several roles at different scopes.

| Capability role | Accountable responsibility |
| --- | --- |
| Requester | Request hardware for self or an explicitly authorized person |
| Line Manager Approver | Confirm business need for an employee in the approved reporting relationship |
| Budget Owner / Cost Center Approver | Approve spend against a governed budget scope |
| IT Service Desk Agent | Triage, verify facts, and coordinate support without overriding policy |
| Policy Exception Approver | Decide authorized exceptions with evidence and reason |
| Security or Architecture Approver | Approve configured security, data, or platform exceptions |
| Procurement Buyer | Create or manage sourcing and purchase work after approval |
| Procurement Approver | Authorize procurement spend; keep separate from buyer when required |
| Inventory Controller / Warehouse Operator | Reserve, pick, receive, count, and release physical stock at a scoped location |
| Fulfillment Coordinator | Own the end-to-end fulfillment task and coordinate people, stock, shipment, and handover |
| IT Deployment Technician | Image, configure, enroll, label, and quality-check a device |
| IT Asset Custodian / Asset Manager | Maintain asset identity, assignment, lifecycle, warranty, and custody records |
| Logistics Coordinator / Courier | Collect, transport, deliver, and record shipment custody |
| Auditor | Inspect immutable lineage without operational mutation |
| Application Administrator | Configure the application without inheriting business approval authority |

For the “person in logistics,” use **Fulfillment Coordinator** when they own the overall delivery cycle, **Logistics Coordinator** when they arrange transport, **Inventory Controller/Warehouse Operator** when they handle stock, and **IT Asset Custodian** when they own asset records. Do not force one job title to cover all responsibilities.

## Resolve policy, spend, and device presentation separately

Build the user-facing catalog from three deterministic results:

1. **Policy eligibility** — resolve the case-pinned policy set and evaluate device classes, replacement cycle, accessory entitlement, caps, required evidence, and approval conditions.
2. **Financial position** — calculate committed, fulfilled, reserved, pending, refunded, and remaining amounts from an authoritative allowance or budget ledger using the correct period and currency.
3. **Catalog and availability** — filter approved offerings by security, compatibility, location, procurement status, price, and current inventory or lead time.

Return aligned options with reason codes and exact evidence, for example:

```text
eligible under policy
eligible but out of stock
eligible and requires purchase
eligible but exceeds remaining allowance
not eligible because replacement date has not been reached
needs review because facts or applicable policies conflict
```

Do not ask an LLM to subtract prior spend, calculate dates, select a policy release, or filter authorization. An explanation agent may describe the immutable results and exact policy evidence.

Show the employee their policy band, eligible categories, cap and period, committed/reserved/remaining amount, assigned device and lifecycle facts, available models, price, lead time, evidence requirements, and expected approval path. Do not expose internal policy or inventory data outside authorization scope.

## Generate an immutable approval plan

Build approval routing deterministically from the verified request, requester/beneficiary relationship, organization snapshot, policy decision, amount, cost center, category, exception status, security requirements, and stock/procurement route.

An approval plan must contain ordered or parallel typed steps, required role, required relationship or scope, candidate approvers, selection reason, quorum, separation-of-duty rule, due date, escalation rule, delegation rule, and source versions.

Resolve a specific approver at step activation and record the relationship snapshot used. Handle manager changes according to an explicit policy: continue with the original valid approver, re-resolve, or require review. Never silently substitute a different manager.

Typical conditional steps include:

- manager approval for business need;
- budget or cost-center approval above a configured threshold;
- policy-owner approval for exceptions;
- IT/security approval for nonstandard or privileged devices;
- procurement approval when purchase is required;
- no human approval for configured low-risk, in-policy accessories only when an approved rule explicitly permits straight-through processing.

Every approval action must be an authenticated, authorized, idempotent record with decision, reason, comments, evidence, task/revision version, timestamp, and delegation context. Rejection and material request changes invalidate downstream approvals according to deterministic rules.

## Make fulfillment a human-owned cycle

Create operational tasks after the necessary approvals. Every human-required task must be assigned to a specific authorized user or a scoped queue that an authorized user must claim.

Use fulfillment task states equivalent to:

```text
QUEUED -> CLAIMED -> IN_PROGRESS -> BLOCKED -> COMPLETED
                     |              |
                     -> REASSIGNED  -> CANCELLED
```

Record `assignedUserId`, `assignedQueueId`, `claimedBy`, role/scope used, due date, SLA, start/completion timestamps, blocker reason, reassignment history, and evidence. A service account may execute an integration command but cannot replace the accountable human for a physical or approval step.

Use the full cycle when applicable:

1. Validate approved request and reserve allowance/budget.
2. Choose the in-stock or procurement branch.
3. Reserve serialized or quantity stock atomically.
4. Assign an Inventory Controller to pick and release items.
5. Assign an IT Deployment Technician to configure devices when required.
6. Have the Asset Custodian register or validate serial, asset tag, warranty, condition, and intended assignee.
7. Assign a Fulfillment Coordinator to coordinate readiness, shipment, pickup, and user communication.
8. Assign a Logistics Coordinator/Courier when physical transport is required.
9. Capture handover with issued-by, delivered-by, received-by, time, location, asset identifiers, and condition.
10. Capture employee acceptance or a verified delivery exception.
11. For replacements, create and track old-device return, data-transfer, sanitization, inspection, disposition, and custody tasks.
12. Commit the allowance/spend and asset assignment only at the approved lifecycle point; release reservations on cancellation or failure.
13. Close the request only when required custody, inventory, asset, receipt, return, and financial records reconcile.

For purchased items, include requisition, procurement review, purchase authorization, order, supplier acknowledgment, receiving, inspection, inventory registration, and then the fulfillment steps. Keep procurement buyer, approver, receiver, and asset issuer separate when controls require it.

Read [references/approval-and-fulfillment.md](references/approval-and-fulfillment.md) before implementing approval plans, MAF workflows, task queues, inventory, procurement, logistics, handover, return, or closure.

## Use Microsoft Agent Framework as workflow orchestration

Model the binding process as an explicit typed MAF workflow. Do not create an approving “manager agent,” “procurement agent,” or “logistics agent” to impersonate human roles.

Use deterministic executors or services for:

- identity and authorization context;
- organization and reporting-line resolution;
- policy-set resolution and policy evaluation;
- current-asset, warranty, replacement-date, spend, and allowance calculations;
- catalog, price, security, compatibility, stock, and lead-time filtering;
- approval-plan construction and approver authorization;
- inventory reservation and release;
- procurement, asset, shipment, notification, and audit integrations;
- fulfillment task creation, assignment, claim, completion, and reconciliation.

Use agents for the LLM activities justified by the completed allocation matrix. Common qualified activities include conversational intake, candidate-fact extraction, grounded option explanation, approval-packet summarization, policy-authoring analysis, and interpretation of unstructured operational blockers. These are examples, not a mandatory agent list.

Permit a bounded autonomous case-coordination capability only when real cases have a durable goal, changing conditions, multiple safe next actions, significant manual coordination cost, and enforceable action limits. Contain it within a workflow stage. Give autonomy per tool action, not per agent name: read-only case observation or limited reminders may be automatic, while approvals, spend, purchase authorization, stock issuance, custody attestation, and policy overrides remain human-gated, deterministic, or prohibited. If known workflow rules cover the case adequately, use executors, timers, and queues instead.

Do not implement separate manager, procurement, warehouse, logistics, or asset agents merely because those people participate. They remain authenticated human roles unless their distinct business activities independently pass the LLM and agent-boundary tests.

Use MAF request/response human-in-the-loop for approvals and information requests. Use durable checkpoints for waits that may last hours or days. Persist authoritative approvals, tasks, custody, and request state in the domain database; MAF state contains continuation data, not the sole business record.

Use typed workflow branches equivalent to:

```text
authenticate
snapshot_identity_and_org
resolve_policy_set
evaluate_entitlement
calculate_financial_position
filter_catalog
collect_selection
revalidate
build_approval_plan
execute_human_approvals
reserve_or_procure
execute_human_fulfillment
handover_and_return
reconcile_and_close
explain_and_audit
```

Make every external callback validate workflow ID, task ID, expected revision, actor authorization, and idempotency key. Never resume a workflow from an untrusted chat response alone.

## Persist a normalized operational model

Use PostgreSQL as the transactional authority when it is the repository's established database. Keep identity-provider and HR data as synchronized, source-attributed projections; keep authoritative requests, role assignments, approval actions, financial ledgers, task ownership, assets, and custody records outside agent memory and Azure AI Search.

Use concepts equivalent to:

- `PrincipalIdentity`, `Person`, `Employment`, `Position`, `OrgUnit`, `ReportingRelationship`, and `OrganizationSnapshot`;
- `RoleDefinition`, `Permission`, `RoleAssignment`, `Delegation`, `ApprovalAuthority`, and `AuthorizationDecision`;
- `HardwareRequest`, `RequestBeneficiary`, `RequestItem`, `RequestFactSnapshot`, `PolicySetBinding`, and `EntitlementDecision`;
- `AllowanceAccount`, `AllowanceLedgerEntry`, `BudgetReservation`, and `SpendCommitment`;
- `CatalogOffering`, `DeviceModel`, `InventoryLocation`, `StockItem`, `StockReservation`, `Asset`, and `AssetAssignment`;
- `ApprovalPlan`, `ApprovalStep`, `ApprovalTask`, and immutable `ApprovalAction`;
- `ProcurementRequisition`, `PurchaseOrderReference`, and `ReceivingRecord`;
- `FulfillmentCase`, `FulfillmentTask`, `QueueAssignment`, `Shipment`, `CustodyEvent`, `HandoverReceipt`, `ReturnCase`, and `DispositionRecord`;
- append-only `AuditEvent`, `OutboxEvent`, and integration idempotency records.

Read [references/contracts-and-verification.md](references/contracts-and-verification.md) before creating schemas, APIs, migrations, audit events, or tests.

## Build management and operational workbenches

Provide authorized views for:

- organization hierarchy and effective manager chains;
- a person's employment attributes, role assignments, scopes, delegations, and policy-relevant facts;
- “why can this user perform this action?” authorization simulation;
- approval matrix, approver coverage, unresolved routes, self-approval, and separation-of-duty violations;
- request timeline with policy, financial, approval, procurement, fulfillment, custody, and return evidence;
- role-scoped manager, procurement, inventory, deployment, fulfillment, logistics, and asset queues;
- queue aging, SLA, blockers, workload, assignment, reassignment, and escalation;
- inventory reservation, serialized asset, shipment, handover, and return reconciliation;
- access reviews, expired assignments, stale delegations, orphaned users, and invalid reporting cycles.

Do not permit free-form editing of effective organization, approval, or role data without validation, versioning, source, authorization, and audit. Show effective dates and source of truth prominently.

## Migrate without weakening access

Use a measured cutover:

1. Inventory existing roles, groups, permissions, manager fields, user levels, approval checks, and UI assumptions.
2. Define the new canonical model and explicit mappings.
3. Add migrations and deterministic backfill with orphan/conflict reports.
4. Move authoritative writes to the new services.
5. Keep legacy models as read-only compatibility projections only when required.
6. Run shadow authorization and approval-plan comparison without changing outcomes.
7. Record mismatches by reason and resolve them before enabling enforcement.
8. Cut over by bounded capability or route with rollback controls.
9. Remove adapters only after dependency scans and production evidence show no remaining consumers.

Do not broaden access to preserve compatibility. When legacy meaning is ambiguous, fail closed and require mapping or review.

Test migrations from an empty database and representative populated data. Preserve user, request, approval, asset, and audit identifiers where semantics are compatible; never rewrite historical approvals.

## Verify the complete lifecycle

Test at least:

- employee versus role versus grade separation;
- direct, indirect, dotted-line, acting, missing, changed, and circular manager relationships;
- multiple departments, cost centers, locations, employments, and scoped role assignments;
- self-request, authorized request-for-another, manager self-approval, delegation, expiry, and separation of duties;
- accessory straight-through, standard in-stock replacement, exception, over-limit, out-of-stock, purchase, security approval, and rejection paths;
- exact policy-set binding, spend/reservation arithmetic, concurrency, currency/period boundaries, and cancellation release;
- queue assignment, human claim, reassignment, blocked work, SLA escalation, and unauthorized completion;
- serialized stock reservation races, procurement retries, receiving, configuration, asset assignment, shipment, handover, return, sanitization, and closure reconciliation;
- duplicate approval and fulfillment callbacks, durable resume, process restart, timeout, and compensation;
- cross-tenant/department/location access, forged identity context, prompt injection, unauthorized evidence, and sensitive telemetry;
- historical decisions, approvals, organization snapshots, and custody events remaining immutable after role or manager changes.

Do not claim completion from route tests alone. Run domain, authorization, policy, workflow, migration, concurrency, security, frontend, and deployed-integration tests relevant to the repository.

## Produce implementation artifacts

For architecture work, produce the relevant subset of:

1. Current-state dependency and write-path assessment.
2. Identity, employment, organization, role, scope, and relationship model.
3. Capability-role and permission matrix with company-title mappings.
4. Policy/financial/catalog alignment contracts.
5. Approval matrix, plan-generation rules, delegation, escalation, and separation of duties.
6. End-to-end MAF workflow with human approval and fulfillment tasks.
7. Procurement, inventory, asset, logistics, custody, return, and reconciliation design.
8. PostgreSQL schema, migrations, adapters, APIs, audit, outbox, and integrations.
9. User, approver, fulfillment, logistics, admin, and audit workbench design.
10. Security, resilience, observability, evaluation, migration, rollout, and rollback plan.

For implementation work:

- preserve repository conventions and installed dependency versions;
- implement domain contracts before provider adapters;
- keep authentication, organization, authorization, policy, finance, catalog, approval, fulfillment, and MAF modules separate;
- extend existing abstractions rather than adding parallel identity or workflow systems;
- implement a vertical slice from signed-in employee through eligible catalog, approval, human fulfillment, handover, and closure;
- add migrations, backfill reports, constraints, fixtures, and compatibility tests;
- run focused checks first and the complete relevant suite afterward;
- report exactly what was verified and what still requires real identity, procurement, inventory, or Azure resources.

## Current official references

Verify APIs and deployed capabilities through current official sources:

- Microsoft identity application authorization: https://learn.microsoft.com/entra/identity-platform/authorization-basics
- Implement application RBAC: https://learn.microsoft.com/entra/identity-platform/howto-implement-rbac-for-apps
- Microsoft Entra app roles: https://learn.microsoft.com/entra/identity-platform/howto-add-app-roles-in-apps
- Microsoft Graph manager relationship: https://learn.microsoft.com/graph/api/user-list-manager
- Microsoft Agent Framework workflows: https://learn.microsoft.com/agent-framework/workflows/
- MAF human-in-the-loop: https://learn.microsoft.com/agent-framework/workflows/human-in-the-loop
- MAF Durable Extension: https://learn.microsoft.com/agent-framework/integrations/durable-extension
- Azure Database for PostgreSQL: https://learn.microsoft.com/azure/postgresql/overview

Use current official documentation and the repository's pinned package documentation. Keep external systems behind typed adapters when real contracts are unavailable rather than fabricating integration code.
