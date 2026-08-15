import { useCallback } from "react";
import { type CandidateRule } from "../api";
import { askAboutRuleInLanguage } from "../askInLanguage";
import { AskAiModal, type AskAiModalProps } from "./AskAiModal";

/**
 * Focused "Ask AI about this rule" — pins the exact rule's content as priority
 * context, so a reviewer/manager can ask "does this conflict with X?" or
 * "explain this in plain English" without leaving the record. Distinct from the
 * global Ask AI drawer, which is unscoped.
 *
 * WHY THIS IS NOW A DOZEN LINES
 *
 * The dialog itself moved to `AskAiModal`, which serves this and the
 * policy-wide ask. What was left here is the only thing that was ever about a
 * rule: which record to ground on and what to put in the heading. Sharing it is
 * not tidiness — the rule that quoted source text is never translated has to
 * hold on both surfaces, and it holds by there being one surface. Two copies of
 * that render tree would be two places to forget it, and the second would be
 * forgotten the first time someone changed only the one they were looking at.
 *
 * TWO KINDS OF RECORD, ONE DIALOG
 *
 * A rule is either a draft row under review or a rule of a published version.
 * Those are two records, not two views of one: they share a `rule_id`, they can
 * say different things, and the draft is where a revision is being written
 * while the published rule is what the version promised. So the target is a
 * union rather than an optional field — a caller supplies one identity or the
 * other and cannot supply half of either, and there is no shape of props that
 * means "a published rule" while quietly resolving to a draft.
 *
 * The draft arm's props are unchanged from when this file held the whole
 * dialog, so the review queue that mounts it needed no edit.
 */
export type AskAboutRuleTarget =
  | {
      /** The draft row under review. Grounds on that row, by its own id. */
      candidate: CandidateRule;
      rule?: never;
      policySetKey?: never;
      policyVersionId?: never;
    }
  | {
      candidate?: never;
      /** A rule of a published version, by its own id — the identity a sealed
       *  record actually has. There is no draft row behind it to point at, and
       *  synthesising one would ask about a record no table holds. */
      rule: { rule_id: string; group_label?: string };
      /** The policy set's key, not its uuid: this is what the server resolves. */
      policySetKey: string;
      /** Which published version states this rule. Required on this arm — a
       *  published rule id without its version does not say which record is on
       *  screen, and the server would read the draft instead. */
      policyVersionId: string;
    };

export function AskAboutRuleModal(props: AskAboutRuleTarget & { onClose: () => void }) {
  const { candidate, rule, policySetKey, policyVersionId, onClose } = props;

  // One identity, read once, so the two arms differ in what they supply and not
  // in what happens after.
  const ruleId = candidate ? candidate.rule.rule_id : rule.rule_id;
  const groupLabel = candidate ? candidate.rule.group_label : rule.group_label;

  const ask = useCallback<AskAiModalProps["ask"]>(
    ({ question, history, answerLanguage }) =>
      askAboutRuleInLanguage({
        question,
        // The published arm grounds through the same rule-ids path the policy
        // ask uses, with one id: a published version holds no candidate row to
        // pin, and its records are read from the version itself. The reply
        // carries a coverage report for that one rule, which is what makes
        // "this rule could not be read" a sentence rather than a silence.
        policySetId: candidate ? candidate.policy_set_id : policySetKey,
        history,
        focusCandidateRuleId: candidate?.id,
        focusRuleIds: candidate ? undefined : [ruleId],
        policyVersionId,
        answerLanguage,
      }),
    [candidate, policySetKey, policyVersionId, ruleId],
  );

  return (
    <AskAiModal
      scope="rule"
      subjectLabel={ruleId}
      wider={Boolean(groupLabel)}
      ask={ask}
      onClose={onClose}
    />
  );
}
