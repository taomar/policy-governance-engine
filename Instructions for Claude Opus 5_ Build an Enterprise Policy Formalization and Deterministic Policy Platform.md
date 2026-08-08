# Instructions for Claude Opus 5: Build an Enterprise Policy Formalization and Deterministic Policy Platform

## 1. Your role

Act as the principal enterprise architect, business analyst, product architect, Microsoft Azure architect, Microsoft Agent Framework architect, security architect, data architect, AI engineer, UX architect, and lead software engineer.

Your responsibility is to design and implement a complete production-oriented application that transforms human-readable company policy documents into governed, versioned, machine-usable policies.

Do not stop after producing an architecture document.

You must:

1. Define the business requirements.
2. Define functional and non-functional requirements.
3. Design the complete architecture.
4. Create architecture decision records.
5. Create the domain model.
6. Define the canonical policy schema.
7. Design the Microsoft Agent Framework workflows.
8. Implement the backend, frontend, workflow workers, deterministic policy engine, infrastructure, tests, and documentation.
9. Produce a locally runnable solution.
10. Produce Azure deployment infrastructure.
11. Clearly document assumptions and incomplete areas.

Perform sufficient internal reasoning before taking architectural decisions, but present only conclusions, trade-offs, assumptions, and implementation details.

---

# 2. Critical context

Claude Opus 5 is the engineering agent building this system.

Claude is not the runtime model used by the finished application.

The finished application must use:

- Microsoft Agent Framework for AI-assisted policy lifecycle workflows.
- Azure OpenAI as the application’s only runtime generative AI endpoint.
- Azure AI Search for indexing and retrieving source evidence.
- Azure Blob Storage for original documents and immutable artifacts.
- A relational database as the transactional policy system of record.
- A deterministic policy evaluator for runtime business decisions.
- Human review and approval before policy publication.

Do not introduce direct Anthropic API dependencies into the generated application.

Do not implement runtime policy decisions using an LLM.

---

# 3. Problem statement

Organizations commonly upload company policy documents into a search or RAG solution and assume that the resulting AI can enforce those policies in business workflows.

This is insufficient.

A RAG system can:

- Find policy content.
- Explain clauses.
- Summarize documents.
- Identify potentially relevant rules.
- Retrieve definitions and exceptions.
- Cite source evidence.

A transactional business system requires more:

- Stable rule identities.
- Explicit conditions.
- Defined facts and data types.
- Effective dates.
- Scope and authority.
- Deterministic outcomes.
- Controlled exception handling.
- Repeatable evaluation.
- Version management.
- Approval history.
- Auditability.
- Conflict management.

The proposed application must accept policy documents as input and produce reviewed, approved, machine-usable policies as output.

The system must not treat model-generated policy extraction as immediately authoritative.

---

# 4. Product definition

Build a:

> Policy ingestion, formalization, verification, comparison, approval, versioning, publication, and deterministic evaluation platform.

The platform must maintain a clear separation between:

1. **Source documents:** What the organization wrote.
2. **Search evidence:** Content indexed for discovery and grounding.
3. **AI candidates:** What Azure OpenAI proposes the document means.
4. **Approved policies:** What authorized reviewers approve.
5. **Executable policies:** What deterministic applications can evaluate.
6. **Explanations:** How results are explained to users.

---

# 5. Fundamental design rules

The following rules are non-negotiable.

## 5.1 Search is not execution

Azure AI Search may retrieve policy evidence, but search ranking must never determine a transactional result.

## 5.2 AI output is a candidate

Every policy produced by Azure OpenAI begins as a candidate.

It remains non-authoritative until approved.

## 5.3 Approved policies are immutable

Never modify an approved policy version in place.

Create a new revision or version.

## 5.4 Runtime evaluation is deterministic

The final runtime policy evaluator:

- Must not call Azure OpenAI.
- Must not call Azure AI Search.
- Must not use embeddings.
- Must not depend on generated prose.
- Must operate only on approved structured rules and structured facts.

## 5.5 Missing facts are not false

A missing required fact must produce an `INDETERMINATE` result rather than silently failing a condition.

## 5.6 No silent policy replacement

A changed source document must create a proposed change set.

It must not silently replace, remove, or retire approved policies.

## 5.7 No invented determinism

When a clause lacks a threshold, deadline, authority, definition, or required fact, flag it as ambiguous or non-machine-executable.

Do not invent the missing information.

## 5.8 Every rule must have lineage

Every candidate and approved rule must reference its exact source evidence.

## 5.9 Separate workflow determinism from model determinism

Microsoft Agent Framework must control the deterministic order of workflow stages.

Azure OpenAI remains probabilistic within the stages where interpretation is needed.

## 5.10 Prefer code over agents

Use a normal typed executor, service, or function for work that can be implemented deterministically.

Use an AI agent only for semantic interpretation that cannot reasonably be expressed as deterministic code.

---

# 6. Business objectives

## BO-001 — Transform policies into usable controls

Convert policy documents into structured rules usable by business systems.

## BO-002 — Preserve organizational authority

Ensure that AI cannot create, alter, activate, or retire authoritative policies without governed approval.

## BO-003 — Improve policy visibility

Allow users to search documents, clauses, definitions, rules, exceptions, ambiguities, and prior versions.

## BO-004 — Support deterministic business workflows

Expose approved rules through APIs that produce repeatable results for identical facts and policy versions.

## BO-005 — Manage policy changes

Detect source-document changes and propose additions, modifications, supersessions, or retirements.

## BO-006 — Identify policy quality problems

Detect possible contradictions, ambiguity, missing definitions, incomplete cross-references, and unenforceable language.

## BO-007 — Provide full auditability

Record all ingestion, extraction, verification, review, editing, approval, publication, and evaluation activities.

## BO-008 — Reduce manual policy analysis

Use Azure OpenAI to accelerate extraction and review without removing human accountability.

## BO-009 — Support multiple business domains

The platform must be domain-neutral and usable for:

- Human resources.
- Procurement.
- Travel and expenses.
- Finance.
- IT.
- Security.
- Access management.
- Compliance.
- Legal operations.
- Customer service.
- Delegation of authority.
- Records retention.

## BO-010 — Integrate with existing systems

Expose approved policy evaluations to workflow platforms, applications, agents, APIs, and line-of-business systems.

---

# 7. Business requirements

## BR-001 — Policy source management

The organization must be able to register and manage policy sources.

Supported initial sources:

- Direct upload.
- Azure Blob Storage.
- Existing Azure AI Search service and index.

The architecture must support future connectors without changing the domain model.

## BR-002 — Policy document lifecycle

The organization must be able to:

- Upload a policy.
- Register its ownership.
- Assign its authority.
- assign its jurisdiction.
- Define its effective date.
- Create new source versions.
- View prior versions.
- retire source documents without deleting their history.

