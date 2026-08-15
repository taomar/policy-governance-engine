/**
 * A card on the review queue is a whole policy, or it is a lie.
 *
 * THE FAILURE THIS EXISTS TO PREVENT
 *
 * A card carries one Approve button and that button decides the policy — every
 * rule of it, including any the reviewer never looked at. That is the right
 * design: a policy is approved as a unit because it was written as one. It is
 * also what makes narrowing the card's contents dangerous rather than merely
 * untidy.
 *
 * Two narrowings have been tried on this queue. A content-kind lane split the
 * queue into "policies" and "definitions" and cut every policy that both
 * defines a term and constrains its use straight down the middle, showing each
 * half as though it were the whole. And building cards from the search matches
 * did the same thing per keystroke: type a word that four of a policy's nine
 * rules contain, and the card shows four, says four, and decides nine.
 *
 * The rule that survived both is: a filter selects cards, never their contents.
 * These tests assert it on the derivation itself rather than through a rendered
 * queue, because the failure is a silent subsetting — it renders perfectly.
 *
 * Each test is paired with a control that fails if nothing was built at all,
 * since "no rule was dropped" is also true of an empty card.
 */

import { describe, expect, it } from "vitest";
import type { AssembledPolicy, CandidateRule, CanonicalRule } from "./api";
import { buildPolicyCards } from "./policyCards";
import {
  candidateAnswersSearch,
  cardsAnsweringSearch,
  matchedCandidateIds,
  placeableCandidates,
} from "./queueCardSelection";

/** A word placed in exactly one rule of the policy, so a search on it matches
 *  one record out of many. Deliberately meaningless: nothing here may lean on
 *  the vocabulary of any real document. */
const NEEDLE = "zzqx";

function canonical(ruleId: string, title: string): CanonicalRule {
  return {
    schema_version: "1.0",
    policy_set_id: "set",
    policy_version_id: "draft",
    rule_id: ruleId,
    rule_revision: 1,
    title,
    description: `Description of ${ruleId}`,
    rule_type: "obligation",
    authority: { level: "ai_drafted", owner: "formulator", rank: 0 },
    scope: { jurisdictions: [], organizational_units: [], personas: [], processes: [] },
    condition: { type: "all", all: [] },
    attributes: { applies: [], produces: [] },
    effect: { action: "record", parameters: {} },
    evidence: [],
    provenance: { document_id: "doc", page: 1 },
    tags: [],
    category: null,
    group_label: null,
    required_facts: [],
    decision_readiness: null,
  } as unknown as CanonicalRule;
}

function candidate(
  ruleId: string,
  title: string,
  overrides: Partial<CandidateRule> = {},
): CandidateRule {
  return {
    id: `cand-${ruleId}`,
    rule_id: ruleId,
    rule_type: "obligation",
    review_status: "pending",
    rule: canonical(ruleId, title),
    superseded_by_candidate_id: null,
    baseline_candidate_id: null,
    ...overrides,
  } as unknown as CandidateRule;
}

/** One policy stating several rules, one of which carries the needle. */
function policyOfManyRules(ruleIds: readonly string[]): AssembledPolicy {
  return {
    key: "policy-under-test",
    heading: "A heading the document supplies",
    heading_trail: [],
    page: 1,
    rule_count: ruleIds.length,
    passages: [
      {
        passage_id: "passage-1",
        text: "The sentence the policy is stated in.",
        title: null,
        rules: ruleIds.map((id) => ({ rule_id: id, evaluation_mode: "ai_ready" })),
      },
    ],
  } as unknown as AssembledPolicy;
}

const RULE_IDS = ["r-1", "r-2", "r-3", "r-4", "r-5"];

function fixture() {
  const candidates = RULE_IDS.map((id) =>
    candidate(id, id === "r-3" ? `A title containing ${NEEDLE}` : `A title for ${id}`),
  );
  return { candidates, policies: [policyOfManyRules(RULE_IDS)] };
}

