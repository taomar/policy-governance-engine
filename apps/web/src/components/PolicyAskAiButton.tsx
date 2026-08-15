import { useCallback, useMemo, useState } from "react";
import { Button, Tooltip } from "antd";
import { ThunderboltOutlined } from "@ant-design/icons";
import { type AssembledPolicy } from "../api";
import { askAboutPolicyInLanguage } from "../askInLanguage";
import { AskAiModal, type AskAiModalProps } from "./AskAiModal";

/**
 * "Ask AI" for a whole policy — every rule it was decomposed into, together
 * with the passages they were read from.
 *
 * SIBLING OF EXPLAIN, NOT A REPLACEMENT FOR IT
 *
 * `PolicyExplainButton` answers one fixed question — what does this say, in
 * plain words — in a single click, without the reviewer having to know what to
 * ask. This answers the reviewer's own question. Those are different jobs and
 * the second does not subsume the first: a reviewer scanning a queue wants an
 * explanation without composing a prompt, and a reviewer who has spotted
 * something wants to ask about that thing. They differ in the icon (a bulb
 * explains, a bolt is asked) and in the shape of what comes back, so they do not
 * read as the same button twice.
 *
 * WHAT THE MODEL IS SHOWN, AND WHERE THIS DIVERGES FROM EXPLAIN ON PURPOSE
 *
 * The explainer shows the model this app's extracted record and never the
 * document's verbatim text, because a model shown both silently reconciles them
 * and hides extraction defects — that choice caught this app's own extraction
 * inverting a prohibition. An ask surface cannot inherit it. Its answer contract
 * requires every quoted fact to be copied character-for-character from what the
 * model was given, so a context with no verbatim text yields no quotable facts
 * and collapses the answer to reflection alone; and "does this match the
 * document?" is a question a reviewer is entitled to ask here. So this path
 * shows both halves — and labels which is which inside the context, and asks for
 * a disagreement between them to be reported rather than smoothed over. The
 * label is what preserves the explainer's actual point: the defect stays visible
 * because the model is told the two are separate claims, not one fact stated
 * twice.
 *
 * The grounding may be a prefix of the policy when it holds more rules than one
 * request carries. That is stated in the answer, never assumed away — see the
 * coverage note in `AskAiModal`.
 *
 * PUBLISHED RECORDS
 *
 * `policyVersionId` is how a sealed record asks. Omitted — the review queue —
 * the server reads the draft rows, which is the record that queue is showing.
 * Given, it reads that published version and never falls back to the drafts:
 * the two share their rule ids and can say different things, so an answer about
 * the wrong one would look exactly like an answer about the right one. The
 * reply names which it read and the dialog prints it.
 *
 * Optional rather than required because the published surface is adopting this
 * after the review surface, and a required argument would have made a
 * one-line render into a coordinated change across two owners' files. The
 * published caller passing nothing is the only way this can be got wrong, and
 * `askOnAPublishedRecord.test.tsx` is what stops it.
 */
export function PolicyAskAiButton({
  policy,
  policySetKey,
  policyVersionId,
}: {
  policy: AssembledPolicy;
  policySetKey: string;
  policyVersionId?: string;
}) {
  const [open, setOpen] = useState(false);

  /** The rules to ground on, by their own ids, in document order — the order
   *  the card shows them in, so a coverage statement naming "the first N" names
   *  a prefix the reader can actually point at. */
  const ruleIds = useMemo(() => policy.rules.map((rule) => rule.rule_id), [policy.rules]);

  const ask = useCallback<AskAiModalProps["ask"]>(
    ({ question, history, answerLanguage }) =>
      askAboutPolicyInLanguage({
        question,
        policySetId: policySetKey,
        history,
        focusRuleIds: ruleIds,
        policyVersionId,
        answerLanguage,
      }),
    [policySetKey, ruleIds, policyVersionId],
  );

  return (
    <>
      <Tooltip title="Ask your own question about this whole policy. Quoted text comes back in the document's own words.">
        <Button
          size="small"
          icon={<ThunderboltOutlined />}
          onClick={() => setOpen(true)}
          data-testid="policy-ask-ai"
          disabled={ruleIds.length === 0}
        >
          Ask AI
        </Button>
      </Tooltip>
      {open && (
        <AskAiModal
          scope="policy"
          // The policy's own heading, verbatim. Its generated topic label is
          // this app's writing and is deliberately not used here: the heading of
          // a dialog about the document should be the document's words.
          subjectLabel={policy.heading}
          wider={policy.passage_count > 1}
          ask={ask}
          onClose={() => setOpen(false)}
        />
      )}
    </>
  );
}
