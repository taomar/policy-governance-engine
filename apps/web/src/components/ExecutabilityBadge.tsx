import { Space, Tag, Tooltip } from "antd";
import { ToolOutlined } from "@ant-design/icons";
import type { CanonicalRule } from "../api";
import {
  READINESS_COLOR,
  READINESS_LABEL,
  READINESS_REASON,
  deterministicLabel,
  deterministicReason,
} from "../ruleExecutability";

/**
 * How a rule's executability is shown, everywhere.
 *
 * Ten tabs each rendered their own ternary over `machine_executable`, and each
 * one invented wording that said more than the flag supports: "Documentation
 * only", "documented prose", "Manual", "Manual-only package", "Not testable
 * yet", "Documentation-only rule". A reader of any of them concludes the
 * extraction produced something unusable.
 *
 * The flag reports one narrow fact: our deterministic FEEL evaluator cannot
 * decide this rule, because no fact model maps the document's wording onto
 * attributes it can read. It is false for nearly every extracted rule, and it
 * says nothing about whether the policy is clear, complete, or evaluable by
 * the LLM that actually runs it — which is what `decision_readiness` answers.
 *
 * Rendering both from one component is what stops the two answers drifting
 * apart again. Ten copies of a ternary is ten places for the next correction
 * to be applied nine times.
 */
export function ExecutabilityBadge({
  rule,
  showReadiness = true,
  size = "default",
}: {
  rule: Pick<CanonicalRule, "machine_executable" | "decision_readiness" | "condition_provenance">;
  /** Hide the readiness half where space is tight, e.g. a dense table row. */
  showReadiness?: boolean;
  size?: "default" | "small";
}) {
  const readiness = rule.decision_readiness;
  const evaluability = readiness?.evaluability;
  const provenance = rule.condition_provenance;
  const className = size === "small" ? "executability-badge is-small" : "executability-badge";

  return (
    <Space size={4} wrap className={className}>
      <Tooltip title={rule.machine_executable ? undefined : deterministicReason(provenance)}>
        <Tag bordered={false} color={rule.machine_executable ? "green" : "default"}>
          {deterministicLabel(rule.machine_executable, provenance)}
        </Tag>
      </Tooltip>
      {showReadiness && evaluability && (
        <Tooltip title={readiness?.reason || READINESS_REASON[evaluability]}>
          <Tag bordered={false} color={READINESS_COLOR[evaluability] ?? "default"}>
            {READINESS_LABEL[evaluability] ?? evaluability}
          </Tag>
        </Tooltip>
      )}
    </Space>
  );
}

/**
 * The dense-row variant: one icon, for tables where a tag pair will not fit.
 *
 * `CandidateRow`, `PolicyRow` and `RuleDiffRow` each carried a byte-identical
 * copy of this block, tooltip included ("Manual rule - not machine-executable").
 * Three copies of one sentence is three places for a correction to be applied
 * twice, which is how the wording drifted from the flag's actual meaning in the
 * first place.
 */
export function ExecutabilityFlag({
  rule,
}: {
  rule: Pick<CanonicalRule, "machine_executable" | "decision_readiness" | "condition_provenance">;
}) {
  if (rule.machine_executable) return null;
  const evaluability = rule.decision_readiness?.evaluability;
  const readable = evaluability ? (READINESS_LABEL[evaluability] ?? evaluability) : null;
  const label = deterministicLabel(false, rule.condition_provenance);
  const reason = deterministicReason(rule.condition_provenance);
  return (
    <Tooltip
      title={
        readable
          ? `${label}. ${reason} Readiness for LLM evaluation: ${readable}.`
          : `${label}. ${reason}`
      }
    >
      <ToolOutlined className="policy-row-flag" />
    </Tooltip>
  );
}