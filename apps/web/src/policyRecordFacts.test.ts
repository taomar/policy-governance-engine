/**
 * What a policy says about itself when its rules are read together.
 *
 * THE FAILURE THESE EXIST TO PREVENT
 *
 * A policy-level summary is a merge, and a merge is where facts go to be lost.
 * The two losses that matter here are both silent — the summary renders, looks
 * complete, and is wrong:
 *
 *   1. An unrestricted rule disappearing into a restricted one. A rule that
 *      names no persona applies to every persona. Union its value list with a
 *      neighbour's and you get the neighbour's list, and the policy is reported
 *      as narrower than it is.
 *
 *   2. A route being reported as a shortfall. A rule the source states in words
 *      names no facts, because it needs none. Rendered in a column beside a rule
 *      that names three, that reads as an omission.
 *
 * Both are asserted below against rules built to disagree, because a fixture
 * whose rules agree cannot fail either way.
 */
import { describe, expect, it } from "vitest";
import type { CanonicalRule, PolicyScope } from "./api";
import {
  policyAuthorities,
  policyComposition,
  policyCompositionLabel,
  policyParties,
  policyRequiredFacts,
  policyRoutes,
  policyScope,
  policyScopeDisagreements,
  policyTakesOneRoute,
  policyUnitCount,
  recordProgressLabel,
  recordScaleLabel,
  reviewBacklogBadge,
} from "./policyRecordFacts";

function rule(
  id: string,
  overrides: Partial<CanonicalRule> = {},
): CanonicalRule {
  return {
    rule_id: id,
    title: id,
    description: "",
    rule_type: "obligation",
    effect: { type: "require_action", action: "do the thing" },
    authority: { owner: "policy-formulator", level: "ai_drafted", rank: 0 },
    scope: { jurisdictions: [], organizational_units: [], personas: [], processes: [] },
    condition: { type: "all", all: [] },
    evaluation_mode: "ai_ready",
    required_facts: [],
    exceptions: [],
    priority: 0,
    effective_from: "2026-01-01",
    effective_to: null,
    machine_executable: false,
    ambiguity_status: "none",
    review_status: "candidate",
    evidence: [],
    lineage: { source_document_id: "d", source_version_id: "v", extracted_by: "x", extracted_at: "t" },
    category: "",
    tags: [],
    group_label: "",
    related_rule_ids: [],
    is_explicit_override: false,
    supersedes_rule_ids: [],
    advice: [],
    ...overrides,
  } as CanonicalRule;
}

const scopeOf = (partial: Partial<PolicyScope>): PolicyScope => ({
  jurisdictions: [],
  organizational_units: [],
  personas: [],
  processes: [],
  ...partial,
});

describe("what a policy is made of", () => {
  it("splits its rules on one axis so none is counted twice", () => {
    const rules = [
      rule("a"),
      rule("b", { effect: { type: "informational", action: "means" } }),
      rule("c", { effect: { type: "deny", action: "no" } }),
    ];
    expect(policyComposition(rules)).toEqual({ decide: 2, define: 1, unstated: 0 });
  });

  it("counts a rule with no readable effect apart, rather than as one that decides", () => {
    // The parts are read against the head count, so they have to sum. This
    // function used to ask the axis question inline as
    // `effect?.type === "informational"`, which put a rule carrying no effect
    // at all on the deciding side — leaving the total right and the split
    // wrong, which is the version of this bug a reader cannot catch.
    const rules = [
      rule("a", { effect: { type: "deny", action: "no" } }),
      rule("b", { effect: undefined }),
      rule("c", { effect: { type: "informational", action: "means" } }),
    ];
    const composition = policyComposition(rules);

    expect(composition).toEqual({ decide: 1, define: 1, unstated: 1 });
    expect(composition.decide + composition.define + composition.unstated).toBe(rules.length);
  });

  it("says nothing when every rule is the same kind, rather than printing a zero", () => {
    // The head already carries the total. "3 decide what happens · 0 supply meanings"
    // asks the reader to look for definitions that were never missing.
    const oneKind = [rule("a"), rule("b"), rule("c")];
    expect(policyCompositionLabel(policyComposition(oneKind))).toBeNull();

    const twoKinds = [rule("a"), rule("b", { effect: { type: "informational", action: "means" } })];
    const label = policyCompositionLabel(policyComposition(twoKinds));
    expect(label).toBe("1 decides what happens · 1 supplies a meaning");
  });
});

