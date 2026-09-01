# Capability flows

This page is for architects and reviewers who need the product boundaries at a glance. It keeps only the diagrams that explain the platform's highest-impact boundaries. The task-oriented journey is in [Workflows](workflows.md); detailed ingestion design remains in [PDF ingestion architecture](specs/pdf-ingestion-architecture-v1.md).

## How to read the diagrams

- Plain arrows are required steps.
- Dotted arrows are best-effort or optional.
- **AI** steps are probabilistic and advisory.
- **Python** and evaluator steps are deterministic.
- **Human review** is the publication gate.

## 1. End-to-end document control

This is the primary product flow.

```mermaid
flowchart LR
    File["PDF / DOCX"]
    Ingest["Deterministic ingestion<br/>canonical text + clauses"]
    Search[("Azure AI Search")]
    Passage["AI passage selection"]
    Verify{"Python verbatim check"}
    Formulate["AI rule formulation"]
    Map["Deterministic mapping<br/>condition, effect, facts"]
    Candidate[("Candidate rules")]
    Review{"Human review"}
    Publish[("Immutable policy version")]
    Tests["Quality + regression"]
    Engine["Deterministic evaluator"]
    Log[("Decision and audit evidence")]

    File --> Ingest --> Passage --> Verify
    Ingest -. "best effort" .-> Search
    Verify -- valid --> Formulate --> Map --> Candidate --> Review
    Verify -- invalid --> Drop["Discard + diagnostic"]
    Review -- approve --> Publish --> Tests --> Engine --> Log
    Review -- revise / reject --> Candidate
```

**Boundary.** AI locates and formulates. Python verifies source text and compiles the executable representation. A human decides what may be published.

**Outputs.** Immutable source versions, clauses, candidate rules, approved policy versions, test history, decisions, and audit events.

## 2. Evidence and provenance

Every governed decision must lead back to one source passage. A policy can contain many rule records; traceability is at the rule-to-source level.

```mermaid
flowchart LR
    Source["Source file"]
    Version[("DocumentVersion<br/>content hash")]
    Clause[("Clause<br/>page, section, offsets")]
    Candidate[("CandidateRule<br/>evidence")]
    Approved[("ApprovedRule<br/>immutable version")]
    Result["Evaluation / quality / test result"]
    Inspector["Read-only evidence inspector"]

    Source --> Version --> Clause --> Candidate --> Approved --> Result --> Inspector
    Clause -. "search key:<br/>documentVersionId_clauseId" .-> Search[("Azure AI Search")]
```

The verbatim check proves the excerpt exists in the canonical source. It does not replace human judgement about whether the excerpt was the right policy statement.

## 3. Deterministic evaluation

All runtime decisions pass through the same engine.

```mermaid
flowchart TD
    Request["Policy set + optional version + facts"]
    Package["Load immutable policy package"]
    Facts["Canonicalize facts"]
    Window["Filter effective rules"]
    Order["Order by precedence"]
    Scope{"Scope matches?"}
    Missing{"Required facts present?"}
    Condition["Evaluate condition AST"]
    Exception["Apply rule exceptions"]
    Combine["Combine effects"]
    Aggregate["Evaluate aggregate limits"]
    Hash["Stable result hash"]
    Response["Evaluation response"]
    Log[("Append-only decision log")]

    Request --> Package --> Facts --> Window --> Order --> Scope
    Scope -- no --> NA["NOT_APPLICABLE"]
    Scope -- yes --> Missing
    Missing -- no --> IND["INDETERMINATE<br/>missing facts listed"]
    Missing -- yes --> Condition --> Exception --> Combine --> Aggregate --> Hash --> Response --> Log
```

The evaluator imports no database, network, or AI dependency. The same package, facts, and evaluation time produce the same result.

## 4. Tests and regression proof

```mermaid
flowchart LR
    Select["Select policies + version"]
    Draft["AI-generated or<br/>reviewer-authored scenario"]
    Seal["Persist expected assertions<br/>and commitment hash"]
    Run["Run blind through<br/>deterministic evaluator"]
    Compare{"All committed<br/>assertions match?"}
    Evidence[("Append-only test run<br/>exact version")]
    Guard["Promote passing scenario<br/>to regression guard"]
    Publish["Future publish"]

    Select --> Draft --> Seal --> Run --> Compare --> Evidence
    Compare -- pass --> Guard
    Publish --> Guard --> Run
```

Expected assertions are committed before execution. AI may draft scenarios; it never decides pass or fail. Historical evidence resolves rules from the exact tested version.

## 5. Quality and correlation assurance

```mermaid
flowchart TD
    Scope{"Published version<br/>or candidates"}
    Deterministic["Deterministic checks<br/>IDs, effects, predicates,<br/>executability, backlog"]
    AI["AI review<br/>gaps, overlap, risk"]
    Validate["Validate severity, structure,<br/>and every referenced rule ID"]
    Findings[("Immutable quality run<br/>methodology version")]
    Evidence["Evidence drawer<br/>exact policy version"]
    Correlation["Correlation<br/>deterministic grouping + AI classification"]
    Disposition[("Reviewer disposition<br/>and audit event")]

    Scope --> Deterministic --> Findings --> Evidence
    Scope --> AI --> Validate --> Findings
    Scope --> Correlation --> Disposition
```

Deterministic findings are confirmed structural checks. AI findings are potential issues requiring human confirmation. Quality trends compare only runs produced by the same methodology version.

## 6. Grounded AI

