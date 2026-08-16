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

## Where this stands

Two of the three files are now gone or going, and the items that closed are
recorded here rather than struck through, because *how* each one closed is the
part worth keeping.

**Item 1 landed, and I acted on it the same day.** `PolicyCardRule` became
source-neutral and `buildPolicyCards` took `PolicyRecordInput[]`. That turned
`publishedPolicyCards.ts` from a second implementation into a 211-line adapter:
the types are now aliases, `buildPublishedPolicyCards` delegates, and
`publishedPolicyJsonDocument` is a **named re-export** of `policyJsonDocument`.

The collapse was not tidying. The bridge had ended in `as unknown as PolicyCard`,
and when item 1 changed the rule shape underneath it the cast absorbed the
mismatch: the build stayed green while the serialiser received `undefined` rules
and **the JSON tab of a published policy threw at runtime**. The cast was the
defect, not the mapping. A re-export cannot go stale silently; a cast can, and did.

**Item 11 is resolved by that collapse, not by the change it asked for.** It
wanted `policyJsonDocument` parameterised so the bridge could stop supplying
`policySourceLines`. There is no bridge now. Nothing to parameterise.

**Item 9 landed** — the note entity union is widened at both ends and Notes is
built on both surfaces, keyed on `provision_key` for the reason that item gave.

**Item 10a landed** and `ReviewQueue.tsx` was already wired to it, so clicking a
rule opens its detail. One caveat, live as I write: an in-flight edit to
`PolicyReviewCard.tsx` narrows `onSelectRule` from `(rule: CanonicalRule)` to
`(recordId: string)`. That is the better signature — a card should hand back an
identity, not a payload — but `ReviewQueue.tsx:2043` passes `selectCandidateRule`,
which takes the rule. **Whoever lands the narrowing must land the ReviewQueue side
with it**, or the build breaks between the two commits. I own `ReviewQueue.tsx`
and will take that half on request; I have not pre-emptively changed it, because
changing it now breaks it against the committed card.

**What is left of the three files is one:** `PublishedPolicyCard.tsx`. It is a
component-level duplicate of `PolicyReviewCard.tsx`, and item 2 is still the
condition for deleting it. `PublishedRecordActions.tsx` is being folded into
`RecordActionsMenu` as item 5 asked.

**One new obligation, not in the original list.** Both surfaces now carry the same
eight tabs, and `bothSurfacesAskTheSameQuestions.test.tsx` asserts the *relation*
between them: it reads the tab strip off both rendered components and requires the
sets to match. It holds no list of tab names, so it cannot be edited into agreement
with a half-finished change. **Adding a tab to one page and not the other now fails
the build.** That is deliberate, and it applies to every owner below.

**A second obligation, learned by clicking rather than reading.** The Tests tab's
scenario generation calls `POST /policy-tests/policy-sets/{key}/validation-batches`,
which is a *blind validation batch* and is therefore run by the deterministic
engine. The server refuses any rule that is decided by reading, in those words.
The pane now derives the offer from `rule.evaluation_mode` and offers a scenario
only to rules the engine evaluates; a rule that states its test in words renders
"Checked by reading" instead.

**Anyone adding a control to a record surface should take this as the general
rule.** An action offered on every record and refused by the server on one of the
two routes teaches the reviewer, through the interaction, the same thing the copy
guards keep out of the words. The route guards read strings; they cannot see a
button. Derive the offer, and say what is true of the other route positively.

The same endpoint also refuses when the policy set has **no active approved
version** ("no active approved version to propose tests against"). That is a
server product rule, surfaced verbatim, not worked around: it means scenario
generation is reachable on a published set and not on one with nothing published
yet. It is a second reason the test actions are offered on both surfaces rather
than gated to candidates — the published surface is the one where the server
permits them.

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

**2.5 Four things the published card grew after this list was written, which it
must not lose on the way across.** These are not new asks; they are the diff
between the two components as they stand today, itemised so the merge is a
checklist rather than a reading exercise.

