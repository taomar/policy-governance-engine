# Duplicate detection: three attempts, two of them wrong

**Defect:** one source sentence produced two candidate rules, twice, in a
47-rule corpus. Neither was reported.

This is written up because the first two fixes were *plausible* and *wrong in
opposite directions*, and the reason they failed generalises well beyond
duplicate detection.

---

## The data

Two sentences each produced two rules:

```
AI-93357d4ac0  ==  AI-ee1e836e37
   " The housing allowance is limited to one employee of the married couple"

AI-fd9b0bdcf2  ==  AI-de9a6b2457
   "The housing allowance is to be paid in monthly prorated installments."
```

The decompositions differ:

```
AI-93357d4ac0   subject: "The housing allowance"  predicate: "is limited to"
                object:  "one employee"           condition: "of the married couple"
                action:  "is limited to one employee"

AI-ee1e836e37   subject: "The housing allowance"  predicate: "is limited to"
                object:  "one employee of the married couple"
                action:  "is limited to one employee of the married couple"

AI-de9a6b2457   object:  "in monthly prorated installments"
                frequency: "monthly"   calculation: "prorated"

AI-fd9b0bdcf2   constraint: "prorated installments"
                frequency:  "monthly"
```

Same content. Different slots. Same run of the same agent.

Nearby, and critical to get right, are three rules that are **not** duplicates:

```
AI-c4c43499ce   object: "Fifteen thousand (15,000) SAR"
                condition: "for administrative, technical and service staff"

AI-98ff28dc85   object: "Fifteen thousand (15,000) SAR"
                condition: "for full time lecturers, instructors, assistant
                            instructors, research and teaching assistants..."

AI-f77f375894   object: "Twenty-five thousand (25,000) SAR"
                condition: "for full-time faculty members holding the rank of
                            Assistant, Associate or Full Professor"
```

Two share an identical `object`. Only the condition separates them.

---

## Attempt 1 — key on subject + predicate + object + action

```python
key = (subject, predicate, object, effect.action)
```

**Result: 1 finding, and it was a false positive.**

```
AI-c4c43499ce  "states the same thing as"  AI-98ff28dc85
```

Those are the two staff-category rules. The key dropped `condition` — the only
field that distinguishes them. **Dropping the field that carries the
distinction is precisely the failure this whole body of work exists to catch,
reproduced inside the check meant to catch it.**

Both genuine duplicates were missed.

---

## Attempt 2 — add the condition

```python
key = (subject, predicate, f"{object} {condition}", effect.action)
```

Joined rather than compared as separate fields, so that
`object="one employee" + condition="of the married couple"` and
`object="one employee of the married couple"` produce the same string.

**Result: 0 findings.** False positive gone; both real duplicates still missed.

The reason was `effect.action`, which is **derived** from
subject/predicate/object. Including it double-counts them — and a difference in
that derivation was enough to mask the pair:

```
AI-93357d4ac0   action: "is limited to one employee"
AI-ee1e836e37   action: "is limited to one employee of the married couple"
```

Removing the action gave **1 finding**: the married-couple pair, correctly.
The prorated-installments pair was still missed, because its content had moved
into `constraint` and `frequency`, which the key did not read.

---

## Attempt 3 — stop naming fields

The failure in attempts 1 and 2 is not that the *right* fields were left
unnamed. It is that:

> **A slot assignment is a judgement the formulator makes per run, so no fixed
> list of slots is stable across runs.**

Naming more fields keeps losing the same race. The fix is to stop reading slots
and read content:

```python
def _content_signature(policy_rule) -> str:
    dumped = policy_rule.model_dump(exclude_none=True)
    for field in ("rule_type", "source_origin", "subject", "predicate", "modality"):
        dumped.pop(field, None)
    words = _normalize(" ".join(str(v) for v in dumped.values())).lower().split()
    return " ".join(sorted({w for w in words if w not in _SEAM_WORDS}))

key = (subject, predicate, _content_signature(policy_rule))
```