describe("how a policy's rules reach a decision", () => {
  it("lists only the routes its rules take", () => {
    const allRead = [rule("a"), rule("b")];
    expect(policyRoutes(allRead)).toEqual([
      { route: "ai_ready", label: "AI Ready", count: 2 },
    ]);
    expect(policyTakesOneRoute(allRead)).toBe(true);
  });

  it("never reports a route no rule takes as a count of zero", () => {
    // A zero beside a route is the shape of a shortfall against a target, and
    // there is no target: both routes are ways of deciding, not grades.
    const routes = policyRoutes([rule("a"), rule("b")]);
    expect(routes.every((entry) => entry.count > 0)).toBe(true);
    expect(routes.map((entry) => entry.route)).not.toContain("deterministic");
  });

  it("reports both routes, predominant first, when the rules differ", () => {
    const mixed = [
      rule("a"),
      rule("b"),
      rule("c", { evaluation_mode: "deterministic" }),
    ];
    const routes = policyRoutes(mixed);
    expect(routes.map((entry) => entry.count)).toEqual([2, 1]);
    expect(policyTakesOneRoute(mixed)).toBe(false);
  });
});

describe("what deciding a policy needs to be told", () => {
  it("gathers facts only from the rules that name them, and represents the others not at all", () => {
    // The AI Ready rule is absent from this list rather than present
    // with nothing in it: an empty row under "required facts" reads as a rule
    // that failed to supply them, and this one was never asked to.
    const rules = [
      rule("computes", {
        evaluation_mode: "deterministic",
        required_facts: [{ name: "days", data_type: "number", required: true }],
      }),
      rule("read"),
    ];
    const facts = policyRequiredFacts(rules);
    expect(facts).toHaveLength(1);
    expect(facts[0].fact.name).toBe("days");
    expect(facts[0].ruleIds).toEqual(["computes"]);
    expect(facts.flatMap((entry) => entry.ruleIds)).not.toContain("read");
  });

  it("records every rule that needs the same fact, not just the first", () => {
    const rules = [
      rule("a", { required_facts: [{ name: "days", data_type: "number", required: true }] }),
      rule("b", { required_facts: [{ name: "days", data_type: "number", required: true }] }),
    ];
    expect(policyRequiredFacts(rules)[0].ruleIds).toEqual(["a", "b"]);
  });
});

describe("who a policy names", () => {
  it("keeps one person's two roles apart", () => {
    const rules = [
      rule("a", {
        decision_readiness: {
          evaluability: "discretionary",
          required_attributes: [],
          parties: [{ name: "the committee", role: "authority", source: "s" }],
        },
      }),
      rule("b", {
        decision_readiness: {
          evaluability: "discretionary",
          required_attributes: [],
          parties: [{ name: "the committee", role: "access_subject", source: "s" }],
        },
      }),
    ];
    const parties = policyParties(rules);
    expect(parties).toHaveLength(2);
    expect(new Set(parties.map((entry) => entry.role))).toEqual(
      new Set(["authority", "access_subject"]),
    );
  });

  it("says how many of the policy's rules name each party", () => {
    const named = {
      evaluability: "discretionary" as const,
      required_attributes: [],
      parties: [{ name: "the committee", role: "authority" as const, source: "s" }],
    };
    const parties = policyParties([
      rule("a", { decision_readiness: named }),
      rule("b", { decision_readiness: named }),
      rule("c"),
    ]);
    expect(parties[0].ruleIds).toEqual(["a", "b"]);
  });

  it("returns nothing rather than an empty shell when no rule names anyone", () => {
    expect(policyParties([rule("a"), rule("b")])).toEqual([]);
  });

  it("gathers who set the rules separately from who the document names", () => {
    const authorities = policyAuthorities([
      rule("a"),
      rule("b", { authority: { owner: "a-person", level: "human_authored", rank: 1 } }),
    ]);
    expect(authorities).toHaveLength(2);
    expect(authorities.map((entry) => entry.owner).sort()).toEqual(["a-person", "policy-formulator"]);
  });
});

