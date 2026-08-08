import { useMemo, useState } from "react";
import { Button, Input, Popover, Segmented, Select, Tag, Tooltip } from "antd";
import { AppstoreOutlined, BarsOutlined, ClusterOutlined, FilterOutlined, SearchOutlined } from "@ant-design/icons";
import { ruleTypeLabel } from "../ruleTypes";
import type { PolicyDensity } from "./PolicyRow";

/** How many family chips show before collapsing behind a "+N more" toggle. */
const FAMILY_CHIP_LIMIT = 12;

export interface PolicyFacetOptions {
  effects: string[];
  ruleTypes: string[];
  categories: string[];
  jurisdictions: string[];
  organizationalUnits: string[];
  processes: string[];
  owners: string[];
}

export interface PolicyFilters {
  effects: string[];
  ruleTypes: string[];
  categories: string[];
  jurisdictions: string[];
  organizationalUnits: string[];
  processes: string[];
  owners: string[];
}

export const EMPTY_POLICY_FILTERS: PolicyFilters = {
  effects: [],
  ruleTypes: [],
  categories: [],
  jurisdictions: [],
  organizationalUnits: [],
  processes: [],
  owners: [],
};

export type PolicyGroupBy = "type" | "category" | "family" | "none";
export type PolicySortBy = "title" | "priority" | "ruleId" | "effectiveFrom";

/** One selectable variation family shown in the at-a-glance strip. */
export interface PolicyFamilyChip {
  id: string;
  label: string;
  color: string;
  count: number;
}

const FILTER_DIMENSIONS: { key: keyof PolicyFilters; label: string; facet: keyof PolicyFacetOptions; humanize?: boolean }[] = [
  { key: "effects", label: "Effect", facet: "effects" },
  { key: "ruleTypes", label: "Rule type", facet: "ruleTypes", humanize: true },
  { key: "categories", label: "Category", facet: "categories" },
  { key: "jurisdictions", label: "Jurisdiction", facet: "jurisdictions" },
  { key: "organizationalUnits", label: "Business unit", facet: "organizationalUnits" },
  { key: "processes", label: "Process", facet: "processes" },
  { key: "owners", label: "Owner", facet: "owners" },
];

function labelForFilterValue(dimensionKey: keyof PolicyFilters, value: string): string {
  return dimensionKey === "ruleTypes" ? ruleTypeLabel(value) : value;
}

export function activeFilterCount(filters: PolicyFilters): number {
  return FILTER_DIMENSIONS.reduce((n, d) => n + filters[d.key].length, 0);
}

interface PoliciesToolbarProps {
  search: string;
  onSearchChange: (v: string) => void;
  groupBy: PolicyGroupBy;
  onGroupByChange: (v: PolicyGroupBy) => void;
  sortBy: PolicySortBy;
  onSortByChange: (v: PolicySortBy) => void;
  density: PolicyDensity;
  onDensityChange: (v: PolicyDensity) => void;
  filters: PolicyFilters;
  onFiltersChange: (f: PolicyFilters) => void;
  facetOptions: PolicyFacetOptions;
  resultCount: number;
  totalCount: number;
  /** Every variation family in the current version, largest first. Rendered as a
   * scannable colored strip so related-but-scattered rules are discoverable
   * *before* you happen to scroll past one of their rows. */
  families?: PolicyFamilyChip[];
  /** Currently isolated family (`clusterIdentity`), or null for "show everything". */
  focusedFamily?: string | null;
  onFocusFamily?: (id: string | null) => void;
}

/**
 * Search + filter + group/sort/density controls above the policy list.
 * Filter options are always built from the *whole* dataset (not the
 * already-filtered subset) so choices never disappear as you narrow down.
 */