## BR-003 — Complete policy inspection

The system must inspect the complete document rather than depending solely on top-k RAG retrieval.

Every document clause must have a recorded disposition.

## BR-004 — Policy formalization

The system must extract candidate:

- Rules.
- Conditions.
- Outcomes.
- Prohibitions.
- Obligations.
- Permissions.
- Approval requirements.
- Evidence requirements.
- Deadlines.
- Calculations.
- Thresholds.
- Exceptions.
- Definitions.
- Scopes.
- Delegation authorities.
- Human-judgment requirements.

## BR-005 — Policy governance

No policy rule may be published without the required review and approval.

Approval requirements must be configurable by policy type, authority, and risk level.

## BR-006 — Deterministic policy publication

Approved policies must be published into a canonical, machine-readable policy format.

## BR-007 — Deterministic policy evaluation

Business applications must be able to submit structured facts and receive stable policy outcomes.

## BR-008 — Policy change management

When source content changes, the system must compare the new document version with the currently approved policy version.

## BR-009 — Policy comparison

Users must be able to compare:

- Two source-document versions.
- Two policy versions.
- A candidate policy against an approved policy.
- Policies from different organizational units.
- Policies with overlapping scopes.

## BR-010 — Contradiction management

The system must identify and track possible conflicts without claiming that every conflict can be resolved automatically.

## BR-011 — Ambiguity management

The system must identify language that requires clarification or human judgment.

## BR-012 — Review assistance

Reviewers must be able to ask Azure OpenAI to:

- Re-examine a clause.
- Find a missing condition.
- Find a missing exception.
- Explain an extraction.
- identify related definitions.
- compare alternative interpretations.
- suggest questions for the policy owner.
- propose test scenarios.

These actions must produce new review artifacts, not silently alter approved content.

## BR-013 — Audit and lineage

Every published rule must be traceable to:

- Source document.
- Source document version.
- Content hash.
- Page.
- Section.
- Clause.
- Extraction run.
- Model deployment.
- Prompt version.
- Schema version.
- Reviewer.
- Approver.
- Publication event.

## BR-014 — Export and integration

The platform must support:

- Canonical JSON export.
- Flattened CSV export.
- API access.
- Event notification after publication.
- Search over approved policies.

CSV must not be the authoritative storage format.

## BR-015 — Access control

Users may only view or act on policy data permitted by their role and organizational access.

---

# 8. Personas and permissions

Implement at least the following roles.

## 8.1 Platform administrator

Can:

- Configure Azure connections.
- Configure model deployments.
- Configure indexes.
- Configure security.
- Configure review workflows.
- Manage system settings.
- View technical operations.

## 8.2 Policy administrator

Can:

- Create policy sets.
- Define authorities.
- Define jurisdictions.
- Define policy taxonomies.
- Assign owners.
- Configure approval requirements.
- Schedule effective dates.

## 8.3 Policy analyst

Can:

- Upload documents.
- Start extraction.
- Inspect clauses.
- Edit candidate rules.
- Request AI re-analysis.
- prepare change sets.
- Submit work for review.

## 8.4 Reviewer

Can:

- Review candidates.
- Accept or reject fields.
- Split or merge candidates.
- Mark ambiguity.
- Resolve non-blocking findings.
- Return work to analysts.
- Request further analysis.

## 8.5 Approver

Can:

- Approve or reject policy versions.
- Approve exceptions to blocking findings where permitted.
- Schedule publication.
- Sign publication records.

## 8.6 Business owner

Can:

- Clarify business meaning.
- Define missing data sources.
- Validate operational feasibility.
- Confirm exception handling.
- Confirm workflow effects.

## 8.7 Auditor

Has read-only access to:

- Documents.
- Rules.
- Comparisons.
- Extraction history.
- Reviews.
- Approvals.
- Publications.
- Evaluations.
- Audit events.

## 8.8 Application client

Can call the deterministic evaluation API for authorized policy sets.

## 8.9 Search user

Can search and read accessible policy knowledge but cannot alter it.

Implement separation of duties.

For high-risk policies, the same person must not both prepare and solely approve the version.

---

# 9. Functional capabilities

## 9.1 Policy workspace

Provide a workspace for each policy set showing:

- Policy owner.
- Business domain.
- Authority.
- Jurisdiction.
- Current approved version.
- Pending source changes.
- Candidate rules.
- Open findings.
- Review status.
- Publication status.
- Dependent systems.
- Recent activity.

## 9.2 Connection management

Support:

- Azure Blob Storage connections.
- Azure AI Search connections.
- Direct upload.
- Connectivity validation.
- Managed identity authentication.
- Selection of containers and paths.
- Inclusion and exclusion rules.
- Metadata mapping.
- Index selection.
- Connection health.
- Synchronization history.

## 9.3 File upload

The upload experience must:

1. Validate file type and MIME type.
2. Validate file size.
3. Scan or quarantine suspicious files.
4. Calculate SHA-256.
5. Detect exact duplicates.
6. Store the immutable original.
7. Create a source-document version.
8. Start parsing.
9. Start indexing.
10. Display processing progress.
11. Display warnings and errors.

Initially support:

- PDF.
- DOCX.
- TXT.
- HTML.
- Markdown.
- JSON.
- CSV where an import mapping exists.

Support OCR or layout extraction for scanned policies.

## 9.4 Document viewer

Provide a viewer that can display:

- Original page.
- Parsed content.
- Section hierarchy.
- Highlighted clause.
- Associated candidates.
- Associated definitions.
- Associated findings.
- Associated approved rules.

## 9.5 Clause ledger

Create a complete clause ledger.

Every section or clause must have:

- Stable clause ID.
- Document version ID.
- Section path.
- Page range.
- Text hash.
- Normalized text.
- Clause classification.
- Processing state.
- Extraction disposition.
- Exclusion reason where relevant.
- Candidate rule links.
- Definition links.
- Cross-reference links.
- Reviewer status.

Allowed clause classifications include:

- Normative rule.
- Prohibition.
- Permission.
- Obligation.
- Exception.
- Definition.
- Scope.
- Procedure.
- Background.
- Example.
- Guidance.
- Cross-reference.
- Informational statement.
- Unclear.
- Unprocessed.

No extraction run is complete while clauses remain `UNPROCESSED`.

## 9.6 Extraction run management

Allow users to select one of three modes:

### Replay mode

Return the previously stored output for the same run fingerprint.

Do not call Azure OpenAI.

### Verification mode

Re-evaluate the existing candidate output against its evidence.

Do not silently replace the candidate.

### Fresh extraction mode

Invoke Azure OpenAI again and create a separate extraction result.

Compare it against prior extraction results.

Require a reason for intentional fresh extraction of an unchanged document.

