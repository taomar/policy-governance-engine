import { useEffect, useMemo, useRef, useState } from "react";
import { Empty } from "antd";
import type { CanonicalRule } from "../api";
import { PolicyRow, type PolicyDensity } from "./PolicyRow";
import { PolicyGroupHeader } from "./PolicyGroupHeader";
import { clusterIdentity, type RuleVariationGroup } from "../ruleDisplay";
import { computeBandGeometry } from "../bandGeometry";

export interface PolicyGroup {
  key: string;
  label: string;
  rules: CanonicalRule[];
}

type FlatItem =
  | { type: "header"; key: string; groupKey: string; label: string; count: number }
  | { type: "row"; key: string; rule: CanonicalRule };

const HEADER_HEIGHT = 34;
const ROW_HEIGHT: Record<PolicyDensity, number> = { comfortable: 78, compact: 54 };
const OVERSCAN_PX = 500;

interface PolicyListProps {
  groups: PolicyGroup[];
  /** When false, rules render as a single flat list with no group dividers
   * (used when the toolbar's "group by" is set to None). */
  showGroupHeaders?: boolean;
  collapsedGroups: Set<string>;
  onToggleGroup: (key: string) => void;
  selectedRuleId?: string;
  density: PolicyDensity;
  searchQuery?: string;
  onSelectRule: (rule: CanonicalRule) => void;
  onReviseRule?: (rule: CanonicalRule) => void;
  onViewHistory?: (rule: CanonicalRule) => void;
  emptyMessage?: React.ReactNode;
  /** Rule ID → the "variations of one decision" family it belongs to (see
   * `buildVariationClusters` in ruleDisplay.ts). Rules absent from the map
   * belong to no visible family and render with no left-edge band. */
  clusterMap?: Map<string, RuleVariationGroup>;
  /** Family currently isolated by the toolbar lens (`clusterIdentity`), or null. */
  focusedFamily?: string | null;
  onFocusFamily?: (id: string | null) => void;
  selectedForExport?: Set<string>;
  onToggleExportSelection?: (ruleId: string) => void;
}

/**
 * The "master" pane: a single scroll container that windows its contents so
 * DOM node count stays flat regardless of how many rules are loaded (tested
 * up to ~500). Headers and rows are flattened into one positioned list so
 * scrolling, keyboard navigation, and group collapse all operate over one
 * consistent index space.
 */
