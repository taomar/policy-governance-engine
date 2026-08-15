import { useCallback } from "react";
import { type CandidateRule } from "../api";
import { askAboutRuleInLanguage } from "../askInLanguage";
import { AskAiModal, type AskAiModalProps } from "./AskAiModal";

/**
 * Focused "Ask AI about this rule" — pins the exact candidate rule's content
 * (plus any sibling rules sharing its variation group) as priority context, so
 * a reviewer/manager can ask "does this conflict with X?" or "explain this in
 * plain English" without leaving the review queue. Distinct from the global Ask
 * AI drawer, which is unscoped.
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
 * The props are unchanged from when this file held the whole dialog, so the
 * review queue that mounts it needed no edit.
 */
export function AskAboutRuleModal({ candidate, onClose }: { candidate: CandidateRule; onClose: () => void }) {
  const ask = useCallback<AskAiModalProps["ask"]>(
    ({ question, history, answerLanguage }) =>
      askAboutRuleInLanguage({
        question,
        policySetId: candidate.policy_set_id,
        history,
        focusCandidateRuleId: candidate.id,
        answerLanguage,
      }),
    [candidate.policy_set_id, candidate.id],
  );

  return (
    <AskAiModal
      scope="rule"
      subjectLabel={candidate.rule.rule_id}
      wider={Boolean(candidate.rule.group_label)}
      ask={ask}
      onClose={onClose}
    />
  );
}
