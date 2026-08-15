/**
 * A published policy is shown whole, or it says what it is holding back.
 *
 * WHAT IS AT STAKE
 *
 * The page this covers used to list records one per row, filed under the kind
 * of rule each one was. That is a label this system assigns; it is not a
 * structure any document has. The effect was that a section stating several
 * rules appeared as pieces under several headings the source never wrote, with
 * nothing on screen connecting them — and the count above the list said
 * "policies" over a number of rules, so a reader had no way to notice.
 *
 * The grouping is now the document's own, which makes a new failure possible:
 * a search or filter can match some of a policy's rules and not others, and a
 * card drawn from those matches alone would present a fragment in the shape of
 * a whole policy. That is worse than the row list was, because it looks
 * complete.
 *
 * WHAT IS ASSERTED
 *
 * That placement loses nothing and duplicates nothing — every rule handed in
 * comes out either on a policy or in the unplaced set, exactly once. That a
 * card whose policy holds more rules than are showing says so, in words, with
 * the number. And that a rule whose policy is unknown is still rendered rather
 * than dropped, because a gap in the grouping is not a reason to withhold a
 * record from the person reading the version.
 *
 * Nothing here is a phrase from any document, and no number in it is a
 * measurement of one.
 */
import { describe, expect, it } from "vitest";
import type { AssembledPolicy, CanonicalRule } from "./api";
import { buildPolicyCards } from "./policyCards";
import {
  buildPublishedPolicyCards,
  policyComposition,
  policyCompositionLabel,
  publishedPolicyTitle,
  publishedSharedFacets,
  unplacedPublishedRules,
  type PublishedPolicyCardRule,
} from "./publishedPolicyCards";

function rule(
  ruleId: string,
  overrides: Partial<CanonicalRule> = {},
): CanonicalRule {
  return {
    schema_version: "1.0",
    policy_set_id: "a-set",
    policy_version_id: "a-version",
    rule_id: ruleId,
    rule_revision: 1,
    title: `Title for ${ruleId}`,
    description: "",
    rule_type: "obligation",
    authority: { owner: "an-owner", source: "", reference: "" },
    scope: { jurisdictions: [], organizational_units: [], processes: [] },
    condition: { type: "always" },
    evaluation_mode: "ai_ready",
    effect: { type: "require_action" },
    required_facts: [],
    exceptions: [],
    priority: 0,
    effective_from: "2024-01-01",
    effective_to: null,
    machine_executable: false,
    ambiguity_status: "clear",
    review_status: "published",
    evidence: [],
    lineage: {
      extraction_run_id: null,
      deployment_name: null,
      prompt_version: null,
      parser_version: null,
      schema_version: "1.0",
    },
    category: "",
    tags: [],
    group_label: "",
    related_rule_ids: [],
    is_explicit_override: false,
    supersedes_rule_ids: [],
    advice: [],
    ...overrides,
  } as unknown as CanonicalRule;
}

/** A rule as it sits on a card, built the way a *published* record reaches one:
 *  carrying no draft id and no review state of its own, so the shared builder's
 *  reading of that absence is what these assertions exercise. */
function asCardRule(record: CanonicalRule): PublishedPolicyCardRule {
  return {
    rule_id: record.rule_id,
    rule: record,
    reviewStatus: "published",
    recordId: record.rule_id,
    evaluation_mode: record.evaluation_mode ?? "",
  };
}

/** A policy as the version records it: a key, a heading, and the ids of the
 *  rules it holds — in the passages the source stated them in. */
function policy(
  key: string,
  passages: { key: string; ruleIds: string[] }[],
  overrides: Partial<AssembledPolicy> = {},
  /** Per-rule route, as the assembly records it on the passage entry. */
  modes: Record<string, string> = {},
): AssembledPolicy {
  const ruleIds = passages.flatMap((p) => p.ruleIds);
  const mode = (id: string) => modes[id] ?? "ai_ready";
  return {
    key,
    heading: `Heading for ${key}`,
    heading_path: ["Outer", `Heading for ${key}`],
    topic_label: null,
    persisted: true,
    provision_id: `provision-${key}`,
    document_version_id: null,
    source_elements: "",
    page: 1,
    rule_count: ruleIds.length,
    passage_count: passages.length,
    route: "ai_ready",
    passages: passages.map((p) => ({
      key: p.key,
      source_elements: "",
      page: 1,
      rule_count: p.ruleIds.length,
      rules: p.ruleIds.map((id) => ({ rule_id: id, evaluation_mode: mode(id) })),
    })),
    rules: ruleIds.map((id) => ({ rule_id: id, evaluation_mode: mode(id) })),
    ...overrides,
  } as unknown as AssembledPolicy;
}

