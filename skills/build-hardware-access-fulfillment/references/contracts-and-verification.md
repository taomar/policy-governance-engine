# Domain contracts, migration, and verification

## Contents

1. Contract principles
2. Request and beneficiary
3. Policy and entitlement
4. Financial position
5. Catalog presentation
6. Approval and work ownership
7. Audit and events
8. Migration contracts
9. Test personas and scenarios
10. Authorization tests
11. Workflow and fulfillment tests
12. Resilience and security tests
13. Definition of done

## Contract principles

Use typed, versioned contracts and trusted references. Adapt naming to repository conventions without losing:

- tenant and stable identity IDs;
- request and beneficiary separation;
- effective-date and source versions;
- case-pinned organization snapshot and policy set;
- policy eligibility separate from spend and availability;
- human actor separate from service executor;
- immutable approvals, custody, and ledger entries;
- idempotency and optimistic concurrency;
- reason codes and exact evidence.

Use UTC instants for events, explicit local dates for policy/employment boundaries, decimal money, ISO currency, typed units, and canonical hashes.

## Request and beneficiary

```json
{
  "hardwareRequestId": "request-id",
  "tenantId": "tenant-id",
  "requesterPersonId": "requester-id",
  "beneficiaryPersonId": "beneficiary-id",
  "requesterRelationship": "self|manager|assistant|service_desk|other_authorized",
  "requesterAuthorizationDecisionId": "authorization-id",
  "requestType": "new_hire|replacement|accessory|repair|exception|other",
  "businessReason": "user supplied text",
  "deliveryLocationId": "location-id",
  "requestFactSnapshotId": "fact-snapshot-id",
  "organizationSnapshotId": "org-snapshot-id",
  "policySetId": "policy-set-id",
  "status": "submitted",
  "version": 1,
  "createdAt": "timestamp"
}
```

Do not trust requester relationship from the request payload. Resolve and authorize it server-side.

Use a separate item contract:

```json
{
  "requestItemId": "item-id",
  "hardwareRequestId": "request-id",
  "category": "laptop|monitor|keyboard|mouse|headset|dock|phone|other",
  "quantity": 1,
  "selectedOfferingId": null,
  "selectedOfferingVersion": null,
  "replacementAssetId": null,
  "requiredBy": null,
  "status": "requested",
  "version": 1
}
```

## Policy and entitlement

Keep the deterministic policy output distinct:

```json
{
  "entitlementDecisionId": "decision-id",
  "requestId": "request-id",
  "requestItemId": "item-id",
  "policySetId": "policy-set-id",
  "organizationSnapshotId": "org-snapshot-id",
  "verifiedFactSnapshotId": "facts-id",
  "decision": "eligible|not_eligible|needs_information|conflict|needs_review",
  "eligibleDeviceClasses": ["standard_laptop"],
  "eligibleAccessoryClasses": [],
  "maximumAmount": {"amount": "6000.00", "currency": "SAR"},
  "entitlementPeriod": {"type": "rolling_years", "value": 3},
  "earliestReplacementDate": "date-or-null",
  "returnRequired": true,
  "requiredEvidence": [],
  "requiredApprovalTypes": ["business_need"],
  "matchedRuleIds": [],
  "evidenceRefs": [
    {"policyReleaseId": "release-id", "clauseId": "clause-id"}
  ],
  "reasonCodes": [],
  "evaluatedAt": "timestamp",
  "decisionHash": "hash"
}
```

Do not include stock or current spend in the pure policy result unless the approved policy rule explicitly uses that fact. The orchestration combines outputs without merging their authority.

## Financial position

Use append-only ledger entries:

```json
{
  "allowanceLedgerEntryId": "entry-id",
  "allowanceAccountId": "account-id",
  "requestItemId": "item-id",
  "entryType": "reserve|commit|release|adjust|refund",
  "amount": "1000.00",
  "currency": "SAR",
  "policyPeriodId": "period-id",
  "effectiveAt": "timestamp",
  "reversesEntryId": null,
  "authorizedBy": "principal-or-service-id",
  "authorizationDecisionId": "authorization-id",
  "idempotencyKey": "key"
}
```

Return a calculated position:

```json
{
  "financialPositionId": "position-id",
  "accountId": "account-id",
  "policyPeriodId": "period-id",
  "cap": {"amount": "6000.00", "currency": "SAR"},
  "committed": {"amount": "2000.00", "currency": "SAR"},
  "reserved": {"amount": "1000.00", "currency": "SAR"},
  "pendingUnreserved": {"amount": "0.00", "currency": "SAR"},
  "remaining": {"amount": "3000.00", "currency": "SAR"},
  "ledgerVersion": "version",
  "calculatedAt": "timestamp"
}
```

