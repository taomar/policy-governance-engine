/**
 * TWO SURFACES, ONE COMPUTATION
 *
 * The review queue and the published version draw the same policy from the same
 * records. Where both need an answer to the same question -- what names this
 * card, what do all its rules agree on -- there must be one implementation of
 * it, because two will be corrected separately and will then disagree without
 * anyone noticing which one is on screen.
 *
 * The published page used to carry its own copy of both, in a module and a
 * component forked from the queue's. It could not do otherwise at first: the
 * shared card model named a reviewable draft row, and a published record is not
 * one. Then the model learned to read a record that has no draft row, the copies
 * decayed into adapters, and four separate user-visible faults were still being
 * reported because a fork cannot inherit a fix. The fork is gone. These tests
 * are what keeps it gone.
 *
 * They assert agreement for the two ways a record *enters* the shared model --
 * as a draft row under review, or as a sealed published rule -- because that is
 * the only difference the two pages still have. A card built either way must
 * answer every shared question the same, and the difference must show up only
 * where the record itself differs: in what may be decided about it.
 */
import { describe, expect, it } from "vitest";
import type { AssembledPolicy, CanonicalRule } from "./api";
import { buildPolicyCards, policyTitle, sharedRuleFacets } from "./policyCards";

function rule(id: string, over: Record<string, unknown> = {}): CanonicalRule {
  return {
    rule_id: id,
    title: `A statement ${id}`,
    description: `A statement ${id}`,
    rule_type: "obligation",
    evaluation_mode: "deterministic",
    rule_revision: 1,
    condition: { type: "all", all: [] },
    effect: { type: "require_action", action: "an action" },
    evidence: [],
    ...over,
  } as unknown as CanonicalRule;
}

function policy(rules: readonly CanonicalRule[], heading: string | null): AssembledPolicy {
  return {
    key: "a-key",
    heading,
    heading_path: heading ? [heading] : [],
    topic_label: null,
    persisted: true,
    provision_id: null,
    document_version_id: null,
    source_elements: "p1-E1",
    page: 1,
    rule_count: rules.length,
    passage_count: 1,
    route: "deterministic",
    passages: [
      {
        // The stub the server places, which carries the route beside the id.
        // `buildPolicyCards` reads the route from here rather than from the
        // record, so a fixture omitting it produces a card with no route at all.
        rules: rules.map((one) => ({
          rule_id: one.rule_id,
          evaluation_mode: one.evaluation_mode,
        })),
      },
    ],
    rules: [],
  } as unknown as AssembledPolicy;
}

/**
 * The same records entered the two ways the two pages enter them.
 *
 * One builder, called twice. There is no second entry point to call any more,
 * which is the point: the published page hands the shared builder a rule with no
 * draft row, and the queue hands it a draft row carrying one.
 */
function bothWays(rules: readonly CanonicalRule[], heading: string | null) {
  const policies = [policy(rules, heading)];
  const [queued] = buildPolicyCards(
    policies,
    rules.map((one) => ({ rule: one, review_status: "candidate", id: `record-${one.rule_id}` })),
  );
  const [published] = buildPolicyCards(
    policies,
    rules.map((one) => ({ rule: one })),
  );
  return { queued, published };
}

describe("what names a policy is asked once", () => {
  it("gives the same title however the record entered when the document supplied a heading", () => {
    const { queued, published } = bothWays([rule("r0"), rule("r1")], "A heading");
    expect(policyTitle(published.policy, published.passages)).toEqual(
      policyTitle(queued.policy, queued.passages),
    );
  });

  it("gives the same title however the record entered when it must fall back to the passage", () => {
    // The branch that differs between a heading and none is exactly where two
    // copies would drift, because it is the one a fix would touch.
    const { queued, published } = bothWays([rule("r0"), rule("r1")], null);
    expect(policyTitle(published.policy, published.passages)).toEqual(
      policyTitle(queued.policy, queued.passages),
    );
  });
});

describe("what a policy's rules agree on is asked once", () => {
  /** Everything the two records can be asked *except* their review status,
   *  which is not a page difference but the record's own answer: a draft row
   *  says where it is in a review, a sealed rule says it is published. Compared
   *  as a whole so a facet added later is compared without this file changing. */
  function facetsApartFromStatus(card: Parameters<typeof sharedRuleFacets>[0]) {
    const { reviewStatus: _reviewStatus, ...rest } = sharedRuleFacets(card);
    return rest;
  }

  it("agrees where every rule matches", () => {
    const { queued, published } = bothWays([rule("r0"), rule("r1")], "A heading");
    expect(facetsApartFromStatus(published)).toEqual(facetsApartFromStatus(queued));
  });

  it("agrees where the rules differ, and reports the disagreement as one", () => {
    const rules = [
      rule("r0"),
      rule("r1", {
        rule_type: "definition",
        // A route, not a fault. A card holding a rule decided by a person and a
        // rule decided by a model agrees on neither, and says so.
        evaluation_mode: "ai_ready",
        effect: { type: "informational" },
      }),
    ];
    const { queued, published } = bothWays(rules, "A heading");
    const facets = sharedRuleFacets(published);
    expect(facetsApartFromStatus(published)).toEqual(facetsApartFromStatus(queued));
    // And the disagreement is reported as one, not flattened to a first value.
    expect(facets.ruleType).toBeFalsy();
    expect(facets.route).toBeFalsy();
  });

  it("agrees on a facet no rule stated", () => {
    const rules = [rule("r0", { effect: undefined }), rule("r1", { effect: undefined })];
    const { queued, published } = bothWays(rules, "A heading");
    expect(sharedRuleFacets(published).effectType).toEqual(sharedRuleFacets(queued).effectType);
  });

  it("reports each record's own review status rather than one for both", () => {
    // The guard for the exclusion above: it would also pass if the facet had
    // been dropped, or if both records reported the same thing.
    const { queued, published } = bothWays([rule("r0"), rule("r1")], "A heading");
    expect(sharedRuleFacets(queued).reviewStatus).toBe("candidate");
    expect(sharedRuleFacets(published).reviewStatus).toBe("published");
  });
});

describe("what differs is the record, not the page", () => {
  it("offers a decision on a draft row and none on a sealed one", () => {
    // The single licensed difference between the two, and it is derived from
    // each record through `candidateEditability` rather than set by a caller.
    // Everything the published page does *not* offer follows from this one fact.
    const { queued, published } = bothWays([rule("r0"), rule("r1")], "A heading");
    expect(queued.reviewableIds.length).toBe(2);
    expect(published.reviewableIds.length).toBe(0);
    // Both still hold every rule. A sealed policy is not a shorter policy.
    // The ids differ because the records do — a draft row is known by its row,
    // a sealed rule by itself — but neither list is short of the other.
    expect(published.allIds.length).toBe(queued.allIds.length);
    expect(published.rules.length).toBe(queued.rules.length);
    expect(published.rules.map((entry) => entry.rule_id)).toEqual(
      queued.rules.map((entry) => entry.rule_id),
    );
  });

  it("names a published rule by the rule, having no draft row to name it by", () => {
    const { queued, published } = bothWays([rule("r0")], "A heading");
    expect(queued.rules[0].recordId).toBe("record-r0");
    expect(published.rules[0].recordId).toBe("r0");
    expect(published.rules[0].candidate).toBeUndefined();
  });
});
