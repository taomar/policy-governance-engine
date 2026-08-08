# Approval and human-owned fulfillment workflow

## Contents

1. Workflow principles
2. Request lifecycle
3. Approval-plan construction
4. Human approval execution
5. Fulfillment case and tasks
6. In-stock branch
7. Procurement branch
8. Device preparation and asset registration
9. Logistics and custody
10. Replacement return cycle
11. Financial and inventory reconciliation
12. Exceptions and compensation
13. Microsoft Agent Framework mapping
14. Operational workbenches

## Workflow principles

Keep the workflow explicit, durable, typed, and replay-safe. Separate:

- request and beneficiary facts;
- policy and entitlement decision;
- financial reservations and commitments;
- approval plan and human actions;
- procurement and inventory operations;
- fulfillment tasks and human ownership;
- asset and custody records;
- workflow continuation state;
- conversation history.

No status transition by itself proves that the underlying action occurred. Require the corresponding immutable evidence, authorized actor, expected version, and idempotency record.

## Request lifecycle

Use a lifecycle equivalent to:

```text
DRAFT
  -> SUBMITTED
  -> FACTS_VERIFIED
  -> POLICY_EVALUATED
  -> SELECTION_CONFIRMED
  -> APPROVAL_PENDING
  -> APPROVED
  -> SOURCING
  -> FULFILLING
  -> HANDOVER_PENDING
  -> RETURN_PENDING
  -> RECONCILING
  -> COMPLETED
```

Terminal or interrupting states may include:

```text
REJECTED
CANCELLED
EXPIRED
NEEDS_INFORMATION
NEEDS_POLICY_REVIEW
NO_APPROVAL_ROUTE
PROCUREMENT_BLOCKED
FULFILLMENT_BLOCKED
FAILED_REQUIRES_OPERATOR
```

Do not force all complexity into one enum. Track approval, sourcing, fulfillment, return, and financial substatus separately while maintaining validated aggregate transitions.

At submission, capture:

- requester and beneficiary identities and relationship;
- immutable request fact snapshot;
- organization snapshot;
- existing assigned assets and verified lifecycle/warranty facts;
- requested categories and business reason;
- delivery/pickup location;
- policy-set binding and entitlement decision;
- allowance/budget position;
- eligible offering snapshot and selected item;
- expected approval and fulfillment route.

Revalidate volatile facts before approvals or reservations according to explicit rules. A model-generated summary is never the authoritative request record.

## Approval-plan construction

Create an immutable, versioned plan:

```json
{
  "approvalPlanId": "plan-id",
  "requestId": "request-id",
  "planVersion": 1,
  "organizationSnapshotId": "snapshot-id",
  "policySetId": "policy-set-id",
  "entitlementDecisionId": "decision-id",
  "financialPositionVersion": "version",
  "selectedOfferingVersion": "version",
  "steps": [],
  "createdAt": "timestamp",
  "inputHash": "hash",
  "status": "pending|active|approved|rejected|superseded"
}
```

Each step contains:

```json
{
  "approvalStepId": "step-id",
  "sequenceGroup": 1,
  "executionMode": "sequential|parallel",
  "approvalType": "business_need|budget|exception|security|procurement",
  "requiredPermission": "approval.decide.business_need",
  "requiredRelationship": "primary_manager_for_business_need",
  "scopeType": "department",
  "scopeId": "department-id",
  "minimumApprovals": 1,
  "candidatePrincipalIds": [],
  "selectionRuleId": "rule-id",
  "separationRuleIds": [],
  "dueAt": "timestamp",
  "escalationRuleId": "rule-id",
  "delegationAllowed": true,
  "status": "pending"
}
```

Plan generation may use:

- manager relationship and business-need rule;
- amount and currency after normalized pricing;
- cost center and budget owner;
- accessory/device category;
- standard versus exception item;
- policy exception requirement;
- security or privileged-access characteristics;
- in-stock versus purchase route;
- legal entity, country, and procurement threshold;
- separation of duties and approver availability.