describe("a search selects cards, never their contents", () => {
  it("builds a card holding every rule of the policy even when one rule matched", () => {
    const { candidates, policies } = fixture();
    const placeable = placeableCandidates(candidates);
    const cards = buildPolicyCards(policies, placeable);

    const matched = matchedCandidateIds(placeable, NEEDLE);
    // Control: the search really did narrow something, or the test proves nothing.
    expect(matched.size).toBe(1);

    const shown = cardsAnsweringSearch(cards, NEEDLE, matched);
    expect(shown).toHaveLength(1);
    expect(shown[0].rules).toHaveLength(RULE_IDS.length);
    expect(shown[0].rules.map((entry) => entry.rule_id).sort()).toEqual([...RULE_IDS].sort());
  });

  it("hides a policy no rule of which answered the search", () => {
    const { candidates, policies } = fixture();
    const placeable = placeableCandidates(candidates);
    const cards = buildPolicyCards(policies, placeable);
    // Control: without the search the card is there to be hidden.
    expect(cardsAnsweringSearch(cards, "", matchedCandidateIds(placeable, ""))).toHaveLength(1);

    const absent = "qqzzxw";
    const shown = cardsAnsweringSearch(cards, absent, matchedCandidateIds(placeable, absent));
    expect(shown).toHaveLength(0);
  });

  it("returns the cards untouched when nothing is searched for", () => {
    const { candidates, policies } = fixture();
    const placeable = placeableCandidates(candidates);
    const cards = buildPolicyCards(policies, placeable);

    const shown = cardsAnsweringSearch(cards, "   ", matchedCandidateIds(placeable, "   "));
    expect(shown).toHaveLength(cards.length);
    expect(shown[0].rules).toHaveLength(RULE_IDS.length);
  });

  it("cannot subset a card: what it selects is what the assembly built", () => {
    const { candidates, policies } = fixture();
    const placeable = placeableCandidates(candidates);
    const cards = buildPolicyCards(policies, placeable);

    const shown = cardsAnsweringSearch(cards, NEEDLE, matchedCandidateIds(placeable, NEEDLE));
    // Identity, not deep equality: selection may not rebuild a card either,
    // because a rebuilt card is a second opinion on what the policy contains.
    expect(shown[0]).toBe(cards[0]);
  });
});

describe("what a policy contains is not a matter of review state", () => {
  it("keeps an already-decided rule in the card beside its pending siblings", () => {
    const candidates = RULE_IDS.map((id) =>
      candidate(id, `A title for ${id}`, id === "r-2" ? { review_status: "approved" } : {}),
    );
    const cards = buildPolicyCards([policyOfManyRules(RULE_IDS)], placeableCandidates(candidates));

    expect(cards).toHaveLength(1);
    expect(cards[0].rules).toHaveLength(RULE_IDS.length);
  });

  it("drops a superseded reading, because it is a different cut of the policy", () => {
    const candidates = RULE_IDS.map((id) =>
      candidate(id, `A title for ${id}`, id === "r-4" ? { superseded_by_candidate_id: "later" } : {}),
    );
    const placeable = placeableCandidates(candidates);
    // Control: everything else survived, so this is supersession and not a bug.
    expect(placeable).toHaveLength(RULE_IDS.length - 1);
    expect(placeable.some((c) => c.rule.rule_id === "r-4")).toBe(false);
  });
});

describe("the search reads only words the reviewer can see", () => {
  it("matches on a title", () => {
    expect(candidateAnswersSearch(candidate("r-1", `Holds ${NEEDLE} here`), NEEDLE)).toBe(true);
  });

  it("does not match a record whose words do not contain the term", () => {
    expect(candidateAnswersSearch(candidate("r-1", "A plain title"), NEEDLE)).toBe(false);
  });

  it("treats an empty search as no question asked", () => {
    expect(candidateAnswersSearch(candidate("r-1", "A plain title"), "  ")).toBe(true);
  });
});
