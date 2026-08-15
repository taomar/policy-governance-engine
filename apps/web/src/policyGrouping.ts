/**
 * What a passage's route and rule count are called on screen.
 *
 * WHAT THIS USED TO BE
 *
 * This module also arranged the review queue: it indexed the server's assembled
 * policies by rule, worked out which row on a page opened a policy's run, and
 * produced the summary line for a band drawn above that run. All of that existed
 * to annotate a list of rules with the passage they came from.
 *
 * That arrangement was the defect. A passage stating three rules got a header
 * and then three rows, each with its own checkbox, approve, reject and JSON — so
 * the interface said the rules belonged together and then asked for three
 * decisions about them. The queue is now built from `policyCards.ts`, where the
 * card *is* the policy and the rules are drawn inside it, and there is no band,
 * no run, and no continuation to describe. The banding functions went with it
 * rather than being left behind for something to start calling again.
 *
 * WHAT REMAINS, AND WHY IT IS SHARED
 *
 * The words. Route is a property of a rule; a card names the mix its rules take
 * for orientation and names each rule's own route beside that rule. Both labels
 * are read by the card, the detail panel and the published Policies view, so
 * they live in one place — three copies of "Decided by reading" is three chances
 * for one of them to become a complaint.
 *
 * None of these is a grade. A rule the source states in words is taking the
 * route the source chose for it, and a passage holding one of each is the
 * ordinary shape of a real document rather than a half-finished version of a
 * better one.
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
