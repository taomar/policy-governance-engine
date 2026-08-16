/**
 * One reading of a case at the policy level, assembled from the per-rule answers
 * without totalling them.
 *
 * WHY THIS IS NOT AGGREGATION
 *
 * A reviewer put one case to a policy and wants one answer they can act on,
 * naming the rule or rules it rests on — not a table of independent verdicts
 * they must reduce themselves. This assembles that answer, and it is careful
 * about the line it must not cross. It never invents a policy-level ruling: it
 * re-presents the verdicts the per-rule deciders already produced, in their own
 * words, and leads with the ones that settle the case. It never combines a
 * computed verdict and a judged one into a single yes/no, because those two
 * answer different questions and are not points on one scale. And when the rules
 * that settle the case do not all point the same way, it says so plainly rather
 * than picking a winner or averaging them — the divergence is the answer.
 *
 * So this is a finding aid over answers that already exist, the same way a rule
 * name is a finding aid over a rule. Citing what the rules said is not summing
 * what they said.
 */
import type { CaseAnswer } from "./policyTesting";

/**
 * Where a whole policy's answers leave the case. Four, kept apart for the same
 * reason the per-rule states are: a case some rule decides, a case rules bear on
 * but none decides, a case no rule bears on, and a case whose requests did not
 * complete are four different situations, and a reviewer shown one dressed as
 * another is misled about what the policy said.
 */
export type PolicyCaseState =
  | "settled"
  | "bears_unsettled"
  | "no_rule_bears"
  | "unresolved";

export interface PolicyCaseReading {
  state: PolicyCaseState;
  /**
   * The rules the answer rests on, in the order they were asked. Populated in
   * `settled`; these are what the reading leads with and names.
   */
  settling: CaseAnswer[];
  /** Rules that bear on the case but do not settle it. */
  unsettled: CaseAnswer[];
  /** Rules that do not bear on the case. */
  standsAside: CaseAnswer[];
  /** Rules whose request did not complete, or that could not be computed. */
  unresolved: CaseAnswer[];
  /**
   * The settling rules do not all point the same way — at least one is a breach
   * and at least one is not. Reported, never resolved: a reader is told the rules
   * diverge and shown each, rather than handed one answer that hid the other.
   */
  divergent: boolean;
  /**
   * How many rules were consulted in all. Stated so a reading that leads with a
   * few rules can never leave a reviewer believing only those few were read —
   * every consulted rule stays reachable beneath the answer.
   */
  rulesRead: number;
}

/**
 * Read the policy-level answer from the per-rule answers.
 *
 * The precedence is the order a reviewer needs: an answer if the case is settled;
 * otherwise the rules that bear but leave it open; otherwise an honest "the
 * requests did not complete" when some did not, in preference to claiming no rule
 * bears while some never answered; and only when every rule answered and all
 * stood aside, "no rule bears".
 */
export function readPolicyCase(answers: readonly CaseAnswer[]): PolicyCaseReading {
  const settling = answers.filter((a) => a.settlement === "settles");
  const unsettled = answers.filter((a) => a.settlement === "unsettled");
  const standsAside = answers.filter((a) => a.settlement === "stands_aside");
  const unresolved = answers.filter(
    (a) => a.settlement === "uncomputable" || a.settlement === "unanswered",
  );

  let state: PolicyCaseState;
  if (settling.length > 0) state = "settled";
  else if (unsettled.length > 0) state = "bears_unsettled";
  else if (unresolved.length > 0) state = "unresolved";
  else state = "no_rule_bears";

  // Divergence is only meaningful among the rules that settle the case: a breach
  // beside a rule met or applied is the split that must not be hidden. Computed
  // from each answer's own settled outcome, not from the words shown.
  const divergent = settling.some((a) => a.adverse) && settling.some((a) => !a.adverse);

  return {
    state,
    settling: [...settling],
    unsettled: [...unsettled],
    standsAside: [...standsAside],
    unresolved: [...unresolved],
    divergent,
    rulesRead: answers.length,
  };
}
