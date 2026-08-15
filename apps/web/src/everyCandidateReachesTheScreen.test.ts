/**
 * No rule falls through the gap between two views.
 *
 * The queue draws a rule in one of two places: on a policy card, or in the
 * unplaced list beneath. Those are computed by two exported functions, and the
 * only thing keeping every rule on screen is that the two agree about which
 * rules the other is showing.
 *
 * They stopped agreeing. One asked `policy.passages`, the other asked
 * `policy.rules`. A policy carrying rules but no passages made the first draw
 * no card and the second report nothing unplaced, and a reviewer got an empty
 * screen over a payload holding every rule they were there to read.
 *
 * So this is written as the invariant rather than as that case: whatever
 * combination of optional fields a policy arrives with, the rules on the cards
 * plus the rules in the unplaced list account for every candidate. A field
 * added later and forgotten later fails this without anyone writing a new test
 * for it.
 */

import { describe, expect, it } from "vitest";

import { buildPolicyCards, unplacedRules } from "./policyCards";
import type { AssembledPolicy, CandidateRule } from "./api";

function candidate(ruleId: string): CandidateRule {
  return {
    id: `c-${ruleId}`,
    policy_set_id: "set",
    extraction_run_id: "run",
    rule_type: "obligation",
    revision: 1,
    review_status: "pending",
    reviewed_by: null,
    reviewed_at: null,
    review_notes: null,
    published_version_id: null,
    created_at: "2024-01-01T00:00:00Z",
    delta_status: "new",
    reworded: false,
    baseline_candidate_id: null,
    superseded_at: null,
    superseded_by_candidate_id: null,
    rule: {
      rule_id: ruleId,
      description: `rule ${ruleId}`,
      rule_type: "obligation",
      evaluation_mode: "deterministic",
    },
  } as unknown as CandidateRule;
}

/**
 * A policy whose optional parts are present or absent as asked.
 *
 * Built by deleting from a complete policy rather than by adding to an empty
 * one, so a field introduced later is present in every combination until it is
 * named here — the failure mode this guards is a field nobody remembered.
 */
function policyWith(ruleIds: string[], absent: readonly string[]): AssembledPolicy {
  const policy: Record<string, unknown> = {
    key: `policy-${ruleIds.join("-")}-${absent.join("-") || "complete"}`,
    provision_id: "provision-1",
    heading: "A heading",
    heading_path: ["A heading"],
    persisted: true,
    document_version_id: "doc-1",
    source_elements: "E1",
    page: 1,
    rule_count: ruleIds.length,
    passage_count: 1,
    route: "deterministic",
    topic_label: null,
    passages: [
      {
        passage_id: "p-1",
        heading: "A heading",
        page: 1,
        rules: ruleIds.map((rule_id) => ({
          rule_id,
          evaluation_mode: "deterministic",
        })),
      },
    ],
    rules: ruleIds.map((rule_id) => ({ rule_id, evaluation_mode: "deterministic" })),
  };
  for (const field of absent) delete policy[field];
  return policy as unknown as AssembledPolicy;
}

/** Every optional part of a policy the two views read, and their combinations. */
const OPTIONAL_FIELDS = ["passages", "rules", "topic_label", "heading_path", "provision_id"] as const;

function combinations<T>(items: readonly T[]): T[][] {
  const out: T[][] = [];
  for (let mask = 0; mask < 1 << items.length; mask += 1) {
    out.push(items.filter((_, index) => (mask >> index) & 1));
  }
  return out;
}