Use database locking or another proven concurrency mechanism when reserving funds. Assert that cap minus committed minus active reserved equals remaining under the defined accounting rules.

## Catalog presentation

Return options as aligned facts:

```json
{
  "catalogOptionId": "option-id",
  "offeringId": "offering-id",
  "offeringVersion": "version",
  "deviceClass": "standard_laptop",
  "modelId": "model-id",
  "price": {"amount": "4500.00", "currency": "SAR"},
  "policyAlignment": "eligible|not_eligible|needs_review",
  "financialAlignment": "within_remaining|over_remaining|unknown",
  "availability": "in_stock|purchase_required|backorder|unavailable",
  "availableQuantity": null,
  "estimatedLeadTime": null,
  "locationId": "location-id",
  "securityCompatibility": "approved|exception_required|not_approved",
  "requiredApprovalTypes": [],
  "reasonCodes": [],
  "evidenceRefs": []
}
```

Use a catalog snapshot or version so the selection can be revalidated. Do not promise a specific serial until inventory reservation succeeds.

## Approval and work ownership

Use a typed approval response command:

```json
{
  "approvalTaskId": "task-id",
  "expectedTaskVersion": 3,
  "actorPrincipalId": "from-auth-context",
  "decision": "approve|reject|request_information",
  "reasonCode": "code",
  "comment": null,
  "evidenceIds": [],
  "idempotencyKey": "key"
}
```

Ignore a client-supplied actor ID; derive it from authentication and reject mismatches.

Use a fulfillment completion command:

```json
{
  "fulfillmentTaskId": "task-id",
  "expectedTaskVersion": 2,
  "completionCode": "picked|configured|shipped|delivered|returned|other",
  "assetIds": [],
  "stockItemIds": [],
  "custodyEventInputs": [],
  "evidenceIds": [],
  "condition": null,
  "notes": null,
  "idempotencyKey": "key"
}
```

Validate the task assignee/claim, role, scope, predecessor completion, resource state, serialized identifiers, and evidence before transition.

Queue assignment should include:

```json
{
  "queueId": "queue-id",
  "queueType": "inventory|deployment|fulfillment|logistics|asset|procurement",
  "scopeType": "site",
  "scopeId": "site-id",
  "membershipRule": "governed-rule-id",
  "active": true
}
```

Do not store only an array of user IDs on a queue. Resolve eligible members through current role assignments and scope; allow governed explicit memberships where necessary.

## Audit and events

Record append-only domain events equivalent to:

```text
HardwareRequestSubmitted
OrganizationSnapshotCaptured
PolicySetBound
EntitlementEvaluated
FinancialPositionCalculated
CatalogSelectionConfirmed
ApprovalPlanCreated
ApprovalTaskAssigned
ApprovalDecisionRecorded
BudgetReserved
StockReserved
ProcurementRequested
ItemReceived
FulfillmentTaskClaimed
DevicePrepared
AssetRegistered
ShipmentDispatched
CustodyTransferred
HandoverAccepted
ReturnReceived
AssetSanitized
FinancialReconciled
RequestCompleted
```

Every event should include tenant, aggregate ID, event ID, actor or service identity, correlation/causation IDs, occurred time, schema version, and sanitized typed payload.

Operational telemetry is not the immutable audit record. Avoid logging policy documents, employee facts, shipping details, or tokens by default.

Use a transactional outbox for events that drive external integrations. Consumers must be idempotent and record external correlation IDs.

## Migration contracts

Before migration, produce mappings for:

- legacy user ID to `Person` and `PrincipalIdentity`;
- legacy role enum/string to `RoleDefinition` and scoped `RoleAssignment`;
- group membership to approved role mappings;
- department/manager fields to effective-dated organization records;
- grade/level fields to employment policy attributes;
- legacy approval status to plan, step, task, and immutable action lineage where evidence permits;
- logistics or fulfillment status to a case and human-owned task;
- existing asset/inventory IDs to canonical assets and stock records.

Classify every backfill as:

```text
exact mapping
derived deterministic mapping
ambiguous and requires review
orphaned
unsupported legacy state
```

Do not fabricate individual approvers or fulfillment users for historical records. Preserve the legacy evidence and mark unknown actor lineage explicitly.

Add constraints only after backfill reports are reviewed, then prevent new invalid writes. Keep a reversible migration plan, but never downgrade by deleting newly captured audit evidence.

## Test personas and scenarios

Create stable, synthetic personas such as:

- standard employee with no operational roles;
- manager with direct reports in one department;
- matrix manager who is not the business-need approver;
- acting manager with expiring delegation;
- budget owner for one cost center;
- IT service desk agent;
- procurement buyer and separate procurement approver;
- inventory controller scoped to Warehouse A;
- fulfillment coordinator scoped to KSA sites;
- deployment technician scoped to one site;
- asset custodian scoped to one legal entity;
- logistics coordinator and external carrier integration;
- application administrator with no business approval authority;
- auditor with read-only scope;
- contractor with sponsor and restricted catalog;
- terminated user and disabled account.

Keep role assignments, manager relationships, policy attributes, and entitlements independent so tests catch accidental conflation.

## Authorization tests

Test:

- token issuer/audience/tenant/subject validation;
- mutable email or display name cannot impersonate identity;
- role assignment scope containment;
- expired, future, revoked, and stale assignments;
- direct versus indirect versus dotted-line manager;
- manager outside effective interval;
- request-for-other relationship;
- cross-department, cost-center, site, warehouse, legal-entity, and tenant denial;
- queue member who has not claimed a task;
- task assignee losing role before completion;
- valid and invalid delegation;
- self-approval and every configured separation pair;
- admin unable to approve without business authority;
- senior grade unable to gain operational permission;
- policy entitlement unable to grant API access;
- authorization cache invalidation;
- consistent route, service, query, workflow, and tool enforcement;
- denial response does not leak sensitive resource facts.

Use table-driven tests over `principal × action × resource × scope × relationship × time × resource state`.

## Workflow and fulfillment tests

Test complete vertical slices:

1. In-policy accessory, in stock, configured straight-through path.
2. Standard laptop replacement with manager approval and old-device return.
3. Eligible device out of stock requiring procurement and receiving.
4. Over-limit selection requiring budget or exception approval.
5. Nonstandard device requiring security and policy exception review.
6. Manager unavailable with valid delegation.
7. Manager is requester and alternate routing is required.
8. No authorized approver exists.
9. Stock race for the same serialized device.
10. Picked device fails quality check and requires compensation.
11. Shipment delayed, lost, or delivered to an authorized alternate.
12. Employee refuses handover or fails to return old device.
13. Request cancellation before approval, after reservation, after purchase, and after issue.
14. Organization, price, policy, or role changes while workflow waits.

For each path assert:

- exact policy set and evidence;
- correct financial arithmetic and reservation release;
- correct approval plan and human actors;
- no unauthorized transition;
- every human task assigned/claimed visibly;
- inventory, procurement, asset, custody, receipt, return, and audit consistency;
- workflow restart and duplicate callback safety;
- historical snapshots and actions remain immutable.

## Resilience and security tests

Inject failures in:

- identity and organization synchronization;
- policy resolver and evidence retrieval;
- database transactions;
- MAF checkpoint save/resume;
- notification delivery;
- budget/allowance reservation;
- inventory reservation;
- procurement submission and callback;
- asset registration;
- shipment tracking;
- handover and return callbacks;
- outbox publishing.

Verify bounded retry, idempotency, compensation, dead-letter/operator queues, reconciliation, and no duplicate physical or financial side effects.

Security tests must include:

- forged actor, tenant, role, manager, beneficiary, or task assignment in request bodies;
- prompt injection attempting to approve or change roles;
- horizontal and vertical privilege escalation;
- duplicate/replayed approvals and task completions;
- stale expected versions;
- unauthorized policy, price, inventory, address, and audit access;
- sensitive prompt/log/trace/notification leakage;
- service principal acting as a human approver;
- malicious external procurement or carrier callback;
- mass assignment and over-posting;
- insecure direct object references.

## Definition of done

Do not claim the restructuring complete until:

- identity, employment, organization, roles, policy, approval authority, and work ownership are distinct;
- every authoritative source and synchronization rule is explicit;
- all privileged operations enforce centralized server-side authorization;
- manager and approver routes are effective-dated, scoped, and explainable;
- user grade affects policy only through approved rules;
- entitlement, financial position, catalog eligibility, and stock availability remain distinct;
- approval plans and actions are immutable and separation rules are tested;
- every physical fulfillment stage has an accountable user or claimable authorized queue;
- inventory, procurement, asset, custody, return, and finance reconciliation is deterministic;
- MAF pauses/resumes safely without becoming the sole business record;
- migrations and populated-data backfill reports are tested;
- shadow authorization/approval comparisons show accepted results;
- security, concurrency, resilience, and end-to-end tests pass;
- real integration behavior and unverified assumptions are reported honestly.