If a material request field, selected offering, price, policy set, beneficiary, cost center, or exception changes, create a new plan version and deterministically invalidate affected approvals. Preserve the old plan.

## Human approval execution

Create an `ApprovalTask` for each active step. Resolve candidate approvers through current approved role, scope, authority, relationship, delegation, and separation rules.

Task lifecycle:

```text
PENDING_ASSIGNMENT -> ASSIGNED -> VIEWED -> DECIDED
                         |          |
                         -> DELEGATED
                         -> ESCALATED
                         -> EXPIRED
                         -> CANCELLED
```

Every decision records:

- approval task, step, plan, request, and revision IDs;
- authenticated actor and effective principal if delegated;
- authorization decision ID;
- `approve`, `reject`, `request_information`, or configured outcome;
- structured reason code and optional comment;
- evidence viewed or supplied;
- expected task version;
- timestamp and idempotency key.

Manager approval confirms business need; it does not reinterpret policy or grant application access. Budget approval confirms spend authority; it does not make an ineligible item eligible. Procurement approval permits governed purchase; it does not replace inventory or asset custody work.

Use request-for-information to pause and resume the workflow. Material new facts must be verified and may require policy re-evaluation and a new approval plan.

## Fulfillment case and tasks

Create a `FulfillmentCase` after approvals and required reservations:

```json
{
  "fulfillmentCaseId": "case-id",
  "requestId": "request-id",
  "requestItemId": "item-id",
  "route": "in_stock|procurement|transfer|exception",
  "sourceLocationId": "location-id-or-null",
  "destinationLocationId": "location-id",
  "coordinatorQueueId": "queue-id",
  "coordinatorUserId": null,
  "status": "queued|in_progress|blocked|handover_pending|return_pending|reconciling|completed|cancelled",
  "version": 1
}
```

The **Fulfillment Coordinator** is accountable for progress and coordination, but does not automatically receive warehouse, deployment, procurement, or asset permissions. Create specialist tasks as required.

Use a common task contract:

```json
{
  "fulfillmentTaskId": "task-id",
  "fulfillmentCaseId": "case-id",
  "taskType": "reserve|pick|configure|quality_check|register_asset|ship|deliver|handover|collect_return|sanitize|inspect|reconcile",
  "requiredPermission": "inventory.pick",
  "requiredRoleCodes": ["inventory_controller"],
  "scopeType": "warehouse",
  "scopeId": "warehouse-id",
  "assignedQueueId": "queue-id",
  "assignedUserId": null,
  "claimedBy": null,
  "status": "queued",
  "dueAt": "timestamp",
  "predecessorTaskIds": [],
  "requiredEvidence": [],
  "version": 1
}
```

Queue membership is not sufficient to complete a task. On claim and completion, evaluate current role/scope and separation rules. Record task assignment history as append-only events.

Support explicit blocker reasons such as no stock, damaged stock, device configuration failure, missing address, beneficiary unavailable, procurement delay, policy decision expired, or old device not returned.

## In-stock branch

Use this sequence when an approved offering is in stock:

1. Create a financial/allowance reservation if required.
2. Reserve quantity or a serialized stock candidate atomically.
3. Create a pick task for the warehouse/location queue.
4. Have an Inventory Controller claim, scan, and pick the item.
5. Record serial, asset tag if present, quantity, condition, and pick evidence.
6. Create device preparation and asset tasks when required.
7. Create pickup or shipment tasks based on destination.
8. Record handover and acceptance.
9. Create return tasks for replacement devices.
10. Reconcile inventory, asset assignment, budget/allowance, custody, and request status.

Use a reservation with expiration, version, and idempotency key. Prevent two requests from reserving the same serialized item. If reservation expires, revalidate approval, price, policy, and stock before selecting another item.

Do not let the model choose a specific serial number.

## Procurement branch

