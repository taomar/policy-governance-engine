/**
 * Arranging the review queue by the passage each rule came from.
 *
 * THE DEFECT THIS CLOSES
 *
 * One sentence can impose several obligations -- "staff must read, understand
 * and comply with the policies" is one passage stating three rules. The queue
 * listed them as three unrelated cards, because it reads the flat rule list and
 * the flat rule list is exactly that: flat.
 *
 * The assembling view already existed on the server, was correct, and was
 * called by nothing. This module is the wiring, not a second implementation.
 *
 * WHY THE GROUPING IS NOT COMPUTED HERE
 *
 * Everything below indexes and arranges what the server returned. No function
 * here decides which rules belong together. That decision lives in one place --
 * `policy_assembly.py` -- and a second copy in the client would be free to
 * disagree with it, silently, on exactly the records where it matters most.
 * This repository already carries the scar of two parsers.
 *
 * WHAT MUST SURVIVE CONTACT
 *
 * A policy of one rule is the ordinary case, not a degenerate one. Most
 * policies hold one rule and they are built the same way as a policy holding
 * nine; nothing here may treat them as a special case or wrap them in an empty
 * container.
 *
 * Route is a property of a rule, not of a policy. A policy can hold a rule
 * whose test is a comparison and a rule the source states in words -- "thirty
 * days annual leave" and "subject to Immigration rules" are one policy. A
 * summary sits on the header for orientation, and the per-rule route is never
 * replaced by it.
 */

import type { AssembledPolicy } from "./api";

export interface PolicyBand {
  policy: AssembledPolicy;
  /** This row opens the policy's run on the current page, so it takes the
   *  header. */
  isStart: boolean;
  /** Rules of this policy present on the current page. */
  inView: number;
  /** Rules of this policy in total, which may exceed `inView` when a page
   *  boundary or a filter falls inside the policy. */
  total: number;
  /** Earlier rules of this policy exist but are not on this page. */
  continuesAbove: boolean;
  /** Later rules of this policy exist but are not on this page. */
  continuesBelow: boolean;
}

/**
 * Index the assembled policies by the rules they contain.
 *
 * A rule appearing in two policies would mean the server broke its own
 * partition; the last write would win here and the queue would quietly show a
 * rule under the wrong passage. Rather than paper over that, the index keeps
 * the first and the caller can compare `size` against the rule count.
 */
export function indexPoliciesByRule(
  policies: readonly AssembledPolicy[],
): Map<string, AssembledPolicy> {
  const index = new Map<string, AssembledPolicy>();
  for (const policy of policies) {
    for (const rule of policy.rules) {
      if (!index.has(rule.rule_id)) index.set(rule.rule_id, policy);
    }
  }
  return index;
}

/**
 * Work out, for the rules visible on this page, where each policy starts and
 * whether it is showing whole.
 *
 * Computed over the rows actually rendered. A policy split by a page boundary
 * or by a filter must say so, because a reviewer shown two of three rules with
 * no indication is being shown a fragment presented as the complete passage --
 * which is worse than the fragmentation this exists to fix.
 */
export function policyBands(
  orderedRuleIds: readonly string[],
  index: Map<string, AssembledPolicy>,
): Map<string, PolicyBand> {
  const bands = new Map<string, PolicyBand>();
  if (index.size === 0) return bands;

  // Which rules of each policy this page is showing, in the policy's own order
  // rather than the page's. The policy knows the sequence its rules were stated
  // in; the page may filter or paginate across it, and only the policy's order
  // can say whether what is missing sits before or after what is shown.
  const visiblePositions = new Map<string, number[]>();
  for (const ruleId of orderedRuleIds) {
    const policy = index.get(ruleId);
    if (!policy) continue;
    const position = policy.rules.findIndex((rule) => rule.rule_id === ruleId);
    if (position < 0) continue;
    const positions = visiblePositions.get(policy.key);
    if (positions) positions.push(position);
    else visiblePositions.set(policy.key, [position]);
  }

  const opened = new Set<string>();
  for (const ruleId of orderedRuleIds) {
    const policy = index.get(ruleId);
    if (!policy) continue;
    const positions = visiblePositions.get(policy.key);
    if (!positions || positions.length === 0) continue;

    const isStart = !opened.has(policy.key);
    if (isStart) opened.add(policy.key);

    const lowest = Math.min(...positions);
    const highest = Math.max(...positions);

    bands.set(ruleId, {
      policy,
      isStart,
      inView: positions.length,
      total: policy.rule_count,
      continuesAbove: lowest > 0,
      continuesBelow: highest < policy.rules.length - 1,
    });
  }

  return bands;
}

/**
 * What a policy's mix of routes is called on screen.
 *
 * The backend emits the code and this owns the words, the same split the rest
 * of the app uses. None of these is a grade: a policy whose rules the source
 * states in words is taking the route the source chose for it, and a policy
 * holding both kinds is the ordinary shape of a real document rather than a
 * half-finished version of a better one.
 */
export const POLICY_ROUTE_LABELS: Record<string, string> = {
  deterministic: "Evaluated directly",
  ai_ready: "Decided by reading",
  mixed: "Evaluated directly and by reading",
};

export function policyRouteLabel(route: string | null | undefined): string {
  if (!route) return "Route not recorded";
  return POLICY_ROUTE_LABELS[route] ?? "Route this view does not recognise";
}

/** How many rules a policy states, said plainly. One is the common case and
 *  reads as an ordinary sentence, not as an exception. */
export function policyRuleCountLabel(count: number): string {
  const safe = Math.max(0, count);
  return safe === 1 ? "1 rule" : `${safe} rules`;
}

/** What the header says beneath the passage: how many rules, where they sit,
 *  and how they are routed. */
export function policyHeaderSummary(band: PolicyBand): string {
  const parts = [policyRuleCountLabel(band.total)];
  if (band.inView < band.total) {
    // Never let a fragment pass as the whole passage.
    parts.push(`${band.inView} shown here`);
  }
  if (band.policy.page !== null) parts.push(`page ${band.policy.page}`);
  parts.push(policyRouteLabel(band.policy.route));
  return parts.join(" · ");
}
