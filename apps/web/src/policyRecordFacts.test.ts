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
    // The head already carries the total. "3 decide cases · 0 supply meanings"
    // asks the reader to look for definitions that were never missing.
    const oneKind = [rule("a"), rule("b"), rule("c")];
    expect(policyCompositionLabel(policyComposition(oneKind))).toBeNull();

    const twoKinds = [rule("a"), rule("b", { effect: { type: "informational", action: "means" } })];
    const label = policyCompositionLabel(policyComposition(twoKinds));
    expect(label).toBe("1 decides a case · 1 supplies a meaning");
  });
});

describe("how a policy's rules reach a decision", () => {
  it("lists only the routes its rules take", () => {
    const allRead = [rule("a"), rule("b")];
    expect(policyRoutes(allRead)).toEqual([
      { route: "ai_ready", label: "Decided by reading", count: 2 },
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
    // The rule decided by reading is absent from this list rather than present
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
