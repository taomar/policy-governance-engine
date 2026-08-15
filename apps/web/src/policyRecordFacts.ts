import type { CanonicalRule, PolicyScope, RequiredFact, RuleParty } from "./api";
import { policyRouteLabel } from "./policyGrouping";

/**
 * What a policy is, read off the rules it holds.
 *
 * A policy is a first-class record: persisted, reviewed as a unit, published as
 * a unit. But almost nothing is stored *about* a policy beyond its boundary and
 * its heading — the substance lives in its rules. So every question a reviewer
 * asks of a policy ("who does this bind", "what does deciding it need to know",
 * "who does it apply to") is answered by reading its rules together.
 *
 * Reading them together is the whole difficulty, and it is why this is a module
 * of its own rather than a loop inside a component. Two rules of one policy can
 * disagree, and the interesting cases are all disagreements:
 *
 *   - one rule restricts who it applies to and its neighbour does not;
 *   - one rule's test is a comparison and its neighbour's is stated in words;
 *   - one rule names an approver and the rest name nobody.
 *
 * A summary that merges those away tells the reviewer the policy speaks with one
 * voice when it does not. Every function here therefore returns what was found
 * *and* whether the rules agreed, and never collapses the second into the first.
 *
 * Nothing here is a judgement. `deterministic` and `ai_ready` are two routes to
 * a decision and this module ranks neither: a policy whose rules are all read
 * rather than computed is not thereby a lesser policy, and no count, ordering
 * or wording below may imply that it is.
 */

/** How many of a policy's rules decide an outcome, and how many define a term. */
export interface PolicyComposition {
  decide: number;
  define: number;
}

/**
 * The one axis that divides a policy's rules without double-counting them.
 *
 * There is an obvious three-way split — decision, definition, informational —
 * and it does not survive contact with the records: a rule whose effect type is
 * `informational` is, in the overwhelming majority, one whose rule type is
 * `definition`. Offering both as separate categories counts the same rules
 * twice and invites a reader to conclude the policy holds more than it does.
 *
 * So the split is binary and taken from the effect, which is the field that
 * says what the rule *does*: a rule that defines a term settles what words mean,
 * and every other rule settles an outcome.
 */
export function policyComposition(rules: readonly CanonicalRule[]): PolicyComposition {
  let define = 0;
  for (const rule of rules) if (rule.effect?.type === "informational") define += 1;
  return { decide: rules.length - define, define };
}

/**
 * The composition as a phrase, or null when there is nothing to contrast.
 *
 * Null when every rule falls on one side: "12 decide cases · 0 supply meanings"
 * invites the reader to look for the missing definitions, and there are none
 * missing — the policy simply does not define anything. A count of zero is the
 * shape a deficit takes, so it is not printed for something that is not one.
 * The head already carries the total, so a policy of one kind says nothing here
 * rather than saying its own count back a second time.
 */
export function policyCompositionLabel(composition: PolicyComposition): string | null {
  const { decide, define } = composition;
  if (decide === 0 || define === 0) return null;
  const decides = decide === 1 ? "1 decides a case" : `${decide} decide cases`;
  const defines = define === 1 ? "1 supplies a meaning" : `${define} supply meanings`;
  return `${decides} · ${defines}`;
}

/**
 * What the policy is made of, always as a true sentence.
 *
 * `policyCompositionLabel` returns null for two unrelated situations — a policy
 * whose rules all fall on one side, and a policy with no rules — and a caller
 * that renders one sentence for null tells the reader the wrong one of them. A
 * live published policy holding a rule was reading "states no rules yet, so
 * there is nothing to compose" underneath a head that said "1 rule".
 *
 * So the two are separated here rather than at each call site. A policy of one
 * kind is described by that kind and no count, which keeps the zero off the
 * page for the reason above while still saying something the head does not.
 */
