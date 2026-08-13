# Why no rule executes, and why 18 of 47 are unlinked

**Document:** AD-103 Benefits Policy (PDF, 44 clauses)
**Extraction run:** `22f1bd18-3851-43f3-b683-19ca8595a338`
**Policy set:** `benefits` (`5aaaca4d-942e-4eea-ba8e-23d38bb9ea90`)
**Measured:** 2026-08-11, against the live database after a clean truncate-and-reload.

Every number and every quoted string in this document came from the running
system, not from a summary. The queries that produced them are given at the end
so any claim here can be re-checked.

---

## 1. The headline

```
rules extracted                          47
machine_executable = True                 0
non-empty condition tree                  0
DMN decision tables built                 0
required_facts across all rules           0
rules whose SOURCE states a condition     21
rules whose condition COMPILED             0
```

Nothing evaluates. Not one rule reaches the deterministic engine, and no rule
carries a single required fact.

Linkage is in better shape than execution:

```
rules with related_rule_ids              29 of 47
total edges                              76
dangling edges                            0
asymmetric edges                          0
connected components (size > 1)           5   sizes 11, 10, 3, 3, 2
isolated rules                           18
rules with a group_label                 12 of 47
```

---

## 2. Execution: what actually blocks it

### 2.1 The fact model is empty

```sql
SELECT key, trusted_config_json FROM policy_sets;
```
```
 benefits | {}
```

This one row explains most of the zeros above. The formulator refuses to emit
an executable FEEL condition unless every fact path it would reference came
from a *trusted* fact model — see `policy_formulator_v1.md` §83. With `{}`
there are no trusted paths, so every decision falls into the honest
non-executable branch.

The requirement codes the agent returned say so directly:

```
FACT_MODEL_REQUIRED                30
OUTPUT_MODEL_REQUIRED              30
RULE_OVERLAP_RESOLUTION_REQUIRED   12
HIT_POLICY_REQUIRED                12
DECISION_CONTEXT_REQUIRED          10
DATA_TYPE_REQUIRED                  9
VALUE_NORMALIZATION_REQUIRED        3
RULE_PRECEDENCE_REQUIRED            3
LOGICAL_RELATIONSHIP_AMBIGUOUS      1
TEMPORAL_MODEL_REQUIRED             1
```

`FACT_MODEL_REQUIRED` on 30 of 30 decisions. Nothing downstream can recover
from that, and nothing downstream should try: inventing
`university.financialPosition = "good"` would assert both a customer schema
this platform cannot see and a threshold the document never wrote.

### 2.2 Where the code stops

`src/policy_platform/infrastructure/extraction/formulation_mapping.py`:

```python
derived = next(
    (d for d in (derive_condition(dec, index) for dec in decisions) if d is not None),
    None,
)
if derived is None:
    condition: ConditionNode = _VACUOUS_CONDITION   # {"type": "all", "all": []}
    required_facts: list[RequiredFact] = []
    machine_executable = False
else:
    condition, required_facts = derived
    machine_executable = True
```

`derive_condition` returns `None` for every decision in this corpus, because
every decision carries `dmn_mapping_status != executable`:

```
enrichment_required     21
not_directly_mappable   15
ambiguous               11
executable               0
```

So all 47 rules take the first branch. This is the intended behaviour, not a
bug — but it is why `machine_executable` reads 0 of 47 and why
`required_facts` is empty everywhere.

### 2.3 The vacuous-condition guard, and why it matters

An empty `all` node is **vacuously true** in ordinary boolean logic: a
conjunction of nothing is true. Without a guard, every one of these 47 rules
would match every request.

`src/policy_platform/evaluator/engine.py` stops that twice over:

```python
if not rule.machine_executable:
    ...
    not_applicable_reason="rule_not_machine_executable"
```

and separately `_is_vacuous`, which refuses to treat an empty conjunction as a
satisfied condition.

The consequence is deliberate and worth stating plainly: **the system is inert
rather than wrong.** Every evaluation returns `NOT_APPLICABLE`. That is the
correct failure mode, and it is the reason the alternative — inventing
bindings so that rules "execute" — would be far worse than the current zeros.

### 2.4 The 21 conditions the document states

21 rules have a condition in the canonical record. Zero compiled. Five are not
restated in any operative field either. Full records:

```
AI-e5cf898854  routing / require_action
  SOURCE : 3.1. FBSU grants employee benefits based on their functions and
           depending on the recommendation of the director of the concerned
           Department.
  SUBJ   : FBSU
  PRED   : grants
  OBJ    : employee benefits
  COND   : based on their functions and depending on the recommendation of the
           director of the concerned Department
  TREE   : {"type":"all","all":[]}
  ACTION : grants employee benefits

AI-2d8d11afbf  obligation / require_action
  SOURCE : 3.2. Employee basic salary shall be increased depending on the
           financial position of the University and subject to the approval of
           the President, in one of the following cases only:
  SUBJ   : Employee basic salary
  PRED   : be increased
  OBJ    : (empty)
  COND   : depending on the financial position of the University and subject to
           the approval of the President
  TREE   : {"type":"all","all":[]}
  ACTION : be increased

AI-7451398981  obligation / require_action
  SOURCE : In the case of medical treatment in clinics and hospitals that are
           not approved by the insurance company, the original medical invoices
           and reports must be submitted to the Human Resources Department...
  SUBJ   : the original medical invoices and reports
  PRED   : be submitted to
  OBJ    : the Human Resources Department
  COND   : In the case of medical treatment in clinics and hospitals that are
           not approved by the insurance company
  TREE   : {"type":"all","all":[]}
  ACTION : be submitted to the Human Resources Department

AI-a2277d8703  permission / allow
  SOURCE : 3.2.4. Exceptional Increase may be granted for specific cases that
           the university deems necessary.
  COND   : for specific cases that the university deems necessary
  TREE   : {"type":"all","all":[]}

AI-f9ea59787f  definition / informational
  SOURCE : In all cases, the benefits and allowances of FBSU faculty and staff
           members are governed by the individual contracts of appointment.
  COND   : In all cases
  TREE   : {"type":"all","all":[]}
```

These five are reported as `condition_not_compiled` (warning). They are **not**
lost — each survives verbatim in `formulation.canonical.rule.condition`, is
derived on read into `decision_readiness.required_attributes` and
`xacml_view.source_semantics.conditions`, and is now displayed in the UI. What
is missing is a compiled tree, which needs the fact model from §2.1.

### 2.5 Most conditions have no test to compile, even with a fact model

From the XACML view across all 47 rules:

```
predicate  not_specified_by_source    28
predicate  specified                   2
fact model not_configured             30
```

Only **2 of 30** conditions state a testable predicate. The rest name a
dependency and stop:

```
"depending on the financial position of the University"
    -> the source never says whether that means a threshold, a boolean,
       or a judgement call

"for specific cases that the university deems necessary"
    -> "necessary" is defined by the university, not by the document

"In all cases"
    -> not a test at all
```

**This half of the problem does not go away when a fact model is configured.**
A fact model supplies the attribute; it cannot supply a comparison the policy
declined to write. These are decisions the document delegates to named humans,
and the correct representation is `DISCRETIONARY`, not a manufactured
threshold.

---

## 3. Linkage: 18 isolated rules

### 3.1 The graph is sound where it exists

```
edges                 76
dangling              0     every target resolves to a real rule
asymmetric            0     every edge is reciprocated
components (size>1)   5     sizes 11, 10, 3, 3, 2
isolated             18
```

No broken references and no one-way edges. The largest component is coherent —
every member is about medical insurance:

```
LARGEST COMPONENT: 11 rules
  AI-02644e474b  [eligibility]  The employees will not be enrolled in FBSU medical insurance program
  AI-14983f658b  [eligibility]  Directors of administrative units may be eligible "A" Class
  AI-3b4dd14554  [definition]   "CT" Class is provided to All administrative staff, technical employees.
  AI-9a164c9854  [eligibility]  Saudi staff employee and his/her spouse and children in the Family Card
  AI-a9ed0ff671  [definition]   FBSU medical insurance coverage is based on their grades and job offer
  AI-b68108f3b9  [definition]   This class is reserved for academic Deans and faculty holding Ph.D
  AI-bcfce6740b  [eligibility]  Non Saudi staff employee and his/her eligible dependence are eligible
  AI-c680742ac2  [obligation]   FBSU outsources and signs an agreement
  AI-d916d6ad81  [obligation]   FBSU provides its employees and their eligible dependents
  AI-e8f86c5190  [definition]   "BT" Class is provided to Faculty members holding Master degree
  AI-f523de3963  [definition]   This class of Medical Insurance is provided to the top managers
```