## 9.7 Candidate policy editor

Display candidate policy information in an editable structured interface.

Support:

- Conditions.
- Outcomes.
- Scope.
- Required facts.
- Data types.
- Thresholds.
- Dates.
- Exceptions.
- Evidence.
- Definitions.
- Authority.
- Priority.
- Ambiguity.
- Machine-executable status.
- Review comments.

Every manual edit must be audited.

## 9.8 Comparison center

Provide side-by-side comparison for:

- Source text changes.
- Clause changes.
- Candidate rule changes.
- Approved rule changes.
- Definition changes.
- Scope changes.
- Threshold changes.
- Effective-date changes.
- Exception changes.
- Required-fact changes.
- Evaluation behavior changes.

## 9.9 Findings center

Provide separate queues for:

- Contradictions.
- Ambiguities.
- Missing definitions.
- Missing references.
- Unsupported extraction.
- Partial extraction.
- Duplicate rules.
- Incomplete rules.
- Non-machine-executable clauses.
- Policy impact findings.
- Failed policy tests.

## 9.10 Review and approval

Support:

- Assignment.
- Due date.
- Comments.
- Reviewer requests.
- Approval requests.
- Return for changes.
- Partial acceptance.
- Rejection.
- Escalation.
- Electronic approval record.
- Multi-stage approval.
- Separation of duties.
- Approval delegation with audit history.

## 9.11 Policy publication

Publication must:

1. Verify required approvals.
2. Verify that blocking findings are resolved.
3. Validate the canonical schema.
4. Validate rule references.
5. Compile the policy package.
6. Run deterministic tests.
7. Calculate the package hash.
8. Save an immutable published artifact.
9. Activate it atomically according to its effective date.
10. Update the approved-policy search index.
11. Publish a domain event.
12. retain the previous version.

## 9.12 Policy simulation

Allow users to enter sample facts and run a candidate or approved policy in simulation.

Simulation results must clearly state that they are not production evaluations.

## 9.13 Runtime evaluation

Expose an authenticated API that accepts:

- Policy set.
- Requested version or active-version flag.
- Evaluation timestamp.
- Structured facts.
- Correlation ID.
- Calling-system identity.

Return:

- Evaluation ID.
- Policy set ID.
- Policy version ID.
- Overall status.
- Outcome.
- Applicable rules.
- Satisfied rules.
- Failed rules.
- Missing facts.
- Required actions.
- Triggered exceptions.
- Evidence references.
- Deterministic result hash.
- Evaluation timestamp.

---

# 10. Proposed Azure architecture

Use a modular architecture with clear boundaries.

## 10.1 Frontend

Preferred stack:

- React.
- TypeScript.
- Accessible component library.
- Generated typed API client.
- Microsoft Entra ID authentication.
- Responsive enterprise user interface.

Primary modules:

- Dashboard.
- Connections.
- Policy workspaces.
- Documents.
- Clause ledger.
- Extraction runs.
- Candidate editor.
- Comparisons.
- Findings.
- Reviews.
- Approvals.
- Published policies.
- Simulation.
- Audit.
- Administration.

## 10.2 Application API

Preferred stack:

- ASP.NET Core.
- Current supported .NET LTS.
- OpenAPI.
- Microsoft Entra ID.
- Policy-based authorization.
- Entity Framework Core.
- Fluent validation or equivalent.
- Problem Details error responses.
- Idempotency middleware.

Responsibilities:

- User-facing business APIs.
- Authorization.
- Document metadata.
- Review operations.
- Policy management.
- Evaluation API.
- Audit queries.
- Workflow invocation.
- Signed upload operations.
- Connection management.

## 10.3 Workflow worker

Implement Microsoft Agent Framework graph workflows in a separate worker boundary.

Preferred deployment:

- Self-hosted MAF Durable Extension worker on Azure Container Apps or another approved managed compute environment.
- Azure Managed Durable Task Scheduler or the supported durable backend.
- A stable abstraction around MAF so framework changes do not contaminate the domain layer.

Alternative:

- Azure Functions hosting with the MAF Durable Extension where serverless execution is preferred.

The final decision must be captured in an architecture decision record.

## 10.4 Azure OpenAI

Use Azure OpenAI for:

- Clause classification when deterministic classification is insufficient.
- Candidate rule extraction.
- Definition resolution.
- Evidence verification.
- Semantic comparison.
- Ambiguity analysis.
- Contradiction explanation.
- Change-impact explanation.
- Test-case proposal.
- Reviewer assistance.
- Human-readable explanations.

Use the Azure OpenAI Responses API through the supported Microsoft Agent Framework provider.

Do not use the deprecated Assistants API.

Use Microsoft Entra authentication and managed identity where supported.

Make deployments configurable:

- `AZURE_OPENAI_REASONING_DEPLOYMENT`
- `AZURE_OPENAI_EXTRACTION_DEPLOYMENT`
- `AZURE_OPENAI_VERIFICATION_DEPLOYMENT`
- `AZURE_OPENAI_EMBEDDING_DEPLOYMENT`

The same deployment may serve multiple roles initially, but the architecture must not require that.

Do not hardcode a model name such as “SOL.”

At startup, validate that configured deployments support required capabilities.

## 10.5 Azure AI Search

Maintain two logical indexes:

### Source evidence index

For original policy content and clause evidence.

### Approved policy index

For discoverability of approved policy rules.

Do not use either index as the policy system of record.

## 10.6 Azure Blob Storage

Store:

- Original documents.
- Parsed representations.
- OCR output.
- Clause inventories.
- Extraction input packages.
- Immutable extraction outputs.
- Comparison artifacts.
- Published canonical JSON.
- Export files.
- Review evidence packages.

Use immutable or retention-controlled storage for approved publication artifacts where organizational requirements demand it.

## 10.7 Relational database

Preferred service:

- Azure SQL Database.

Store transactional and relational state, including:

- Users and roles.
- Policy sets.
- Documents.
- Document versions.
- Clauses.
- Extraction runs.
- Candidates.
- Approved rules.
- Rule revisions.
- Definitions.
- Findings.
- Reviews.
- Approvals.
- Publications.
- Workflow references.
- Evaluations.
- Audit events.

## 10.8 Messaging

Use Azure Service Bus or the approved enterprise event mechanism for:

- Document-ingested events.
- Indexing-completed events.
- Extraction-requested events.
- Review-requested events.
- Policy-published events.
- Policy-activation events.
- Dependent-system notifications.

Use an outbox pattern to prevent database and event-publication inconsistency.

## 10.9 Security services

Use:

- Microsoft Entra ID.
- Managed identities.
- Azure Key Vault.
- Private endpoints where required.
- Azure API Management where the evaluation API is consumed across applications.
- Defender and approved file-scanning controls.
- Application Insights.
- Log Analytics.