describe("every candidate reaches the screen", () => {
  const ruleIds = ["r1", "r2", "r3"];
  const candidates = ruleIds.map(candidate);

  for (const absent of combinations(OPTIONAL_FIELDS)) {
    const naming = absent.length === 0 ? "every field present" : `without ${absent.join(", ")}`;

    it(`accounts for every candidate ${naming}`, () => {
      const policies = [policyWith(ruleIds, absent)];

      const onCards = buildPolicyCards(policies, candidates).flatMap((card) =>
        card.rules.map((rule) => rule.rule_id),
      );
      const left = unplacedRules(policies, candidates).map((c) => c.rule.rule_id);

      const shown = new Set([...onCards, ...left]);
      expect([...shown].sort()).toEqual([...ruleIds].sort());
      expect(onCards.length + left.length).toBeGreaterThanOrEqual(candidates.length);
    });

    it(`draws no candidate twice ${naming}`, () => {
      const policies = [policyWith(ruleIds, absent)];

      const onCards = buildPolicyCards(policies, candidates).flatMap((card) =>
        card.rules.map((rule) => rule.rule_id),
      );
      const left = unplacedRules(policies, candidates).map((c) => c.rule.rule_id);

      const shown = [...onCards, ...left];
      expect(shown.length).toBe(new Set(shown).size);
    });
  }

  it("keeps a policy's rules on screen when it arrives with no passages at all", () => {
    // The case that produced the blank screen, kept by name as well as by the
    // property, because a regression here is the most visible one there is.
    const policies = [policyWith(ruleIds, ["passages"])];

    expect(buildPolicyCards(policies, candidates)).toEqual([]);
    expect(unplacedRules(policies, candidates).map((c) => c.rule.rule_id)).toEqual(ruleIds);
  });

  it("keeps a rule on screen when the policy lists it but no passage states it", () => {
    // Not the same as having no passages: the layout is present and simply does
    // not reach this rule. It is invisible for the same reason, so it is
    // rescued by the same test.
    const policy = policyWith(ruleIds, []) as unknown as Record<string, unknown>;
    (policy.passages as { rules: { rule_id: string }[] }[])[0].rules = [{ rule_id: "r1" }];
    const policies = [policy as unknown as AssembledPolicy];

    const onCards = buildPolicyCards(policies, candidates).flatMap((card) =>
      card.rules.map((rule) => rule.rule_id),
    );
    const left = unplacedRules(policies, candidates).map((c) => c.rule.rule_id);

    expect(onCards).toEqual(["r1"]);
    expect(left).toEqual(["r2", "r3"]);
  });

  it("reports nothing unplaced when every rule is drawn", () => {
    const policies = [policyWith(ruleIds, [])];

    expect(buildPolicyCards(policies, candidates)[0].rules).toHaveLength(3);
    expect(unplacedRules(policies, candidates)).toEqual([]);
  });

  it("does not invent a passage to hold a policy it could not lay out", () => {
    // Fabricating one would put a claim on screen that the document stated
    // these rules together in one run of text. Nothing read the document and
    // concluded that; the layout merely needed somewhere to put them.
    const policies = [policyWith(ruleIds, ["passages"])];

    for (const card of buildPolicyCards(policies, candidates)) {
      expect(card.passages).toEqual([]);
    }
  });

  it("answers the same whether the cards or the unplaced list is asked first", () => {
    // The two are read from separate memos and share a cached pass. Order must
    // not be able to change either answer.
    const policies = [policyWith(ruleIds, ["passages"])];

    const cardsFirst = buildPolicyCards(policies, candidates);
    const leftAfter = unplacedRules(policies, candidates);
    const leftFirst = unplacedRules(policies, candidates);
    const cardsAfter = buildPolicyCards(policies, candidates);

    expect(cardsAfter).toEqual(cardsFirst);
    expect(leftAfter).toEqual(leftFirst);
  });

  it("re-reads when the candidates change but the policies do not", () => {
    // The shared pass is keyed on identity. A filter that narrows the flat list
    // hands over a new array with the old policies, and the answer has to move.
    const policies = [policyWith(ruleIds, [])];

    expect(buildPolicyCards(policies, candidates)[0].rules).toHaveLength(3);
    const narrowed = [candidate("r1")];
    expect(buildPolicyCards(policies, narrowed)[0].rules).toHaveLength(1);
    expect(unplacedRules(policies, narrowed)).toEqual([]);
  });
});