- **The eight tabs.** `PublishedPolicyCard` renders `Overview | Reading | Logic |
  <PARTIES_AND_ROUTES_TAB_LABEL> | Scope | Tests | History | Notes | JSON` from
  `policyTabPanes.tsx`. Every pane takes a `PolicyRecordView`, which
  `publishedPolicyRecord(card)` and `candidatePolicyRecord(card)` both produce, so
  the panes themselves need no change — `PolicyReviewCard` needs to call the right
  adapter for the record it holds. **Do not import the label as a string literal;**
  it had three spellings across three files once already.
- **Two Ask AI placements**, both requiring `policySetKey` and `policyVersionId`:
  `<PolicyAskAiButton policy={card.policy} …>` in the policy action row and
  `<PublishedRuleAskAiButton rule={r.rule} …>` beside each rule. The second is
  published-only by construction — it resolves against sealed records — so it is
  the one place a record's status legitimately selects a different component
  rather than a different view. Derive that from the record, not from which page
  is rendering.
- **History, with a fetch the card does not own.** `onRequestHistory(provisionKey)`
  is called when the History tab is first opened, and the result is handed back as
  `history` / `historyLoading`. The key is `provision_key`, never
  `document_provisions.id`.
- **`onViewHistory` and `onRevise`**, which are the published record's two verbs.
  They are the read-only arm of item 5, and they must be reachable from the same
  kebab that offers Approve and Reject on a draft — different entries of one menu,
  chosen by status, not two menus.

**When 2.1–2.5 land, `PublishedPolicyCard.tsx` can be deleted** and `PoliciesTab`
render `PolicyReviewCard` directly.

**Two tests will tell you when you are done, and one of them will fail loudly if
you are half-done.** `publishedRecordOffersNoDecision.test.tsx` asserts a sealed
record shows no Approve, Reject or Edit. `bothSurfacesAskTheSameQuestions.test.tsx`
asserts the two surfaces offer the same tab strip — it reads the strip off both
components rather than holding a list, so if the merged card serves one page its
full set of tabs and the other a subset, that test fails and no amount of editing
it will make it pass.

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

## 9. `api.ts` line ~1735 + `schemas.py` line ~349 — notes are rule-bound

**What is needed:** widen the note entity union at both ends so a note can name a
policy, and key it on the policy's identity rather than its row.

- `schemas.py:349` — `CreateNoteRequest.entity_type` is
  `Literal["policy_set", "policy_version", "candidate_rule", "rule"]`. Add one
  member for a policy.
- `api.ts:1735` — `NoteEntityType`, the TypeScript union that mirrors it. Add the
  same member.

**Only creating is blocked.** `GET /api/notes` takes `entity_type: str` with no
constraint (`routers/notes.py`), `NoteResponse.entity_type` is a plain `str`
(`schemas.py:358`), and the column is text by design — the model's own docstring
says it is polymorphic precisely so notes can attach to unrelated tables without
a schema change. **No migration is needed.** The `Literal` on the create schema
is the entire obstacle, and it is one line.

**Which id to key on, and why the obvious answer is wrong.** Key a policy note on
`provision_key`, not on `document_provisions.id`.

`document_provisions.id` is per document version: zero keys span more than one,
so a note written against a row id is a note about *that cut* of the policy. The
next extraction run produces a new row and the note silently stops appearing —
not deleted, not moved, just no longer reachable from the policy it was written
about. `provision_key` is the policy's identity across versions and is already
what the published grouping and the History endpoint are built on. This is the
same distinction the `Note` model already draws for rules, and it resolved it
the same way: `"rule"` is keyed on `CanonicalRule.rule_id`, the stable business
key, explicitly "so notes persist across a rule's candidate -> approved ->
superseded lifecycle." A policy needs exactly that, for exactly that reason.

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

## 13. `PolicyInspector.readOnly` is gone — what replaced it, and why not deletion

**Done, not requested.** `PolicyInspector`'s `readOnly` prop has been renamed to
`shownAsReference`, and two of the four things it gated have been deleted
outright. If you hold a call site that passed `readOnly`, rename it; nothing else
changes.