That is a genuine family: the class definitions and the eligibility rules that
reference them, linked together.

### 3.2 "Isolated" was overstated, and candidates were being discarded

An earlier version of this document reported isolation from `related_rule_ids`
alone. An independent review flagged that as too narrow, and measurement
confirmed it:

```
isolated by related_rule_ids     21
isolated by all graph evidence   16
```

Discovery produces **typed** edges with a confirmed/candidate state, and
`ai_extraction` dropped every non-confirmed one:

```python
for edge in edges:
    if edge.state != "confirmed":
        continue          # <- 6 typed candidate edges discarded here
```

On this corpus:

```
edges discovered      30
  confirmed           24    same_decision 13, definition_used_by 7, precedes 4
  candidate            6    definition_used_by 6
```

All six discarded candidates were `definition_used_by` — which is the link a
**non-executable** rule most needs. A definition cannot be grouped by a shared
fact comparison, because it has no facts; the structural link is the only
grouping it will ever have.

Keeping `related_rule_ids` confirmed-only is correct — that field states a
relationship, and a candidate is a proposal. The error was discarding the
proposal instead of surfacing it. Candidates now ship on the rule as
`candidate_relationships`, typed and with their reason, and are not merged into
`related_rule_ids`.

### 3.3 Why `group_label` is nearly empty

Only **12 of 47** rules carry a `group_label`, and only three labels exist:

```
  35  (none)
   6  FBSU medical insurance coverage is based on
   3  The housing allowance per calendar year (12 months) up to a maximum of
   3  Non Saudi staff employee and his/her eligible dependence are eligible
```

`group_label` is populated by `_group_labels()`, which only fires when a **DMN
decision covers 2 or more canonical policies**. Building such a decision
requires enough trusted configuration for the agent to emit `executable`
instead of `enrichment_required` — which returns us to §2.1. **The empty fact
model suppresses grouping as a side effect.**

The two labels that do exist are also visibly truncated stems, not topics:

```
"The housing allowance per calendar year (12 months) up to a maximum of"
```

That is a sentence cut mid-clause, used as a family name.

### 3.4 Exceptions and supersessions

```
supersedes_rule_ids   0
exceptions            0  ->  5   (fixed)
```

The document states exception language — `"Unless otherwise stipulated in the
employment contract"` on `AI-c3e9ccec25`, `"except for a co-payment of medical
cost…"` elsewhere — and the canonical record captured it all along. The
canonical-to-runtime mapping then dropped it, so no rule carried a structured
`RuleException`.

Now projected. Only `description` is populated: the source says what the
exception *is*, not what it tests or what it changes the outcome to, and
`RuleException` permits exactly that shape — a prose carve-out with no
machine-readable condition. The `exception_id` derives from the text rather
than a UUID, so re-extracting an unchanged document does not report a change
that did not happen.

`supersedes_rule_ids` remains 0, which is correct: AD-103 supersedes nothing.

---

## 4. Where the extraction itself is lossy

### 4.1 The clause splitter cuts mid-sentence

```sql
SELECT id, left(text, 96) FROM clauses WHERE btrim(text) ~ '^[a-z(]';
```
```
5d2297cd-3f9b-4f79-8f5f-505ac743df4c | the monthly basic salary up to a maximum of:
7b08d2bc-4f5b-4403-94a0-3efbdab04e8a | (husband and wife). In the case of a married
                                       couple are employed by FBSU or Astra Internal School
```

The second is the tail of:

> "The housing allowance is limited to one employee of the married couple
> **(husband and wife). In the case of** a married couple are employed by FBSU..."

The break lands between `"married couple"` and `"(husband and wife)"`.

The formulator, reading the orphaned half, correctly reconstructs the governing
sentence from inherited context — and produces a rule the *preceding* clause
already produced.

**2 clauses cut mid-sentence -> 2 duplicate rule pairs. Exact correspondence.**

