# Route vocabulary: the names that were retired and the framings that keep escaping

This document exists because writing it anywhere else breaks the build.

Two guards scan every Markdown file under `docs/` except this directory:

| guard | rejects |
|---|---|
| `tests/unit/test_no_readiness_framing.py` | the retired route names, anywhere in prose |
| `tests/unit/test_no_route_framed_as_a_shortfall.py` | a sentence naming a route and a shortfall together |

`docs/failures/` is excluded from both, and its exclusion comment says why:
*recording retired wording is its purpose*. So the retired names and the
forbidden framings are written out here, once, and everything else links to
this file instead of repeating them.

---

## 1. The two routes

| route | how a case is decided | verdict |
|---|---|---|
| Deterministic | the deterministic engine computes the comparison | exact |
| AI Ready | an LLM judge reads the rule against the case | verdict with confidence |

`AI Ready` exists so that a rule whose test is language can still be decided.
It is not a holding pen, not a backlog, and not an unfinished Deterministic
rule. Live counts are 670 AI Ready and 7 Deterministic: the judged path is the
product, not the exception.

---

## 2. The retired names

Settled by the user. Do not re-litigate.

| use | retired |
|---|---|
| `AI Ready` | `Decided by reading` |
| `Deterministic` | `Human Judgment Requirement` |

Only guard test files and this document may still contain the retired strings,
because they assert against them.

---

## 3. The framing that keeps escaping

`AI Ready` is a route. Copy must never present it as a deficiency, a gap, a
limitation, or something the engine "cannot" do.

**Seven phrasings evaded the guards in one session.** Assume yours is the
eighth. Mutation-test it: inject a bad phrasing, watch the guard fail, then
restore it. A guard nobody has seen go red is not known to work — that is the
same failure recorded in `validators-that-could-not-fail.md`.

### Three consequences people keep getting wrong

1. **Empty `required_facts` on an AI Ready rule is not a gap.** Its test is
   words, so there are no named quantities to list. A table pairing it with a
   Deterministic rule's fact list manufactures a deficit out of a route.
2. **`decision_readiness` is `null` on all 2062 rules.** Do not build a surface
   that mirrors it uncritically.
3. **"No test" on an AI Ready rule** means no scenario has been put to the judge
   yet. It does not mean the rule is untestable.

---

## 4. What the guards cannot catch

Both guards match on phrasing and are blind to polarity. A sentence that names
a route and a shortfall word is rejected **whether it asserts the framing or
denies it**, so the sentence "AI Ready is a route, not a fault" is rejected by
the guard that exists to enforce exactly that claim.

This was found when `docs/HANDOVER.md` was committed and turned the suite red:
2 failed, 3141 passed. The handover was written to warn about these guards and
was rejected by both of them.

Two things follow:

- Prose that must discuss the forbidden framing belongs here, not in `docs/`.
  That is what this directory is for, and it needs no change to either guard.
- Teaching the guards to read negation was considered and rejected. It would
  mean matching a vocabulary of negations, which is the approach that already
  failed elsewhere in this repository for not surviving Arabic. A guard that is
  over-eager and has a documented escape hatch is safer than a guard that is
  clever and wrong in a language nobody tested it against.

`test_no_route_framed_as_a_shortfall.py` also carries a one-entry allowlist,
`_QUOTED_TO_FORBID_IT`, keyed by a fingerprint of the sentence so that editing
the sentence re-triggers review. It is deliberately minimal and holds a system
prompt line that has to spell the framing out in order to forbid it. Adding
documentation to it would grow an allowlist where a directory exclusion already
does the job.

---

## Reproducing

```powershell
$env:PYTHONIOENCODING='utf-8'
.\.venv-graph\Scripts\python.exe -m pytest -q `
  tests/unit/test_no_readiness_framing.py `
  tests/unit/test_no_route_framed_as_a_shortfall.py
```

To see a guard go red before trusting it, paste one of the retired names from
section 2 into any `docs/*.md` file outside this directory, run the command
above, then remove it.
