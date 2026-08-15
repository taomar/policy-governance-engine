# What the shared components must accept to serve a published record

The Policies page now renders published records as whole policies, read-only. It
does so through three files it had to write for itself — `publishedPolicyCards.ts`,
`PublishedPolicyCard.tsx`, `PublishedRecordActions.tsx` — because the equivalents
on the Review side are bound to `CandidateRule`.

**Those three files exist to be deleted.** Each item below removes one of them, or
part of one. They are a second copy of Review's logic, and a second copy is exactly
the drift this work was closing. The longer they live the more they diverge.

The rule that governs every item: **editability is a property of the record, not an
argument.** `candidateEditability(status)` already answers it. A component that
takes `canReview` or infers editability from whether an `onApprove` was passed can
be made to offer a decision on a sealed record by wiring it wrongly. One that reads
the record's own status cannot.

---

## 1. `policyCards.ts` — owner: `dev-rulename`

This is the largest item and the one that deletes the most duplicate code.
`publishedPolicyCards.ts` is a transliteration of this file with `CandidateRule`
swapped for `CanonicalRule`. Everything else — the placement partition, the
ordering, the `hiddenByFilter` accounting — is the same algorithm written twice.

**1.1 Widen `PolicyCardRule` so it does not name a candidate.**

```ts
// now
export interface PolicyCardRule {
  candidate: CandidateRule;
  // ...
}

// wanted
export interface PolicyCardRule {
  /** The rule as the record states it. Both a candidate and a published row
   *  carry one; nothing above this line needs to know which it came from. */
  rule: CanonicalRule;
  /** Identifies the rule within its version. */
  ruleId: string;
  /** Drives `candidateEditability`. `"candidate"`, `"published"`, and so on. */
  reviewStatus: string;
  /** The row this rule was read from, when the caller has one — the candidate
   *  id on the review side, the approved-rule id on the published side. Used
   *  for Copy ID and View history, never for deciding what may be done. */
  recordId?: string;
  evaluationMode?: string | null;
}
```

Keep a `candidate?: CandidateRule` field if the review side still needs the fuller
row; the point is that no consumer may *require* it.

**1.2 `buildPolicyCards` and `unplacedCandidates` follow the widened type.**
Both are already pure functions of `(policies, rules)`. Rename `unplacedCandidates`
to `unplacedRules` — a published row is not a candidate, and the name is the only
thing stopping the published page calling it.

**1.3 `sharedRuleFacets` reads `evaluationMode` off the card rule, not off the
candidate.** Note the shape: on `AssembledPassage`, `rules` is a list of objects
`{rule_id, evaluation_mode}` — the mode lives on the *passage entry*, not on the
rule. `publishedPolicyCards.ts:222` shows the join.

**1.4 `policyTitle`'s fallback path takes the widened rule.** It currently reaches
`candidate.rule` to derive a name from the rules themselves when a policy has no
heading. Reaching `PolicyCardRule.rule` instead deletes `publishedPolicyTitle`
outright.

**1.5 `policyJsonDocument` likewise.**

**When 1.1–1.5 land, `apps/web/src/publishedPolicyCards.ts` can be deleted in full**
and `PoliciesTab.tsx` switched to `buildPolicyCards`. That is roughly 270 lines of
duplicate logic gone.

---

## 2. `PolicyReviewCard.tsx` — owner: `dev-rulename`

**2.1 Derive editability from the record.** The card currently decides whether to
draw Approve/Reject from whether `onApprove`/`onReject` were passed. Read
`candidateEditability(rule.reviewStatus).canReview` instead, and treat the handlers
as *how* to do it rather than *whether* it may be done. A published record then
cannot render a decision control even if a caller passes handlers by mistake.

**2.2 Render the composition line.** How many of a policy's rules decide an outcome
and how many define a term. `publishedPolicyCards.ts` has `policyComposition` and
`policyCompositionLabel`; move both into `policyCards.ts` and call them here.
`policyCompositionLabel` returns `null` when one side is zero — a policy whose rules
all decide should say nothing rather than say "and 0 define".

