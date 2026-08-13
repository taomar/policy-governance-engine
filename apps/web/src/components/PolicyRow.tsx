import { Button, Checkbox, Dropdown, message, Tag, Tooltip } from "antd";
import type { MenuProps } from "antd";
import {
  ClockCircleOutlined,
  ClusterOutlined,
  CopyOutlined,
  CrownOutlined,
  EditOutlined,
  ExclamationCircleOutlined,
  MoreOutlined,
} from "@ant-design/icons";
import type { CanonicalRule } from "../api";
import {
  ambiguityMeta,
  clusterColor,
  clusterIdentity,
  clusterLabel,
  hasAmbiguityFlag,
  hexToRgba,
  ruleDecisionSummary,
  type RuleVariationGroup,
} from "../ruleDisplay";
import { ruleTypeLabel } from "../ruleTypes";
import { colorForCategory } from "../policyCategories";
import { PolicyEffectBadge } from "./PolicyEffectBadge";

export type PolicyDensity = "comfortable" | "compact";

interface PolicyRowProps {
  rule: CanonicalRule;
  selected: boolean;
  density: PolicyDensity;
  /** Current search text, used only to subtly highlight matches — never
   * changes what's shown, only how it's rendered. */
  searchQuery?: string;
  onSelect: (rule: CanonicalRule) => void;
  /** Present only when this rule's version is the active one (matches the
   * previous Revise-availability rule in PoliciesTab/RuleCard). */
  onRevise?: (rule: CanonicalRule) => void;
  /** Opens the inspector on this rule with the History tab active. */
  onViewHistory?: (rule: CanonicalRule) => void;
  /** The "variations of one decision" family this rule belongs to, if any —
   * see `buildVariationClusters` in ruleDisplay.ts. `null`/`undefined` means
   * this rule has no visible siblings, and no band/badge is rendered. */
  cluster?: RuleVariationGroup | null;
  /** Whether this row is the first/last in a run of consecutive rows that
   * share the same cluster, as currently displayed — drives the rounded
   * "bracket" caps so N adjacent siblings read as one continuous band. */
  isBandStart?: boolean;
  isBandEnd?: boolean;
  /** Position of this row within its family across the whole displayed list
   * ("3 of 7"), independent of whether siblings happen to be adjacent. */
  bandOrdinal?: number;
  bandTotal?: number;
  /** True when siblings exist above/below the current run — renders a faded
   * band cap so a fragment never reads as the complete family. */
  continuesAbove?: boolean;
  continuesBelow?: boolean;
  /** True when the run this row sits in holds only *some* of the family's
   * members — i.e. siblings are scattered elsewhere in the list. A run-level
   * fact, so a run's middle rows know it too, not just its end caps. */
  familyFragmented?: boolean;
  /** True while a sibling row (sharing this row's cluster) is hovered —
   * paints a soft cluster-colored tint so the whole family lights up
   * together while scanning the list. */
  isClusterHighlighted?: boolean;
  /** True when the toolbar lens has isolated this row's family. */
  isClusterFocused?: boolean;
  /** Reports this row's cluster identity on hover (`null` on mouse-leave) so
   * the parent list can highlight every currently-visible sibling. */
  onHoverCluster?: (clusterId: string | null) => void;
  /** Isolates this row's family in the list (toggles off when already focused). */
  onFocusCluster?: (clusterId: string | null) => void;
  selectedForExport?: boolean;
  onToggleExportSelection?: (ruleId: string) => void;
  style?: React.CSSProperties;
}

function highlight(text: string, query?: string): React.ReactNode {
  const q = query?.trim();
  if (!q) return text;
  const escaped = q.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const parts = text.split(new RegExp(`(${escaped})`, "ig"));
  if (parts.length === 1) return text;
  return parts.map((part, i) =>
    part.toLowerCase() === q.toLowerCase() ? (
      <mark key={i} className="policy-row-highlight">
        {part}
      </mark>
    ) : (
      <span key={i}>{part}</span>
    )
  );
}

/**
 * One compact, information-dense row in the Policies list — the "master"
 * half of the master/detail workspace. Replaces the old giant accordion
 * card: title + condition-to-effect summary + light metadata caption, with
 * a "Revise" and overflow menu instead of everything expanding inline.
 */