export function policyCompositionSentence(rules: readonly CanonicalRule[]): string {
  if (rules.length === 0) return "This policy states no rules.";
  const composition = policyComposition(rules);
  const contrast = policyCompositionLabel(composition);
  if (contrast) return contrast;
  const settles =
    composition.define === rules.length ? "supplies a meaning" : "decides a case";
  return rules.length === 1
    ? `Its one rule ${settles}.`
    : `Every rule of this policy ${settles}.`;
}

/** One route through the policy's rules, with how many take it. */
export interface PolicyRouteTally {
  route: string;
  label: string;
  count: number;
}

/**
 * Which routes this policy's rules take to a decision.
 *
 * Routes with no rules are absent rather than listed as zero, for the reason
 * `projectRegisterRow` already established: "0 evaluated directly" reads as a
 * shortfall against a target, and there is no target. A policy every rule of
 * which is read yields exactly one entry, which is the truth about it.
 *
 * Ordered by count so the policy's predominant route reads first, with ties
 * broken by route name so the same policy always renders the same way.
 */
export function policyRoutes(rules: readonly CanonicalRule[]): PolicyRouteTally[] {
  const counts = new Map<string, number>();
  for (const rule of rules) {
    const route = rule.evaluation_mode ?? "ai_ready";
    counts.set(route, (counts.get(route) ?? 0) + 1);
  }
  return [...counts.entries()]
    .map(([route, count]) => ({ route, label: policyRouteLabel(route), count }))
    .sort((a, b) => b.count - a.count || a.route.localeCompare(b.route));
}

/** Whether every rule of the policy reaches its decision the same way. */
export function policyTakesOneRoute(rules: readonly CanonicalRule[]): boolean {
  return policyRoutes(rules).length <= 1;
}

/** A party named by at least one of the policy's rules. */
export interface PolicyPartyEntry {
  name: string;
  role: RuleParty["role"];
  /** The rules that name this party. A party named by one rule of twelve is a
   *  different fact from one named by all twelve, and the reviewer needs both. */
  ruleIds: string[];
}

/**
 * Who the policy names, gathered from its rules.
 *
 * Deduplicated on name and role together: the same person named as the subject
 * of one rule and the approver of another is two facts about the policy, not
 * one, and merging them would lose the distinction that matters most.
 */
export function policyParties(rules: readonly CanonicalRule[]): PolicyPartyEntry[] {
  const found = new Map<string, PolicyPartyEntry>();
  for (const rule of rules) {
    for (const party of rule.decision_readiness?.parties ?? []) {
      const key = `${party.role}\u0000${party.name}`;
      const existing = found.get(key);
      if (existing) existing.ruleIds.push(rule.rule_id);
      else found.set(key, { name: party.name, role: party.role, ruleIds: [rule.rule_id] });
    }
  }
  return [...found.values()];
}

/** Who set the policy's rules, and how many rules each set. */
export interface PolicyAuthorityEntry {
  owner: string;
  level: string;
  ruleIds: string[];
}

/**
 * The authorities behind the policy's rules.
 *
 * Separate from `policyParties` because these are not people the document
 * names — they are the record's own account of who put each rule there. A
 * reviewer weighing a policy wants to know whether it came from one hand or
 * several, and that question is about the record rather than about the source.
 */
export function policyAuthorities(rules: readonly CanonicalRule[]): PolicyAuthorityEntry[] {
  const found = new Map<string, PolicyAuthorityEntry>();
  for (const rule of rules) {
    const authority = rule.authority;
    if (!authority?.owner) continue;
    const key = `${authority.owner}\u0000${authority.level ?? ""}`;
    const existing = found.get(key);
    if (existing) existing.ruleIds.push(rule.rule_id);
    else found.set(key, { owner: authority.owner, level: authority.level ?? "", ruleIds: [rule.rule_id] });
  }
  return [...found.values()];
}

/** A fact one of the policy's rules needs before it can be computed. */
export interface PolicyRequiredFactEntry {
  fact: RequiredFact;
  ruleIds: string[];
}