Use this branch when no approved stock can satisfy the request and policy permits purchase:

1. Confirm purchase route and financial reservation.
2. Create an approved requisition from immutable request and offering facts.
3. Assign a Procurement Buyer to source or create the external order.
4. Add Procurement Approver steps according to amount, category, supplier, and legal-entity controls.
5. Record purchase-order reference and supplier acknowledgment through idempotent integration.
6. Track expected delivery and exceptions.
7. Assign receiving work to an authorized receiving/warehouse user.
8. Capture quantity, serials, condition, discrepancies, and receiving evidence.
9. Register received stock and assets.
10. Continue through preparation, logistics, handover, return, and reconciliation.

Do not fabricate supplier, price, PO, or receipt data when the procurement integration is mocked. Mark mock data and preserve the same typed contracts.

Separate requester, buyer, purchase approver, receiver, and issuer as configured. A procurement service account may transmit the order but the human actions remain attributable.

## Device preparation and asset registration

Assign **IT Deployment Technician** tasks for required operations such as:

- hardware inspection;
- approved image or operating-system installation;
- device management enrollment;
- security configuration;
- approved application bundle;
- encryption and update verification;
- asset label placement;
- quality check and readiness evidence.

Do not have an LLM execute configuration commands or attest compliance without verified tooling results.

Assign **IT Asset Custodian/Asset Manager** tasks for:

- asset identity and serial validation;
- asset tag registration;
- ownership/legal entity and site;
- model, warranty, acquisition, and lifecycle dates;
- assignment state;
- relationship to request and beneficiary;
- previous asset replacement relationship;
- custody and return status.

Use explicit asset states such as `received`, `in_stock`, `reserved`, `in_preparation`, `ready`, `in_transit`, `assigned`, `return_due`, `returned`, `quarantined`, `retired`, and `disposed`. Validate transitions.

## Logistics and custody

Use **Logistics Coordinator** for transport planning and **Courier** or external carrier identity for execution when relevant. Use **Fulfillment Coordinator** for overall coordination.

Create shipment records with:

- origin and destination;
- shipment method and carrier reference;
- package/asset identifiers;
- assigned coordinator or integration;
- dispatch, expected delivery, and delivery times;
- custody events;
- delivery exception and proof;
- recipient identity and verification method.

Record custody as an append-only chain:

```json
{
  "custodyEventId": "event-id",
  "assetId": "asset-id",
  "fromCustodianType": "warehouse|person|carrier|site",
  "fromCustodianId": "id",
  "toCustodianType": "carrier|person|site",
  "toCustodianId": "id",
  "eventType": "release|pickup|transfer|delivery|handover|return",
  "performedBy": "principal-id",
  "occurredAt": "timestamp",
  "locationId": "location-id",
  "condition": "condition-code",
  "evidenceIds": [],
  "idempotencyKey": "key"
}
```

The employee's handover receipt must identify the actual beneficiary or authorized receiver. The issuer, carrier, and recipient are different identities where applicable.

Do not close a lost/damaged shipment automatically. Create an exception task, preserve custody evidence, and apply approved incident procedures.

## Replacement return cycle

For replacement requests, determine return requirements through the policy decision. Do not assume every replacement requires immediate return or that a return can be waived by a fulfillment user.

When required:

1. create a `ReturnCase` tied to the previous asset and replacement request;
2. assign return coordination;
3. arrange pickup or drop-off;
4. record employee release and carrier/warehouse custody;
5. receive and inspect condition and accessories;
6. perform approved data backup/transfer before sanitization when required;
7. record sanitization evidence through verified tools and a human accountable task;
8. classify repair, redeploy, warranty, quarantine, recycling, or disposal route;
9. update asset and financial records;
10. escalate missing or damaged returns under approved policy.

Keep issuance and return cases linked but independently resumable. Do not block an emergency replacement unless policy explicitly requires it; use a return deadline and follow-up workflow when allowed.

