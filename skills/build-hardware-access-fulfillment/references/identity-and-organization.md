# Identity and organization model

## Contents

1. Authority map
2. Core entities
3. Identity linkage
4. Employment and position
5. Organization units
6. Reporting relationships
7. Organization snapshots
8. Synchronization
9. Edge cases
10. Query patterns
11. Administrative controls

## Authority map

Declare the authoritative source for each field before migration or synchronization. Do not assume one directory contains complete HR truth.

| Data | Possible authority | Application treatment |
| --- | --- | --- |
| Sign-in subject and account state | Microsoft Entra ID or configured identity provider | Authenticate and link to internal principal |
| Legal person and employee identifier | HR system or approved employee registry | Stable internal person and employment mapping |
| Employment status/type/dates | HR system | Effective-dated policy facts |
| Job grade, level, and family | HR system | Policy attributes, never implicit permissions |
| Position and department | HR organizational system | Effective-dated organization facts |
| Primary manager | HR system or approved organization source | Approval relationship candidate |
| Functional/dotted-line manager | Approved organization source | Use only for declared purposes |
| Cost center and budget owner | Finance/HR authority | Approval and budget routing facts |
| Application roles and scopes | Application authorization store or approved app-role assignments | Permission authority |
| Temporary delegation | Governed application workflow | Time-limited approval/work assignment authority |
| Policy entitlement | Deterministic policy decision | Case-pinned output, not an identity claim |

Record authority, source record ID, source version or timestamp, last synchronization, and validation status. When sources disagree, do not silently select one; apply an approved source-priority rule or create a review condition.

## Core entities

Use entities equivalent to:

```text
PrincipalIdentity
Person
Employment
Position
PositionAssignment
OrgUnit
OrgMembership
ReportingRelationship
CostCenter
Location
OrganizationSnapshot
IdentitySyncRun
OrganizationDataIssue
```

Do not collapse `Person`, `Employment`, and `PrincipalIdentity` into one mutable `User` row when the application must support multiple accounts, rehires, contractors, future hires, service principals, or multiple employments.

### PrincipalIdentity

```json
{
  "principalIdentityId": "internal-id",
  "tenantId": "tenant-id",
  "provider": "entra|local|other",
  "providerTenantId": "external-tenant-id",
  "providerSubjectId": "immutable-subject-id",
  "principalType": "person|service",
  "personId": "person-id-or-null",
  "displayName": "display-only",
  "email": "mutable-contact-value",
  "accountEnabled": true,
  "lastSynchronizedAt": "timestamp",
  "version": 1
}
```

Require uniqueness on provider tenant plus subject ID. Do not authorize using display name or email.

### Person

```json
{
  "personId": "person-id",
  "tenantId": "tenant-id",
  "employeeNumber": "source-key-if-permitted",
  "preferredName": "name",
  "status": "active|inactive|future|terminated",
  "sourceSystem": "hr-system",
  "sourceRecordId": "source-id",
  "version": 1
}
```

Store only personal fields required for the application. Apply retention and access controls to employee identifiers and employment data.

## Identity linkage

Link a signed-in principal to a person through approved source identifiers. Do not automatically merge accounts because names or email addresses resemble each other.

Handle:

- one person with multiple identities;
- guest or external accounts;
- local demo identities mapped to seeded people;
- service principals with no person;
- account disablement and termination;
- identity re-creation with a new subject;
- duplicate or ambiguous linkage.

Fail closed for business actions when identity-to-person linkage is missing or ambiguous. Permit only explicitly designed onboarding or support routes.

Build a trusted `ActorContext` after authentication:

```json
{
  "principalId": "principal-id",
  "personId": "person-id",
  "tenantId": "tenant-id",
  "authenticationTime": "timestamp",
  "authenticationStrength": null,
  "sessionId": "session-id",
  "correlationId": "correlation-id"
}
```

Do not accept tenant, person, manager, role, or department values from a user message as trusted context.

## Employment and position

Model effective-dated employment separately from position assignment:

```json
{
  "employmentId": "employment-id",
  "personId": "person-id",
  "legalEntityId": "entity-id",
  "employmentType": "employee|contractor|intern|other",
  "workerStatus": "active|leave|suspended|terminated|future",
  "jobFamilyId": "job-family-id",
  "jobProfileId": "job-profile-id",
  "jobGrade": "grade-code",
  "employeeLevel": "level-code",
  "startDate": "local-date",
  "endDate": null,
  "sourceVersion": "source-version"
}
```

```json
{
  "positionAssignmentId": "assignment-id",
  "employmentId": "employment-id",
  "positionId": "position-id",
  "orgUnitId": "org-unit-id",
  "costCenterId": "cost-center-id",
  "locationId": "location-id",
  "isPrimary": true,
  "allocationPercent": "100.00",
  "effectiveFrom": "date",
  "effectiveTo": null
}
```

Do not derive application permissions directly from `jobGrade`, `employeeLevel`, `jobFamily`, or `positionTitle`. These are policy and routing facts unless explicitly mapped through a governed role assignment.

Support more than one position assignment. Require deterministic selection of the assignment relevant to a request, such as primary employment, beneficiary-selected authorized employment, or policy-approved location.

## Organization units

Represent organizations as effective-dated units and relationships rather than a fixed department column:

```json
{
  "orgUnitId": "unit-id",
  "tenantId": "tenant-id",
  "unitType": "company|business_unit|division|department|team|cost_center|site",
  "code": "stable-code",
  "displayName": "name",
  "parentOrgUnitId": "parent-id-or-null",
  "effectiveFrom": "date",
  "effectiveTo": null,
  "sourceSystem": "source",
  "sourceRecordId": "source-id"
}
```

Avoid assuming that parent-unit hierarchy equals reporting hierarchy, approval authority, budget ownership, or data-access scope. Model those separately.

Validate no impossible parent cycles in the organization tree. Preserve history when units are renamed, merged, split, or closed.

## Reporting relationships

Use explicit effective-dated edges:

```json
{
  "reportingRelationshipId": "relationship-id",
  "tenantId": "tenant-id",
  "subordinatePositionAssignmentId": "assignment-id",
  "managerPositionAssignmentId": "manager-assignment-id",
  "relationshipType": "primary|functional|project|acting",
  "purposes": ["business_need_approval"],
  "effectiveFrom": "timestamp",
  "effectiveTo": null,
  "sourceSystem": "source",
  "sourceRecordId": "source-id",
  "approved": true
}
```

Use the relationship `purposes` or an approved routing rule to decide which edge may approve hardware requests. Do not assume a functional manager can approve budget or a primary manager can approve every exception.

Detect and route:

- no manager;
- manager account disabled;
- manager position vacant;
- manager is the requester or beneficiary;
- circular manager chain;
- duplicate primary managers;
- conflicting source records;
- relationship starts after or ends before the relevant request time;
- manager lacks required role/scope;
- manager is unavailable and no approved delegation exists.

For indirect-manager approval, traverse only the approved relationship type with cycle detection and maximum depth. Store the complete path used.

## Organization snapshots

Create an immutable snapshot for binding decisions and approval plans:

```json
{
  "organizationSnapshotId": "snapshot-id",
  "tenantId": "tenant-id",
  "personId": "beneficiary-person-id",
  "asOf": "timestamp",
  "employmentIds": [],
  "positionAssignmentIds": [],
  "orgUnitIds": [],
  "costCenterIds": [],
  "locationIds": [],
  "managerPaths": [],
  "sourceVersions": {},
  "snapshotHash": "canonical-hash",
  "dataIssues": []
}
```

Pin the snapshot used for policy evaluation and approval planning. If organization data changes before action, apply a configured revalidation rule and append a new snapshot; never mutate the old one.

Separate:

- request-time organization facts;
- approval-step activation facts;
- fulfillment-time location and assignment facts;
- current profile shown in the UI.

## Synchronization

Keep external sources behind typed adapters. Use a synchronization process that:

1. obtains changes or a bounded source snapshot;
2. validates tenant, source identity, required fields, and effective dates;
3. stages records without changing authoritative application projections;
4. detects duplicates, missing references, cycles, and conflicts;
5. computes deterministic changes;
6. applies one database transaction or bounded batches with audit/outbox records;
7. records source checkpoints and reconciliation metrics;
8. quarantines invalid records for review;
9. triggers access and approval-route recalculation where appropriate without rewriting history.

Make sync idempotent. Record source version/checkpoint and content fingerprint. Do not use best-effort email matching as an automatic identity join.

For Microsoft Graph, inspect the configured permissions and use stable object IDs. The manager relationship can supply directory manager data, but confirm whether it is the organization's approved source for hardware approval routing. HR or finance systems may contain required grade, employment, cost-center, and budget facts that directory data does not.

## Edge cases

Design explicit outcomes for:

- new hire before account creation;
- future-dated transfer;
- user on leave;
- terminated beneficiary with open request;
- contractor with sponsor instead of line manager;
- executive whose manager is outside the tenant;
- matrix employee with two departments;
- shared-service fulfillment across legal entities;
- user requesting for a direct report;
- assistant requesting for an executive;
- manager delegation during leave;
- emergency replacement requiring later reconciliation;
- role assignment expiring while work is in progress;
- organization source unavailable.

Use typed `needs_review`, `no_authorized_route`, or `temporarily_unavailable` states rather than guessed relationships.

## Query patterns

Provide deterministic queries/services equivalent to:

```text
resolve_actor_context(principal_subject, as_of)
resolve_person_employments(person_id, as_of)
resolve_policy_attributes(person_id, employment_id, as_of)
resolve_manager_path(person_id, purpose, as_of)
resolve_org_scope(person_id, as_of)
create_organization_snapshot(person_id, purpose, as_of)
find_data_issues(person_id_or_org_unit)
```

Apply tenant and authorization filters inside the query/service. Avoid loading the entire organization graph and filtering it in the browser or model.

## Administrative controls

Provide:

- source and synchronization health;
- unmatched and duplicate identity records;
- missing and circular manager relationships;
- conflicting grades, positions, departments, or cost centers;
- effective-date timeline and source history;
- organization snapshot inspection;
- controlled manual overrides with reason, approval, expiry, and source priority;
- revalidation and rollback of erroneous synchronization batches.

Manual overrides must not silently overwrite source data. Store them as governed overlays with explicit purpose, scope, effective interval, approver, and audit trail.
