# Extraction and lineage contracts

## Contents

1. Contract principles
2. Source bundle
3. Canonical document model
4. Extraction run
5. Source evidence
6. Clause and definition candidates
7. Normalized rule candidate
8. Process candidate
9. Publication entities
10. Persistence constraints
11. API and event contracts

## Contract principles

Adapt names to repository conventions while preserving these semantics:

- use immutable opaque IDs internally and human-readable codes separately;
- distinguish source-supplied metadata, deterministically derived values, model-inferred candidates, and human-approved values;
- attach every material candidate to one or more immutable source spans;
- use `unknown` or explicit uncertainty instead of fabricated defaults;
- preserve raw and normalized values;
- version every schema, prompt, extractor, ontology, compiler, and search projection;
- never make an extraction run or published release mutable;
- use UTC instants for system timestamps and explicit local date/calendar semantics for policy dates;
- use decimal types for money and quantities; never binary floating point;
- represent logic as typed trees, not executable strings.

Use snake_case internally unless the repository already establishes another convention. Apply API aliases at serialization boundaries rather than duplicating fields.

## Source bundle

```json
{
  "sourceBundleId": "bundle-id",
  "tenantId": "tenant-id",
  "submittedBy": "principal-id",
  "submittedAt": "RFC3339 timestamp",
  "declaredPolicyDefinitionId": null,
  "declaredDocumentType": null,
  "declaredAuthority": null,
  "declaredRelationship": null,
  "bundleHash": "sha256 over canonical manifest and asset hashes",
  "manifestVersion": "1",
  "assets": [
    {
      "sourceAssetId": "asset-id",
      "order": 0,
      "role": "primary|attachment|annex|translation|cover|evidence",
      "filename": "policy.pdf",
      "mediaType": "application/pdf",
      "byteLength": 0,
      "contentHash": "sha256",
      "storageVersionUri": "immutable-object-version",
      "languageHints": ["en"],
      "parentAssetId": null,
      "securityClassification": "internal",
      "malwareScanStatus": "clean"
    }
  ]
}
```

Do not deduplicate solely by filename. An exact bundle duplicate requires matching tenant, canonical manifest, asset order/roles, and hashes. Decide explicitly whether translations or signatures create a new bundle identity.

## Canonical document model

Persist or address an immutable canonical artifact with:

```json
{
  "canonicalDocumentId": "canonical-id",
  "sourceAssetId": "asset-id",
  "layoutProvider": "provider",
  "layoutModel": "configured-model",
  "layoutApiVersion": "configured-version",
  "contentHash": "sha256",
  "pageCount": 0,
  "pages": [
    {
      "pageNumber": 1,
      "width": 0,
      "height": 0,
      "unit": "pixel|inch",
      "blocks": [
        {
          "blockId": "stable-block-id",
          "kind": "title|heading|paragraph|list|table|footnote|header|footer|figure|signature|other",
          "readingOrder": 0,
          "rawText": "verbatim extracted text",
          "normalizedText": "normalization that preserves meaning",
          "polygon": [],
          "ocrConfidence": null,
          "tableId": null,
          "row": null,
          "column": null,
          "spans": []
        }
      ]
    }
  ],
  "warnings": []
}
```

Do not discard repeated headers, footers, struck text, handwritten annotations, selection marks, or signatures until a deterministic classification records why they are non-normative.

For tables, preserve merged cells, row and column headers, units, notes, and reading order. A reconstructed row without the headers required to interpret it is invalid evidence.

## Extraction run

```json
{
  "extractionRunId": "run-id",
  "sourceBundleId": "bundle-id",
  "pipelineVersion": "version",
  "ontologyVersion": "version",
  "schemaVersions": {},
  "promptVersions": {},
  "modelInvocations": [
    {
      "purpose": "document_map|clause_semantics|rule_normalization|verification|comparison",
      "provider": "azure-openai",
      "deployment": "configured-deployment",
      "modelVersion": null,
      "parameters": {},
      "inputArtifactHashes": [],
      "outputArtifactHash": "sha256",
      "startedAt": "timestamp",
      "completedAt": "timestamp",
      "inputTokens": null,
      "outputTokens": null
    }
  ],
  "status": "running|complete|needs_review|failed",
  "validationSummary": {},
  "createdAt": "timestamp"
}
```

Do not overwrite an extraction run after completion. A retry that can change output creates a new run linked through `retriesRunId` or `supersedesRunId`.

## Source evidence

Represent exact evidence independently so many fields can cite the same span:

```json
{
  "sourceSpanId": "span-id",
  "sourceAssetId": "asset-id",
  "canonicalDocumentId": "canonical-id",
  "pageStart": 1,
  "pageEnd": 1,
  "blockIds": ["block-id"],
  "characterStart": null,
  "characterEnd": null,
  "tableId": null,
  "cells": [],
  "polygon": [],
  "quotedText": "exact supporting text",
  "spanHash": "sha256"
}
```

Require the quoted text and location to resolve against the immutable canonical artifact. Detect stale or mismatched spans before review or publication.

## Clause and definition candidates

```json
{
  "clauseCandidateId": "candidate-id",
  "extractionRunId": "run-id",
  "candidateCode": "candidate-human-code",
  "sectionPath": ["4", "4.2"],
  "title": "Accessory replacement",
  "originalText": "source-preserving text",
  "normalizedText": "meaning-preserving normalized text",
  "classification": ["binding_rule", "exception"],
  "sourceSpanIds": ["span-id"],
  "definitionDependencies": ["definition-candidate-id"],
  "crossReferenceCandidates": [],
  "materiality": "low|medium|high|critical",
  "uncertainties": [],
  "validationStatus": "pending|valid|invalid|needs_review"
}
```

