import { Button, Checkbox, Space, Tag, Tooltip } from "antd";
import {
  CheckOutlined,
  CloseOutlined,
  ClusterOutlined,
  CrownOutlined,
  ExclamationCircleOutlined,
  ReadOutlined,
  RightOutlined,
} from "@ant-design/icons";
import type { CandidateRule } from "../api";
import {
  clusterLabel,
  hexToRgba,
  ruleDecisionSummary,
  type RuleVariationGroup,
} from "../ruleDisplay";
import type { BandGeometry } from "../bandGeometry";
import { ruleTypeLabel } from "../ruleTypes";
import { DOCUMENT_GUIDANCE_TAG } from "../ruleTags";
import { colorForCategory } from "../policyCategories";
import { PolicyEffectBadge } from "./PolicyEffectBadge";
import { DELTA_META } from "./ReviewFilterBar";

interface CandidateRowProps {
  candidate: CandidateRule;
  expanded: boolean;
  selected: boolean;
  /** Whether this candidate is in a reviewable state (shows the checkbox + quick actions). */
  selectable: boolean;
  findingsCount: number;
  statusColor: string;
  statusLabel: string;
  /** Variation family this candidate belongs to, or undefined when it stands
   * alone. Same clustering criterion as the Policies view, so a rule that reads
   * as part of a family after publication also reads that way while pending. */
  cluster?: RuleVariationGroup;
  /** Accent color for the family band, keyed by cluster identity. */
  clusterColor?: string;
  band?: BandGeometry;
  /** Select every open sibling in this rule's family for bulk review. Absent
   *  when the row isn't selectable, so the chip stays purely informational. */
  onSelectFamily?: () => void;
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
 * `expanded` means "currently shown in the detail pane". The summary stays
 * complete so selecting a row never makes its list entry less useful.
 */
export function CandidateRow({
  candidate,
  expanded,
  selected,
  selectable,
  findingsCount,
  statusColor,
  statusLabel,
  cluster,
  clusterColor,
  band,
  onSelectFamily,
  onToggleExpand,
  onToggleSelect,
  onApprove,
  onReject,
}: CandidateRowProps) {
  const rule = candidate.rule;
  const decision = ruleDecisionSummary(rule);
  const isBandStart = band?.isStart ?? true;
  const isBandEnd = band?.isEnd ?? true;

  // Same custom properties PolicyRow sets, so the family spine, node, resting
  // wash and hover tint all read identically in the queue and after publication.
  const rowStyle: React.CSSProperties = {};
  if (clusterColor) {
    const vars = rowStyle as Record<string, string>;
    vars["--cluster-accent"] = clusterColor;
    vars["--cluster-tint"] = hexToRgba(clusterColor, 0.1);
    vars["--cluster-wash"] = hexToRgba(clusterColor, 0.055);
  }

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
      className={`policy-row candidate-row${expanded ? " candidate-row--expanded policy-row-selected" : ""}${
        cluster ? " policy-row--family" : ""
      }${cluster && isBandStart ? " policy-row--family-start" : ""}${
        cluster && isBandEnd ? " policy-row--family-end" : ""
      }`}
      style={clusterColor ? rowStyle : undefined}
      onClick={onToggleExpand}
      onKeyDown={handleKeyDown}
    >
      {cluster && (
        <>
          <span
            className={`policy-row-band${isBandStart ? " policy-row-band--start" : ""}${
              isBandEnd ? " policy-row-band--end" : ""
            }${band?.continuesAbove ? " policy-row-band--continues-up" : ""}${
              band?.continuesBelow ? " policy-row-band--continues-down" : ""
            }`}
            aria-hidden="true"
          />
          <span className="policy-row-band-node" aria-hidden="true" />
        </>
      )}
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
          </span>
          <span className="policy-row-statuses">
            <PolicyEffectBadge effect={rule.effect} size="small" />
            <Tag color={statusColor} className="candidate-row-status-tag">
              {statusLabel}
            </Tag>
            {candidate.delta_status && candidate.delta_status !== "baseline" && (
              <Tooltip
                title={
                  candidate.delta_status === "unchanged" && candidate.reworded
                    ? "Identical in meaning to the previous extraction, but the wording was regenerated. Nothing to review."
                    : DELTA_META[candidate.delta_status]?.help
                }
              >
                <Tag
                  color={DELTA_META[candidate.delta_status]?.color}
                  className="candidate-row-delta-tag"
                >
                  {DELTA_META[candidate.delta_status]?.label}
                  {candidate.delta_status === "unchanged" && candidate.reworded ? " · reworded" : ""}
                </Tag>
              </Tooltip>
            )}
            {findingsCount > 0 && (
              <Tooltip title={`${findingsCount} quality finding(s) from the last AI readiness check`}>
                <Tag color="volcano" icon={<ExclamationCircleOutlined />}>
                  {findingsCount}
                </Tag>
              </Tooltip>
            )}
          </span>
        </div>
        <div className="policy-decision-line" title={decision.text}>
          <span className="policy-decision-key">When</span>
          <span
            className={
              decision.conditionIsStatedOnly
                ? "policy-decision-value is-stated-only"
                : "policy-decision-value"
            }
            title={
              decision.conditionIsStatedOnly
                ? "Stated by the source. No fact model compiles it yet, so the deterministic engine does not test it."
                : undefined
            }
          >
            {decision.condition}
          </span>
          <span className="policy-decision-arrow">→</span>
          <span className="policy-decision-key">Then</span>
          <span className="policy-decision-result">{decision.action}</span>
        </div>
        <div className="policy-row-line3">
              {cluster && (
                <Tooltip
                  title={
                    <>
                      <div className="policy-row-cluster-tip-title">{clusterLabel(cluster)}</div>
                      <div className="policy-row-cluster-tip-sub">
                        {cluster.kind === "group"
                          ? "Grouped by the curated variation group on each rule"
                          : "Grouped automatically because these rules test the same fact"}
                      </div>
                      {cluster.members
                        .filter((m) => m.rule_id !== rule.rule_id)
                        .slice(0, 8)
                        .map((m) => (
                          <div key={m.rule_id}>{m.title}</div>
                        ))}
                      {cluster.members.length > 9 && <div>…and {cluster.members.length - 9} more</div>}
                      {onSelectFamily && (
                        <div className="policy-row-cluster-tip-action">
                          Click to select all {cluster.members.length} for bulk review
                        </div>
                      )}
                    </>
                  }
                >
                  <span
                    className={`policy-row-family-chip${isBandStart ? "" : " policy-row-family-chip--continuation"}${
                      onSelectFamily ? " policy-row-family-chip--actionable" : ""
                    }`}
                    role={onSelectFamily ? "button" : undefined}
                    tabIndex={onSelectFamily ? 0 : undefined}
                    onClick={
                      onSelectFamily
                        ? (e) => {
                            // The row itself toggles expand — a chip click means
                            // "act on the family", not "open this one rule".
                            e.stopPropagation();
                            onSelectFamily();
                          }
                        : undefined
                    }
                    onKeyDown={
                      onSelectFamily
                        ? (e) => {
                            if (e.key === "Enter" || e.key === " ") {
                              e.preventDefault();
                              e.stopPropagation();
                              onSelectFamily();
                            }
                          }
                        : undefined
                    }
                  >
                    <ClusterOutlined className="policy-row-family-chip-icon" />
                    {isBandStart ? (
                      <>
                        <span className="policy-row-family-chip-name">{clusterLabel(cluster)}</span>
                        {/* When the family is split across the list this run is only
                            part of it, so the head carries position as well as size —
                            a bare total would imply "these are all of them". */}
                        <span className="policy-row-family-chip-count">
                          {band?.fragmented && band.ordinal && band.total
                            ? `${band.ordinal}/${band.total}`
                            : (band && band.total > 1 ? band.total : cluster.members.length)}
                        </span>
                      </>
                    ) : (
                      <span className="policy-row-family-chip-name">
                        {band?.ordinal} of {band?.total}
                      </span>
                    )}
                  </span>
                </Tooltip>
              )}
              <span>{ruleTypeLabel(rule.rule_type)}</span>
              {rule.tags.includes(DOCUMENT_GUIDANCE_TAG) && (
                <Tooltip title="The subject of this statement is the document itself — what it is, who it is for, or how to read it. It was kept for you to decide, but it is not treated as an enforceable rule.">
                  <Tag bordered={false} color="default" className="policy-row-category-tag">
                    <ReadOutlined /> Describes the document
                  </Tag>
                </Tooltip>
              )}
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
      </div>
      <Space size={4} className="candidate-row-actions" onClick={(e) => e.stopPropagation()}>
        {onApprove && onReject && (
          <>
            <Tooltip title="Quick approve">
              <Button size="small" type="text" icon={<CheckOutlined style={{ color: "#16a34a" }} />} onClick={onApprove} />
            </Tooltip>
            <Tooltip title="Quick reject">
              <Button size="small" type="text" icon={<CloseOutlined style={{ color: "#dc2626" }} />} onClick={onReject} />
            </Tooltip>
          </>
        )}
        <Tooltip title={expanded ? "Viewing details" : "Open details"}>
          <Button
            size="small"
            type="text"
            icon={<RightOutlined />}
            className="candidate-row-open-btn"
            onClick={onToggleExpand}
            aria-label={expanded ? `Viewing ${rule.title}` : `Open details for ${rule.title}`}
          />
        </Tooltip>
      </Space>
    </div>
  );
}
