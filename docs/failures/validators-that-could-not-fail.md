# Four validators that could not fail

Each of these was written to catch a specific defect, shipped reporting
success, and was found to be structurally incapable of reporting anything
else. They are recorded together because the pattern repeated four times in
one body of work, which means it is not carelessness — it is a shape that is
easy to write and hard to see.

**The shape:** a check compares a value against a surface that already
contains that value, or derives its expected value from the record it is
auditing. It then reports agreement, which was guaranteed.

---

## 1. A regex that could never match

**File:** `src/policy_platform/infrastructure/quality/policy_faithfulness.py`
**Check:** `check_quantities_preserved`

```python
# BROKEN
_QUANTITY_RE = re.compile(r"(\d+(?:\.\d+)?\s*(?:%|percent|days?|months?|years?|SAR|USD))\b")
```

The alternation ends with `\b`. When the match ends in `%`, the next character
is a space — and `%` and space are **both non-word characters**, so no word
boundary exists between them. `\b` fails, the match fails.

Every percentage in every document went unchecked. The check reported success
on all of them.

**Live impact:** the source `"Annual increase which shall not exceed 10% of the
employee's current basic salary"` produced a rule with no 10% anywhere, and the
quantity check said nothing.

**Fix:** drop the trailing `\b` and anchor on the unit instead.

**Caught by:** writing the test. Never by running the pipeline, because a check
that always passes is indistinguishable from a codebase with no defects.

---

## 2. A surface containing the field being checked

**Check:** `check_conditions_represented`

```python
# BROKEN
surface = _rule_surface(rule)          # includes canonical.rule.condition
if stated.lower() in surface.lower():
    return None                        # "nothing was lost"
```

`stated` **is** `canonical.rule.condition`. `_rule_surface` included that same
field. The check compared the text against itself and returned `None` every
time.

**Fix:** `_rule_surface(rule, include_stated_condition=False)`.

---

## 3. A surface containing the note about the loss

Same check, after fix #2. Still reported **0 findings across 47 rules** while
three housing-allowance rules visibly displayed a lost condition.

`_rule_surface` still included `description`, and `formulation_mapping` appends
a provenance note to every description:

```
[Conditions: conditions_not_projected — The source states conditions, but they
 could not be projected into executable bindings: 'for administrative,
 technical and service staff'. The rule must not be treated as unconditional —
 a reviewer must supply the missing mapping.]
```

The note quotes the very condition it reports as unprojected. So the condition
was found in the surface every single time.

**The note written to make the loss legible is what made the loss invisible.**

**Fix:** `include_description=False`.

**Result:** the same corpus, unchanged, went from 0 findings to 5.

**Verified by deliberately reintroducing the bug:**

```
--- with the bug reintroduced ---
FAILED  test_the_lost_condition_is_reported
FAILED  test_the_note_alone_does_not_count_as_carrying_it
2 failed, 14 passed
--- restored ---
16 passed
```

A regression test that has not been seen to fail is not evidence.

---

## 4. A check that read its expected value from the record it audited

Same check again, and the deepest version. After fixes #2 and #3 it correctly
reported 5 findings — but every one carried `severity="blocking"` and the
message:

> "The rule would apply unconditionally."

That is **false**. All five conditions survive:

* verbatim in `formulation.canonical.rule.condition`
* derived on read into `decision_readiness.required_attributes`
* derived on read into `xacml_view.source_semantics.conditions`
* displayed in the Logic view and every rule row

and the evaluator's vacuous guard stops an empty `all` matching anything, so
nothing applies unconditionally anywhere.

The structural problem is worse than the wrong message:

```python
stated = _normalize(policy_rule.condition if policy_rule else "")
if not stated:
    return None          # <-- a genuinely lost condition exits here, silently
```

The check reads the condition it compares against **from the canonical
record**. So it can only fire when the condition is present. A condition that
was genuinely lost leaves that field empty, and the check returns `None`
without a word.

**It was structurally incapable of detecting the thing its name claimed.**

Unlike #1–#3, the self-reference here is in the *choice of input*, not in a
text comparison — which is why it survived three previous rounds of fixing the
same function.

**Fix:** split into two checks that ask different questions.

```
condition_not_compiled          warning    source states a condition, no fact
                                           model compiles it, condition IS
                                           preserved and ships with the rule

source_condition_not_captured   blocking   source uses conditional language and
                                           the canonical decomposition recorded
                                           NO condition, prerequisite, trigger,
                                           temporal_constraint, constraint,
                                           exception or location at all
```

The second reads `canonical.source_text` — the actual lossy step — and asks
only whether *something* conditional was captured. Never what the test should
be: deciding that would manufacture policy the document did not write.

**Proof it can fire**, on six constructions:

```python
"The allowance is paid if the employee has completed the trial period."
"Paid unless the contract states otherwise."
"Paid subject to the approval of the President."
"Paid depending on the financial position of the University."
"In the case of a married couple, the allowance is halved."
"Paid provided that the receipt is submitted."
"Paid only if the employee is full time."
```

**And proof it stays quiet** where it should — `"provided"` as a past
participle:

```python
"Furnished housing provided by FBSU is available."   # not conditional
```

Only `"provided that"` counts. Without that anchor the check would fire on most
benefit sentences in the corpus, which is the false-alarm rate that teaches
reviewers to skip a category entirely.

---

## The related failure: severity inflation

Not a dead check, but the same family of error — a finding that says more than
the evidence supports.

The first negation check flagged any `"not"` in the first half of the source:

```
"In clinics that are NOT approved by the insurer, the receipt shall be
 submitted to HR"
```

The negation is inside a **condition**. The obligation is real. Six findings,
three of them false — **50% precision**.

A check that cries wolf half the time trains reviewers to ignore it, leaving
true inversions *less* visible than before the check existed.

**Fix:** require the action to be the negated phrase with the negation
stripped. **6 findings -> 1**, and the one left is the true inversion:

```
source: "Annual increase which shall not exceed 10% of the employee's current
         basic salary"
rule:   effect REQUIRE_ACTION, action "exceed 10% of the employee's current
         basic salary"
```

An instruction to do the forbidden thing.

---

## The rule this produced

> **A validator must be shown failing on a real defect before its passing
> result means anything.**

Concretely, before trusting any new check:

1. **Write the failing case first**, from real output, not an imagined one.
2. **Reintroduce the bug** and watch the test fail. #3 above was only proven
   this way.
3. **Read the findings, do not count them.** #4's wrong severity and the
   negation check's 50% precision were both invisible in a count and obvious in
   a list of five.
4. **Ask what the check reads.** If its expected value comes from a field
   derived from the thing it audits, it cannot fail. That is #2, #3 and #4.
5. **Check the silent direction too.** A check that returns `None` on the
   condition it exists to catch is worse than no check, because it occupies the
   slot where a working one would go.

Any comparison of derived text against source text should be treated as
suspect until item 2 has been done.
