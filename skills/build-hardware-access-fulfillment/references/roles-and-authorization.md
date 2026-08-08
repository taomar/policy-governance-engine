# Roles, scopes, authorization, and approval authority

## Contents

1. Authorization model
2. Role and permission contracts
3. Capability catalog
4. Scope model
5. Relationship checks
6. Approval authority
7. Delegation
8. Separation of duties
9. Authorization decisions
10. Identity-provider integration
11. Administrative review

## Authorization model

Use a layered application authorization model:

```text
authenticated principal
  + active role assignments
  + resource/action scope
  + trusted organization attributes
  + verified relationships
  + delegation
  + separation-of-duty constraints
  + resource state
= authorization decision
```

Use roles for stable capability groupings. Use attributes and relationships only from trusted stores. Use policy decisions for entitlement, not application permissions.

Evaluate authorization in a central domain service or policy-enforcement component, then call it from every route, command handler, query, workflow callback, background task, and tool adapter. UI visibility is convenience, not enforcement.

## Role and permission contracts

```json
{
  "roleDefinitionId": "role-id",
  "code": "fulfillment_coordinator",
  "displayName": "Fulfillment Coordinator",
  "description": "Coordinate authorized hardware fulfillment",
  "permissionCodes": ["fulfillment.read", "fulfillment.assign", "fulfillment.coordinate"],
  "allowedScopeTypes": ["tenant", "legal_entity", "site", "warehouse"],
  "riskClass": "standard|privileged",
  "assignable": true,
  "version": 1
}
```

```json
{
  "roleAssignmentId": "assignment-id",
  "tenantId": "tenant-id",
  "principalId": "principal-id",
  "roleDefinitionId": "role-id",
  "scopeType": "site",
  "scopeId": "site-id",
  "effectiveFrom": "timestamp",
  "effectiveTo": null,
  "source": "entra_app_role|entra_group_mapping|application|migration",
  "externalAssignmentId": null,
  "grantedBy": "principal-id",
  "approvalId": "approval-id",
  "version": 1
}
```

Keep permission codes stable and implementation-focused. Display labels and company job titles can change without changing permission semantics.

Avoid role explosion. Do not create one role per department, manager, warehouse, or policy band; use scoped assignments.

## Capability catalog

Define the smallest permissions required. Adapt to the repository while preserving boundaries.

### Request and self-service

```text
request.create.self
request.create.for_other
request.read.self
request.read.scoped
request.modify.own_draft
request.cancel.own
catalog.read.eligible
decision.read.own
```

### Manager and business approval

```text
approval.read.assigned
approval.decide.business_need
approval.decide.budget
approval.decide.exception
approval.decide.security
approval.delegate
approval.escalate
```

Possessing a permission does not make every task approvable. The actor must also match the step's required relationship/scope and separation rules.

### Service desk and policy operations

```text
request.triage
request.request_information
request.correct_verified_fact
policy_decision.read.scoped
policy_exception.prepare
```

Do not grant service desk users the ability to alter policy releases or approve exceptions unless separately assigned.

### Procurement

```text
procurement.requisition.create
procurement.requisition.read.scoped
procurement.requisition.modify
procurement.purchase.approve
procurement.order.record
procurement.receiving.read
```

Keep buyer and procurement approver permissions distinct.

### Inventory and warehouse

```text
inventory.read.scoped
inventory.reserve
inventory.pick
inventory.release
inventory.receive
inventory.adjust
inventory.count
inventory.record_condition
```

Require stronger controls for inventory adjustments than ordinary pick/release work.

### Fulfillment, deployment, logistics, and assets

```text
fulfillment.read.scoped
fulfillment.assign
fulfillment.claim
fulfillment.coordinate
fulfillment.complete_step
device.prepare
device.quality_check
shipment.create
shipment.update_custody
shipment.confirm_delivery
asset.register
asset.assign
asset.transfer
asset.record_warranty
asset.record_return
asset.record_sanitization
asset.dispose
```

Restrict each capability to appropriate task type, site, warehouse, asset, or request scope.

### Administration and audit

```text
role_definition.read
role_assignment.read
role_assignment.manage
organization.read.scoped
organization_override.manage
approval_matrix.manage
queue.manage
configuration.manage
audit.read.scoped
authorization.simulate
```

None of these implies business approval.

## Scope model

Represent scopes as typed nodes and containment rules. Typical scopes:

```text
tenant
legal_entity
business_unit
department
cost_center
site
warehouse
catalog
request_category
request
fulfillment_case
task
```

Define containment explicitly, for example a site may contain warehouses, but a department does not automatically contain a cost center unless approved organizational data says so.

Evaluate a role assignment against a resource through a trusted resource-scope projection. Do not accept the requested resource's department or location from client-supplied JSON without loading the authoritative record.

For cross-scope work, require an assignment covering every material resource or a purpose-built cross-scope role.

## Relationship checks

Some permissions require a relationship:

```text
requester is beneficiary
requester is authorized assistant for beneficiary
approver is beneficiary's primary manager for business_need_approval
approver owns request cost center
fulfillment user is assigned to task
inventory user is assigned to inventory location
asset custodian owns beneficiary's legal entity or site
auditor scope contains request tenant/legal entity
```