## Financial and inventory reconciliation

Use append-only ledgers or transaction records for:

- policy allowance reservation;
- cost-center budget reservation;
- purchase commitment;
- fulfillment commitment;
- cancellation release;
- return credit or adjustment when approved;
- final expenditure.

Use decimal money, explicit currency, rate source/version if conversion is allowed, and policy period. Do not count the same request in pending, reserved, and committed totals twice.

At closure, require deterministic reconciliation:

```text
approved request item
== fulfilled catalog/asset item
== inventory issue or purchase receipt
== asset assignment and custody
== financial commitment
== employee receipt
== required old-asset return outcome
```

If reconciliation fails, keep the request open in `RECONCILING` and assign an authorized task. Do not let an agent explain away mismatched records.

## Exceptions and compensation

Define compensation for failures after each side effect:

| Failure | Compensation candidate |
| --- | --- |
| Approval rejected | Cancel inactive downstream tasks and release reservations |
| Stock reservation expired | Release and re-source after revalidation |
| Picked item damaged | Quarantine item, reverse reservation, select approved alternative |
| Procurement cancelled | Release budget commitment and reopen sourcing |
| Configuration failed | Block asset, create technician/repair task |
| Shipment lost | Freeze custody state and start incident/claim workflow |
| Employee refuses handover | Return item to controlled custody and release/adjust records |
| Request cancelled after issue | Start governed return rather than deleting assignment |

Compensation must be idempotent and preserve history. Do not delete approvals, procurement references, stock movements, assets, or custody events.

Route policy exceptions to the authorized policy owner with exact decision evidence. Route operational exceptions to the appropriate manager, inventory, procurement, logistics, security, or asset role. Keep the two kinds distinct.

## Microsoft Agent Framework mapping

Use typed messages equivalent to:

```text
RequestSubmitted
IdentityOrganizationSnapshotReady
EntitlementDecisionReady
CatalogOptionsReady
SelectionConfirmed
ApprovalPlanReady
ApprovalResponseReceived
SourcingRouteSelected
FulfillmentTaskCompleted
HandoverConfirmed
ReturnOutcomeRecorded
ReconciliationCompleted
```

Use executors for deterministic services and MAF request/response for human waits. Persist workflow checkpoint IDs with the domain case, but do not treat checkpoint payload as the business audit.

For each wait:

- create the domain task first;
- send notification with a task reference;
- pause the workflow;
- authenticate the responding actor;
- authorize the exact task action;
- validate expected task/workflow revision;
- persist the immutable action idempotently;
- resume using trusted IDs;
- handle timeout, reassignment, escalation, cancellation, and duplicate responses.

Avoid one agent per department or human role. A conversation agent can help the requester; an explanation agent can help approvers and operators understand immutable packets. Human roles remain people and task queues.

## Operational workbenches

### Approver workbench

Show beneficiary, requester relationship, business reason, policy decision, exact evidence, current asset, replacement/warranty facts, selected offering, price, allowance/budget, organization snapshot, requested exception, prior steps, conflicts, and required decision.

### Fulfillment coordinator workbench

Show end-to-end case, approvals, sourcing route, reservations, specialist tasks, owners, SLA, blockers, shipment, handover, return, and reconciliation. Permit assignment only within actor scope.

### Inventory workbench

Show scoped reservations, locations, bins, serialized items, pick/receive tasks, scans, condition, discrepancies, and audit.

### Deployment workbench

Show assigned devices, required configuration profile, verified tooling results, quality checklist, blockers, and readiness handoff.

### Logistics workbench

Show origin/destination, packages/assets, carrier, pickup/delivery windows, custody chain, recipient verification, and exceptions.

### Asset workbench

Show lifecycle, warranty, assignment, custody, replacement, return, sanitization, repair, and disposition.

Every workbench must enforce tenant, role, scope, relationship, task assignment, and data sensitivity server-side. Show why the user can act and which role/scope they are using.