export function PolicyList({
  groups,
  showGroupHeaders = true,
  collapsedGroups,
  onToggleGroup,
  selectedRuleId,
  density,
  searchQuery,
  onSelectRule,
  onReviseRule,
  onViewHistory,
  emptyMessage,
  clusterMap,
  focusedFamily = null,
  onFocusFamily,
  selectedForExport,
  onToggleExportSelection,
}: PolicyListProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [scrollTop, setScrollTop] = useState(0);
  const [viewportHeight, setViewportHeight] = useState(600);
  const [hoveredCluster, setHoveredCluster] = useState<string | null>(null);
  const rowHeight = ROW_HEIGHT[density];

  const items = useMemo<FlatItem[]>(() => {
    const flat: FlatItem[] = [];
    for (const g of groups) {
      if (showGroupHeaders) {
        flat.push({ type: "header", key: `h:${g.key}`, groupKey: g.key, label: g.label, count: g.rules.length });
      }
      if (!showGroupHeaders || !collapsedGroups.has(g.key)) {
        for (const rule of g.rules) {
          flat.push({ type: "row", key: rule.rule_id, rule });
        }
      }
    }
    return flat;
  }, [groups, showGroupHeaders, collapsedGroups]);

  const { offsets, total } = useMemo(() => {
    const arr: number[] = new Array(items.length);
    let acc = 0;
    for (let i = 0; i < items.length; i++) {
      arr[i] = acc;
      acc += items[i].type === "header" ? HEADER_HEIGHT : rowHeight;
    }
    return { offsets: arr, total: acc };
  }, [items, rowHeight]);

  const totalRuleCount = useMemo(() => groups.reduce((n, g) => n + g.rules.length, 0), [groups]);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const update = () => setViewportHeight(el.clientHeight);
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const handleScroll = () => {
    if (containerRef.current) setScrollTop(containerRef.current.scrollTop);
  };

  let startIndex = 0;
  let endIndex = items.length - 1;
  for (let i = 0; i < items.length; i++) {
    const h = items[i].type === "header" ? HEADER_HEIGHT : rowHeight;
    if (offsets[i] + h >= scrollTop - OVERSCAN_PX) {
      startIndex = i;
      break;
    }
    startIndex = i + 1;
  }
  for (let i = startIndex; i < items.length; i++) {
    if (offsets[i] > scrollTop + viewportHeight + OVERSCAN_PX) {
      endIndex = i - 1;
      break;
    }
    endIndex = i;
  }

  const visible = items.slice(startIndex, Math.max(startIndex, endIndex + 1));

  const rowItems = useMemo(() => items.filter((i): i is Extract<FlatItem, { type: "row" }> => i.type === "row"), [items]);

  // Band geometry lives in `bandGeometry.ts` so the Review queue can band
  // pending candidates by the same criterion this list uses.
  const bandInfo = useMemo(
    () =>
      computeBandGeometry(
        items.map((item) => (item.type === "row" ? { kind: "rule" as const, ruleId: item.rule.rule_id } : { kind: "divider" as const })),
        clusterMap,
      ),
    [items, clusterMap],
  );

  const scrollRuleIntoView = (ruleId: string) => {
    const idx = items.findIndex((i) => i.type === "row" && i.rule.rule_id === ruleId);
    if (idx < 0 || !containerRef.current) return;
    const top = offsets[idx];
    const bottom = top + rowHeight;
    const el = containerRef.current;
    if (top < el.scrollTop) el.scrollTop = top;
    else if (bottom > el.scrollTop + el.clientHeight) el.scrollTop = bottom - el.clientHeight;
  };

  const handleListKeyDown = (e: React.KeyboardEvent) => {
    if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(e.key)) return;
    if (rowItems.length === 0) return;
    e.preventDefault();
    const idx = rowItems.findIndex((r) => r.rule.rule_id === selectedRuleId);
    let nextIdx = idx;
    if (e.key === "ArrowDown") nextIdx = idx < 0 ? 0 : Math.min(rowItems.length - 1, idx + 1);
    else if (e.key === "ArrowUp") nextIdx = idx < 0 ? 0 : Math.max(0, idx - 1);
    else if (e.key === "Home") nextIdx = 0;
    else if (e.key === "End") nextIdx = rowItems.length - 1;
    const next = rowItems[nextIdx];
    if (next) {
      onSelectRule(next.rule);
      scrollRuleIntoView(next.rule.rule_id);
    }
  };

  if (totalRuleCount === 0) {
    return (
      <div className="policy-list-empty">
        <Empty description={emptyMessage ?? "No policies match the current filters"} />
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className="policy-list-scroll"
      onScroll={handleScroll}
      onKeyDown={handleListKeyDown}
      tabIndex={-1}
      role="listbox"
      aria-label="Policies"
    >
      <div className="policy-list-spacer" style={{ height: total }}>
        {visible.map((item, i) => {
          const absoluteIndex = startIndex + i;
          const top = offsets[absoluteIndex];
          if (item.type === "header") {
            return (
              <PolicyGroupHeader
                key={item.key}
                label={item.label}
                count={item.count}
                collapsed={collapsedGroups.has(item.groupKey)}
                onToggle={() => onToggleGroup(item.groupKey)}
                style={{ position: "absolute", top, left: 0, right: 0, height: HEADER_HEIGHT }}
              />
            );
          }
          const cluster = clusterMap?.get(item.rule.rule_id) ?? null;
          const band = bandInfo.get(item.rule.rule_id);
          const clusterId = cluster ? clusterIdentity(cluster) : null;
          return (
            <PolicyRow
              key={item.key}
              rule={item.rule}
              selected={item.rule.rule_id === selectedRuleId}
              density={density}
              searchQuery={searchQuery}
              onSelect={onSelectRule}
              onRevise={onReviseRule}
              onViewHistory={onViewHistory}
              cluster={cluster}
              isBandStart={band?.isStart ?? true}
              isBandEnd={band?.isEnd ?? true}
              bandOrdinal={band?.ordinal}
              bandTotal={band?.total}
              continuesAbove={band?.continuesAbove ?? false}
              continuesBelow={band?.continuesBelow ?? false}
              familyFragmented={band?.fragmented ?? false}
              isClusterHighlighted={!!clusterId && hoveredCluster === clusterId}
              isClusterFocused={!!clusterId && focusedFamily === clusterId}
              onHoverCluster={setHoveredCluster}
              onFocusCluster={onFocusFamily}
              selectedForExport={selectedForExport?.has(item.rule.rule_id)}
              onToggleExportSelection={onToggleExportSelection}
              style={{ position: "absolute", top, left: 0, right: 0, height: rowHeight }}
            />
          );
        })}
      </div>
    </div>
  );
}