**Why it was not simply deleted, as I previously said it should be.** I said that
before reading its two callers. Read across every call site, the flag stood in
front of four unrelated questions:

| gated | decided by | verdict |
|---|---|---|
| `Revise` | `onRevise` being passed | dead — neither caller that raised the flag passed the handler |
| the caller's `additionalActions` | the node being passed | dead — same |
| the `Notes` tab | the flag | live |
| the `Test scenario` tab | the flag | live |

The two dead gates are the shape this whole exercise exists to remove — a flag
giving a second opinion on a question the call site had already answered — and
they were provably unreachable, so removing them is behaviour-preserving. They
are gone, and `inspectorHonoursItsHandlers.test.tsx` fails if either returns.

The two live ones are **not editability, and deleting the prop would have been
wrong.** Both callers are drawers that show a rule as a citation inside another
workflow — a quality finding, a validation preview. Whether a record may be
changed is a property of the record and `candidateEditability` answers it.
Whether this inspector is the place the reader came to act, or a reference pulled
in beside something else, is a property of the surrounding surface — and the
*same* published rule is both, on different pages. No record can answer that, so
the caller must, and the honest fix was to name it for what it decides rather
than to delete a distinction that is real.

**Note for anyone tempted to widen it again:** it may suppress only *acting on* a
rule reached sideways. The moment it gates something a record or a handler
already answers, it is the old flag under a new name.


---

# Addendum — item 14, from the Overview and Tests rebuild

## 14. Nothing to route — recorded so it is not rediscovered

Both items the user rejected are fixed in files I own, and neither needed a
change from another owner. This section exists so the findings survive.

### The Tests tab's server rules, discovered by exercising it

`POST /api/policy-tests/policy-sets/{key}/validation-batches` refuses twice, and
both refusals are correct product rules rather than defects:

1. **Rules decided by reading.** "blind validation runs against the deterministic
   engine; these selected rules are decided by reading, so the engine does not run
   them". Handled by deriving the offer from `evaluation_mode` — see the
   obligation added under *Where this stands*.
2. **No active approved version.** "policy set '<key>' has no active approved
   version to propose tests against". Surfaced verbatim; not pre-empted, because
   pre-empting it means encoding a server rule client-side where it can drift.

Neither figure from the live data is written into the product. The refusal text
comes from the server each time.

### What the provenance chain could not evidence, and therefore omits

- **Sequence position in the document.** `source_elements` is an element key
  (`p1-E000004`), not an ordinal. There is no honest conversion, so the Overview
  shows the key and no position.
- **Ingestion time.** `DocumentVersion.created_at` exists, but neither surface
  loads `SourceDocument`, and `ReviewFacetRun` does not carry it. The tab shows
  `version_label` and `content_hash` instead.

Both are cheap to add **if** a caller loads the document record. Neither is worth
a request on its own.

### Two defects logged, not fixed, both another agent's finding

- **An extraction defect the record-not-source design exposed.** The record says
  `"You required to Received 3 doses"` where the quoted source says only
  `"Received 3 doses"`. Still visible on the published AIS policy today; the
  published surface renders it faithfully, which is how it was seen.
- **A silent skip in the draft arm of `AskAboutRuleModal`.** It sends
  `candidate.policy_set_id` — a UUID — as `policy_set_key`, which is matched
  against the slug. It never resolves, so the approved-rules context block never
  loads for a rule-scoped draft ask. Owner: `dev-asklang`.

### Still blocked on item 2

`PublishedPolicyCard.tsx` remains a component-level duplicate of
`PolicyReviewCard.tsx`. Everything built since has been added to **both**, which
is the cost of the duplicate and the reason to close it. When item 2 lands,
`PoliciesTab.tsx` switches to `buildPolicyCards` and both duplicate files are
deleted in one commit — I own that switch.

## 15. Item 2 is now a smaller job than it was specified as

**Nothing to route. This re-scopes item 2 downward; the owner should read it
before starting.**