describe("who a policy applies to", () => {
  it("does not let a rule that applies to everyone vanish into one that does not", () => {
    // This is the merge that must not happen. Rule `b` names no persona, so it
    // binds every persona. A union of the value lists alone would report this
    // policy as applying to one persona, which is narrower than it is.
    const rules = [
      rule("a", { scope: scopeOf({ personas: ["one-persona"] }) }),
      rule("b"),
    ];
    const personas = policyScope(rules).find((dimension) => dimension.key === "personas")!;
    expect(personas.values).toEqual(["one-persona"]);
    expect(personas.unrestrictedRuleIds).toEqual(["b"]);
    expect(personas.agreement).toBe("mixed");
  });

  it("calls a dimension uniform when every rule says the same thing", () => {
    const same = [
      rule("a", { scope: scopeOf({ personas: ["one-persona"] }) }),
      rule("b", { scope: scopeOf({ personas: ["one-persona"] }) }),
    ];
    const personas = policyScope(same).find((dimension) => dimension.key === "personas")!;
    expect(personas.agreement).toBe("uniform");
    expect(personas.unrestrictedRuleIds).toEqual([]);
  });

  it("calls a dimension uniform when no rule restricts it at all", () => {
    // A policy that applies to everyone is a complete answer, not a gap.
    const personas = policyScope([rule("a"), rule("b")]).find(
      (dimension) => dimension.key === "personas",
    )!;
    expect(personas.agreement).toBe("uniform");
    expect(personas.values).toEqual([]);
    expect(personas.restrictedRuleIds).toEqual([]);
  });

  it("treats two different restrictions as a disagreement, not a longer list", () => {
    const rules = [
      rule("a", { scope: scopeOf({ jurisdictions: ["one-place"] }) }),
      rule("b", { scope: scopeOf({ jurisdictions: ["another-place"] }) }),
    ];
    const disagreements = policyScopeDisagreements(rules);
    expect(disagreements.map((dimension) => dimension.key)).toEqual(["jurisdictions"]);
    expect(disagreements[0].values).toEqual(["one-place", "another-place"]);
  });

  it("reports no disagreement when the rules genuinely agree", () => {
    expect(policyScopeDisagreements([rule("a"), rule("b")])).toEqual([]);
  });

  it("always reports every dimension, so one is never silently dropped", () => {
    const dimensions = policyScope([rule("a")]).map((dimension) => dimension.key);
    expect(dimensions).toEqual([
      "personas",
      "organizational_units",
      "jurisdictions",
      "processes",
    ]);
  });
});

/**
 * The size of the job, stated in the unit the job is done in.
 *
 * THE FAILURE THIS EXISTS TO PREVENT
 *
 * A queue of policies headed by a rule count invites the reviewer to read that
 * number as how many decisions are ahead of them. It is not: the same number of
 * rules can be a handful of policies or hundreds, and nothing in the number
 * says which. Leading with policies fixes the unit; keeping the rule count
 * beside it keeps the fact that a policy is made of rules.
 *
 * The second failure is quieter. A surface that has not assembled its policies
 * yet knows the rule count and nothing else, and a label that fills that hole
 * with zero reports a measurement nobody took — worse than the rule count on
 * its own, because it looks like an answer.
 */