```json
{
  "definitionCandidateId": "definition-id",
  "term": "business day",
  "normalizedTerm": "business_day",
  "definitionText": "definition",
  "scope": {},
  "sourceSpanIds": ["span-id"],
  "possibleCatalogMatches": [],
  "driftWarnings": []
}
```

Keep document vocabulary and application vocabulary distinct. Map them explicitly and preserve synonyms and local meanings.

## Normalized rule candidate

Use a safe typed representation equivalent to:

```json
{
  "ruleCandidateId": "rule-candidate-id",
  "clauseCandidateId": "clause-candidate-id",
  "ruleKind": "applicability|eligibility|entitlement|obligation|prohibition|calculation|approval|exception",
  "subject": {"type": "employee", "selectors": []},
  "actor": null,
  "action": "receive",
  "object": {"type": "leave_days", "qualifiers": []},
  "modality": "must|must_not|may|entitled|requires_approval",
  "condition": {
    "operator": "all",
    "operands": [
      {
        "operator": "compare",
        "fact": "employment.tenure_months",
        "comparator": "greater_than_or_equal",
        "value": {"decimal": "6", "unit": "month"}
      }
    ]
  },
  "exceptions": [],
  "outcome": {
    "type": "grant",
    "value": {"decimal": "5", "unit": "business_day"}
  },
  "dateSemantics": {
    "effectiveFrom": null,
    "effectiveTo": null,
    "eventDateFact": null,
    "calendarId": null,
    "timeZone": null
  },
  "applicability": {},
  "evidenceRequirements": [],
  "approvalRequirements": [],
  "sourceSpanIds": ["span-id"],
  "extractionMode": "explicit|deterministic_derivation|model_inference",
  "uncertainties": [],
  "compilerStatus": "not_attempted|valid|invalid"
}
```

Define a closed operator and comparator vocabulary. Reject arbitrary function names, code snippets, SQL, regular expressions with unsafe complexity, and dynamically resolved field paths.

Represent inclusive and exclusive boundaries explicitly. Store `5 business days`, `120 calendar days`, and `three months after purchase` as different semantics.

If a sentence contains discretion such as “normally,” “where appropriate,” or “management may,” do not normalize it into an unconditional rule. Preserve discretion and route it to the approved human path.

## Process candidate

```json
{
  "processCandidateId": "process-id",
  "name": "warranty replacement",
  "trigger": {},
  "steps": [
    {
      "stepId": "step-id",
      "actorRole": "requester|manager|service_desk|procurement",
      "action": "typed-action",
      "preconditions": [],
      "requiredInputs": [],
      "evidenceRequirements": [],
      "approvalRequirements": [],
      "deadline": null,
      "next": []
    }
  ],
  "terminationConditions": [],
  "exceptionPaths": [],
  "sourceSpanIds": [],
  "uncertainties": []
}
```

Do not infer system side effects from prose unless the source actually requires them and an integration owner approves the executable mapping.

## Publication entities

An approved release should contain or reference:

```json
{
  "policyReleaseId": "release-id",
  "policyDefinitionId": "definition-id",
  "humanVersion": "version-label",
  "authority": {},
  "scope": {},
  "effectiveFrom": null,
  "effectiveTo": null,
  "approvedClauseIds": [],
  "approvedRuleIds": [],
  "approvedProcessIds": [],
  "relationshipIds": [],
  "sourceBundleIds": [],
  "approvalIds": [],
  "contentFingerprint": "sha256 over canonical approved semantics",
  "lifecycleStatus": "approved|scheduled|published|retired|withdrawn",
  "frozenAt": "timestamp"
}
```

The content fingerprint must be based on a documented canonical serialization. Exclude mutable operational fields such as timestamps that do not change policy meaning.

## Persistence constraints

Enforce constraints equivalent to:

- source asset content hash and immutable storage version are required;
- completed extraction artifacts cannot be updated or deleted through normal application roles;
- every material candidate has at least one valid source span;
- every approved clause/rule/process links to an approved review revision;
- published release content and membership cannot change;
- effective intervals are valid, but overlapping intervals are not rejected blindly because addenda and exceptions may legitimately overlap;
- relationship endpoints exist and cannot create invalid self-relations;
- review decisions are append-only and reference the revision reviewed;
- only one active lease/assignee may own a review task when exclusive ownership is configured;
- outbox idempotency and search-document identities are unique;
- tenant IDs agree across every relationship;
- legacy compatibility projections are not writable.

Use database transactions for catalog state plus outbox events. Do not attempt a distributed transaction with Blob Storage or Azure AI Search.

## API and event contracts

Use narrow commands such as:

```text
CreateIngestionJob
AttachSourceBundle
StartExtractionRun
CompleteExtractionStage
CreateComparisonRun
SubmitReviewDecision
RequestPolicyPublication
VerifyIndexProjection
ActivatePolicyRelease
RetirePolicyRelease
```

Every command should carry `tenantId`, authenticated actor context, correlation ID, idempotency key, expected version where mutable state is involved, and a typed payload.

Use events equivalent to:

```text
SourceBundleRegistered
ExtractionRunCompleted
PolicyCandidatesValidated
PolicyConflictDetected
PolicyReviewRequested
PolicyReviewCompleted
PolicyReleaseFrozen
PolicyPublicationRequested
PolicyIndexProjectionVerified
PolicyReleaseActivated
PolicyReleaseRetired
```

Events report immutable facts. Commands request actions. Do not use an event named as an instruction or mutate a past event to correct it; append a correction event.