describe("placing published rules into the policies their version records", () => {
  it("is a partition: nothing is lost, nothing is shown twice", () => {
    const policies = [
      policy("one", [{ key: "one-a", ruleIds: ["r1", "r2"] }]),
      policy("two", [
        { key: "two-a", ruleIds: ["r3"] },
        { key: "two-b", ruleIds: ["r4", "r5"] },
      ]),
    ];
    // One rule the version serves that no policy claims. It must survive.
    const rules = ["r1", "r2", "r3", "r4", "r5", "r6"].map((id) => rule(id));

    const cards = buildPublishedPolicyCards(policies, rules);
    const unplaced = unplacedPublishedRules(policies, rules);

    const placedIds = cards.flatMap((card) => card.rules.map((entry) => entry.rule_id));
    const allIds = [...placedIds, ...unplaced.map((r) => r.rule_id)].sort();

    expect(allIds).toEqual(rules.map((r) => r.rule_id).sort());
    expect(new Set(allIds).size).toBe(allIds.length);
    expect(unplaced.map((r) => r.rule_id)).toEqual(["r6"]);
  });

  it("keeps a policy's rules in the passages the source stated them in", () => {
    const policies = [
      policy("two", [
        { key: "two-a", ruleIds: ["r3"] },
        { key: "two-b", ruleIds: ["r4", "r5"] },
      ]),
    ];
    const cards = buildPublishedPolicyCards(
      policies,
      ["r5", "r3", "r4"].map((id) => rule(id)),
    );

    // Passage order and within-passage order come from the version, not from
    // the order the rules happened to arrive in.
    expect(cards[0].passages.map((p) => p.passage.key)).toEqual(["two-a", "two-b"]);
    expect(cards[0].rules.map((entry) => entry.rule_id)).toEqual(["r3", "r4", "r5"]);
  });

  it("counts what a narrowing is holding back, so a fragment is never shown as a whole", () => {
    const policies = [policy("one", [{ key: "one-a", ruleIds: ["r1", "r2", "r3"] }])];

    const whole = buildPublishedPolicyCards(
      policies,
      ["r1", "r2", "r3"].map((id) => rule(id)),
    );
    expect(whole[0].hiddenByFilter).toBe(0);

    // The same policy, with a narrowing that matched only one of its rules.
    const narrowed = buildPublishedPolicyCards(policies, [rule("r1")]);
    expect(narrowed[0].rules).toHaveLength(1);
    expect(narrowed[0].hiddenByFilter).toBe(
      policies[0].rule_count - narrowed[0].rules.length,
    );
  });

  it("drops a policy entirely rather than drawing an empty one", () => {
    const policies = [
      policy("one", [{ key: "one-a", ruleIds: ["r1"] }]),
      policy("two", [{ key: "two-a", ruleIds: ["r2"] }]),
    ];
    const cards = buildPublishedPolicyCards(policies, [rule("r2")]);
    expect(cards.map((card) => card.policy.key)).toEqual(["two"]);
  });
});