describe("recordScaleLabel", () => {
  it("leads with the unit the work is decided in", () => {
    expect(recordScaleLabel(70, 398)).toBe("70 policies · 398 rules");
  });

  it("keeps the rule count, because a policy is made of rules", () => {
    expect(recordScaleLabel(70, 398)).toContain("398 rules");
  });

  it("says only what it knows when the policies are not counted yet", () => {
    expect(recordScaleLabel(null, 398)).toBe("398 rules");
  });

  it("never reports zero policies for an uncounted queue", () => {
    expect(recordScaleLabel(null, 398)).not.toMatch(/0 polic/);
  });

  it("distinguishes an empty result from an uncounted one", () => {
    expect(recordScaleLabel(0, 0)).toBe("0 policies · 0 rules");
    expect(recordScaleLabel(null, 0)).toBe("0 rules");
  });

  it("agrees with itself about one", () => {
    expect(recordScaleLabel(1, 1)).toBe("1 policy · 1 rule");
    expect(recordScaleLabel(2, 2)).toBe("2 policies · 2 rules");
  });

  it("states both counts exactly, rounding and abbreviating nothing", () => {
    for (const [policies, rules] of [
      [1, 1],
      [9, 10],
      [70, 398],
      [1234, 56789],
    ] as const) {
      const label = recordScaleLabel(policies, rules);
      expect(label).toContain(String(policies));
      expect(label).toContain(String(rules));
      expect(label).not.toMatch(/[~kKmM+]/);
    }
  });

  it("never adds the two counts together, because they count different things", () => {
    expect(recordScaleLabel(70, 398)).not.toContain("468");
  });

  it("names no route, and so cannot rank one", () => {
    for (const label of [recordScaleLabel(70, 398), recordScaleLabel(null, 1)]) {
      expect(label).not.toMatch(/deterministic|ai.ready|read|comput/i);
    }
  });
});

/**
 * A number in a pill, and the unit it is counted in.
 *
 * THE FAILURE THIS EXISTS TO PREVENT
 *
 * A badge is a bare number: the same pill reading 398 or 70 looks identical,
 * so whichever it holds the reader supplies the unit themselves. Beside a queue
 * of policies they supply "policies", and a rule count there quietly overstates
 * the work ahead by however many rules a policy happens to hold.
 *
 * The second failure is the fix going wrong. The policy count comes from a
 * server field that a not-yet-restarted server does not send, and reading that
 * absence as zero would badge an empty queue over work that is plainly there.
 * Absent falls back and says which unit it fell back to; it never invents one.
 */
describe("reviewBacklogBadge", () => {
  it("badges the unit the work is decided in", () => {
    expect(reviewBacklogBadge(398, 70).value).toBe(70);
  });

  it("names the unit, because the pill cannot", () => {
    expect(reviewBacklogBadge(398, 70).hint).toContain("70 policies");
    expect(reviewBacklogBadge(398, 70).hint).toContain("398 rules");
  });

  it("falls back to what it has when the policy count is not served", () => {
    const badge = reviewBacklogBadge(398, undefined);
    expect(badge.value).toBe(398);
    expect(badge.hint).toContain("398 rules");
  });

  it("does not read an unserved policy count as none outstanding", () => {
    expect(reviewBacklogBadge(398, undefined).value).not.toBe(0);
    expect(reviewBacklogBadge(398, undefined).value).not.toBeNull();
    expect(reviewBacklogBadge(398, undefined).hint).not.toContain("0 polic");
  });

  it("does not claim a policy unit it was not given", () => {
    expect(reviewBacklogBadge(398, undefined).hint).not.toMatch(/polic/i);
  });

  it("withholds the pill only when the work really is finished", () => {
    expect(reviewBacklogBadge(0, 0).value).toBeNull();
    expect(reviewBacklogBadge(398, 0).value).toBeNull();
  });

  it("says something even before any count has arrived", () => {
    const badge = reviewBacklogBadge(undefined, undefined);
    expect(badge.value).toBeNull();
    expect(badge.hint.trim().length).toBeGreaterThan(0);
    expect(badge.hint).not.toMatch(/\d/);
  });

  it("agrees with itself about one", () => {
    expect(reviewBacklogBadge(1, 1).hint).toContain("1 policy · 1 rule");
  });

  it("ranks no route, and calls no record a shortfall", () => {
    for (const badge of [
      reviewBacklogBadge(398, 70),
      reviewBacklogBadge(398, undefined),
      reviewBacklogBadge(undefined, undefined),
    ]) {
      expect(badge.hint).not.toMatch(
        /deterministic|ai.ready|unread|cannot|fail|gap|limitation|incomplete|missing/i,
      );
    }
  });

  it("shows the same number the hint leads with, so the two cannot disagree", () => {
    for (const [rules, policies] of [
      [398, 70],
      [1, 1],
      [9, 4],
    ] as const) {
      const badge = reviewBacklogBadge(rules, policies);
      expect(badge.hint.startsWith(String(badge.value))).toBe(true);
    }
  });
});

