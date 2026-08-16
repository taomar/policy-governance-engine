import type { CanonicalRule, PolicyScope, RequiredFact, RuleParty } from "./api";
import { policyRouteLabel } from "./policyGrouping";
import {
  compositionPhrase,
  recordStance,
  stanceComposition,
  stanceHeading,
  type RecordStance,
} from "./recordStance";

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

/**
 * How many of a policy's rules take each stance.
 *
 * `unstated` is a third number, not a rounding error. A record carrying no
 * effect to read is one the app knows nothing about, and adding it to either
 * side would claim knowledge that was never there — while leaving the total
 * correct, which is precisely what would make the claim invisible.
 */
export interface PolicyComposition {
  decide: number;
  define: number;
  unstated: number;
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
 * So the split is taken from the effect, which is the field that says what the
 * rule *does*: a rule that defines a term settles what words mean, and every
 * other rule settles an outcome.
 *
 * The question itself is not asked here. `recordStance` owns it, with the
 * reasoning for why the axis is what a record does rather than what it is
 * about, and why an unfamiliar effect counts as constraining. This function
 * used to ask it inline, and that second copy answered differently: it read
 * `effect?.type === "informational"` and so counted a record with no effect at
 * all as one that decides what happens. Every count here is now that module's.
 */
export function policyComposition(rules: readonly CanonicalRule[]): PolicyComposition {
  const tally = stanceComposition(rules, recordStance);
  const count = (stance: RecordStance) =>
    tally.find((entry) => entry.stance === stance)?.count ?? 0;
  return {
    decide: count("decides"),
    define: count("supplies-meaning"),
    unstated: count("unstated"),
  };
}

/**
 * The composition as a phrase, or null when there is nothing to contrast.
 *
 * Null when every rule falls on one side: "12 decide what happens · 0 supply meanings"
 * invites the reader to look for the missing definitions, and there are none
 * missing — the policy simply does not define anything. A count of zero is the
 * shape a deficit takes, so it is not printed for something that is not one.
 * The head already carries the total, so a policy of one kind says nothing here
 * rather than saying its own count back a second time.
 *
 * Built from whatever stances are present rather than from a fixed pair of
 * slots, so a policy holding a record with no readable effect can say so
 * instead of that record being counted as something it is not.
 */
export function policyCompositionLabel(composition: PolicyComposition): string | null {
  return compositionPhrase(
    [
      { stance: "decides" as const, count: composition.decide },
      { stance: "supplies-meaning" as const, count: composition.define },
      { stance: "unstated" as const, count: composition.unstated ?? 0 },
    ].filter((entry) => entry.count > 0),
  );
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
  const contrast = policyCompositionLabel(policyComposition(rules));
  if (contrast) return contrast;
  // One stance holds every rule, so naming it needs no count. Asked of the
  // records rather than inferred from the counts, so a policy whose rules all
  // carry no readable effect says that rather than being described as deciding.
  //
  // Read in the singular whatever the count, because both sentences below take
  // a singular subject — "Its one rule", "Every rule" — and the heading's plural
  // form is built for a group heading standing over many rows, not for this.
  const settles = stanceHeading(recordStance(rules[0]), 1).toLowerCase();
  return rules.length === 1
    ? `Its one rule ${settles}.`
    : `Every rule of this policy ${settles}.`;
}

/**
 * How much there is to work through, said in the unit the work is done in.
 *
 * A reviewer decides policies. The rule count answered a different question —
 * how many records the extraction produced — and standing alone at the top of a
 * queue of policies it read as the size of the job, which it is not: four
 * hundred rules can be seventy decisions or four hundred, and the number alone
 * does not say which.
 *
 * So the policy count leads and the rule count follows it, and neither is
 * dropped: the rules are what a policy is made of and a reviewer sizing a card
 * still wants them. Both are exact — this rounds nothing and approximates
 * nothing, and the two numbers are counts of different things rather than parts
 * of one total, so they are joined rather than summed.
 *
 * `policies` may be null, which is not zero: a surface that has not assembled
 * the policies yet cannot say how many there are, and saying "0 policies" over
 * a queue holding rules would be a measurement nobody took. It then says what
 * it can, which is the rule count on its own.
 */
export function recordScaleLabel(policies: number | null, rules: number): string {
  const rulePart = `${rules} ${rules === 1 ? "rule" : "rules"}`;
  if (policies === null) return rulePart;
  return `${policies} ${policies === 1 ? "policy" : "policies"} · ${rulePart}`;
}

/**
 * How many policies a set of candidate records amounts to.
 *
 * A policy is the unit of review, approval, publication and export; the records
 * are its contents, and one policy commonly holds several. Counting the records
 * answers a different question from the one a reviewer sizing a queue is asking.
 *
 * Deliberately the same arithmetic the server does for `review_pending_policies`
 * — distinct provisions, plus one apiece for the records attached to no
 * provision. The second term is not double-counting: nothing groups a record
 * with no provision, so it is its own unit, and the two terms partition the
 * input on whether `provision_id` is set. Dropping it would let a queue that
 * plainly holds work report no policies at all.
 *
 * Matching the server's arithmetic exactly is the point. A client that counted
 * differently would put two numbers for one quantity on the same screen, and a
 * reader has no way to tell which is the measurement.
 */
export function policyUnitCount(
  records: readonly { readonly provision_id?: string | null }[],
): number {
  const provisions = new Set<string>();
  let ungrouped = 0;
  for (const record of records) {
    const provision = record.provision_id;
    if (provision) provisions.add(provision);
    else ungrouped += 1;
  }
  return provisions.size + ungrouped;
}

/**
 * How far through something is, said in both units.
 *
 * The same rule as `recordScaleLabel` — policies lead, rules stay, neither is
 * dropped and the two are joined rather than summed — in the shape a progress
 * figure needs. "13 of 279" cannot be built out of a scale label, because a
 * scale states one quantity and this states a part of a whole; they share the
 * unit-naming and nothing else, which is why this is a sibling rather than a
 * caller.
 *
 * A null policy figure is absent, not zero. It falls back to stating the rule
 * progress *and naming it as rules*, so the number a reader is given always
 * carries the unit it was measured in.
 */
export function recordProgressLabel(
  donePolicies: number | null,
  allPolicies: number | null,
  doneRules: number,
  allRules: number,
): string {
  const rulePart = `${doneRules} of ${allRules} ${allRules === 1 ? "rule" : "rules"}`;
  if (donePolicies === null || allPolicies === null) return rulePart;
  const policyNoun = allPolicies === 1 ? "policy" : "policies";
  return `${donePolicies} of ${allPolicies} ${policyNoun} · ${rulePart}`;
}

/**
 * What a count badge should show for a policy/rule pair, and what to say it is.
 *
 * A badge is a bare number in a pill: it has no room for a unit, so the number
 * has to be the one the reader assumes. Beside a queue of policies that is the
 * policy count, and showing the rule count there overstates the work — the same
 * pill reading 398 or 70 is indistinguishable without a unit, which is exactly
 * the ambiguity a bare count invites.
 *
 * So the unit is never left to the reader: the returned `hint` always names it,
 * and the two numbers are returned together so a surface with room can show
 * both. When the policy count is absent — a server that does not serve it yet —
 * this falls back to the rule count and *says so*, rather than badging a
 * confident policy figure it does not have or a zero it never measured.
 */
export interface ReviewBacklogBadge {
  /** The number to put in the pill, or null when there is nothing outstanding. */
  value: number | null;
  /** What that number counts, always stated because the pill cannot state it. */
  hint: string;
}

/**
 * The lead-with-policies badge, shared by every tab that counts a policy/rule
 * pair. The pill carries the policy count — the unit the work is governed in —
 * and the `hint` states both numbers via `recordScaleLabel` so the bare pill is
 * never read in a unit the reader supplied. `trailingClause` says what the pair
 * is being counted for ("waiting for a decision.", "in the currently active
 * published version."), and is capitalised into a standalone line only when
 * there is no count to lead with yet. An absent policy count falls back to the
 * rule count and *says so*; it never invents a policy figure or a measured zero.
 */
export function recordScaleBadge(
  rules: number | null | undefined,
  policies: number | null | undefined,
  trailingClause: string,
): ReviewBacklogBadge {
  const ruleCount = typeof rules === "number" ? rules : null;
  const policyCount = typeof policies === "number" ? policies : null;

  if (policyCount !== null) {
    return {
      value: policyCount === 0 ? null : policyCount,
      hint:
        ruleCount === null
          ? `${policyCount} ${policyCount === 1 ? "policy" : "policies"} ${trailingClause}`
          : `${recordScaleLabel(policyCount, ruleCount)} ${trailingClause}`,
    };
  }
  if (ruleCount !== null) {
    return {
      value: ruleCount === 0 ? null : ruleCount,
      hint: `${recordScaleLabel(null, ruleCount)} ${trailingClause}`,
    };
  }
  const [first, ...rest] = trailingClause;
  return { value: null, hint: first ? `${first.toUpperCase()}${rest.join("")}` : trailingClause };
}

/**
 * The review tab's backlog badge: `recordScaleBadge` with the review wording.
 *
 * Kept as a named wrapper because its call sites read as "the review badge" and
 * its exact phrasing ("… waiting for a decision.") is pinned by tests; the
 * lead-with-policies logic itself lives once, in `recordScaleBadge`, so the
 * publish tab cannot drift from it.
 */
export function reviewBacklogBadge(
  rules: number | null | undefined,
  policies: number | null | undefined,
): ReviewBacklogBadge {
  return recordScaleBadge(rules, policies, "waiting for a decision.");
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
 * `projectRegisterRow` already established: a route name over a nought reads as a
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
 * are the rules for which a named fact is what a decision waits on. An AI Ready
 * rule is decided from the words of its source, so it names no
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
