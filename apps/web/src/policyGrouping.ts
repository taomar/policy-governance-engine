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
 * they live in one place — three copies of a route name is three chances for one
 * of them to drift into a complaint.
 *
 * There are two routes and each has exactly one name. A rule whose test the
 * source states as a comparison is Deterministic: the engine computes it. A rule
 * whose test the source states in words is AI Ready: a judge reads the rule
 * against the case and returns a verdict with its confidence. Earlier releases
 * called the second one three different things at once, which is how a route
 * starts reading as a diagnosis.
 *
 * None of these is a grade. A rule the source states in words is taking the
 * route the source chose for it, and a passage holding one of each is the
 * ordinary shape of a real document rather than a half-finished version of a
 * better one.
 */

export const POLICY_ROUTE_LABELS: Record<string, string> = {
  deterministic: "Deterministic",
  ai_ready: "AI Ready",
  mixed: "Deterministic and AI Ready",
};

export function policyRouteLabel(route: string | null | undefined): string {
  if (!route) return "Route not recorded";
  return POLICY_ROUTE_LABELS[route] ?? "Route this view does not recognise";
}

/** How many rules a policy states, said plainly. One is the common case and
 *  reads as an ordinary sentence, not as an exception.
 *
 *  `shown` is what the reader can see; `stated` is what the policy holds. They
 *  differ whenever a filter admits only some of a policy's rules — a policy of
 *  twenty rules with three already decided shows seventeen. Labelling that card
 *  "20 rules" over seventeen rule blocks makes the reader reconcile two numbers
 *  that never appear beside each other, and the Logic tab made it worse by
 *  comparing seventeen rows under a head that said twenty.
 *
 *  So the label names both: the number on the card first, because that is what
 *  the reader is counting, and the number the policy states second, because a
 *  fragment presented as a whole policy is the defect this grouping exists to
 *  prevent. The sentence naming what is missing stays where it is; this makes
 *  the head agree with it instead of contradicting it.
 */
export function policyRuleCountLabel(shown: number, stated?: number): string {
  const safe = Math.max(0, shown);
  // A `stated` below `shown` would be an inconsistency upstream, and reading
  // "17 of 3 rules" would tell the reader nothing they could act on. Take the
  // larger, so the label degrades to the plain form rather than to nonsense.
  const whole = stated === undefined ? safe : Math.max(safe, Math.max(0, stated));
  if (whole !== safe) return `${safe} of ${whole} rules`;
  return safe === 1 ? "1 rule" : `${safe} rules`;
}
