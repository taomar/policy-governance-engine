# Policy collision, difference, and impact analysis

## Contents

1. Purpose
2. Comparison candidate selection
3. Comparison layers
4. Relationship taxonomy
5. Conflict criteria
6. Precedence handling
7. Definition and terminology drift
8. Temporal and scope analysis
9. Rule and process comparison
10. Impact analysis
11. LLM responsibilities
12. Review routing

## Purpose

Detect meaningful relationships across policy releases without assuming that newer, longer, more specific, more similar, or more favorable text is authoritative.

Return evidence-backed candidates and witness scenarios. Human owners or approved deterministic precedence data resolve material ambiguity.

## Comparison candidate selection

Build the comparison set in stages:

1. Restrict by tenant and caller authorization.
2. Include explicitly declared parents, amendments, addenda, translations, annexes, and superseded releases.
3. Filter by policy domain, authority type, issuing entity, jurisdiction, legal entity, population, product, asset, contract, and temporal overlap.
4. Include releases that share referenced definitions, procedures, forms, or downstream decisions.
5. Run lexical search for exact policy codes, terms, clause references, product names, and quoted wording.
6. Run vector or hybrid discovery for paraphrase and conceptual overlap.
7. Record why every candidate was included and which catalog regions were searched.

Do not cap the comparison set using similarity alone. Use pagination and bounded batches while preserving catalog coverage metrics.

The system must be able to say that comparison coverage is incomplete because a source was inaccessible, metadata was missing, an index was stale, or a dependency could not be resolved.

## Comparison layers

### Layer 1: Source identity

Compare content hashes, signatures, issuer, owner, approval marks, declared versions, filenames, and source locations.

Do not classify different files as different policy meaning when they differ only in rendering, and do not classify identical text as identical authority when issuer, approval, scope, or effective dates differ.

### Layer 2: Metadata and applicability

Compare:

- policy family and authority type;
- jurisdiction and legal entity;
- employee, customer, supplier, product, asset, plan, contract, or program scope;
- effective, expiry, event, grandfathering, and transition dates;
- inclusion, exclusion, and exception selectors;
- document status and approval state.

### Layer 3: Structural text

Create stable section and clause alignments. Detect inserted, deleted, moved, split, merged, renumbered, or rewritten units. Preserve table and footnote context.

Text similarity is diagnostic only. A single changed `not`, boundary operator, date, currency, unit, or exception may reverse policy meaning.

### Layer 4: Definitions

Compare normalized terms, exact definitions, scope, synonyms, referenced authorities, and downstream dependent rules.

Definition drift is material when the same apparent term changes the set of people, events, products, dates, evidence, or calculations covered.

### Layer 5: Rule semantics

Compare typed logic after canonicalization:

- subject, actor, action, object, and modality;
- condition trees and grouping;
- inclusions and exclusions;
- thresholds and boundary operators;
- quantities, units, currencies, rounding, calendars, and date anchors;
- outcomes, evidence, and approvals;
- exceptions and nested exceptions;
- source and definition dependencies.

Canonicalization may sort commutative operands and normalize equivalent units only through approved conversions. It must not reorder noncommutative process steps or erase short-circuit meaning.

### Layer 6: Process behavior

Compare triggers, actors, ordering, parallelism, conditions, approvals, timers, escalation, retries, side effects, termination, and compensation.

### Layer 7: Scenario impact

Evaluate representative inputs through both approved rule interpretations when safe. Report which outcomes change and why.

## Relationship taxonomy

Use a typed relationship with confidence signals, evidence, scope, affected rules, and review state.

| Relationship | Meaning |
| --- | --- |
| `EXACT_DUPLICATE` | Same governed source bytes and authority metadata |
| `FORMATTING_ONLY` | Meaning and authority match; rendering differs |
| `SEMANTICALLY_EQUIVALENT` | Wording differs but normalized behavior matches over the evaluated domain |
| `ADDITIVE` | Adds independent rules or guidance without changing existing outcomes |
| `CLARIFYING` | Makes existing meaning explicit without changing behavior; human confirmation is normally required |
| `NARROWING` | Reduces applicability, entitlement, permission, or accepted evidence |
| `WIDENING` | Expands applicability, entitlement, permission, or accepted evidence |
| `AMENDS` | Changes a defined part of another release while leaving the remainder in force |
| `SUPERSEDES` | Replaces another release for an approved scope and effective period |
| `ADDS_EXCEPTION` | Introduces a scoped exception to another rule |
| `PARTIAL_OVERLAP` | Applies to some of the same scenarios without proven incompatibility |
| `DEFINITION_DRIFT` | Changes a term used by one or more rules |
| `TEMPORAL_OVERLAP` | Effective periods overlap and require applicability or transition resolution |
| `DIRECT_CONFLICT` | Applicable normative outcomes cannot both hold for at least one scenario |
| `PROCEDURAL_CONFLICT` | Required steps, actors, ordering, approvals, or deadlines are incompatible |
| `AUTHORITY_OR_PRECEDENCE_UNKNOWN` | Potential collision cannot be resolved from approved catalog data |
| `AMBIGUOUS` | Source supports multiple material interpretations |
| `UNRELATED` | No material relationship found within verified comparison coverage |

Do not infer `SUPERSEDES`, `AMENDS`, or `CLARIFYING` merely from semantic shape. Require source language, approved catalog metadata, or an authorized review decision.

## Conflict criteria

Create a conflict case when any relevant scenario has one or more of these conditions:

- one rule requires an action another prohibits;
- entitlement, amount, threshold, deadline, evidence, approval, or outcome differs incompatibly;
- one release includes a case another excludes and precedence is unknown;
- definitions cause the same rule to select different populations or facts;
- procedures require incompatible order, actor, approval, or timing;
- two sources claim the same authority and period but disagree;
- an exception may apply but its target or boundary is unresolved;
- material applicability or effective-date language is ambiguous;
- an external reference required for interpretation is missing or versionless.

Store a conflict with:

```json
{
  "conflictCaseId": "conflict-id",
  "severity": "low|medium|high|critical",
  "type": "direct|procedural|definition|temporal|scope|authority|ambiguity",
  "leftReleaseId": "release-id",
  "rightReleaseId": "release-id",
  "leftRuleIds": [],
  "rightRuleIds": [],
  "sourceSpanIds": [],
  "overlapDomain": {},
  "witnessScenarios": [],
  "candidateExplanations": [],
  "approvedPrecedenceFound": false,
  "blocksPublication": true,
  "reviewTaskId": null
}
```

Do not reduce severity because the affected population appears small without an approved impact and risk model.

## Precedence handling

Represent approved precedence as catalog data, not prompt text. Model its source, scope, effective interval, approver, and rationale.

Possible organizational dimensions include law, regulation, contract, collective agreement, corporate standard, regional addendum, product terms, local procedure, and approved individual exception. The platform must not prescribe their ordering.

Apply precedence only when:

- both releases match the rule's declared authority classes;
- the precedence rule applies to the same scope and time;
- the precedence rule is approved and active;
- no more specific approved precedence rule contradicts it;
- authorization permits using the sources.

If no approved rule resolves a material overlap, return `AUTHORITY_OR_PRECEDENCE_UNKNOWN` and block automatic publication or application.

Do not use “newer wins” or “specific wins” unless the organization explicitly approved those principles for the relevant policy family.

## Definition and terminology drift

Build a definition dependency graph:

```text
term -> definition release -> dependent clauses -> normalized rules -> workflows/tests
```

When a definition changes:

1. Align the old and candidate terms.
2. Compare scope and exact meaning.
3. Find every dependent candidate and approved rule.
4. Re-run semantic comparison for those rules.
5. Generate witness scenarios newly included or excluded.
6. Route material changes for review even when no rule sentence changed.

Treat synonyms as suggestions. Similar wording in different jurisdictions or contracts may have different legal meanings.

## Temporal and scope analysis

Keep these dates distinct:

- document publication date;
- policy effective and expiry dates;
- event/request/incident/purchase/employment dates used by rules;
- transition period;
- grandfathering cutoff;
- review and approval timestamps;
- system activation timestamp.

Calculate interval overlap deterministically. Do not assume policy activation time equals policy effective time.

Represent applicability as typed predicates rather than opaque tags. Unknown selectors must not evaluate as false silently; use three-valued handling and route material unknowns.

Check overlaps using representative values at boundaries, immediately before and after dates, and across inclusivity/exclusivity rules.

## Rule and process comparison

Normalize rule trees before diffing, then emit atomic changes such as:

```text
MODALITY_CHANGED: may -> must
BOUNDARY_CHANGED: > 6 months -> >= 6 months
VALUE_CHANGED: 5 business days -> 7 calendar days
CONDITION_ADDED: region == KSA
EXCEPTION_REMOVED: approved medical exception
EVIDENCE_ADDED: manager confirmation
APPROVAL_CHANGED: line manager -> HR director
DATE_ANCHOR_CHANGED: request date -> incident date
```

For process graphs, emit step, edge, guard, actor, timer, and side-effect changes. A moved paragraph is not necessarily a process-order change; compare explicit semantics.

If canonicalization cannot establish equivalence safely, mark the result `AMBIGUOUS` rather than treating syntactic equality or model agreement as proof.

## Impact analysis

Impact analysis assists judgment; it does not establish authority.

Use three sources of scenarios:

- deterministic boundary cases generated from changed conditions;
- policy-owner-curated golden scenarios;
- authorized, deidentified or synthetic representative cases.

For each scenario, compare:

- applicable release set;
- matched rules;
- decision status and outcome;
- required evidence and approvals;
- process path and deadlines;
- explanation and exact source evidence.

Do not rerun and overwrite historical decisions. If historical records are used for impact estimates, write a separate simulation result linked to immutable decisions and protect sensitive data.

Report coverage limits. “No changed scenarios found” is not proof of equivalence unless the evaluated input domain is exhaustive and documented.

## LLM responsibilities

An LLM may:

- propose clause alignments and paraphrase matches;
- explain textual and semantic changes;
- identify possible missing qualifiers, references, or exceptions;
- propose relationship and conflict classifications;
- generate candidate witness and boundary scenarios;
- summarize reviewer impact packets.

An LLM may not:

- approve a relationship or conflict resolution;
- select authority or precedence;
- mark material changes as behavior-preserving without deterministic evidence and required review;
- fabricate missing effective dates or scope;
- broaden the comparison set beyond caller authorization;
- convert a review suggestion directly into a published rule.

Require structured output with cited left and right source spans. Reject comparisons that cite only one side or lack a concrete changed field.

## Review routing

Always route these conditions for authorized review unless explicit governance says otherwise:

- direct or procedural conflict;
- missing authority or precedence;
- definition drift with dependent binding rules;
- changed entitlement, prohibition, amount, threshold, deadline, scope, evidence, approval, or exception;
- temporal overlap without an approved transition rule;
- ambiguity with more than one material interpretation;
- low OCR or extraction quality on normative content;
- inaccessible referenced authority;
- impact changes in high-risk scenarios;
- candidate supersession or amendment relationships.

Allow automatic closure only for configured low-risk cases such as byte-identical duplicates or non-normative formatting changes, and still retain the evidence and decision rule that closed them.