export function PolicyRow({
  rule,
  selected,
  density,
  searchQuery,
  onSelect,
  onRevise,
  onViewHistory,
  cluster,
  isBandStart = true,
  isBandEnd = true,
  bandOrdinal,
  bandTotal,
  continuesAbove = false,
  continuesBelow = false,
  familyFragmented = false,
  isClusterHighlighted,
  isClusterFocused,
  onHoverCluster,
  onFocusCluster,
  selectedForExport,
  onToggleExportSelection,
  style,
}: PolicyRowProps) {
  const decision = ruleDecisionSummary(rule);
  const accent = cluster ? clusterColor(cluster) : undefined;

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      onSelect(rule);
    }
  };

  const copyId = async () => {
    try {
      await navigator.clipboard.writeText(rule.rule_id);
      message.success(`Copied ${rule.rule_id}`);
    } catch {
      message.error("Couldn't copy — clipboard unavailable");
    }
  };

  const menuItems: MenuProps["items"] = [
    onRevise && { key: "revise", label: "Revise", icon: <EditOutlined /> },
    { key: "copy", label: "Copy ID", icon: <CopyOutlined /> },
    onViewHistory && { key: "history", label: "View history", icon: <ClockCircleOutlined /> },
  ].filter(Boolean) as MenuProps["items"];

  const handleMenuClick: MenuProps["onClick"] = ({ key, domEvent }) => {
    domEvent.stopPropagation();
    if (key === "revise") onRevise?.(rule);
    else if (key === "copy") void copyId();
    else if (key === "history") onViewHistory?.(rule);
  };

  const handleClusterEnter = () => cluster && onHoverCluster?.(clusterIdentity(cluster));
  const handleClusterLeave = () => cluster && onHoverCluster?.(null);

  const rowStyle: React.CSSProperties = { ...style };
  if (accent) {
    const vars = rowStyle as Record<string, string>;
    vars["--cluster-accent"] = accent;
    vars["--cluster-tint"] = hexToRgba(accent, 0.1);
    // Resting wash for a whole family run. Much fainter than the hover/lens
    // tint so the block reads as one recessed surface without shouting.
    vars["--cluster-wash"] = hexToRgba(accent, 0.055);
  }

  // A run's first row acts as its head and carries the family name; the rest
  // are identified by the shared rail, wash and node dots. The exception is a
  // *fragmented* run (siblings scattered elsewhere in the list), where every
  // row needs its "3 of 7" position — otherwise a partial run silently reads
  // as the whole family.
  const fragmented = familyFragmented || continuesAbove || continuesBelow;
  const showFamilyChip = !!cluster && (isBandStart || fragmented);

  return (
    <div
      role="button"
      tabIndex={0}
      aria-pressed={selected}
      className={`policy-row policy-row--${density}${cluster ? " policy-row--family" : ""}${
        cluster && isBandStart ? " policy-row--family-start" : ""
      }${cluster && isBandEnd ? " policy-row--family-end" : ""}${selected ? " policy-row-selected" : ""}${
        isClusterHighlighted ? " policy-row-cluster-lit" : ""
      }${isClusterFocused ? " policy-row-cluster-focused" : ""}`}
      style={rowStyle}
      onClick={() => onSelect(rule)}
      onKeyDown={handleKeyDown}
      onMouseEnter={handleClusterEnter}
      onMouseLeave={handleClusterLeave}
    >
      {onToggleExportSelection && (
        <Checkbox
          checked={selectedForExport}
          onChange={() => onToggleExportSelection(rule.rule_id)}
          onClick={(event) => event.stopPropagation()}
          aria-label={`Select ${rule.title} for export`}
          className="policy-row-export-checkbox"
        />
      )}
      {cluster && (
        <>
          <span
            className={`policy-row-band${isBandStart ? " policy-row-band--start" : ""}${
              isBandEnd ? " policy-row-band--end" : ""
            }${continuesAbove ? " policy-row-band--continues-up" : ""}${
              continuesBelow ? " policy-row-band--continues-down" : ""
            }`}
            aria-hidden="true"
          />
          {/* Timeline node — the per-member marker that turns a plain stripe
              into a countable "N things hanging off one spine". */}
          <span className="policy-row-band-node" aria-hidden="true" />
        </>
      )}
      <div className="policy-row-main">
        <div className="policy-row-line1">
          <span className="policy-row-title">{highlight(rule.title, searchQuery)}</span>
          <span className="policy-row-flags">
            {rule.is_explicit_override && (
              <Tooltip title="Explicit override — outranks otherwise-applicable rules">
                <CrownOutlined className="policy-row-flag policy-row-flag-override" />
              </Tooltip>
            )}
            {hasAmbiguityFlag(rule.ambiguity_status) && (
              <Tooltip title={`Ambiguity: ${ambiguityMeta(rule.ambiguity_status).label}`}>
                <ExclamationCircleOutlined
                  className={`policy-row-flag policy-row-flag-ambiguity policy-row-flag-ambiguity--${ambiguityMeta(rule.ambiguity_status).color}`}
                />
              </Tooltip>
            )}
          </span>
          <span className="policy-row-statuses">
            <PolicyEffectBadge effect={rule.effect} size="small" />
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
                ? "The source states this test in words rather than as a comparison between named quantities, so a judge settles a case by reading it."
                : undefined
            }
          >
            {highlight(decision.condition, searchQuery)}
          </span>
          <span className="policy-decision-arrow">→</span>
          <span className="policy-decision-key">Then</span>
          <span className="policy-decision-result">{highlight(decision.action, searchQuery)}</span>
        </div>
        <div className="policy-row-line3">
          {showFamilyChip && (
            <Tooltip
              title={
                <>
                  <div className="policy-row-cluster-tip-title">{clusterLabel(cluster!)}</div>
                  <div className="policy-row-cluster-tip-sub">
                    {isClusterFocused ? "Click to show all policies again" : "Click to show only this family"}
                  </div>
                  {cluster!.members
                    .filter((m) => m.rule_id !== rule.rule_id)
                    .slice(0, 8)
                    .map((m) => (
                      <div key={m.rule_id}>{m.title}</div>
                    ))}
                  {cluster!.members.length > 9 && <div>…and {cluster!.members.length - 9} more</div>}
                </>
              }
            >
              <span
                className={`policy-row-family-chip${onFocusCluster ? " policy-row-family-chip--clickable" : ""}${
                  isClusterFocused ? " policy-row-family-chip--focused" : ""
                }${isBandStart ? "" : " policy-row-family-chip--continuation"}`}
                onMouseEnter={handleClusterEnter}
                onMouseLeave={handleClusterLeave}
                onClick={(e) => {
                  if (!onFocusCluster) return;
                  // The row itself is a button; without this the click would also
                  // change the inspector selection, which is a different intent.
                  e.stopPropagation();
                  const id = clusterIdentity(cluster!);
                  onFocusCluster(isClusterFocused ? null : id);
                }}
              >
                <ClusterOutlined className="policy-row-family-chip-icon" />
                {isBandStart ? (
                  <>
                    <span className="policy-row-family-chip-name">{clusterLabel(cluster!)}</span>
                    {/* When the family is fragmented across the list this run is
                        only part of it, so the head carries position as well as
                        size — a bare total would imply "these are all of them". */}
                    <span className="policy-row-family-chip-count">
                      {fragmented && bandOrdinal && bandTotal
                        ? `${bandOrdinal}/${bandTotal}`
                        : (bandTotal && bandTotal > 1 ? bandTotal : cluster!.members.length)}
                    </span>
                  </>
                ) : (
                  <span className="policy-row-family-chip-name">
                    {bandOrdinal} of {bandTotal}
                  </span>
                )}
              </span>
            </Tooltip>
          )}
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
      </div>
      {menuItems && menuItems.length > 0 && (
        <Dropdown menu={{ items: menuItems, onClick: handleMenuClick }} trigger={["click"]} placement="bottomRight">
          <Button
            type="text"
            size="small"
            icon={<MoreOutlined />}
            className="policy-row-more-btn"
            onClick={(e) => e.stopPropagation()}
            aria-label={`More actions for ${rule.title}`}
          />
        </Dropdown>
      )}
    </div>
  );
}
