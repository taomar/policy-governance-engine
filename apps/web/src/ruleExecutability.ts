import type { CanonicalRule, ConditionNode, ConditionProvenance } from "./api";
import { candidateEditability } from "./candidateEditability";
import { isVacuousCondition } from "./conditionRows";

/**
 * Which decider answers a case put to this rule.
 *
 * A rule stating a comparison is computed by the engine. A rule stating its
 * test in words is read by a judge. Both are decisions; they are reached
 * differently.
 *
 * This lives here, in one function, because the two surfaces that ask the
 * question were already answering it differently: the scenario tester keyed
 * its result rendering off `evaluation_mode` while disabling its controls off
 * `machine_executable`, so a rule whose two fields disagreed was offered a
 * control that led to a refusal. The pane listing a policy's rules asked only
 * `evaluation_mode`, and would therefore have sent a non-executable rule to
 * the engine, which short-circuits before reading the case at all.
 *
 * Both fields are consulted, and the engine is chosen only when both say so.
 * That is not a preference for the judge: it is the only ordering under which
 * a reader is never handed an answer from a decider that never looked at their
 * case. The engine refuses a rule it cannot execute; the judge refuses nothing.
 */
export function engineDecidesRule(
  rule: Pick<CanonicalRule, "evaluation_mode" | "machine_executable">,
): boolean {
  return Boolean(rule.machine_executable) && rule.evaluation_mode === "deterministic";
}

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
  yes: "Deterministic",
  no: "AI Ready",
} as const;

/**
 * Why the deterministic engine cannot decide this rule, in one sentence that
 * does not overclaim.
 *
 * @deprecated Prefer `deterministicReason(provenance)`, which distinguishes the
 * four reasons a tree can be empty. This constant states the
 * `conditions_not_projected` case and is kept only for callers that have no
 * provenance to hand — a hand-authored rule, or a summary over mixed rules.
 */
export const DETERMINISTIC_REASON =
  "No fact model maps this rule's terms onto attributes the deterministic engine can read, so it returns NOT_APPLICABLE before looking at any scenario. That is a configuration gap on our side, not a judgement about the policy.";

/**
 * Why the deterministic engine cannot decide this rule.
 *
 * There is no single answer, and pretending there was one is how the interface
 * came to give a reviewer the wrong instruction. Every non-executable rule used
 * to show the same sentence — "no fact model maps this rule's terms" — which is
 * true for one of four cases and actively misleading for the others:
 *
 * * `conditions_not_representable`: the fact model *did* map every term and the
 *   agent produced grounded, executable logic. We could not compile it. Telling
 *   a reviewer to supply a mapping sends them to edit a configuration that is
 *   already correct and cannot possibly fix it.
 * * `no_scope_derived`: the source states no condition at all. There is nothing
 *   to map, so a missing mapping is not what is holding it back.
 * * `conditions_not_projected`: the original sentence, and still right.
 *
 * The server derives the code, so this only chooses wording — it never decides
 * which case a rule is in.
 */
export function deterministicReason(provenance?: ConditionProvenance | null): string {
  switch (provenance?.code) {
    case "conditions_not_representable":
      return (
        "The trusted configuration is complete for this rule and the extraction produced " +
        "a comparison from it, but this platform's condition format cannot yet express " +
        "that comparison — it compares a fact against a fixed value, and this rule compares " +
        "one fact against a proportion of another. Nothing you can change in the fact model " +
        "will resolve it; it needs an engineering change."
      );
    case "no_scope_derived":
      return (
        "The source states no condition for this rule, so there is nothing to map onto the " +
        "deterministic engine. It may genuinely apply always, or its scope may have been " +
        "missed during extraction — that is a reading of the document, not a configuration gap."
      );
    case "conditions_not_projected":
    default:
      return (
        "No fact model maps this rule's terms onto attributes the deterministic engine can " +
        "read, so it returns NOT_APPLICABLE before looking at any scenario. That is a " +
        "configuration gap on our side, not a judgement about the policy."
      );
  }
}

/**
 * Short label for the same distinction, for places with no room for a sentence.
 *
 * It returns one of exactly two route names. The provenance code changes *why*
 * the deterministic engine does not run a rule, and that belongs in
 * `deterministicReason`; it does not change which route the rule takes. An
 * earlier version returned a third and fourth string here, so the same route
 * arrived on screen under several names and each extra name read as a further
 * diagnosis of the rule.
 */
export function deterministicLabel(
  machineExecutable: boolean,
  _provenance?: ConditionProvenance | null
): string {
  return machineExecutable ? DETERMINISTIC_LABEL.yes : DETERMINISTIC_LABEL.no;
}

/** Short readiness wording, matching the server's `evaluability` values. */
export const READINESS_LABEL: Record<string, string> = {
  decidable: "Decidable",
  discretionary: "Delegated",
  underspecified: "Underspecified",
  not_a_decision: "States meaning only",
  malformed: "Split in the wrong place",
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
 * The one readiness value that is a defect in this app rather than a fact about
 * the document.
 *
 * The other four say how the source states its test - fully, by delegating it,
 * incompletely, or not at all. Each is a property of the document and none is
 * anybody's fault. `malformed` says the app divided the document's sentence in
 * the wrong place, so the rule on screen is not a claim the document makes.
 *
 * It was being shown as a red box holding a two-word label and one sentence,
 * with no statement of what it meant for the reviewer's decision and nothing to
 * do about it. A reviewer read it as a crash. It is not a crash; it is a
 * finding, and a finding that does not say what to do next is only an alarm.
 */
export interface SplitDefectFinding {
  /** What went wrong, in words that name this app as the cause. */
  heading: string;
  /** What it means for everything derived from the split. */
  consequence: string;
  /** Whether the rule should be approved while it reads this way. */
  blocksApproval: boolean;
  /** What the reviewer does about it, given what this record still admits. */
  nextStep: string;
}

/**
 * Derived from the record's own review status, never from the surface drawing
 * it. A candidate can still be re-split; an approved or published rule cannot,
 * and `candidateEditability` already holds the route out of each of those - the
 * same sentences the edit controls give, so a reviewer meets one account of
 * what this record admits rather than two.
 */
export function splitDefectFinding(reviewStatus: string): SplitDefectFinding {
  const editability = candidateEditability(reviewStatus);
  return {
    heading: "This app split the document's sentence in the wrong place.",
    consequence:
      "Everything below is read off that split - who the rule governs, what it looks for, and what it decides. None of it can be relied on here, however sound it reads, and the document is not the reason.",
    blocksApproval: true,
    nextStep: editability.canEdit
      ? "Use Suggest rewrite on this rule to have the sentence read again, then check the result against the source before deciding."
      : (editability.editBlockedReason ??
        "This rule cannot be changed from here, so the split has to be corrected where the record is still open."),
  };
}

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
