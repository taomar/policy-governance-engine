# Display failures: when the UI said something the data did not

Three defects where the extraction was correct and the interface reported
something false. Grouped together because they share a cause: **a fallback
chosen for convenience became an assertion.**

---

## 1. "WHEN Always" — the worst of them

### What the screen showed

```
The housing allowance per calend...   INFORMATIONAL   Candidate
WHEN Always  ->  THEN up to a maximum of Fifteen thousand (15,000) SAR

The housing allowance per calend...   INFORMATIONAL   Candidate
WHEN Always  ->  THEN up to a maximum of Fifteen thousand (15,000) SAR

The housing allowance per calend...   INFORMATIONAL   Candidate
WHEN Always  ->  THEN up to a maximum of Twenty-five thousand (25,000)...
```

Two rows identical. All three claiming to apply to everyone.

### What the data actually held

```
AI-c4c43499ce  condition: "for administrative, technical and service staff"
               threshold: "Fifteen thousand (15,000) SAR"

AI-98ff28dc85  condition: "for full time lecturers, instructors, assistant
                           instructors, research and teaching assistants,
                           and postdoctoral researchers"
               threshold: "Fifteen thousand (15,000) SAR"

AI-f77f375894  condition: "for full-time faculty members holding the rank of
                           Assistant, Associate or Full Professor"
               threshold: "Twenty-five thousand (25,000) SAR"
```

Three staff categories, two limits. **The formulator captured all of it
correctly.** The condition is the only thing separating the two 15,000 SAR
rules, and it was exactly what the display dropped — so they became
indistinguishable.

### The code

`apps/web/src/ruleDisplay.ts`:

```typescript
// BROKEN
const condition = cond.text || "Always";
```

`cond.text` is empty whenever the compiled condition tree is empty — which is
**all 47 rules in this corpus**, because no fact model exists to compile
against (see `execution-and-linkage.md` §2.1).

So "Always" was not a rare fallback. It was printed for every rule in the
document.

### Why this is a lie and not a simplification

"Always" inverts the rule's scope: from *"these staff"* to *"everyone"*. A
reviewer approving that row is approving a claim the document never made. The
underlying data was right; the sentence on screen was wrong.

### The fix

```typescript
function statedCondition(rule: CanonicalRule): string | null {
  const canonical = rule.formulation?.canonical?.rule?.condition;
  if (canonical && canonical.trim()) return canonical.trim();
  for (const decision of rule.formulation?.dmn_decisions ?? []) {
    const projection = decision.semantic_projection;
    if (!projection) continue;
    const phrases = [...(projection.conditions ?? []),
                     projection.condition_source ?? ""].filter(p => p && p.trim());
    if (phrases.length > 0) return phrases.join(" · ");
  }
  return null;
}

const stated = cond.text ? null : statedCondition(rule);
const condition = cond.text || stated || "Always";
```

Nothing is inferred: the wording is read from the canonical decomposition and
the semantic projection, both of which already carry it verbatim. When the
source genuinely states no condition, `statedCondition` returns `null` and
"Always" is then true.

A `conditionIsStatedOnly` flag is returned alongside, so the row can mark a
stated-but-uncompiled condition rather than let it pass for a compiled one:

```css
.policy-decision-value.is-stated-only {
  font-style: italic;
  border-bottom: 1px dotted var(--border);
}
```

### Verified live

```
AI-c3e9ccec25  WHEN Unless otherwise stipulated in the employment contract
               THEN is calculated
AI-c4c43499ce  WHEN for administrative, technical and service staff
               THEN up to a maximum of Fifteen thousand (15,000) SAR
AI-98ff28dc85  WHEN for full time lecturers, instructors, assistant instructors...
               THEN up to a maximum of Fifteen thousand (15,000) SAR
AI-f77f375894  WHEN for full-time faculty members holding the rank of Assistant...
               THEN up to a maximum of Twenty-five thousand (25,000) SAR
```

---

## 2. Ten tabs, ten different overclaims about one boolean

Every tab rendered its own ternary over `machine_executable`, and each invented
wording that said more than the flag supports:

| File | String shown to the user |
|------|--------------------------|
| `PolicyValidationLab.tsx` | `"Documentation only"` |
| `PolicyValidationLab.tsx` | `"Machine-executable" : "Documentation only"` |
| `PolicyValidationLab.tsx` | `"{n} documentation-only excluded"` |
| `QualityFindingDrawer.tsx` | `"Documentation only"` |
| `RuleScenarioTester.tsx` | `"This published rule is documentation-only and cannot be scenario-tested yet"` |
| `RuleScenarioTester.tsx` | `"Not testable yet"` |
| `RuleScenarioTester.tsx` | `"Documentation-only rule"` |
| `ProjectsPage.tsx` | `"Manual-only package"` |
| `RuleCard.tsx` | `<Tag color="orange">Manual</Tag>` |
| `PolicyTestsPage.tsx` | `"All 47 published rules are documented prose that has not been reduced to executable logic"` |
| `PolicyTestsPage.tsx` | `"The remaining rules are documented prose and always evaluate to NOT_APPLICABLE"` |

A reader of any of these concludes the extraction produced something unusable.

**What the flag actually reports:** no fact model maps the document's wording
onto attributes the deterministic engine can read. It says nothing about
whether the policy is clear, complete, or evaluable by the LLM that runs it —
and by that measure 40 of these 47 rules are `decidable`.

### The structural cause

`CandidateRow.tsx`, `PolicyRow.tsx` and `RuleDiffRow.tsx` each carried a
**byte-identical** five-line block, tooltip included:

```tsx
{!rule.machine_executable && (
  <Tooltip title="Manual rule — not machine-executable">
    <ToolOutlined className="policy-row-flag" />
  </Tooltip>
)}
```

Three copies of one sentence is three places for a correction to be applied
twice. That is how the wording drifted from the flag's meaning in the first
place.

### The fix

One vocabulary in `apps/web/src/ruleExecutability.ts`:

```typescript
export const DETERMINISTIC_LABEL = {
  yes: "Deterministic engine ready",
  no: "Needs a fact mapping",
} as const;

export const DETERMINISTIC_REASON =
  "No fact model maps this rule's terms onto attributes the deterministic " +
  "engine can read, so it returns NOT_APPLICABLE before looking at any " +
  "scenario. That is a configuration gap on our side, not a judgement about " +
  "the policy.";
```

and one component, `ExecutabilityBadge` / `ExecutabilityFlag`, which renders
the flag **beside** `decision_readiness` so the two answers cannot separate
again.

---

## 3. The prompts taught the same error to the models

`src/policy_platform/infrastructure/policy_tests/ai_test_proposal.py`:

```python
# BEFORE
"A rule with machine_executable=false is documented prose that has not been \
reduced to executable logic ... say plainly in each description that the rule \
is not machine-executable yet."
```

So every AI-generated test description carried the misreading into the product.

`src/policy_platform/infrastructure/ai_scenario_engine.py`, shown to the user
verbatim:

```python
# BEFORE
"This is not a failed policy decision. The published rule is documentation-only "
"(machine_executable=false), so the deterministic evaluator returns NOT_APPLICABLE "
"before reading scenario facts."
```

### The fix

Both now receive `decision_readiness` and are told to name the missing fact
mapping rather than call the policy vague:

```python
# AFTER (ai_test_proposal.py)
"machine_executable=false means only that no fact model maps this rule's terms \
onto attributes this engine can read. It does NOT mean the rule is vague, \
documentation-only, or unusable: the same rule may state its subject, its \
threshold and its approver completely, and be decided correctly by an LLM \
reading it against a case. Each rule carries a "decision_readiness" object \
saying which of those it is — read it, and describe the rule accordingly."
```

---

## 4. Two populations shown side by side as if comparable

`ReviewQueue.tsx` operations strip:

```
Decision progress      0%     0 of 47 decided
Related families        3     25 of 38 stand alone
```

47 and 38 sit adjacent and read as the same denominator. They are not:

```tsx
<small>{reviewedCount} of {totalCandidates} decided</small>       // all candidates
...
? `${unfamiliedCount} of ${filteredCandidates.length} stand alone` // the filtered page
```

**Fix:** both now use `totalCandidates`.

---

## The pattern across all four

Each began as a reasonable default:

* `|| "Always"` — a fallback for the empty case
* `? "Executable" : "Documentation only"` — a readable label for a boolean
* `filteredCandidates.length` — the list the component already had

None was written as an assertion. Each became one the moment it was rendered
next to real data, because a user reads a label as a **claim about the rule**,
not as a rendering convenience.

The check that catches this class: **read the string out loud as a sentence
about the specific rule on screen, and ask whether the document supports it.**

* "This housing allowance rule applies always." — the document says *for
  administrative, technical and service staff*.
* "This rule is documentation only." — the document states a subject, a
  threshold and an approver.

Both fail that test immediately. Neither failed a type check, a lint, or a
test suite.
