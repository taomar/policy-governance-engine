# Failure reports

Written from the running system against the AD-103 Benefits Policy corpus (47
rules), not from memory. Every figure is reproducible with the queries given at
the end of each document.

| Document | What it covers |
|----------|----------------|
| [`execution-and-linkage.md`](execution-and-linkage.md) | Why 0 of 47 rules execute, why 18 are unlinked, and which blockers are fixable here |
| [`validators-that-could-not-fail.md`](validators-that-could-not-fail.md) | Four checks that shipped reporting success while being structurally unable to report anything else |
| [`duplicate-detection.md`](duplicate-detection.md) | Three attempts at one check; the first merged two real rules, the second hid two real duplicates |
| [`display-overclaims.md`](display-overclaims.md) | Where the UI stated something the data did not, including `WHEN Always` on conditioned rules |
| [`designed-pipeline-and-running-pipeline.md`](designed-pipeline-and-running-pipeline.md) | Nine designed extraction stages, two reached; why ten dead subsystems are one fact, and the order they depend on |
| [`rotated-cell-content-loss.md`](rotated-cell-content-loss.md) | A provision lost in a rotated merged cell; three mechanisms behaved correctly and the content still vanished |

---

## The state in one table

| | |
|---|---|
| rules extracted | 47 |
| `machine_executable = True` | **0** |
| non-empty condition tree | **0** |
| DMN decision tables built | **0** |
| `required_facts` across all rules | **0** |
| rules whose source states a condition | 21 |
| rules whose condition compiled | **0** |
| | |
| rules with `related_rule_ids` | 29 |
| edges (all reciprocated, none dangling) | 76 |
| connected components > 1 | 5 (sizes 11, 10, 3, 3, 2) |
| isolated rules | 18 |
| rules with a `group_label` | 12 |
| | |
| `decidable` (LLM evaluation) | **40** |
| parties extracted | 15 (7 authorities) |
| extraction targets emitted | 132 |
| | |
| faithfulness: `condition_not_compiled` | 5 (warning) |
| faithfulness: `duplicate_rule` | 2 (warning) |
| faithfulness: blocking | **0** |

Two of those numbers look contradictory and are both true. **0 of 47
executable** answers *"can our deterministic FEEL engine decide this?"* — it
cannot, because no fact model is configured. **40 of 47 decidable** answers
*"can an evaluator decide this against a customer's case?"* — mostly yes.
Reporting only the first is what made the extraction look broken when it is
mostly not.

---

## What cannot be fixed in this repository

1. **`trusted_config = {}`.** No fact model exists for this policy set.
   Supplying one requires the customer's data model. Inventing
   `university.financialPosition = "good"` would assert both a schema this
   platform cannot see and a threshold the document never wrote.

2. **28 of 30 conditions state no test.** *"depending on the financial position
   of the University"*, *"for specific cases that the university deems
   necessary"*, *"In all cases"* — the document delegates rather than
   specifies. A fact model supplies the attribute; it cannot supply a
   comparison the policy declined to write.

Everything else on the list is fixable here.

---

## The one lesson that generalises

Four validators and four display strings failed the same way: **each asserted
more than its evidence supported, and each looked correct until read against
real output.**

None was caught by a type check, a lint, or a passing test suite. Every one was
caught by reading actual output and asking whether the sentence on screen — or
in the finding — was true of the specific rule in front of it.

Counting findings hides this. Reading five findings does not.