**2.3 Accept a selection slot rather than owning the checkbox.** Review selects to
approve in bulk; Policies selects to export. Same affordance, different verb. Let
the caller supply the control and the label.

**2.4 Accept an actions slot** for the kebab (see item 5).

**When 2.1–2.4 land, `PublishedPolicyCard.tsx` can be deleted** and `PoliciesTab`
render `PolicyReviewCard` directly.

---

## 3. `RuleName.tsx` — owner: `dev-rulename`

Generated rule names are absent on the Policies page today, and that is the single
most visible remaining parity gap.

`RuleName` requires a `candidateId`. A published rule has none — it has a rule id
and a version id. Either:

- key the lookup by `{ruleId, versionId}` with `candidateId` as one of the keys it
  accepts, **or**
- have it render nothing when it cannot resolve a name, so a published card degrades
  to the statement rather than crashing.

Both are acceptable; the first gives parity, the second only prevents a break.

Whichever is chosen: the generated name must stay display-only and must never enter
the exported record. The published page exports JSONL, so a name that leaked into
`policyJsonDocument` would leave the app and become someone's input.

---

## 4. `PolicyLogicTable.tsx`, `policyLogic.ts`, `policyLogicShape.ts` — owner: `dev-logicviz`

The published Logic tab currently renders one `RuleCard` per rule. That is the
endorsed logic-tree idiom — it is what `EditRuleModal`'s Live preview draws — so it
is correct, but it is not the policy-level logic view Review has.

`PolicyLogicTable` takes candidate-shaped cards. Once item 1.1 lands, take
`PolicyCardRule` and the published page gets the policy-level logic view for free.

No other change needed: the table reads condition, outcome, and attributes, all of
which are on `CanonicalRule` already.

---

## 5. `RecordActionsMenu.tsx`, `PolicyInspector.tsx`, `RuleDetailInline.tsx` — owner: `dev-onedetail`

**5.1 `RecordActionsMenu` grows a read-only arm.** For a record whose
`candidateEditability(status).canEdit` is false, the menu is exactly:

- **Revise** — starts a revision. Present only when the version is active.
- **Copy ID**
- **View history**

and no others. `PublishedRecordActions.tsx` is that arm, written standalone; it is
about 90 lines and folds in whole. It already derives from `candidateEditability`
and defaults its status to `"published"`. Its `data-testid` is `record-actions`,
matching yours, so the published page's tests will keep passing through the swap.

Argument for keeping Revise in a read-only menu, since it looks like an editing
affordance and is not: a published version is immutable, and the server's own
`editBlockedReason` names starting a revision as the route. A revision writes a new
record; an edit would rewrite what a version already promised. The user endorsed
Revise on this page explicitly. `publishedRecordOffersNoDecision.test.tsx` asserts
both "no decision controls" **and** "Revise survives", so neither can be satisfied
by breaking the other — please keep both assertions green.

**5.2 `PolicyInspector` and `RuleDetailInline`: `Reading | Logic` and in-place
detail.** The published card implements both itself. Once the shared components take
`PolicyCardRule`, that implementation should be dropped in favour of yours.

**5.3 The inspector must not offer a decision.** It is reachable from both pages. It
should read `candidateEditability` for what it draws rather than be told.

---

## 6. `AskAboutRuleModal.tsx`, `PolicyAskAiButton.tsx` — owner: `dev-asklang`

The published page draws `PolicyExplainButton` at policy scope. It does **not** draw
Ask AI at either scope, because both entry points are candidate-bound.

Needed: rule scope and policy scope on a published record, keyed by rule id +
version id rather than candidate id, with the En/Ar toggle unchanged. Nothing about
the answer differs — the grounding passages are the same passages.

---

## 7. `api.ts` — owner: `dev-rulename`