describe("what a published card says about itself", () => {
  it("names a policy by its heading, and says so when it has none", () => {
    const withHeading = policy("one", [{ key: "one-a", ruleIds: ["r1"] }]);
    expect(publishedPolicyTitle(withHeading, []).source).toBe("heading");
    expect(publishedPolicyTitle(withHeading, []).text).toBe(withHeading.heading);

    // `heading` is the document's own characters, so "no heading" is the empty
    // string rather than a null: the server sends what the document wrote.
    const headless: AssembledPolicy = {
      ...withHeading,
      heading: "",
      heading_path: [],
    };
    // With no heading and no passage to read one from, the card must not
    // invent a name: it reports that it has none.
    expect(publishedPolicyTitle(headless, []).source).toBe("unnamed");
  });

  it("reports a facet as shared only when every rule of the policy has it", () => {
    const uniformPolicy = [policy("one", [{ key: "one-a", ruleIds: ["r1", "r2"] }])];

    const uniform = buildPublishedPolicyCards(uniformPolicy, [
      rule("r1"),
      rule("r2"),
    ]);
    expect(publishedSharedFacets(uniform[0]).route).toBe("ai_ready");
    expect(publishedSharedFacets(uniform[0]).ruleType).toBe("obligation");

    const mixedPolicy = [
      policy("one", [{ key: "one-a", ruleIds: ["r1", "r2"] }], {}, { r2: "deterministic" }),
    ];
    const mixed = buildPublishedPolicyCards(mixedPolicy, [
      rule("r1"),
      rule("r2", { evaluation_mode: "deterministic", rule_type: "prohibition" }),
    ]);
    // A shared badge over rules that differ would be a claim about the policy
    // that is false of half of it, so the card must fall back to per-rule.
    expect(publishedSharedFacets(mixed[0]).route).toBeNull();
    expect(publishedSharedFacets(mixed[0]).ruleType).toBeNull();
  });

  it("describes what a policy is made of, and stays silent when there is nothing to contrast", () => {
    const deciding = [rule("r1"), rule("r2")].map((r) => asCardRule(r));
    // Every rule decides a case. "2 decide cases · 0 supply a meaning" tells a
    // reader nothing they cannot see from the rule count.
    expect(policyCompositionLabel(policyComposition(deciding))).toBeNull();

    const mixed = [
      ...deciding,
      asCardRule(rule("r3", { effect: { type: "informational" } as CanonicalRule["effect"] })),
    ];
    const counts = policyComposition(mixed);
    expect(counts).toEqual({ decide: 2, define: 1, unstated: 0 });
    const label = policyCompositionLabel(counts);
    expect(label).toBeTruthy();
    // Both halves must be readable as words, not as a bare pair of numerals.
    expect(label).toMatch(/2/);
    expect(label).toMatch(/1/);
  });
});

/**
 * One builder, one card, and a sealed record that seals itself.
 *
 * The published page used to have its own placement, its own card type and its
 * own serialiser, because the shared card named a reviewable draft row and a
 * published rule is not one. Two implementations of the same arrangement is the
 * drift this whole line of work exists to close, and it closed here the moment
 * the shared card started carrying a canonical rule and a status instead.
 *
 * What is asserted below is the property that made the collapse safe: nothing
 * tells the shared builder that these records are published. It reads each
 * record's own status through `candidateEditability` and returns an empty set of
 * decidable ids because the record answers no — so the same builder, handed a
 * record that is open to review, returns a non-empty one. If that reversal ever
 * stops holding, read-only has become a property of the page rather than of the
 * record, and the next page to show a published rule will get it wrong.
 */
describe("read-only as a fact about the record", () => {
  const A_POLICY = [policy("p", [{ key: "p-a", ruleIds: ["r1", "r2"] }])];

  it("offers no decision on a published version's rules", () => {
    const [card] = buildPublishedPolicyCards(A_POLICY, [rule("r1"), rule("r2")]);
    expect(card.rules).toHaveLength(2);
    expect(card.reviewableIds).toEqual([]);
    // Every rule is still addressable — a sealed record is read, copied and
    // asked about; it is only not decided.
    expect(card.allIds).toEqual(["r1", "r2"]);
  });

  it("carries no draft row behind a published rule", () => {
    const [card] = buildPublishedPolicyCards(A_POLICY, [rule("r1"), rule("r2")]);
    for (const entry of card.rules) {
      // A synthesised draft row would be a record no table holds, keyed by an
      // id that resolves to nothing, and everything downstream reaching for one
      // would find it.
      expect(entry.candidate).toBeUndefined();
      expect(entry.recordId).toBe(entry.rule_id);
    }
  });

  it("offers the decision when the same builder is handed a record open to one", () => {
    // The mutation that proves the previous two are about the record and not
    // about which builder was called: same policies, same shared builder, a
    // record that says it is under review.
    const [card] = buildPolicyCards(A_POLICY, [
      { rule: rule("r1"), review_status: "candidate", id: "a-draft-row" },
    ]);
    expect(card.reviewableIds).toEqual(["a-draft-row"]);
  });
});