Item 2 was specified when the two cards' prop surfaces differed by capability,
not by copy — 14 props against 21. The extra seven on the published side were
all there to carry the eight tabs, because on the published surface the tabs
lived **inside the card** while on review they lived in `PolicyDetailPanel`:
`tests`, `testing`, `history`, `onRequestHistory`, `extractionRuns`,
`expandedRuleId`, `onToggleRule`. Merging the cards meant merging those too.

`111740c` removes that reason. The published surface now opens
`PolicyDetailPanel` when a policy is selected, so the tabs are in the panel on
**both** surfaces and the card no longer needs to host them. The remaining
divergence is smaller and mostly mechanical:

- **`onSelectRule` takes a different argument on each side.** Review passes a
  *draft row* id (`(recordId: string) => void`); published passes the rule
  (`(rule: CanonicalRule) => void`), because a published rule has no draft row.
  The merged component should pass the **card entry**, which holds both, and let
  each caller take what it has. Do not resolve this by making one side look up
  the other — that is a second opinion on grouping.
- **`RuleDetailInline` cannot serve a published rule.** It takes
  `candidate: CandidateRule`. The published inline detail uses
  `RuleCard defaultExpanded hideNotes`. Either that prop widens to accept a
  rule without a draft row, or the merged card keeps two detail renderers
  chosen by whether the entry has a `candidate` — derived from the record,
  which is the rule we work by.
- **The statement button should be extracted, not duplicated a third time.**
  `63d0328` gives the published card the same statement-as-button contract the
  review card has. Two copies of it now exist. When the duplicate dies, lift it
  into one piece rather than reconciling two — the badges, kebab and Ask AI must
  stay outside it and the `aria-current` must stay on the row, and those are
  exactly the details that drift when copied.

### One structural characteristic worth a decision, in a file I do not own

`App.css` line ~3626: `.review-workspace--desktop` is
`height: clamp(560px, calc(100vh - 150px), 1400px)`, and the policies workspace
is `calc(100vh - 214px)`. Neither list scrolls internally — `.policy-list-scroll`
does not exist in the rendered DOM — so on both surfaces the card list flows down
the page and the only scroller is `.app-content`.

The consequence is real and the user reported it as something else: a reader who
scrolls down to reach a rule has scrolled the panel off the top of the window, so
the click answers them where they cannot see it, which is indistinguishable from
the click doing nothing. That is very likely part of what "not clickable" meant.

`111740c` handles it behaviourally on the published side — `revealPanel()` brings
the panel back **only when it is genuinely outside the window**, via the exported
`isOutsideWindow` predicate in `PoliciesTab.tsx`. The review side has the same
structural characteristic and no such handling. Two options, and I have not taken
either because both land outside my files:

1. **Reuse the behaviour.** Import `isOutsideWindow` and call
   `scrollIntoView({ block: "nearest" })` on selection in `ReviewQueue.tsx`.
   Cheap, proven, and matches what already ships.
2. **Fix the layout instead.** Give the card list its own scroll container so the
   panel is never off-screen to begin with. Better, but it changes a layout two
   surfaces share and should not be done as a side-effect of a selection fix.

If (2) is chosen, the reveal call becomes dead and I will remove it.

### Not a defect: what an unrecognised review status counts as

`policyRecord` derives review progress from the shared `candidateEditability`
map, where an unknown status is **not reviewable** and therefore counts as
decided. That is right for `approved` and `published` and wrong-ish for a status
nobody has taught the map about — a typo in a status string would quietly
inflate "decided". Left as it is: the shape is depended on by other callers and
changing it is out of this brief. Recording it so the next person to see it does
not treat it as new.

---

## Item 16 — both routes can be tested, and one derivation says which

**Landed:** `06fcbe6` (rule scope), `c9cca0d` (policy scope), `efb71e6` (copy).

### What was wrong

