# Data Model (Local Build Subset)

This document describes the entity subset implemented in this phase, mapped to the
full entity list required by Section 23 of the specification.

## Implemented entities (SQLAlchemy models in `policy_platform.domain`)

| Table | Purpose | Section 23 reference |
|-------|---------|----------------------|
| `policy_sets` | A named collection of policies for one business domain. | PolicySet |
| `policy_authorities` | Authority level + owner + rank used for precedence. | PolicyAuthority |
| `source_documents` | A registered source document (metadata, ownership). | SourceDocument |
| `document_versions` | An immutable version of a source document (hash, storage pointer). | DocumentVersion |
| `clauses` | A stable clause within a document version (ledger entry). | Clause / ClauseVersion (merged for this phase) |
| `extraction_runs` | Record of an extraction attempt (fingerprint, status) — persisted for future MAF use. | ExtractionRun |
| `candidate_rules` | A non-authoritative candidate rule produced by extraction (schema present; population deferred). | CandidateRule / CandidateRuleRevision |
| `approved_policy_versions` | An immutable, approved, versioned policy package. | ApprovedPolicyVersion |
| `approved_rules` | A single approved, versioned rule belonging to an `ApprovedPolicyVersion`. | ApprovedRule / RuleRevision |
| `rule_exceptions` | An approved exception attached to a rule. | RuleException |
| `evidence_references` | Source lineage for a rule (document version, page, section, clause, offsets). | EvidenceReference |
| `evaluations` | A recorded runtime evaluation request/response pair with result hash. | Evaluation |
| `audit_events` | Immutable audit trail record for authoritative actions. | AuditEvent |
| `outbox_messages` | Reserved table for future transactional outbox publishing. | OutboxMessage |
| `policy_tests` | A named, saved test case for a policy set (inputs + expected assertions), re-runnable across versions. | PolicyTest |
| `policy_test_runs` | Append-only result of executing one `PolicyTest` against one `ApprovedPolicyVersion`. | PolicyTestRun |

## Deferred entities (schema not yet created)

`Tenant`, `User`, `Role`, `Permission`, `SourceConnection`, `ParsedArtifact`,
`ClauseRelationship`, `ModelInvocation`, `Definition`, `FactDefinition`,
`RuleDependency`, `ConflictFinding`, `AmbiguityFinding`, `VerificationFinding`,
`ReviewTask`, `ReviewComment`, `Approval`, `Publication`.

These are deferred alongside the MAF/governance workflow phase (see
`docs/known-limitations.md`).

## Lifecycle rules enforced

- `approved_policy_versions` and `approved_rules` rows are **never updated in
  place** after publication; the API and repository layer only ever insert new
  versions/revisions (Rule 5.3).
- `evaluations` rows are append-only audit records of runtime calls.
- `policy_test_runs` rows are append-only: re-running a test always inserts a
  new row (recording which `ApprovedPolicyVersion` it ran against), never
  updates a previous result. `policy_tests` rows themselves *are* mutable
  (`is_active`, `review_status`, and the test definition) — a test case is a
  quality-assurance artifact, not an authoritative governance record, so
  editing or retiring one is not a Rule 5.3 violation. See ADR-0010.
- `document_versions` rows are immutable once created; a new upload creates a new
  version row, never overwrites an existing one.
