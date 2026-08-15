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