Add beside `listPolicies`:

```ts
export async function listVersionPolicies(
  policySetKey: string,
  versionId: string,
): Promise<AssembledPolicy[]>
```

`GET /api/policy-sets/{key}/versions/{version_id}/policies` — already on the server,
in `policy_sets.py`, returning the same payload shape as the candidate-side
`GET /{key}/policies`.

`publishedPolicyCards.ts` currently duplicates `API_BASE_URL` and calls `fetch`
directly, only because it could not edit `api.ts`. That duplication is a second
place for the base URL to be wrong. It disappears with this function.

---

## Order of work

Item 1 unblocks 2 and 4 and is worth doing first. Items 3, 5, 6, 7 are independent
of it and of each other.

Nothing here is blocking: the Policies page works today. Every item removes a
duplicate rather than fixing a break, which is precisely why they are easy to defer
and why deferring them is what produced the drift in the first place.

---

# Addendum — items 8 to 11, added after the eight-tab work

Items 1 to 7 above were written when the Policies page was being brought level
with Review. These four were found while giving a *policy* the same eight-tab
information surface a *rule* has, on both surfaces. Same rule as before: each is
a duplicate that exists only because the file could not be edited, or a contract
another agent owns.

## 8. `api.ts` — owner: `dev-rulename` — move the History client, do not write it

**Status changed. This is no longer "write a function"; it is "move one."** The
History tab shipped and is rendering real sightings on both surfaces today, so
the ask here has shrunk to removing a duplicate base URL.

**What exists now**, in `apps/web/src/publishedPolicyCards.ts`:

```ts
async function getJson<T>(path: string): Promise<T>          // ~line 38
export async function listProvisionHistory(
  policySetKey: string,
  provisionKey: string,
): Promise<PolicySightingView[]>                              // ~line 90
```

It is called from `PoliciesTab.tsx` (`requestHistory`) and `ReviewQueue.tsx`
(`requestPolicyHistory`), lazily, when the History tab is opened.

**What is still wanted:** `getJson` is a second copy of what `request` (line 68)
already does with `API_BASE_URL` (line 9), both module-private. Export a generic
GET from `api.ts`, or move `listProvisionHistory` into it, and delete the copy.
That is item 7's duplication, one instance of it, with a caller already attached.

**Correction to what this document said before.** The field names previously
printed here — `effective_from`, `rule_count`, `rules_changed` — **were wrong.**
They came from the design, not from a response. The server sends:

```ts
{ version_id, version_number, is_active, approved_by, approved_at,
  heading_path, change, rules: { rule_id, title, fingerprint }[],
  rules_added, rules_removed, rules_reworded }
```

The invented names cost a runtime crash that no test on either side caught,
because each side tested against its own idea of the shape. Two guards now
prevent a repeat: `tests/unit/test_provision_history.py` compares the endpoint's
emitted key names against the fields the pane declares **in both directions**,
and `policyPanesTellTheTruth.test.tsx` renders a fixture recorded from a live
response. **If you move this function, do not retype the interface** — import
`PolicySightingView` from `policyTabPanes.tsx`, or the Python guard will fail
and it will be right to.

`null` must keep meaning *never asked*: a failed load must not become `[]`,
because `[]` is a claim that no other version exists.

**The call needs `provision_key`, not the policy's row id.** A policy is a key
seen at a version; `document_provisions.id` belongs to one document version and
cannot follow a policy across a re-extraction. `AssembledPolicy.key` is the right
argument.

## 9. `api.ts` line ~1717 + `schemas.py` line ~349 — notes are rule-bound

**What is needed:** widen the note entity union at both ends so a note can name a
policy.

- `schemas.py:349` — the Pydantic `Literal` listing note entity types.
- `api.ts:1717` — the TypeScript union that mirrors it.

Both are literal unions over an existing column. **No migration is needed** — the
column already stores a string.

