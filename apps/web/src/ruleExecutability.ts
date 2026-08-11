import type { ConditionNode } from "./api";
import { isVacuousCondition } from "./conditionRows";

/**
 * Whether the deterministic evaluator can decide a rule, derived from its
 * condition.
 *
 * `machine_executable` is the flag `evaluator/engine.py` checks *before* scope,
 * condition or exceptions: a false one short-circuits to NOT_APPLICABLE with
 * reason `rule_not_machine_executable`. So it has to agree with the condition,
 * and both the draft form and the edit modal were setting it independently of
 * one:
 *
 * * The draft form never set it at all. With no condition entered, the server
 *   default (`True`) was paired with an empty conjunction — a rule claiming to
 *   be executable with nothing to evaluate. With a condition entered *and* an
 *   AI-generated rule present, the AI rule's `false` was spread over the top,
 *   so a hand-built condition arrived at the evaluator already switched off.
 * * The edit modal spread the whole existing rule, so adding a condition to
 *   any of the 45 extracted rules left `machine_executable` false. The reviewer
 *   built the logic, saved successfully, and it never ran.
 *
 * Deriving it removes the disagreement by construction. A rule is executable
 * exactly when it carries a condition the engine can test, which is the same
 * question `isVacuousCondition` already answers for the UI.
 *
 * This does not weaken the extraction-time guarantee. `formulation_mapping`
 * still refuses to invent a condition it cannot ground in the source, so an
 * extracted rule with no projectable logic still arrives vacuous and therefore
 * still reports false. What changes is that a *human* who supplies the missing
 * logic now gets a rule that actually evaluates.
 */
export function machineExecutableFor(condition: ConditionNode | undefined | null): boolean {
  return !isVacuousCondition(condition);
}

/**
 * How to describe a rule's executability to a user. One definition, used by
 * every tab.
 *
 * Ten tabs each invented their own wording for the same boolean, and every one
 * of them said something stronger than the flag supports: "Documentation
 * only", "documented prose", "Manual", "Manual-only package", "Not testable
 * yet". A reader of any of those concludes the extraction produced something
 * unusable. What the flag actually reports is that *our Python FEEL evaluator*
 * cannot decide the rule, which is true of nearly every extracted rule because
 * no fact model has been configured — and says nothing about whether the
 * policy is clear, complete, or evaluable by the LLM that actually runs it.
 *
 * `decision_readiness` answers that second question, so where it is available
 * the two are shown together rather than one standing in for the other.
 */
export const DETERMINISTIC_LABEL = {
  yes: "Deterministic engine ready",
  no: "Needs a fact mapping",
} as const;

/**
 * Why the deterministic engine cannot decide this rule, in one sentence that
 * does not overclaim.
 *
 * Deliberately mentions the fact model rather than the rule: the missing piece
 * is a mapping from the document's wording onto a customer's schema, and that
 * is work nobody has done yet rather than a defect in the extraction.
 */
export const DETERMINISTIC_REASON =
  "No fact model maps this rule's terms onto attributes the deterministic engine can read, so it returns NOT_APPLICABLE before looking at any scenario. That is a configuration gap on our side, not a judgement about the policy.";

/** Short readiness wording, matching the server's `evaluability` values. */
export const READINESS_LABEL: Record<string, string> = {
  decidable: "Decidable",
  discretionary: "Delegated",
  underspecified: "Underspecified",
  not_a_decision: "States meaning only",
  malformed: "Decomposition damaged",
};

export const READINESS_COLOR: Record<string, string> = {
  decidable: "green",
  discretionary: "blue",
  underspecified: "orange",
  not_a_decision: "default",
  malformed: "red",
};

/**
 * Fallback explanation per readiness value, used when the server did not send
 * a per-rule reason (hand-authored rules carry no canonical decomposition).
 */
export const READINESS_REASON: Record<string, string> = {
  decidable: "The source states a test and its terms, so an evaluator has everything the document offers.",
  discretionary:
    "The source states no test because it delegated the decision. A delegated decision is still a decision.",
  underspecified:
    "The source names a subject and a verb and nothing else. The gap belongs to the document, not the extraction.",
  not_a_decision: "A definition or classification. It grants and refuses nothing.",
  malformed: "The sentence was mis-split, so claims derived from it cannot be trusted.",
};

/**
 * The condition to save, given what the row editor could represent.
 *
 * `rowsFromCondition === null` means the stored condition is richer than the
 * row editor can show — OR/NOT/nesting — and the modal has switched to raw
 * JSON. In that case an empty row list means "the editor was never usable
 * here", so the original must be kept; overwriting it would silently flatten a
 * reviewer's nested logic into nothing.
 *
 * When the editor *could* represent it, an empty row list means the reviewer
 * deleted the rows on purpose. Falling back to the original there is what made
 * clearing a condition impossible: the rows disappeared from the form, the save
 * succeeded, and the old condition came straight back with no error to explain
 * it.
 */
export function conditionToSave(
  rows: { fact: string }[],
  rowsFromCondition: unknown[] | null,
  original: ConditionNode,
  build: (rows: never) => ConditionNode
): ConditionNode {
  const filled = rows.filter((r) => r.fact.trim() !== "");
  if (filled.length > 0) return build(filled as never);
  // No usable rows. Honour the clear only when the editor was representing the
  // condition in the first place.
  if (rowsFromCondition === null) return original;
  return { type: "all", all: [] };
}