---

# 11. Microsoft Agent Framework design

Use MAF for controlled policy-processing workflows.

Do not build one autonomous “policy agent” that decides what to do next without constraints.

Use graph workflows composed of:

- Typed deterministic executors.
- Specialized AI agents.
- Explicit edges.
- Conditional edges based on typed results.
- Checkpoints.
- Human-in-the-loop requests.
- Durable state.
- Error events.
- Retry boundaries.

## 11.1 Policy ingestion workflow

Implement:

```text
ValidateSourceExecutor
    ↓
StoreOriginalExecutor
    ↓
CalculateDocumentIdentityExecutor
    ↓
ParseLayoutExecutor
    ↓
BuildDocumentHierarchyExecutor
    ↓
BuildClauseLedgerExecutor
    ↓
IndexSourceEvidenceExecutor
    ↓
ValidateIngestionCompletenessExecutor
    ↓
IngestionCompleted
```

All stages should be deterministic except any explicitly selected AI-assisted clause classification.

## 11.2 Policy formalization workflow

Implement:

```text
LoadExtractionPackageExecutor
    ↓
CheckRunFingerprintExecutor
    ├── Existing successful fingerprint → ReplayStoredResultExecutor
    └── New fingerprint
            ↓
       ClauseClassificationAgent
            ↓
       CandidateExtractionAgent
            ↓
       StructuredSchemaValidatorExecutor
            ↓
       CanonicalNormalizationExecutor
            ↓
       DefinitionResolutionAgent
            ↓
       EvidenceVerificationAgent
            ↓
       DeterministicEvidenceValidatorExecutor
            ↓
       CoverageValidatorExecutor
            ↓
       ConflictCandidateGeneratorExecutor
            ↓
       ConflictAnalysisAgent
            ↓
       AmbiguityAnalysisAgent
            ↓
       PolicyTestProposalAgent
            ↓
       DeterministicTestValidatorExecutor
            ↓
       HumanReviewRequest
```

The human review request must pause the durable workflow until a response is submitted.

## 11.3 Policy change workflow

Implement:

```text
LoadOldAndNewDocumentVersionsExecutor
    ↓
DeterministicClauseDiffExecutor
    ↓
StableClauseMatchingExecutor
    ↓
DetermineAffectedRulesExecutor
    ↓
TargetedChangeExtractionAgent
    ↓
RuleContinuityAnalysisAgent
    ↓
DeterministicChangeClassifierExecutor
    ↓
ImpactAnalysisAgent
    ↓
ChangeSetBuilderExecutor
    ↓
ConflictAndAmbiguityChecks
    ↓
HumanReviewRequest
```

## 11.4 Publication workflow

Implement:

```text
ValidateApprovalRequirementsExecutor
    ↓
ValidateBlockingFindingsExecutor
    ↓
ValidateCanonicalPackageExecutor
    ↓
CompilePolicyPackageExecutor
    ↓
RunGoldenAndGeneratedTestsExecutor
    ↓
CalculatePublicationHashExecutor
    ↓
AtomicPublicationExecutor
    ↓
UpdateApprovedPolicySearchIndexExecutor
    ↓
PublishPolicyActivatedEventExecutor
    ↓
PublicationCompleted
```

No AI agent may perform `AtomicPublicationExecutor`.

## 11.5 Reviewer re-analysis sub-workflow

Support targeted requests such as:

- Re-extract this clause.
- Search for a missed exception.
- Explain this condition.
- Compare two interpretations.
- Identify related definitions.
- Generate more boundary tests.

Every request must create a separate analysis artifact.

It must not overwrite the current candidate automatically.

## 11.6 Agent definitions

Implement specialized agents rather than a single general agent.

### Clause Classification Agent

Classifies clauses according to the allowed taxonomy.

### Candidate Extraction Agent

Transforms one or more related clauses into canonical candidate structures.

### Definition Resolution Agent

Links terms to explicit definitions and identifies unresolved terms.

### Evidence Verification Agent

Checks whether every candidate field is supported by cited source evidence.

### Conflict Analysis Agent

Explains conflict candidates produced by deterministic overlap analysis.

### Ambiguity Analysis Agent

Identifies missing information and non-deterministic language.

### Change Impact Agent

Explains how proposed changes may affect rules and consuming systems.

### Policy Test Proposal Agent

Proposes positive, negative, boundary, exception, missing-fact, scope, and effective-date tests.

### Reviewer Assistant Agent

Answers reviewer questions using the selected document version, candidates, findings, and approved policies.

It must not perform publication.

---

# 12. Azure OpenAI invocation requirements

## 12.1 Structured outputs

Use strict structured outputs for all machine-consumed AI responses.

Define JSON schemas in code and version them.

Reject responses that do not satisfy the required schema.

Do not parse policy rules from free-form prose using regular expressions.

## 12.2 Grounding package

Each AI call must receive only the necessary controlled context:

- Source clause.
- Parent section.
- Related definitions.
- Explicit cross-references.
- Relevant policy metadata.
- Prior approved rule when performing comparison.
- Output schema.
- Task-specific instructions.

Do not send the entire policy corpus to every call.

## 12.3 Prompt injection protection

Treat document content as untrusted data.

Instructions found inside a policy document must never modify system behavior.

The model prompt must explicitly distinguish:

- Application instructions.
- Source-policy content.
- Reviewer comments.
- Retrieved evidence.

Never allow uploaded content to select tools, change endpoints, reveal secrets, or bypass workflow stages.

## 12.4 Model configuration record

Record for every invocation:

- Azure OpenAI resource identifier.
- Deployment name.
- Returned model identifier where available.
- API surface.
- Prompt template version.
- Schema version.
- Input artifact hashes.
- Correlation ID.
- Token usage.
- Latency.
- Result status.
- Content-safety result where applicable.
- Output hash.

Do not store secrets.

## 12.5 Retry behavior

Retries must not create duplicate candidates.

Use idempotency keys at the workflow and persistence layers.

Differentiate:

- Transient transport retry.
- Model refusal.
- Schema failure.
- Content-safety block.
- Context-length failure.
- Business validation failure.
- Human-review requirement.

---

# 13. Deterministic extraction contract

The application must define determinism precisely.

## 13.1 Structural determinism

All candidate output must conform to a versioned schema.

## 13.2 Replay determinism

The same extraction fingerprint must return the previously stored immutable output.

This is the strongest guarantee of identical extraction results.

## 13.3 Processing completeness

Every clause must have a disposition in the clause ledger.

No clause may disappear merely because it was not retrieved by semantic search.

## 13.4 Canonical normalization

Normalize deterministically:

- Property ordering.
- Identifier format.
- Date format.
- Currency codes.
- Whitespace.
- Enumerations.
- Number representation.
- Boolean representation.
- Scope representation.
- Operator names.
- Evidence ordering.