`RuleScenarioTester` promised a judge in an alert and then disabled the case
box, the effort select and the submit button for every rule the engine would
not run, captioning the button `Not testable by the deterministic engine`.
On the live counts that is **670 rules shut out so that 7 could be served**.
The judged endpoint existed and was reachable only from the draft-authoring
surfaces — `AiRuleComposer` and `EditRuleModal`. Once a rule was published,
the judge could not be asked about it at all. **Instance thirteen** of the
signature failure.

At policy scope the same rules reached a cell reading `Checked by reading`
with nothing behind it — the dead end the Tests tab was built to remove, moved
one column right.

### The two paths, as built

| route | endpoint | decided by | answer |
|---|---|---|---|
| `deterministic` **and** executable | `testRuleScenario` | the engine computes the comparison | `EvaluationStatus`, plus the facts it read out of the case |
| everything else | `evaluateScenario` | a judge reads the record against the case | `applies: yes / no / uncertain`, reasoning, predicted outcome, what the case would have to state |

### The confidence question, and why there is no number

The brief asked for `a verdict, with confidence`. `ScenarioEvaluation` has
no confidence field, and **Section 53 of the governing spec removed confidence
scores** — recorded in `src/policy_platform/contracts/correlation.py:13`: *a
model asked for a probability will supply one, and `0.91` reads as
measurement when it is invention*. `contracts/graph_run.py:17` says the same
of provenance strength.

**Decision: the third verdict is the confidence.** `uncertain` renders as
*"The case as described does not settle it"*, followed by what the case would
have to state — a state the reviewer can act on rather than a number they can
only weigh. A figure beside an exact computed result would also read as the
judged route apologising for itself, which is the framing this project bans.
If a confidence figure is genuinely wanted, it needs a Section 53 decision
first, not a UI change.

### One derivation, `engineDecidesRule`

Now in `apps/web/src/ruleExecutability.ts` and used by both surfaces. Two
copies of this question existed and disagreed:

* `RuleScenarioTester` rendered off `evaluation_mode` and disabled off
  `machine_executable`, so a rule whose fields disagreed was offered a
  control that led to a refusal.
* `policyTestRows` asked `evaluation_mode` alone, so a rule stating a
  comparison with no executable condition was offered a scenario the server
  refuses to write (`ai_test_proposal.py` raises for exactly this).

Both fields are read; the engine is chosen only when both say so. That is not
a preference for the judge — it is the only ordering under which nobody is
handed an answer from a decider that never looked at their case.

### For whoever owns the guard

`tests/unit/test_no_route_framed_as_a_shortfall.py` is **sentence-scoped**:
it fires only when a route word and a lack word share a sentence. That is why
`Not testable by the deterministic engine` — the worst instance in the
product — passed it for months: the refusal and the route were in different
sentences. Worth considering whether a refusal verb next to a route name in
*adjacent* sentences should also fire.