Evaluate relationship as of the configured event time. Store the relationship ID/path in the authorization and approval record.

Do not infer authorization from an agent's statement that “the user is my direct report.”

## Approval authority

Model approval authority separately from ordinary role assignments when thresholds, categories, legal entities, or cost centers matter:

```json
{
  "approvalAuthorityId": "authority-id",
  "principalId": "principal-id-or-null",
  "roleDefinitionId": "budget_owner-role-id",
  "authorityType": "business_need|budget|exception|security|procurement",
  "scopeType": "cost_center",
  "scopeId": "cost-center-id",
  "categories": ["laptop", "accessory"],
  "currency": "SAR",
  "minimumAmount": null,
  "maximumAmount": "50000.00",
  "effectiveFrom": "timestamp",
  "effectiveTo": null,
  "approvalEvidenceId": "evidence-id",
  "version": 1
}
```

An approval step requires both the permission and matching authority/relationship. Resolve candidates deterministically and return `no_authorized_approver` if none exists.

Do not let an approver raise their own authority threshold or modify the approval plan they are deciding.

## Delegation

Use explicit, time-bounded delegation:

```json
{
  "delegationId": "delegation-id",
  "delegatorPrincipalId": "principal-id",
  "delegatePrincipalId": "principal-id",
  "capabilities": ["approval.decide.business_need"],
  "scopeType": "department",
  "scopeId": "department-id",
  "effectiveFrom": "timestamp",
  "effectiveTo": "timestamp",
  "reason": "approved leave coverage",
  "approvedBy": "principal-id",
  "status": "active|revoked|expired"
}
```

Require the delegator to possess delegable authority, the delegate to meet required qualifications, and the delegation not to violate separation of duties. Record both identities on every delegated action.

Do not delegate:

- application administration automatically with manager approval;
- authority beyond the delegator's scope or amount;
- nondelegable security or policy-exception powers;
- fulfillment completion to an unauthorized location;
- authority indefinitely without review.

## Separation of duties

Represent incompatible action pairs or lifecycle combinations as deterministic rules. Typical controls include:

| Action already performed | Incompatible action when configured |
| --- | --- |
| Request for self | Approve business need, budget, exception, or procurement |
| Prepare policy exception | Solely approve the same exception |
| Create purchase requisition | Solely approve the same purchase |
| Approve purchase | Confirm receiving alone above controlled thresholds |
| Adjust inventory | Solely approve/reconcile the same adjustment |
| Pick device | Confirm final warehouse count for the same transaction |
| Issue asset | Confirm recipient acceptance on behalf of employee |
| Configure role assignment | Approve own privileged assignment |

Apply configured rules by request, item, transaction, asset, and task. Do not block legitimate low-risk workflows by assuming every pair is universally incompatible; store the organization's approved matrix.

If a conflict is detected, route to an alternative authorized user or return a review state. Do not silently skip the step.

## Authorization decisions

Use a typed output:

```json
{
  "authorizationDecisionId": "decision-id",
  "principalId": "principal-id",
  "action": "fulfillment.complete_step",
  "resourceType": "fulfillment_task",
  "resourceId": "task-id",
  "decision": "allow|deny|needs_review",
  "reasonCodes": [],
  "matchedRoleAssignmentIds": [],
  "matchedAuthorityIds": [],
  "matchedDelegationIds": [],
  "relationshipEvidenceIds": [],
  "separationChecks": [],
  "evaluatedAt": "timestamp",
  "inputVersionHash": "hash"
}
```

Return deny without disclosing sensitive facts the principal cannot access. Persist binding or privileged decisions; log ordinary read decisions according to risk and volume.

Use a single command boundary:

```text
authorize(actor_context, action, resource_reference, purpose, as_of)
```

Load trusted resource and relationship data inside the authorization boundary. Do not let callers construct a favorable authorization context.

## Identity-provider integration

Use configured app roles or approved group-to-role mappings for broad application capabilities. Keep detailed department, warehouse, cost-center, relationship, delegation, and task scopes in the domain authorization model when they cannot be represented safely in identity tokens.

Validate issuer, audience, tenant, subject, signature, lifetime, and required authentication context. Do not trust token display fields as current HR facts.

Account for stale tokens and role revocation. Privileged mutations should evaluate current assignments or use a short, governed cache rather than rely indefinitely on sign-in-time claims.

For local/demo authentication, implement the same `ActorContext` and authorization contracts with seeded identities. Do not add bypasses that disappear only by convention in production.

## Administrative review

Provide authorized tools to identify:

- users with no app access or excessive access;
- roles with unused or overly broad permissions;
- assignments without scope, source, approval, or expiry;
- duplicate and conflicting assignments;
- privileged role combinations;
- expired but cached access;
- unavailable approvers and uncovered scopes;
- delegations near expiry or outside policy;
- users who can approve, purchase, issue, and receive the same request;
- queues with no eligible members;
- authorization denials and shadow-mode mismatches.

Make role and approval simulations deterministic and explainable. A simulator must not mutate assignments or reveal data outside the operator's review scope.