**Result: 2 findings — both genuine pairs, no false positive.**

### Why each part is there

**`subject` and `predicate` stay separate.** Folding them into the bag would
let `"A limits B"` and `"B limits A"` collide. They anchor who-does-what while
everything else is read slot-agnostically.

**Seam words are stripped:**

```python
_SEAM_WORDS = frozenset({
    "a", "an", "the", "of", "in", "on", "at", "and", "or", "as", "for",
    "its", "their", "this",
})
```

These appear or vanish purely because of *where a phrase was cut*. When a
clause boundary falls mid-sentence the same content redistributes across slots
and gains or loses a connective at the seam — `"in monthly prorated
installments"` against `"prorated installments"` + `"monthly"`. The content
words are identical; only the joinery moves.

**Meaning-inverting prepositions are deliberately kept** — `by, to, from,
before, after, without, not`. `"paid by HR"` and `"paid to HR"` name different
parties, and collapsing them would report two real rules as one copy. The
listed seam words cannot carry that distinction on their own: whatever they
attach to survives as a content word either way.

**Exact set equality only — never an overlap threshold.** Two rules sharing
most of their words are not evidence of anything, and a check that guesses adds
a second source of error to the one it was meant to catch.

---

## The root cause the check only reports

Both duplicates trace to one thing: the clause splitter cuts mid-sentence.

```sql
SELECT id, left(text, 96) FROM clauses WHERE btrim(text) ~ '^[a-z(]';
```
```
5d2297cd  | the monthly basic salary up to a maximum of:
7b08d2bc  | (husband and wife). In the case of a married couple are employed by FBSU
```

The second is the tail of:

> "The housing allowance is limited to one employee of the married couple
> **(husband and wife). In the case of** a married couple are employed by
> FBSU..."

Reading the orphaned half, the formulator correctly reconstructs the governing
sentence from inherited context — and produces a rule the preceding clause
already produced.

**2 clauses cut mid-sentence -> 2 duplicate pairs. Exact correspondence.**

The check **reports** rather than silently de-duplicates, because which copy to
keep depends on which clause carries the better evidence, and that is a
reviewer's decision.

---

## The platform's own fingerprint answers a different question

```sql
SELECT content_fingerprint, count(*)
FROM candidate_rules WHERE superseded_at IS NULL
GROUP BY 1 HAVING count(*) > 1;
```
```
(0 rows)
```

An earlier draft of this document treated that as a competing duplicate
detector that had gone blind. **It is not one.** `content_fingerprint` is a
cross-run delta identity: it hashes `SEMANTIC_FIELDS` to answer "is this the
same rule the previous extraction produced?", and it includes `effect`, which
is derived from subject/predicate/object. Two copies of one sentence that
decomposed differently legitimately hash differently.

The correct reading is that **no within-run duplicate check existed** before
`find_duplicate_rules`. The two coexist:

| | question | scope |
|---|---|---|
| `content_fingerprint` | is this the rule the last run produced? | across runs |
| `find_duplicate_rules` | did one sentence produce two rules? | within a run |

---

## Tests

Both directions are pinned, from live output:

```python
test_content_moving_between_slots_is_still_one_rule
test_a_seam_connective_does_not_make_two_rules
test_different_content_words_are_not_duplicates          # the false positive
test_a_meaning_inverting_preposition_is_not_a_seam_word  # "by" vs "to"
test_reversing_subject_and_predicate_is_not_a_duplicate
test_word_order_within_a_slot_does_not_matter
```

---

## The transferable lesson

Attempt 1 dropped a distinguishing field and merged two real rules.
Attempt 2 kept a derived field and hid a real duplicate.

Both were reasonable-looking keys over named slots. The generalisation is:

> When comparing records produced by a model that assigns content to slots by
> judgement, compare the **content**, not the slots — because the slot
> assignment is exactly the part that varies between runs.

The same reasoning applies to `check_source_conditions_reached_canonical`,
which accepts a condition in **any** condition-bearing field rather than
demanding `condition` specifically, for exactly this reason.