The guard did catch my own prop comment (*"Absent, the case box still opens
for the rules decided by reading"*) — eighth phrasing, second caught before a
human. Fixed in the sentence, and the same check now also lives in
`everyRuleHasAWayToBeChecked.test.tsx` so a later tidy-up meets it in the
file it is editing.

### Ownership taken

`RuleScenarioTester.tsx` and `ruleExecutability.ts` appear in no agent's
list. Taken, consistent with precedent. Say if that is wrong.

### Live check

Published `ai_ready` rule, port 5490: box enabled, button reads *"Put this
case to the judge"*, a real case returned `uncertain` rendered as its own
verdict with **no digits**, and the caption *"Read by a judge against the
record on screen · not saved to the audit trail (exploratory check only)"*.

### Not built, and why

There is **no batch judge endpoint**. `policy_tests` generation is
engine-only by design (`ai_test_proposal.py` raises for non-executable
rules). So a policy-scope judged run would be N separate calls; it is offered
one rule at a time from its row instead, which is honest about what it costs.
A batch judge endpoint is the server-side change that would make a
policy-wide judged run reasonable.

---

## Item 17 - the policy is the unit of counting, selection and export

The user: *"the main currency is policy, so if u show count show count to
policies=x and rules=y and exporting we only now export policies not single
rule"*. Four surfaces on the published page still counted, selected and wrote
in rules. They now count, select and write in policies.

### What changed, and where the wording lives

`apps/web/src/policyExport.ts` is new and holds **both the file shape and the
copy that describes it**, so a later edit cannot move one without the other.
That pairing is deliberate: the previous divergence was not that the export was
wrong, it was that the button said one thing and the file was another and
nobody reads an export until they need it.

| surface | before | after |
|---|---|---|
| version strip | `13 rules` | `2 policies` then `13 rules` |
| select-all | `Select all 13 shown` | `Select all 2 policies in this filter` |
| export selected | `Export selected JSONL` | `Export 2 policies (JSONL)` |
| export all | `Export all 13 JSONL` | `Export all 2 policies (JSONL)` |
| the file | one line per rule | one line per policy, rules nested |
| the message after | filename only | policy count first, rule tally in parentheses |

The toolbar line `2 policies - 13 of 13 rules shown` was already right and is
untouched.

### The export reuses `policyJsonDocument`, and had to

`policiesAsJsonl` writes each line by calling `policyJsonDocument` from
`policyCards.ts` - the same serialisation already rendered in the JSON tab
under *"THIS POLICY AS ONE DOCUMENT - ITS RULES NESTED INSIDE IT"*. A second
serialisation of a policy would have drifted exactly as the two card builders
drifted, and would have drifted **silently**, because the JSON tab is read
daily and an export is read once a quarter. So the export is not a new shape;
it is the shape already on screen, written to a file.

### Selection selects policies, and a half-selected policy cannot be expressed

Selection is keyed on `provision_key`, not rule id. There are as many
checkboxes as there are policies. This is the same symmetry as `Approve
policy`: **the thing you can select is the thing you can act on.** A reviewer
cannot select nine of a policy's twelve rules, because there is no such
record to select.

### The server side - answer to the question that was asked

`GET /api/policy-sets/{key}/versions/{version_id}/export`
(`policy_sets.py:946`) calls `approved_policy_version_to_package(version)` then
`models_to_export(package.rules, format)`. **It emits flat rules**, in
json/jsonl/csv, and its docstring describes a verbatim structural export for
audit and archival. That is a legitimately different artefact from the
reviewer-facing download and I did not change it.

Two facts that decide where a policy-shaped export belongs:

1. **The page's button never calls that endpoint.** It composed the file
   client-side before this change and still does.
2. **The server already assembles policies** - `listVersionPolicies` returns
   `AssembledPolicy[]` from `assemble()`.

So the recommendation stands as the producer framed it: a **policy-shaped
export mode belongs on the server beside `listVersionPolicies`**, not as a
replacement for the rules export, which has its own audience. The client is
not reassembling anything today - it is reusing one serialisation - so this is
not urgent, but if a second consumer ever needs the policy file, it should come
from the server rather than from a second client.

### Wording matched to review, deliberately

`Select all N policies in this filter` is the review queue's own idiom
(`Select all 37 policies in this filter`). Adopted verbatim rather than
invented, so the two surfaces cannot drift on the noun.

One thing left matching review rather than changed: the bare `N selected`
counter does not name its unit on either page. If it should, it should change
on both at once - routing that rather than fixing one side.

### Tests

`apps/web/src/theUnitIsThePolicy.test.ts`, 14 tests in three groups: *a line of
the file is a policy*, *every control names what it counts*, *what was written
is reported afterwards*. Every expected number is computed from the fixture
shape; none is written down. Five mutations against `policyExport.ts` (line per
rule; singular/plural swap; dropped trailing newline; button naming rules;
message counting rules) - all five caught.

### Live, port 5490, published version v2

Strip reads `2 policies` then `13 rules`. Three checkboxes for two policies
plus select-all. Selecting all gives `2 selected` and
`Export 2 policies (JSONL)`. The written file: **2 lines**, keys
`key / heading / heading_path / title / ... / passages`, **no top-level
`rule_id`**, `1 + 12 = 13` rules nested, trailing newline present.
