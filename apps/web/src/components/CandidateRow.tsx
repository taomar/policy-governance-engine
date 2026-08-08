import { Button, Checkbox, Space, Tag, Tooltip } from "antd";
import {
  CheckOutlined,
  CloseOutlined,
  CrownOutlined,
  DownOutlined,
  ExclamationCircleOutlined,
  ToolOutlined,
  UpOutlined,
} from "@ant-design/icons";
import type { CandidateRule } from "../api";
import { ambiguityMeta, hasAmbiguityFlag, ruleConditionLine } from "../ruleDisplay";
import { ruleTypeLabel } from "../ruleTypes";
import { colorForCategory } from "../policyCategories";
import { PolicyEffectBadge } from "./PolicyEffectBadge";

interface CandidateRowProps {
  candidate: CandidateRule;
  expanded: boolean;
  selected: boolean;
  /** Whether this candidate is in a reviewable state (shows the checkbox + quick actions). */
  selectable: boolean;
  findingsCount: number;
  statusColor: string;
  statusLabel: string;
  onToggleExpand: () => void;
  onToggleSelect: () => void;
  onApprove?: () => void;
  onReject?: () => void;
}

/**
 * Compact, information-dense summary row for one candidate rule in the
 * Review queue — the collapsed "master" view. Mirrors PolicyRow's proven
 * layout/CSS (title + condition-to-effect line + metadata caption) so the
 * whole app reads consistently, with review-specific additions: a bulk-select
 * checkbox, status tag, quality-findings badge, and quick approve/reject
 * buttons that don't require expanding the row.
 *
 * When expanded, this collapses to a minimal identity strip (title + status +
 * collapse toggle) since the full RuleCard rendered underneath already shows
 * title/badges/detail — avoids showing the same metadata twice at once.
 */
export function CandidateRow({
  candidate,
  expanded,
  selected,
  selectable,
  findingsCount,
  statusColor,
  statusLabel,
  onToggleExpand,
  onToggleSelect,
  onApprove,
  onReject,
}: CandidateRowProps) {
  const rule = candidate.rule;
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
      {selectable && (
        <Checkbox
          checked={selected}
          onChange={onToggleSelect}
          onClick={(e) => e.stopPropagation()}
          title="Select for bulk review"
        />
      )}
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
          <Tag color={statusColor} className="candidate-row-status-tag">
            {statusLabel}
          </Tag>
          {findingsCount > 0 && (
            <Tooltip title={`${findingsCount} quality finding(s) from the last AI readiness check`}>
              <Tag color="volcano" icon={<ExclamationCircleOutlined />}>
                {findingsCount}
              </Tag>
            </Tooltip>
          )}
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
      <Space size={4} className="candidate-row-actions" onClick={(e) => e.stopPropagation()}>
        {!expanded && onApprove && onReject && (
          <>
            <Tooltip title="Quick approve">
              <Button size="small" type="text" icon={<CheckOutlined style={{ color: "#16a34a" }} />} onClick={onApprove} />
            </Tooltip>
            <Tooltip title="Quick reject">
              <Button size="small" type="text" icon={<CloseOutlined style={{ color: "#dc2626" }} />} onClick={onReject} />
            </Tooltip>
          </>
        )}
        <Tooltip title={expanded ? "Collapse" : "Expand for full detail"}>
          <Button size="small" type="text" icon={expanded ? <UpOutlined /> : <DownOutlined />} onClick={onToggleExpand} />
        </Tooltip>
      </Space>
    </div>
  );
}