```mermaid
sequenceDiagram
    participant UI as Ask AI / extraction / test proposal
    participant API as FastAPI service
    participant DB as PostgreSQL
    participant AOAI as Azure OpenAI
    participant Search as Azure AI Search

    UI->>API: question or generation request
    API->>DB: load approved rules and project scope
    opt retrieval needed
        API->>AOAI: embed query
        API->>Search: hybrid search filtered to platform documents
        Search-->>API: clauses + provenance
    end
    API->>AOAI: structured prompt with bounded context
    AOAI-->>API: advisory JSON
    API->>API: validate schema and references
    API-->>UI: answer / proposal + evidence
```

Search is grounding, never execution. Retrieval failure must not silently convert an ungrounded answer into authoritative policy.

### 6a. Putting a case to a whole project

A reviewer can describe a situation in plain English and put it to one policy or to a whole project. The project scope never evaluates every policy: it retrieves the ones that bear on the question from that project's **own** policy index, and discards the rest before anything is evaluated.

```mermaid
sequenceDiagram
    participant UI as Test a Case
    participant API as FastAPI service
    participant DB as PostgreSQL
    participant AOAI as Azure OpenAI
    participant PIdx as Per-project policy index

    UI->>API: scenario (+ optional provision_id)
    alt one policy chosen
        API->>DB: published payload for that policy
    else whole project
        API->>DB: published payloads for the active version
        API->>AOAI: embed scenario
        par concurrent discovery
            API->>PIdx: search policy documents
        and
            API->>PIdx: search rule documents
        end
        PIdx-->>API: ranked policy and rule documents
        API->>API: fuse, cut at the semantic elbow, rescue by rule
        API->>API: collapse duplicates, retain in-budget, discard the rest
        API->>API: slice large policies to the rule budget
    end
    API->>AOAI: classify what the question asks for
    par requested tracks
        API->>AOAI: informational gather over the retained records
    and
        API->>AOAI: verdict gather over the same retained records
    end
    AOAI-->>API: informational answer, verdict, or both
    API->>API: check every citation against the payload
    API-->>UI: outcome + retained/discarded + rule selection + size vs budget
```

Rule documents take part in discovery but never inflate a policy's score: a strong rule match can only *rescue* its parent policy through an independent threshold. Both gathers read the one closed set of records retrieval settled, so the statement a reviewer is told and the verdict they are given can never rest on two different corpora.

Four things this flow guarantees, each of which was a defect first:

- **It never fans out.** The retained policies are evaluated together — one gather per requested track over the whole retained set, never one call per policy — and the combined size is reported against a budget. An oversize payload is refused rather than silently trimmed.
- **It never falls back to "evaluate everything".** When retrieval cannot be relied on, the reviewer is told which of the distinct states applies — no published version, index not built, index stale, index empty, search unavailable, search failed, or a genuine no-match — and no evaluation is made. Those are kept apart because collapsing any pair reports one situation as another.
- **It only claims to have narrowed when it did.** A project with no more published policies than the retention budget has all of them evaluated, and that is reported as `not_narrowed` rather than as a selection. Saying "search kept the highest matching policies and discarded the rest" when nothing was discarded credits search with a choice it never made, and leaves a reviewer believing the listed policies matched their question when they are simply all the project has.
- **It returns policies, not standalone clauses.** The index contains one policy document per published policy plus rule documents for large policies. Rule hits can only rescue their parent policy; the retained result remains a policy keyed on stable provision identity, and rule documents never surface as independent policies. An earlier design exposed retrieval through clause ids, which are regenerated whenever a document is re-read, and it failed silently on every project with history.

Narrowing is a cost control and a scope control, not a relevance guarantee. A policy that is retained has not been judged to bear on the question — the gather decides that, and reports `no_rule_bears` when none of them does. Over-retention is the deliberate direction: a policy kept but not bearing costs a little context, while one dropped that did bear is the outcome the reviewer forbade.

The index holds policy and rule projection documents only for published policies at the latest approved version, which is what makes it cheap to maintain: edits, approvals, rejections and re-extractions all act on candidates and cannot change it. Only two events can — publishing rebuilds a project's index, and deleting the project drops it.

## 7. Outputs and audit

```mermaid
flowchart LR
    Rules[("Approved rules")]
    Candidates[("Candidate rules")]
    Evaluations[("Evaluations")]
    Runs[("Quality, test,<br/>correlation runs")]
    Audit[("Audit events")]
    Export["JSON / JSONL / CSV"]
    UI["Read-only history and evidence views"]
    Consumer["Auditor, reviewer,<br/>archive, downstream system"]

    Rules --> Export --> Consumer
    Candidates --> Export
    Evaluations --> UI --> Consumer
    Runs --> UI
    Audit --> UI
```

Exports are verbatim structural re-serialization. Decision, quality, and test history remain version-owned and read-only.

## Secondary capabilities

These are important but do not need separate diagrams:

| Capability | Control boundary |
|---|---|
| **Version compare** | Python computes added/removed/changed rules; AI may narrate the already-correct diff. |
| **Exceptions** | Human waiver record; currently not consumed by the evaluator. |
| **Attestations** | Human acknowledgement tied to one published version. |
| **Notes** | Mutable collaboration context, not audit evidence. |
| **Navigation** | Browser state and typed API client; no URL router or deep links. |

## Known boundaries

- AI, Search, and extraction work are synchronous request-driven operations.
- Search indexing is best-effort and has no scheduled reconciliation.
- Actor persona is workflow attribution, not production authorization.
- Hidden Correlation, Exceptions, and Attestations surfaces remain callable by API but are not in current navigation.
- There is no transactional outbox publisher, notification delivery, or scheduled policy run.