Calculate an output hash over canonical JSON.

## 13.5 Semantic determinism

Do not promise that independent fresh model calls will always infer exactly the same rules.

Instead:

- Store prior results.
- Compare fresh results.
- Flag additions and removals.
- Require review.
- Preserve the approved baseline.

## 13.6 Extraction fingerprint

The fingerprint must incorporate at least:

```text
source document hashes
+ selected document-version IDs
+ parser version
+ OCR version
+ clause-ledger version
+ clause-ledger hash
+ Azure OpenAI deployment configuration
+ prompt-template version
+ structured-output schema version
+ normalization version
+ extraction settings
+ application extraction-pipeline version
```

## 13.7 Extraction immutability

An extraction result must be immutable after completion.

Reviewer edits create candidate revisions.

Fresh extractions create new extraction runs.

---

# 14. Canonical policy representation

Create a provider-neutral canonical policy intermediate representation.

The canonical format must not depend on:

- Azure OpenAI response objects.
- Microsoft Agent Framework messages.
- Azure AI Search documents.
- UI component structures.
- A particular workflow engine.
- Generated source code.

A representative structure is:

```json
{
  "schemaVersion": "1.0",
  "policySetId": "hardware-policy",
  "policyVersionId": "hardware-policy:2026-08-01",
  "ruleId": "POL-HW-REPLACE-001",
  "ruleRevision": 3,
  "title": "Standard device replacement eligibility",
  "description": "Determines eligibility for standard device replacement.",
  "ruleType": "eligibility",
  "authority": {
    "level": "corporate",
    "owner": "IT",
    "rank": 300
  },
  "scope": {
    "jurisdictions": ["SA"],
    "organizationalUnits": ["*"],
    "personas": ["employee"],
    "processes": ["hardware_replacement"]
  },
  "condition": {
    "all": [
      {
        "fact": "employee.employmentType",
        "operator": "equals",
        "value": "full_time"
      },
      {
        "fact": "device.ageMonths",
        "operator": "greaterThanOrEqual",
        "value": 36
      },
      {
        "fact": "device.status",
        "operator": "equals",
        "value": "active"
      }
    ]
  },
  "effect": {
    "type": "allow",
    "action": "standard_device_replacement"
  },
  "requiredFacts": [
    {
      "name": "employee.employmentType",
      "dataType": "string",
      "required": true
    },
    {
      "name": "device.ageMonths",
      "dataType": "integer",
      "required": true
    },
    {
      "name": "device.status",
      "dataType": "string",
      "required": true
    }
  ],
  "exceptions": [],
  "priority": 100,
  "effectiveFrom": "2026-08-01",
  "effectiveTo": null,
  "machineExecutable": true,
  "ambiguityStatus": "none",
  "reviewStatus": "approved",
  "evidence": [
    {
      "documentVersionId": "doc-104:v2",
      "sourceHash": "sha256-value",
      "page": 12,
      "section": "4.2 Device Replacement",
      "clauseId": "clause-4.2.1",
      "startOffset": 240,
      "endOffset": 426
    }
  ],
  "lineage": {
    "extractionRunId": "run-9201",
    "deploymentName": "configured-deployment",
    "promptVersion": "policy-extract-v4",
    "parserVersion": "layout-parser-v2",
    "schemaVersion": "1.0"
  }
}
```

## 14.1 Condition AST

Use an allowlisted condition abstract syntax tree.

Support operators such as:

- `equals`
- `notEquals`
- `greaterThan`
- `greaterThanOrEqual`
- `lessThan`
- `lessThanOrEqual`
- `in`
- `notIn`
- `contains`
- `startsWith`
- `endsWith`
- `exists`
- `isNull`
- `before`
- `after`
- `onOrBefore`
- `onOrAfter`
- `withinDuration`
- `countEquals`
- `countGreaterThan`
- Boolean `all`
- Boolean `any`
- Boolean `not`

Do not support:

- `eval`.
- Arbitrary code.
- Arbitrary SQL.
- Generated JavaScript.
- Generated C#.
- Arbitrary method invocation.
- Unrestricted regular expressions.
- Network calls during condition evaluation.

## 14.2 Supported policy types

Support:

- Eligibility.
- Permission.
- Prohibition.
- Obligation.
- Approval requirement.
- Evidence requirement.
- Threshold.
- Deadline.
- Calculation.
- Routing.
- Notification.
- Escalation.
- Exception.
- Definition.
- Scope.
- Delegation of authority.
- Retention.
- Access restriction.
- Human-judgment requirement.

---

# 15. Deterministic policy evaluator

Build the evaluator as a normal domain library and service.

Do not implement it as an AI agent.

## 15.1 Evaluation statuses

Support:

- `SATISFIED`
- `NOT_SATISFIED`
- `NOT_APPLICABLE`
- `INDETERMINATE`
- `ERROR`

## 15.2 Evaluation rules

The evaluator must:

1. Load an immutable approved policy package.
2. Validate submitted facts.
3. Canonicalize facts.
4. Select applicable rules deterministically.
5. Evaluate conditions.
6. Apply approved exceptions.
7. Apply explicit precedence.
8. Return the result.
9. Calculate a stable result hash.
10. Record or emit evaluation metadata according to policy.

## 15.3 Missing information

Missing required facts must be returned explicitly.

Example:

```json
{
  "status": "INDETERMINATE",
  "missingFacts": [
    "device.ageMonths"
  ]
}
```

## 15.4 Precedence

Implement explicit precedence based on approved metadata:

- Authority rank.
- Jurisdiction.
- Scope specificity.
- Explicit override.
- Explicit exception.
- Effective date.
- Rule priority.
- Supersession relationship.

Do not implement “newest rule always wins.”

## 15.5 Explanations

Generate a deterministic templated explanation first.

An optional Azure OpenAI explanation may be generated afterward.

The AI explanation must consume the completed deterministic result and must not change it.

---

# 16. Document ingestion and Azure AI Search

## 16.1 Source identity

For every file record:

- Source-system ID.
- Source path.
- File name.
- MIME type.
- Size.
- ETag where available.
- Source last-modified timestamp.
- SHA-256 content hash.
- Upload timestamp.
- Security classification.
- Access metadata.

## 16.2 Parsing

Preserve:

- Pages.
- Headings.
- Paragraphs.
- Lists.
- Tables.
- Footnotes where feasible.
- Definitions.
- Cross-references.
- Character offsets or layout coordinates where available.
- Reading order.
- Header and footer distinctions.

Flag:

- Low OCR quality.
- Missing pages.
- Unsupported encryption.
- Corrupt files.
- Incomplete tables.
- Unresolved cross-references.

## 16.3 Search index fields

The source evidence index should include:

- `chunkId`
- `documentId`
- `documentVersionId`
- `policySetId`
- `sourceName`
- `sourcePath`
- `sourceHash`
- `content`
- `contentVector`
- `pageStart`
- `pageEnd`
- `sectionPath`
- `clauseIds`
- `language`
- `documentType`
- `authority`
- `jurisdiction`
- `effectiveDate`
- `expirationDate`
- `accessControlMetadata`
- `ingestionTimestamp`
- `indexSchemaVersion`

## 16.4 Chunking

Use structure-aware chunking.

Maintain parent-child relationships.

Do not split clauses arbitrarily when avoidable.

Keep chunking for retrieval separate from clause segmentation for policy formalization.

## 16.5 Indexing behavior

Support:

- Initial indexing.
- Incremental indexing.
- Scheduled indexing.
- Manual indexing.
- Retry.
- Dead-letter handling.
- Partial failure reporting.
- Reindexing.
- Index schema migration.
- Deletion detection.
- Access-control metadata.

A file removed from a source must not automatically erase historical policy evidence required for an approved policy.

---

# 17. Policy change management

When source content changes:

1. Create a new document version.
2. Retain the prior document version.
3. Parse the new version.
4. Build a new clause ledger.
5. Diff clause ledgers.
6. Match unchanged and moved clauses.
7. Identify changed clauses.
8. Identify affected approved rules.
9. Run targeted extraction.
10. Build a proposed policy change set.
11. Run conflict and ambiguity analysis.
12. Run impact analysis.
13. Require review.
14. Require approval.
15. Publish a new immutable policy version.

Classify changes as:

- Added.
- Modified.
- Removed from source.
- Moved.
- Renamed.
- Split.
- Merged.
- Superseded.
- Retired.
- Unchanged.
- Potential conflict.
- Review required.

Removal of source language must create a proposed retirement.

It must not immediately delete the approved rule.

---

# 18. Stable identities

Separate:

- Policy set ID.
- Policy version ID.
- Stable logical rule ID.
- Immutable rule revision ID.
- Source document ID.
- Source document version ID.
- Stable clause ID.
- Clause-version ID.
- Extraction-run ID.
- Candidate-revision ID.
- Publication ID.

Use deterministic matching to suggest whether a changed clause represents the same logical rule.

Consider:

- Prior explicit linkage.
- Source section.
- Subject.
- Action.
- Effect.
- Scope.
- Conditions.
- Required facts.
- Evidence.
- Semantic similarity.

The final continuity decision must be reviewable.

Do not use generated prose hashes as the only identity mechanism.

---

# 19. Contradiction detection

Use two stages.

## 19.1 Deterministic overlap detection

Generate conflict candidates when rules overlap in:

- Subject.
- Action.
- Resource.
- Process.
- Jurisdiction.
- Organizational unit.
- Persona.
- Product.
- Time period.
- Scope.
- Required facts.
- Condition ranges.

## 19.2 AI semantic analysis

Azure OpenAI may analyze the conflict candidate and explain:

- Nature of conflict.
- Relevant evidence.
- Possible precedence.
- Whether one rule is likely an exception.
- Clarifying questions.
- Potential remediation.

AI must not automatically resolve blocking contradictions.

## 19.3 Conflict types

Support:

- Allow versus deny.
- Required versus prohibited.
- Incompatible thresholds.
- Conflicting deadlines.
- Conflicting approval authority.
- Duplicate conditions with different outcomes.
- Conflicting definitions.
- Overlapping effective periods.
- Scope collision.
- Exception collision.
- Circular reference.
- Missing referenced policy.
- Calculation conflict.
- Evidence-requirement conflict.
- Authority conflict.

---

# 20. Ambiguity detection

Detect language such as:

- Reasonable.
- Significant.
- Timely.
- Normally.
- Where appropriate.
- Material.
- Adequate.
- High risk.
- As soon as possible.
- Management discretion.
- Sufficient justification.

Also detect missing:

- Subject.
- Action.
- Object.
- Threshold.
- Currency.
- Time zone.
- Deadline start event.
- Owner.
- Approver.
- Evidence.
- Fact source.
- Exception behavior.
- Jurisdiction.
- Effective date.
- Definition.
- Precedence.
- Cross-reference.

Classify ambiguity as:

- Blocking.
- Non-blocking.
- Missing definition.
- Missing data.
- Human judgment required.
- Conflicting interpretation.
- Incomplete cross-reference.
- Non-deterministic by design.

Allow resolution through:

- Approved definition.
- Approved threshold.
- Source-policy correction.
- Linked clause.
- Human-judgment classification.
- Non-machine-executable classification.
- Policy-owner clarification.

---

# 21. Extraction verification

Perform multiple forms of verification.

## 21.1 Evidence verification

Every candidate field must be tied to evidence.

A rule may contain several evidence references.

## 21.2 Coverage verification

Produce a coverage report containing:

- Total clauses.
- Processed clauses.
- Normative clauses.
- Extracted rules.
- Excluded clauses.
- Unresolved clauses.
- Low-confidence clauses.
- Clauses requiring review.

## 21.3 Structural validation

Validate:

- Required fields.
- Data types.
- Operator compatibility.
- Identifier uniqueness.
- Date ranges.
- Scope validity.
- Rule references.
- Definition references.
- Exception references.
- Cyclic dependencies.
- Authority values.

## 21.4 Semantic verification

Classify each candidate as:

- Fully supported.
- Partially supported.
- Unsupported.
- Missing condition.
- Missing exception.
- Over-interpreted.
- Under-specified.
- Requires human interpretation.

The verification agent must not silently rewrite the candidate.

## 21.5 Round-trip rendering

Render the structured rule back into plain language.

Show the source clause and rendered rule side by side.

## 21.6 Tests

Generate and execute:

- Positive test.
- Negative test.
- Boundary test.
- Missing-fact test.
- Scope test.
- Effective-date test.
- Exception test where relevant.
- Precedence test where relevant.

Azure OpenAI proposes tests.

The deterministic evaluator executes them.

---

# 22. Human oversight

Human review is an integral workflow stage, not an optional user-interface feature.

Reviewers must be able to:

- Approve.
- Reject.
- Edit.
- Return for rework.
- Request targeted AI analysis.
- Split a rule.
- Merge duplicate rules.
- Mark as informational.
- Mark as non-machine-executable.
- Add a definition.
- Link evidence.
- Resolve a finding.
- Escalate to a business owner.
- Add comments.
- compare with prior versions.

The system must preserve:

- Original AI proposal.
- Every candidate revision.
- Reviewer changes.
- Reviewer identity.
- Reviewer comments.
- Approval identity.
- Approval timestamp.
- Approval scope.

---

# 23. Data model

Create entities for at least:

- Tenant or organization.
- User.
- Role.
- Permission.
- PolicySet.
- PolicyOwner.
- PolicyAuthority.
- SourceConnection.
- SourceDocument.
- DocumentVersion.
- ParsedArtifact.
- Clause.
- ClauseVersion.
- ClauseRelationship.
- ExtractionRun.
- ModelInvocation.
- CandidateRule.
- CandidateRuleRevision.
- Definition.
- FactDefinition.
- ApprovedPolicyVersion.
- ApprovedRule.
- RuleRevision.
- RuleDependency.
- RuleException.
- EvidenceReference.
- ConflictFinding.
- AmbiguityFinding.
- VerificationFinding.
- ReviewTask.
- ReviewComment.
- Approval.
- Publication.
- PolicyTest.
- PolicyTestRun.
- Evaluation.
- AuditEvent.
- OutboxMessage.

Produce an entity-relationship diagram.

Apply database constraints that enforce valid lifecycle transitions where practical.

---

# 24. API requirements

Design REST APIs with OpenAPI documentation.

Suggested resource groups:

```text
/api/connections
/api/policy-sets
/api/documents
/api/document-versions
/api/clauses
/api/indexing-runs
/api/extraction-runs
/api/candidate-rules
/api/findings
/api/comparisons
/api/reviews
/api/approvals
/api/policy-versions
/api/publications
/api/policy-tests
/api/simulations
/api/evaluations
/api/audit-events
/api/admin
```

Important commands should include idempotency keys.

Use optimistic concurrency for editable drafts.

Do not expose internal workflow implementation details as domain APIs.

---

# 25. Security requirements

Implement:

- Microsoft Entra ID authentication.
- Role and permission checks.
- Organizational data scoping.
- Managed identity.
- Key Vault.
- Private networking where required.
- Encryption in transit.
- Encryption at rest.
- Secret-free source control.
- Secure file validation.
- Malware-scanning integration point.
- Audit logging.
- Data-retention configuration.
- PII and sensitive-data handling.
- Least-privilege access.
- Security headers.
- API rate limits.
- Input validation.
- Output encoding.
- Dependency scanning.
- Container scanning.
- Software bill of materials.
- Prompt-injection defenses.
- Model-output validation.

Do not log:

- Access tokens.
- Secrets.
- Full connection strings.
- Unnecessary sensitive document content.
- Raw credentials.

---

# 26. Non-functional requirements

## NFR-001 — Reliability

Workflow steps must be idempotent and recoverable.

## NFR-002 — Durability

Long-running reviews must survive worker restarts and deployments.

## NFR-003 — Auditability

All authoritative actions must produce immutable audit events.

## NFR-004 — Performance

Large documents must be processed asynchronously.

Interactive APIs must not wait synchronously for complete extraction.

## NFR-005 — Scalability

Extraction and verification should support controlled parallelism by document or clause batch.

## NFR-006 — Cost control

Implement:

- Token budgets.
- Clause batching limits.
- Model deployment selection by task.
- Retrieval limits.
- Caching.
- Run replay.
- Usage reporting.
- Concurrency limits.

## NFR-007 — Observability

Implement distributed tracing across:

- API request.
- Workflow run.
- Executor.
- Agent invocation.
- Azure OpenAI request.
- Search request.
- Database transaction.
- Publication.
- Evaluation.

Use correlation IDs.

## NFR-008 — Explainability

Every rule and result must include traceable evidence and rule identifiers.

## NFR-009 — Maintainability

Keep domain logic independent from Azure SDKs and MAF SDK classes.

## NFR-010 — Portability

The canonical policy model and deterministic evaluator must not depend on Azure OpenAI.

## NFR-011 — Accessibility

The review interface must support keyboard use, semantic labels, and accessible contrast.

## NFR-012 — Localization

Design for multilingual policies and user interfaces.

Do not assume English-only documents.

---

# 27. Testing requirements

Implement:

## 27.1 Unit tests

Cover:

- Canonical normalization.
- Hash calculation.
- Rule evaluation.
- Date handling.
- Scope handling.
- Exception handling.
- Missing facts.
- Precedence.
- Stable IDs.
- Change classification.
- Lifecycle transitions.

## 27.2 Contract tests

Cover:

- Azure OpenAI structured-output schemas.
- Azure AI Search index mapping.
- Blob metadata.
- Database persistence.
- Workflow message contracts.
- Public APIs.

## 27.3 Integration tests

Cover:

- Upload to storage.
- Parsing.
- Indexing.
- Extraction workflow.
- Review pause and resume.
- Approval.
- Publication.
- Evaluation.
- Reindexing.
- Failure recovery.

## 27.4 Golden document tests

Create representative policy documents containing:

- Simple rules.
- Tables.
- Nested exceptions.
- Cross-references.
- Conflicting policies.
- Ambiguous language.
- Missing definitions.
- Multiple jurisdictions.
- Future-effective rules.
- Scanned pages.

Store approved expected outputs.

## 27.5 Determinism tests

Verify:

- Same fingerprint returns the same immutable extraction artifact.
- Same approved package and same canonical facts return the same result hash.
- Retry does not create duplicate candidates.
- Replay does not invoke Azure OpenAI.
- A changed document does not overwrite an approved version.
- Missing facts return `INDETERMINATE`.

## 27.6 Security tests

Include:

- Prompt injection in document content.
- Malicious file names.
- Unsupported MIME types.
- Unauthorized policy access.
- Cross-tenant access attempts.
- Tool-instruction injection.
- Oversized requests.
- Malformed structured output.
- Duplicate-event replay.

---

# 28. Acceptance criteria

The solution is not complete until the following end-to-end scenario works:

1. An administrator configures Azure resources.
2. A policy analyst uploads a PDF.
3. The application stores and hashes the original.
4. The document is parsed.
5. The complete clause ledger is created.
6. The document is indexed in Azure AI Search.
7. The analyst starts an extraction.
8. MAF executes the formalization workflow using Azure OpenAI.
9. Strict structured candidates are created.
10. Evidence validation runs.
11. Coverage is displayed.
12. Contradictions and ambiguities are displayed.
13. A reviewer modifies or approves candidates.
14. The workflow pauses and resumes correctly.
15. An approver approves a policy version.
16. The publication workflow validates and publishes it.
17. Canonical JSON is available.
18. Flattened CSV export is available.
19. The approved policy is searchable.
20. A client submits structured facts.
21. The deterministic evaluator returns a stable result.
22. The result cites the exact policy version and rule IDs.
23. Repeating the evaluation produces the same result hash.
24. Uploading a modified document creates a change set rather than overwriting the policy.
25. Audit history shows the entire lifecycle.

---

# 29. Repository structure

Create a clean repository similar to:

```text
/
├── README.md
├── docs/
│   ├── product-vision.md
│   ├── problem-statement.md
│   ├── business-requirements.md
│   ├── functional-requirements.md
│   ├── non-functional-requirements.md
│   ├── architecture.md
│   ├── security.md
│   ├── threat-model.md
│   ├── data-model.md
│   ├── policy-schema.md
│   ├── workflow-design.md
│   ├── deployment.md
│   ├── operations.md
│   └── adr/
├── src/
│   ├── Web/
│   ├── Api/
│   ├── Application/
│   ├── Domain/
│   ├── Infrastructure/
│   ├── PolicyEngine/
│   ├── PolicySchema/
│   ├── WorkflowWorker/
│   ├── Agents/
│   ├── Search/
│   ├── DocumentProcessing/
│   └── Contracts/
├── tests/
│   ├── Unit/
│   ├── Integration/
│   ├── Contract/
│   ├── GoldenDocuments/
│   ├── Determinism/
│   └── Security/
├── infra/
│   ├── bicep/
│   ├── environments/
│   └── scripts/
├── samples/
│   ├── policies/
│   ├── expected-output/
│   └── evaluation-requests/
├── schemas/
│   ├── canonical-policy.schema.json
│   ├── extraction-output.schema.json
│   └── evaluation.schema.json
└── .github/
    └── workflows/
```

---

# 30. Infrastructure as code

Provide Bicep for:

- Resource group assumptions.
- Managed identities.
- Azure OpenAI configuration references.
- Azure AI Search.
- Blob Storage.
- Azure SQL.
- Key Vault.
- Service Bus.
- Application Insights.
- Log Analytics.
- Container Apps environment or selected workflow host.
- API hosting.
- Static web hosting or frontend hosting.
- Private endpoints where enabled.
- DNS integration placeholders.
- Role assignments.
- Diagnostic settings.

Do not place secrets in Bicep parameter files.

Provide environment overlays for:

- Development.
- Test.
- Production.

---

# 31. Architecture decision records

Create ADRs covering at least:

1. Why RAG is not the policy execution engine.
2. Why Microsoft Agent Framework is used.
3. Why Azure OpenAI is the runtime model endpoint.
4. Why the deterministic evaluator is outside MAF.
5. Why Azure SQL is the authoritative registry.
6. Why Azure AI Search is not the system of record.
7. Why canonical JSON is the portable policy representation.
8. Why CSV is export-only.
9. Why extraction replay is used for exact reproducibility.
10. Why approved rules are immutable.
11. Why human approval is required.
12. Choice of MAF hosting and durability model.
13. Choice of parsing and OCR strategy.
14. Rule precedence strategy.
15. Prompt-injection and untrusted-content strategy.

---

# 32. Implementation order

Implement incrementally.

## Phase 1 — Foundation

- Repository.
- Domain model.
- Database.
- Authentication.
- Policy-set management.
- File upload.
- Blob storage.
- Audit logging.

## Phase 2 — Document processing

- Parsing.
- Clause ledger.
- Azure AI Search indexing.
- Evidence viewer.
- Indexing status.

## Phase 3 — Policy formalization

- Azure OpenAI integration.
- Structured outputs.
- MAF workflows.
- Candidate extraction.
- Evidence verification.
- Run fingerprints.
- Replay behavior.

## Phase 4 — Governance

- Candidate editor.
- Findings.
- Review.
- HITL pause/resume.
- Approval.
- Versioning.

## Phase 5 — Deterministic execution

- Canonical policy package.
- Evaluator.
- Simulation.
- Runtime API.
- Result hashes.

## Phase 6 — Change management

- Document diff.
- Rule matching.
- Change sets.
- Impact analysis.
- Scheduled activation.

## Phase 7 — Production hardening

- Private networking.
- Monitoring.
- Load tests.
- Security tests.
- Disaster recovery.
- Operational documentation.
- CI/CD.

At the end of every phase:

- Build the solution.
- Run tests.
- Fix failures.
- Update documentation.
- Record unresolved risks.

---

# 33. Engineering behavior

While implementing:

- Do not create placeholder implementations and call them complete.
- Do not hide failures.
- Do not fabricate Azure SDK APIs.
- Inspect installed package versions before using APIs.
- Pin package versions.
- Avoid obsolete Azure OpenAI Assistants APIs.
- Keep MAF integration behind interfaces.
- Prefer typed messages between executors.
- Make every workflow executor idempotent.
- Use cancellation tokens.
- Use structured logging.
- Use UTC internally.
- Use ISO 8601 dates and times.
- Use explicit currency codes.
- Validate all external inputs.
- Use database transactions for authoritative state changes.
- Use an outbox for events.
- Add migration scripts.
- Include sample configuration without secrets.
- Provide meaningful error messages.
- Document every limitation honestly.

When a package or API differs from these instructions because the installed version has changed:

1. Inspect the actual official API surface.
2. Use the current supported mechanism.
3. Preserve the architectural boundary and requirement.
4. Record the deviation in an ADR.
5. Do not invent method names or unavailable functionality.

---

# 34. Required final deliverables

Produce:

1. Complete source repository.
2. Business requirements document.
3. Functional requirements document.
4. Non-functional requirements document.
5. Solution architecture.
6. Component diagram.
7. Deployment diagram.
8. Data-flow diagram.
9. Sequence diagrams for key workflows.
10. Entity-relationship diagram.
11. MAF workflow diagrams.
12. Canonical policy JSON Schema.
13. Database migrations.
14. Azure AI Search index definitions.
15. Azure OpenAI structured-output schemas.
16. Deterministic evaluator.
17. Web application.
18. APIs.
19. Workflow worker.
20. Infrastructure as code.
21. Automated tests.
22. Sample policies.
23. Sample approved outputs.
24. Local-development guide.
25. Azure deployment guide.
26. Security and threat model.
27. Operations runbook.
28. Architecture decision records.
29. Known-limitations register.
30. Demonstration script.

---

# 35. Final quality gate

Before declaring completion, confirm explicitly:

- Claude is not used by the runtime application.
- Azure OpenAI is the runtime generative endpoint.
- Microsoft Agent Framework orchestrates policy lifecycle workflows.
- Azure AI Search stores searchable evidence, not authoritative decisions.
- Every source clause has a disposition.
- Every candidate has evidence.
- Every approved rule is versioned.
- Every publication is approved.
- Every workflow is recoverable.
- Every AI output is schema validated.
- Every policy evaluation is deterministic.
- Every missing fact is explicit.
- Every policy change creates a reviewable change set.
- Every authoritative action is audited.
- No LLM participates in the final runtime rule calculation.
- The full end-to-end acceptance scenario passes.

Do not declare the solution production-ready merely because the demonstration path works.

List remaining security, operational, legal, model-quality, scaling, and governance risks separately.