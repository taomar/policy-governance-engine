/**
 * TWO SURFACES, ONE COMPUTATION
 *
 * The review queue and the published version draw the same policy from the same
 * records. Where both need an answer to the same question -- what names this
 * card, what do all its rules agree on -- there must be one implementation of
 * it, because two will be corrected separately and will then disagree without
 * anyone noticing which one is on screen.
 *
 * The published module used to carry its own copy of both. It could not do
 * otherwise: the shared card model named a reviewable draft row, and a published
 * record is not one. That has been fixed, the copies are gone, and these tests
 * are what keeps them gone.
 *
 * They assert agreement, not sameness of source. A future implementation may
 * legitimately want the published page's narrower shape -- what it may not do is
 * answer a question differently from the queue for the same records.
 */
import { describe, expect, it } from "vitest";
import type { AssembledPolicy, CanonicalRule } from "./api";
import { buildPolicyCards, policyTitle, sharedRuleFacets } from "./policyCards";
import {
  buildPublishedPolicyCards,
  publishedPolicyTitle,
  publishedSharedFacets,
} from "./publishedPolicyCards";

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

/** The same records, arranged by each surface's own entry point. */
function bothWays(rules: readonly CanonicalRule[], heading: string | null) {
  const policies = [policy(rules, heading)];
  const [queued] = buildPolicyCards(
    policies,
    rules.map((one) => ({ rule: one, review_status: "candidate", id: `record-${one.rule_id}` })),
  );
  const [published] = buildPublishedPolicyCards(policies, rules);
  return { queued, published };
}

/**
 * The queue's answer as the published page states it.
 *
 * The only licensed difference between the two is that this page reports an
 * absent facet as null where the shared reading may report it as the empty
 * string it read. Applying that here rather than asserting the raw values keeps
 * the tests about agreement, and keeps the one permitted difference written down
 * in one place instead of assumed at each call.
 */
function asPublishedWouldState(facets: {
  ruleType: string | null;
  effectType: string | null;
  route: string | null;
}) {
  return {
    ruleType: facets.ruleType || null,
    effectType: facets.effectType || null,
    route: facets.route || null,
  };
}

describe("what names a policy is asked once", () => {
  it("gives the same title on both surfaces when the document supplied a heading", () => {
    const { queued, published } = bothWays([rule("r0"), rule("r1")], "A heading");
    expect(publishedPolicyTitle(published.policy, published.passages)).toEqual(
      policyTitle(queued.policy, queued.passages),
    );
  });

  it("gives the same title on both surfaces when it must fall back to the passage", () => {
    // The branch that differs between a heading and none is exactly where two
    // copies would drift, because it is the one a fix would touch.
    const { queued, published } = bothWays([rule("r0"), rule("r1")], null);
    expect(publishedPolicyTitle(published.policy, published.passages)).toEqual(
      policyTitle(queued.policy, queued.passages),
    );
  });

  it("is the queue's own function, so it cannot answer differently", () => {
    expect(publishedPolicyTitle).toBe(policyTitle);
  });
});

describe("what a policy's rules agree on is asked once", () => {
  it("agrees with the shared reading where every rule matches", () => {
    const { queued, published } = bothWays([rule("r0"), rule("r1")], "A heading");
    expect(publishedSharedFacets(published)).toEqual(
      asPublishedWouldState(sharedRuleFacets(queued)),
    );
  });

  it("agrees with the shared reading where the rules differ", () => {
    const rules = [
      rule("r0"),
      rule("r1", {
        rule_type: "definition",
        evaluation_mode: "ai_ready",
        effect: { type: "informational" },
      }),
    ];
    const { queued, published } = bothWays(rules, "A heading");
    const facets = publishedSharedFacets(published);
    expect(facets).toEqual(asPublishedWouldState(sharedRuleFacets(queued)));
    // And the disagreement is reported as one, not flattened to a first value.
    expect(facets.ruleType).toBeNull();
    expect(facets.route).toBeNull();
  });

  it("says null, not the empty string, for a facet no rule stated", () => {
    // The published page's callers ask `=== null`. A shared-but-absent facet
    // reaching them as "" would read as a value they could print.
    const rules = [rule("r0", { effect: undefined }), rule("r1", { effect: undefined })];
    const { published } = bothWays(rules, "A heading");
    expect(publishedSharedFacets(published).effectType).toBeNull();
  });

  it("reports the facets this page draws and no others", () => {
    // The shared reading also carries the review status and the revision of the
    // row under each rule. Both are true of a published card and neither is
    // drawn on it, so they are dropped here rather than answered differently --
    // and the difference between dropping and recomputing is the whole point.
    const { published } = bothWays([rule("r0")], "A heading");
    expect(Object.keys(publishedSharedFacets(published)).sort()).toEqual([
      "effectType",
      "route",
      "ruleType",
    ]);
  });
});