/**
 * The facts the policy's rules need supplied to reach a decision.
 *
 * Gathered only from the rules that state a test as a comparison, because those
 * are the rules for which a named fact is what a decision waits on. A rule the
 * source states in words is decided by reading those words, so it names no
 * facts — and listing it here with an empty entry would put it in a column
 * headed by something it does not need, which reads as an omission on the
 * rule's part rather than a property of its route.
 *
 * The rules that name nothing are therefore not represented at all. What the
 * reviewer is told about them belongs in `policyRoutes`, where it is a route
 * and not an absence.
 */
export function policyRequiredFacts(rules: readonly CanonicalRule[]): PolicyRequiredFactEntry[] {
  const found = new Map<string, PolicyRequiredFactEntry>();
  for (const rule of rules) {
    for (const fact of rule.required_facts ?? []) {
      if (!fact?.name) continue;
      const existing = found.get(fact.name);
      if (existing) existing.ruleIds.push(rule.rule_id);
      else found.set(fact.name, { fact, ruleIds: [rule.rule_id] });
    }
  }
  return [...found.values()];
}

/** The four dimensions a rule's scope is stated in, in a fixed order. */
const SCOPE_DIMENSIONS = [
  { key: "personas", label: "Persona" },
  { key: "organizational_units", label: "Business Unit" },
  { key: "jurisdictions", label: "Jurisdiction" },
  { key: "processes", label: "Process" },
] as const satisfies readonly { key: keyof PolicyScope; label: string }[];

export interface PolicyScopeDimension {
  key: keyof PolicyScope;
  label: string;
  /** Every value any rule of the policy named on this dimension, deduplicated. */
  values: string[];
  /** Rules that named nothing here, and so apply to everyone on this dimension. */
  unrestrictedRuleIds: string[];
  /** Rules that named something here. */
  restrictedRuleIds: string[];
  /**
   * Whether the policy's rules say the same thing on this dimension.
   *
   * `uniform` when every rule named the identical set — including the case
   * where every rule named nothing at all, which is a policy that applies to
   * everyone and is a perfectly good answer.
   *
   * `mixed` when they did not. This is the finding: a policy whose rules are
   * scoped differently binds different people depending on which of its rules
   * is being applied, which the reviewer is entitled to see before deciding it.
   */
  agreement: "uniform" | "mixed";
}

/**
 * The policy's scope, as the union of its rules' scopes, with disagreement kept.
 *
 * The union alone cannot be the answer, and the reason is a quiet one. An empty
 * list on a rule does not mean "nothing" — it means "everyone". So unioning the
 * value lists of a rule scoped to one persona and a rule scoped to all of them
 * yields that one persona, and states that the policy is narrower than it is.
 * The rule that applies to everyone disappears into the answer.
 *
 * So the union is reported alongside how many rules named nothing, and the two
 * together are what the reviewer reads. Where they conflict the dimension is
 * `mixed`, and a surface drawing this must show that rather than pick a side.
 */
export function policyScope(rules: readonly CanonicalRule[]): PolicyScopeDimension[] {
  return SCOPE_DIMENSIONS.map(({ key, label }) => {
    const values: string[] = [];
    const seen = new Set<string>();
    const unrestrictedRuleIds: string[] = [];
    const restrictedRuleIds: string[] = [];
    const signatures = new Set<string>();

    for (const rule of rules) {
      const named = rule.scope?.[key] ?? [];
      signatures.add([...named].sort().join("\u0000"));
      if (named.length === 0) unrestrictedRuleIds.push(rule.rule_id);
      else restrictedRuleIds.push(rule.rule_id);
      for (const value of named) {
        if (seen.has(value)) continue;
        seen.add(value);
        values.push(value);
      }
    }

    return {
      key,
      label,
      values,
      unrestrictedRuleIds,
      restrictedRuleIds,
      agreement: signatures.size > 1 ? "mixed" : "uniform",
    };
  });
}

/** The dimensions on which this policy's rules do not agree. */
export function policyScopeDisagreements(rules: readonly CanonicalRule[]): PolicyScopeDimension[] {
  return policyScope(rules).filter((dimension) => dimension.agreement === "mixed");
}