**Why it matters:** Notes is the one tab of the eight not built, and it is not
built because there is nowhere to put a policy-scoped note. The cost of leaving
it is not a missing tab; it is that a reviewer who wants to record something
about a policy has to attach it to one of its rules, which makes the note look
like a remark about that rule to everyone who reads it afterwards. That is a
silent misattribution, so the tab was left out rather than faked.

## 10. `PolicyReviewCard.tsx` — owner: `dev-rulename` — two items

**10a. `onSelectRule` — blocks a request the user has made three times.**

The producer's Job 2 ("rules are not clickable any longer") cannot be completed
from `ReviewQueue.tsx`. The card has no such prop, so passing one is a TypeScript
excess-property error. The contract, matching what the queue already has wired:

```ts
onSelectRule?: (rule: CanonicalRule) => void;
```

Called with the rule the reader clicked. `ReviewQueue` will pass
`selectCandidateRule`, which already exists and already opens the right-hand
panel. `PublishedPolicyCard.tsx` implements the same prop today and is a working
reference, including the in-place expansion the user asked for: the control reads
`Open rule` / `Hide rule`, expands the detail inside the card, and selects the
rule for the panel in the same click — no second destination, nothing to click
back from.

**10b. Line 523 says something that is no longer true.**

`hiddenByFilter` renders "N rules outside the current filter". The content-kind
filter was deleted in `4fa7286`, so nothing is filtering.

**Do not delete the mechanism — the count is still real.** `hiddenByFilter` is
`policy.rule_count - flat.length`, which stays positive when a rule was
superseded or when its record was not among those loaded. Only the sentence is
wrong. Both call sites in files I own now name supersession and unloaded records
instead. Note an existing test asserts the literal phrase "more rules of this
policy", so keep those words.

## 11. `policyCards.ts` — owner: `dev-rulename` — one serialiser, one bridge

`policyJsonDocument(card: PolicyCard)` is the only serialiser and must stay the
only one, so the published surface reaches it through
`publishedPolicyJsonDocument` in `publishedPolicyCards.ts`, which builds a
`PolicyCard`-shaped object and casts.

**The coupling is real and worth removing:** the bridge supplies
`candidate: { rule }` and nothing else. If the serialiser ever reads another
candidate field, the published JSON silently gets `undefined` for it. Two tests
guard the shape — every rule present, and `toBe` identity on each rule object —
but they cannot guard a field that does not exist yet.

**The fix:** give `policyJsonDocument` a `PolicyRecordView`-shaped parameter
(`{ policy, passageCount, rules: { rule_id, rule }[] }`, exported from
`policyTabPanes.tsx`), which both surfaces already build. The bridge then
deletes. This is the same parameterisation that let one set of panes serve both
surfaces; the serialiser is the last thing still shaped like one of them.

## 12. `RuleDetailInline.tsx` line ~262 — owner: `dev-onedetail` — one tab, one name

**One line.** Replace the literal `"Parties & readiness"` with the exported
constant:

```ts
import { PARTIES_AND_ROUTES_TAB_LABEL } from "./policyTabPanes";
...
label: PARTIES_AND_ROUTES_TAB_LABEL,
```

**Why it is worth a change to your file.** That tab had three spellings across
three components. Two said "Parties & routes"; yours and the rule inspector's
still said "readiness". The inspector is fixed. Yours is the last, and while it
stands, the same rule opened two ways shows two different tab names — which
reads as two different tabs holding two different things.

The word is not cosmetic. "Readiness" invites the reader to score a rule decided
by reading its source against one decided by computing a comparison, as if the
first were an incomplete version of the second. Both are routes to a decision.
`ai_ready` is a route, not a fault, and a tab label is the most-read copy on the
surface.

**`ruleTabsOpenInsideTheRow.test.tsx` line 79 pins the old string** in its
`EVERY_TAB` list, so that literal changes with it — and is better read from the
same constant, so the list can never again agree with a spelling it was copied
from.