```
AI-93357d4ac0  ==  AI-ee1e836e37
   " The housing allowance is limited to one employee of the married couple"
   src_idx 0 (clause 7b08d2bc)  and  src_idx 20 (clause 14165f60)

AI-fd9b0bdcf2  ==  AI-de9a6b2457
   "The housing allowance is to be paid in monthly prorated installments."
```

### 4.2 `content_fingerprint` does not see them, and is not supposed to

```sql
SELECT content_fingerprint, count(*)
FROM candidate_rules WHERE superseded_at IS NULL
GROUP BY 1 HAVING count(*) > 1;
```
```
(0 rows)
```

An earlier version of this document called that a defect, on the reading that
two detectors of the same property disagreed. **That was wrong**, and an
independent review caught it.

`content_fingerprint` is a **cross-run delta identity**, not a within-run
duplicate detector. It hashes `SEMANTIC_FIELDS` — rule type, scope, condition,
effect, priority, exceptions, required facts — to answer "is this the same rule
the previous extraction produced?". It includes `effect`, which is *derived*
from subject/predicate/object, so two copies of one sentence that decomposed
differently legitimately hash differently:

```
AI-93357d4ac0   object: "one employee"                       condition: "of the married couple"
AI-ee1e836e37   object: "one employee of the married couple" condition: (none)

AI-de9a6b2457   object: "in monthly prorated installments"   frequency: "monthly"  calculation: "prorated"
AI-fd9b0bdcf2   constraint: "prorated installments"          frequency: "monthly"
```

Nothing is broken. The two answer different questions, and the real gap was
that **no within-run duplicate check existed at all** until
`find_duplicate_rules` was added. See `duplicate-detection.md`.

---

## 5. What the numbers mean, and what they do not

`0 of 47 executable` is the **honest** number for:

* a document that delegates most of its decisions to named humans
  ("subject to the approval of the President", "cases the university deems
  necessary"), and
* a deployment with no fact model configured.

It is not a measure of extraction quality. Measured against the question the
deployment actually asks — *can an evaluator decide this rule against a
customer's case?* — the same 47 rules read:

```
decidable          40
not_a_decision      7
parties extracted  15   (8 recipient-subject, 7 authority)
extraction targets 132
judgement-bounded   7
```

Both numbers are true. They answer different questions, and reporting only the
first is what made the extraction look broken when it is mostly not.

---

## 6. Ordered blockers

| # | Blocker | Owner | Status |
|---|---------|-------|--------|
| 1 | `trusted_config = {}` — no fact model | needs the customer's data model | **open** — unfixable here |
| 2 | 28 of 30 conditions state no test | the document delegates | **open** — not solvable by engineering |
| 3 | Clause splitter cuts mid-sentence | this repo | **fixed** — 44 clauses -> 41, mid-sentence starts 2 -> 0 |
| 4 | Duplicates detected but invisible | this repo | **fixed** — escalated and tagged |
| 5 | Canonical `exception` never projected | this repo | **fixed** — 5 exceptions now carried |
| 6 | Typed candidate relationships discarded | this repo | **fixed** — surfaced as `candidate_relationships` |

Blocker 1 is the one that unblocks the most. Blocker 2 is unblockable by
anyone: a fact model supplies the attribute, and cannot supply a comparison
the policy declined to write. The right representation for those is a manual
review gate, which `decision_readiness.evaluability = "discretionary"` and the
`authority` parties already provide.

---

## Reproducing every figure

```powershell
$c = docker ps --filter "publish=5433" --format "{{.Names}}"

# fact model
docker exec -i $c psql -U policy_admin -d policy_platform_advtool `
  -c "SELECT key, trusted_config_json FROM policy_sets;"

# mid-sentence clause starts
docker exec -i $c psql -U policy_admin -d policy_platform_advtool `
  -c "SELECT id, left(text,96) FROM clauses WHERE btrim(text) ~ '^[a-z(]';"

# fingerprint duplicates (returns 0 rows)
docker exec -i $c psql -U policy_admin -d policy_platform_advtool `
  -c "SELECT content_fingerprint, count(*) FROM candidate_rules
      WHERE superseded_at IS NULL GROUP BY 1 HAVING count(*)>1;"

# linkage, evaluability, faithfulness, XACML view
curl -s "http://127.0.0.1:8050/api/policy-sets/benefits/candidate-rules" -o w.json
```
