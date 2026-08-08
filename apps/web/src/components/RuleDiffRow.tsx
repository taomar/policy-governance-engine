import { Button, Tag, Tooltip } from "antd";
import { CrownOutlined, DownOutlined, ExclamationCircleOutlined, ToolOutlined, UpOutlined } from "@ant-design/icons";
import type { CanonicalRule } from "../api";
import { ambiguityMeta, hasAmbiguityFlag, ruleConditionLine } from "../ruleDisplay";
import { ruleTypeLabel } from "../ruleTypes";
import { colorForCategory } from "../policyCategories";
import { PolicyEffectBadge } from "./PolicyEffectBadge";

interface RuleDiffRowProps {
  rule: CanonicalRule;
  /** Which side of the diff this rule appeared on — drives the leading +/− tag. */
  diffKind: "added" | "removed";
  expanded: boolean;
  onToggleExpand: () => void;
}

/**
 * Compact, information-dense summary row for one rule inside the Compare
 * view's "Added Rules" / "Removed Rules" sections. Mirrors PolicyRow's/
 * CandidateRow's proven layout so the app reads consistently, but scoped to
 * just a bare CanonicalRule + a diff-side tag (no candidate status, bulk
 * select, or cluster banding — those don't apply to a version diff).
 *
 * Exists so a version comparison with hundreds of added/removed rules (a
 * real possibility once a large candidate batch — e.g. hr-guide-policy's
 * 340+ pending rules — gets published as a new version) doesn't mount a full
 * RuleCard (and its per-instance evidence-resolution + Notes fetch) for
 * every row up front. The full RuleCard is only mounted when a row expands.
 */
export function RuleDiffRow({ rule, diffKind, expanded, onToggleExpand }: RuleDiffRowProps) {
  const line = ruleConditionLine(rule);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      onToggleExpand();
    }
  };

  return (
    <div
      role="button"
      tabIndex={0}
      aria-pressed={expanded}
      className={`policy-row candidate-row${expanded ? " policy-row-selected" : ""}`}
      onClick={onToggleExpand}
      onKeyDown={handleKeyDown}
    >
      <Tag color={diffKind === "added" ? "green" : "red"} style={{ marginInlineEnd: 0 }}>
        {diffKind === "added" ? "+" : "\u2212"}
      </Tag>
      <div className="policy-row-main">
        <div className="policy-row-line1">
          <span className="policy-row-title">{rule.title}</span>
          <span className="policy-row-flags">
            {rule.is_explicit_override && (
              <Tooltip title="Explicit override — outranks otherwise-applicable rules">
                <CrownOutlined className="policy-row-flag policy-row-flag-override" />
              </Tooltip>
            )}
            {hasAmbiguityFlag(rule.ambiguity_status) && (
              <Tooltip title={`Ambiguity: ${ambiguityMeta(rule.ambiguity_status).label}`}>
                <ExclamationCircleOutlined
                  className={`policy-row-flag policy-row-flag-ambiguity--${ambiguityMeta(rule.ambiguity_status).color}`}
                />
              </Tooltip>
            )}
            {!rule.machine_executable && (
              <Tooltip title="Manual rule — not machine-executable">
                <ToolOutlined className="policy-row-flag" />
              </Tooltip>
            )}
          </span>
          <PolicyEffectBadge effect={rule.effect} size="small" />
        </div>
        {!expanded && (
          <>
            <div className="policy-row-line2" title={line.text}>
              {line.text}
            </div>
            <div className="policy-row-line3">
              <span>{ruleTypeLabel(rule.rule_type)}</span>
              <span className="policy-row-dot">·</span>
              <span className="policy-row-mono">{rule.rule_id}</span>
              <span className="policy-row-dot">·</span>
              <span>rev {rule.rule_revision}</span>
              {rule.category && (
                <Tag bordered={false} color={colorForCategory(rule.category)} className="policy-row-category-tag">
                  {rule.category}
                </Tag>
              )}
            </div>
          </>
        )}
      </div>
      <Tooltip title={expanded ? "Collapse" : "Expand for full detail"}>
        <Button
          size="small"
          type="text"
          icon={expanded ? <UpOutlined /> : <DownOutlined />}
          onClick={(e) => {
            e.stopPropagation();
            onToggleExpand();
          }}
        />
      </Tooltip>
    </div>
  );
}