export function PoliciesToolbar({
  search,
  onSearchChange,
  groupBy,
  onGroupByChange,
  sortBy,
  onSortByChange,
  density,
  onDensityChange,
  filters,
  onFiltersChange,
  facetOptions,
  resultCount,
  totalCount,
  families = [],
  focusedFamily = null,
  onFocusFamily,
}: PoliciesToolbarProps) {
  const activeCount = activeFilterCount(filters);
  const [showAllFamilies, setShowAllFamilies] = useState(false);

  // Families are ordered largest-first, so the first dozen carry nearly all the
  // signal; a version with dozens of small families would otherwise turn the strip
  // into a wall of chips taller than the list it describes. A focused family is
  // always kept visible so the active lens never scrolls out of its own control.
  const visibleFamilies = useMemo(() => {
    if (showAllFamilies || families.length <= FAMILY_CHIP_LIMIT) return families;
    const head = families.slice(0, FAMILY_CHIP_LIMIT);
    if (focusedFamily && !head.some((f) => f.id === focusedFamily)) {
      const active = families.find((f) => f.id === focusedFamily);
      if (active) return [...head.slice(0, FAMILY_CHIP_LIMIT - 1), active];
    }
    return head;
  }, [families, showAllFamilies, focusedFamily]);

  const hiddenFamilyCount = families.length - visibleFamilies.length;

  const setDimension = (key: keyof PolicyFilters, values: string[]) => {
    onFiltersChange({ ...filters, [key]: values });
  };

  const removeValue = (key: keyof PolicyFilters, value: string) => {
    setDimension(key, filters[key].filter((v) => v !== value));
  };

  const filterPopoverContent = (
    <div className="policies-filter-popover">
      {FILTER_DIMENSIONS.map((d) => {
        const options = facetOptions[d.facet];
        if (options.length === 0) return null;
        return (
          <div key={d.key} className="policies-filter-row">
            <span className="policies-filter-row-label">{d.label}</span>
            <Select
              mode="multiple"
              allowClear
              placeholder="Any"
              size="small"
              className="policies-filter-row-select"
              value={filters[d.key]}
              onChange={(v) => setDimension(d.key, v)}
              options={options.map((o) => ({ value: o, label: labelForFilterValue(d.key, o) }))}
              maxTagCount="responsive"
            />
          </div>
        );
      })}
      {activeCount > 0 && (
        <Button size="small" onClick={() => onFiltersChange(EMPTY_POLICY_FILTERS)} className="policies-filter-clear-btn">
          Clear all filters
        </Button>
      )}
    </div>
  );

  return (
    <div className="policies-toolbar">
      <div className="policies-toolbar-row">
        <Input
          allowClear
          placeholder="Search policies…"
          prefix={<SearchOutlined />}
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
          className="policies-toolbar-search"
        />
        <Popover content={filterPopoverContent} trigger="click" placement="bottomLeft" title="Filter policies">
          <Button icon={<FilterOutlined />}>
            Filters{activeCount > 0 ? ` (${activeCount})` : ""}
          </Button>
        </Popover>
        <Select
          value={groupBy}
          onChange={onGroupByChange}
          className="policies-toolbar-select"
          options={[
            { value: "type", label: "Group: Type" },
            { value: "category", label: "Group: Category" },
            { value: "family", label: "Group: Related family" },
            { value: "none", label: "No grouping" },
          ]}
        />
        <Select
          value={sortBy}
          onChange={onSortByChange}
          className="policies-toolbar-select"
          options={[
            { value: "title", label: "Sort: Title A–Z" },
            { value: "priority", label: "Sort: Priority" },
            { value: "ruleId", label: "Sort: Rule ID" },
            { value: "effectiveFrom", label: "Sort: Effective date" },
          ]}
        />
        <Segmented
          value={density}
          onChange={(v) => onDensityChange(v as PolicyDensity)}
          options={[
            { value: "comfortable", icon: <AppstoreOutlined />, title: "Comfortable" },
            { value: "compact", icon: <BarsOutlined />, title: "Compact" },
          ]}
        />
      </div>

      {families.length > 0 && onFocusFamily && (
        <div className="policies-family-strip">
          <span className="policies-family-strip-label">
            <ClusterOutlined /> {families.length} related {families.length === 1 ? "family" : "families"}
          </span>
          <div className="policies-family-strip-chips">
            {visibleFamilies.map((f) => {
              const active = focusedFamily === f.id;
              return (
                <Tooltip key={f.id} title={active ? "Show all policies again" : `Show only these ${f.count} related policies`}>
                  <button
                    type="button"
                    aria-pressed={active}
                    className={`policies-family-chip${active ? " policies-family-chip--active" : ""}`}
                    style={{ "--family-color": f.color } as React.CSSProperties}
                    onClick={() => onFocusFamily(active ? null : f.id)}
                  >
                    <span className="policies-family-chip-dot" />
                    <span className="policies-family-chip-label">{f.label}</span>
                    <span className="policies-family-chip-count">{f.count}</span>
                  </button>
                </Tooltip>
              );
            })}
            {families.length > FAMILY_CHIP_LIMIT && (
              <button type="button" className="policies-family-more" onClick={() => setShowAllFamilies((v) => !v)}>
                {showAllFamilies ? "show fewer" : `+${hiddenFamilyCount} more`}
              </button>
            )}
          </div>
        </div>
      )}

      {activeCount > 0 && (
        <div className="policies-toolbar-chips">
          {FILTER_DIMENSIONS.flatMap((d) =>
            filters[d.key].map((v) => (
              <Tag key={`${d.key}:${v}`} closable onClose={() => removeValue(d.key, v)}>
                {d.label}: {labelForFilterValue(d.key, v)}
              </Tag>
            ))
          )}
        </div>
      )}

      <div className="policies-toolbar-count">
        {resultCount} of {totalCount} polic{totalCount === 1 ? "y" : "ies"} shown
        {focusedFamily && onFocusFamily && (
          <>
            {" · "}
            <button type="button" className="policies-family-clear" onClick={() => onFocusFamily(null)}>
              clear family focus
            </button>
          </>
        )}
      </div>
    </div>
  );
}