/**
 * THE FAILURE THIS EXISTS TO PREVENT
 *
 * A queue that plainly holds work reporting no policies at all. The count of
 * policies is not the count of records, and the two ways of getting it wrong
 * pull in opposite directions:
 *
 *   1. Counting distinct provisions only. Every record attached to no provision
 *      then vanishes, and a queue of four hundred ungrouped records reports
 *      zero policies -- a nought over a queue that plainly holds work.
 *
 *   2. Counting the records. That is the rule count wearing the policy count's
 *      name, and it overstates the job: four hundred rules can be seventy
 *      decisions, and the number alone does not say which.
 *
 * Asserted below against inputs built to separate the two, because a fixture
 * where every record carries its own provision cannot tell them apart.
 */
describe("counting a queue in policies", () => {
  const record = (provision: string | null | undefined) => ({ provision_id: provision });

  it("counts one policy per provision however many records share it", () => {
    expect(
      policyUnitCount([record("p1"), record("p1"), record("p1"), record("p2")]),
    ).toBe(2);
  });

  it("does not lose a record that belongs to no provision", () => {
    // The nought this prevents: three records, no provisions, and a distinct
    // count of provisions is zero. Nothing groups an ungrouped record, so it
    // is its own unit of review.
    expect(policyUnitCount([record(null), record(undefined), record("")])).toBe(3);
  });

  it("partitions rather than double-counting", () => {
    const mixed = [record("p1"), record("p1"), record(null), record("p2"), record(null)];
    expect(policyUnitCount(mixed)).toBe(4);
    expect(policyUnitCount(mixed)).toBeLessThan(mixed.length);
  });

  it("is zero only when there is genuinely nothing", () => {
    expect(policyUnitCount([])).toBe(0);
  });

  it("never reports fewer policies than an empty queue over a queue holding records", () => {
    for (const records of [
      [record("p1")],
      [record(null)],
      [record("p1"), record(null)],
      [record("p1"), record("p1")],
    ]) {
      expect(policyUnitCount(records)).toBeGreaterThan(0);
    }
  });
});

/**
 * THE FAILURE THIS EXISTS TO PREVENT
 *
 * "13 of 279" over a queue whose unit of review is the policy. The reader is
 * given a fraction and no unit, and 13/279 rules is a different statement from
 * 13/70 policies -- one of them says the job is nearly untouched and the other
 * that a fifth of it is done.
 *
 * The absent case matters as much as the present one: a surface that has not
 * been served the policy figure must still name what its number counts, rather
 * than falling back to a bare fraction or inventing a nought.
 */
describe("stating progress in the unit the work is done in", () => {
  it("leads with policies and keeps the rules", () => {
    expect(recordProgressLabel(4, 32, 13, 279)).toBe("4 of 32 policies · 13 of 279 rules");
  });

  it("joins the two rather than summing them", () => {
    const label = recordProgressLabel(4, 32, 13, 279);
    expect(label).toContain("32");
    expect(label).toContain("279");
    expect(label).not.toContain("311");
  });

  it("names the unit even when the policy figure is absent", () => {
    for (const label of [
      recordProgressLabel(null, 32, 13, 279),
      recordProgressLabel(4, null, 13, 279),
      recordProgressLabel(null, null, 13, 279),
    ]) {
      expect(label).toBe("13 of 279 rules");
      expect(label).toMatch(/rules?$/);
    }
  });

  it("does not report a policy figure it was not given", () => {
    // Absent is not zero. "0 of 0 policies" beside 13 of 279 rules is a
    // measurement nobody took.
    expect(recordProgressLabel(null, null, 13, 279)).not.toContain("polic");
  });

  it("reads in the singular when there is one of a thing", () => {
    expect(recordProgressLabel(1, 1, 1, 1)).toBe("1 of 1 policy · 1 of 1 rule");
  });

  it("survives a genuinely empty queue without claiming anything", () => {
    expect(recordProgressLabel(0, 0, 0, 0)).toBe("0 of 0 policies · 0 of 0 rules");
  });
});