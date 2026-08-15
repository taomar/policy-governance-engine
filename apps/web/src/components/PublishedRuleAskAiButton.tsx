import { useState } from "react";
import { Button, Tooltip } from "antd";
import { ThunderboltOutlined } from "@ant-design/icons";
import { AskAboutRuleModal } from "./AskAboutRuleModal";

/**
 * "Ask AI" for one rule of a published version.
 *
 * WHY A PUBLISHED RECORD NEEDS THIS AT ALL
 *
 * A reader of a sealed rule has the reviewer's questions and fewer of the
 * reviewer's remedies: they cannot change what they are reading, so
 * understanding it is the whole of what they can do. Leaving the ask on the
 * review surface alone made the question answerable exactly where it was least
 * needed.
 *
 * THE CONTRACT, AND WHY IT IS THE RECORD RATHER THAN A FLAG
 *
 * It takes the rule and where the rule is published, and nothing about who is
 * looking or what they are allowed to do. There is no `canReview`, no
 * `readOnly`, no handler whose presence decides anything: asking a question is
 * not a decision on a record, so no editability answer changes what this draws.
 * The same component would serve a draft — it is not used for one only because
 * the review queue already mounts the dialog directly, and a second button onto
 * the same dialog would be a second way to do one thing.
 *
 * `policyVersionId` is required, not optional. A published rule id without its
 * version does not identify a record: the draft row that produced it carries
 * the same id, may since have been revised, and would be what the server read.
 * Making the version part of the identity is what stops a sealed record being
 * explained by a draft.
 */
export function PublishedRuleAskAiButton({
  rule,
  policySetKey,
  policyVersionId,
}: {
  /** The published rule, by the identity a sealed record has. */
  rule: { rule_id: string; group_label?: string };
  policySetKey: string;
  policyVersionId: string;
}) {
  const [open, setOpen] = useState(false);

  return (
    <>
      <Tooltip title="Ask your own question about this published rule. Quoted text comes back in the document's own words.">
        <Button
          size="small"
          icon={<ThunderboltOutlined />}
          onClick={() => setOpen(true)}
          data-testid="published-rule-ask-ai"
        >
          Ask AI
        </Button>
      </Tooltip>
      {open && (
        <AskAboutRuleModal
          rule={rule}
          policySetKey={policySetKey}
          policyVersionId={policyVersionId}
          onClose={() => setOpen(false)}
        />
      )}
    </>
  );
}
