import { useEffect, useMemo, useState } from "react";
import { Alert, Card, Drawer, Empty, Grid, Select, Space, Tag, Typography, message } from "antd";
import { api, PolicyPlatformApiError, type AggregateLimit, type ApprovedPolicyVersion, type CanonicalRule } from "../api";
import { EditRuleModal } from "./EditRuleModal";
import { RULE_TYPES, ruleTypeLabel } from "../ruleTypes";
import { buildVariationClusters, clusterColor, clusterIdentity, clusterLabel, type RuleVariationGroup } from "../ruleDisplay";
import { PolicyList, type PolicyGroup } from "./PolicyList";
import { PolicyInspector } from "./PolicyInspector";
import {
  PoliciesToolbar,
  EMPTY_POLICY_FILTERS,
  type PolicyFacetOptions,
  type PolicyFilters,
  type PolicyGroupBy,
  type PolicySortBy,
} from "./PoliciesToolbar";
import type { PolicyDensity } from "./PolicyRow";

const { Title, Text, Paragraph } = Typography;

const DENSITY_STORAGE_KEY = "policyPlatform.policiesDensity";

function loadStoredDensity(): PolicyDensity {
  try {
    const v = localStorage.getItem(DENSITY_STORAGE_KEY);
    return v === "compact" ? "compact" : "comfortable";
  } catch {
    return "comfortable";
  }
}

interface PoliciesTabProps {
  policySetKey: string;
  onNavigate?: (page: string) => void;
}

/**
 * Read-oriented master/detail view of a project's *approved* policy rules: a compact,
 * virtualized, filterable/sortable list on one side and a full-depth inspector (Overview /
 * Logic / Scope / History / Notes) on the other — replacing the old accordion-of-accordions
 * so browsing hundreds of rules stays fast and a single selected rule can show its full
 * detail without forcing every other row to expand too. This is deliberately separate from
 * the Review tab, which is about the draft/approve/publish workflow for candidate rules;
 * Policies shows the result of that workflow, organized for reading. Defaults to the active
 * published version; older versions can be selected to see how policies looked at an earlier
 * point in time.
 */
export function PoliciesTab({ policySetKey, onNavigate }: PoliciesTabProps) {
  const screens = Grid.useBreakpoint();
  const isDesktop = !!screens.lg;

  const [versions, setVersions] = useState<ApprovedPolicyVersion[]>([]);
  const [versionId, setVersionId] = useState<string>("");
  const [rules, setRules] = useState<CanonicalRule[]>([]);
  const [aggregateLimits, setAggregateLimits] = useState<AggregateLimit[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [search, setSearch] = useState("");
  const [filters, setFilters] = useState<PolicyFilters>(EMPTY_POLICY_FILTERS);
  const [groupBy, setGroupBy] = useState<PolicyGroupBy>("type");
  const [sortBy, setSortBy] = useState<PolicySortBy>("title");
  const [density, setDensity] = useState<PolicyDensity>(loadStoredDensity);
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(new Set());
  /** When set, the list is narrowed to a single variation family (by
   * `clusterIdentity`) — the "show me only these related rules" affordance,
   * since family members are otherwise scattered by title/type ordering. */
  const [focusedFamily, setFocusedFamily] = useState<string | null>(null);

  const [selectedRuleId, setSelectedRuleId] = useState<string | null>(null);
  const [inspectorTab, setInspectorTab] = useState("overview");
  const [mobileInspectorOpen, setMobileInspectorOpen] = useState(false);
  const [reviseTarget, setReviseTarget] = useState<CanonicalRule | null>(null);

  useEffect(() => {
    setError(null);
    api
      .listPolicyVersions(policySetKey)
      .then((vs) => {
        const sorted = [...vs].sort((a, b) => b.version_number - a.version_number);
        setVersions(sorted);
        const active = sorted.find((v) => v.is_active) ?? sorted[0];
        setVersionId(active ? active.id : "");
      })
      .catch((e) => setError(e instanceof PolicyPlatformApiError ? e.detail : String(e)));
  }, [policySetKey]);

  useEffect(() => {
    if (!versionId) {
      setRules([]);
      setAggregateLimits([]);
      return;
    }
    setLoading(true);
    Promise.all([api.getVersionRules(policySetKey, versionId), api.getVersionAggregateLimits(policySetKey, versionId)])
      .then(([rs, aggs]) => {
        setRules(rs);
        setAggregateLimits(aggs);
      })
      .catch((e) => setError(e instanceof PolicyPlatformApiError ? e.detail : String(e)))
      .finally(() => setLoading(false));
  }, [policySetKey, versionId]);

  useEffect(() => {
    try {
      localStorage.setItem(DENSITY_STORAGE_KEY, density);
    } catch {
      // localStorage unavailable (e.g. private browsing) — density preference just won't persist.
    }
  }, [density]);

  // Reset manual group-collapse choices whenever a new version's rules load or the grouping
  // mode changes — the group *keys* change meaning at that point, so stale collapse state
  // could otherwise hide an unrelated group under the same key.
  useEffect(() => {
    setCollapsedGroups(new Set());
  }, [versionId, groupBy]);

  // Cluster identities are derived from the loaded rule set, so a focus held across a
  // version switch could silently resolve to nothing and show an empty list with no
  // obvious cause. Deliberately not keyed on groupBy — a family lens stays meaningful
  // no matter how the remaining rules are grouped.
  useEffect(() => {
    setFocusedFamily(null);
  }, [versionId]);

  // Auto-select the first rule whenever a new rule set loads, but keep the current selection
  // (and whichever inspector tab the user is on) if it's still present — e.g. after switching
  // grouping/sort/filters, which never change the underlying `rules` array.
  useEffect(() => {
    if (rules.length === 0) {
      setSelectedRuleId(null);
      return;
    }
    setSelectedRuleId((prev) => (prev && rules.some((r) => r.rule_id === prev) ? prev : rules[0].rule_id));
  }, [rules]);

  // Computed once over the full, unfiltered rule set (not `sorted`/`filtered`) so a rule's
  // cluster identity — and its left-list band color — stays stable regardless of search,
  // facet filters, or grouping; only which *currently rendered* rows a band actually spans
  // depends on what's visible. See ruleDisplay.ts's buildVariationClusters doc comment.
  const clusterMap = useMemo(() => buildVariationClusters(rules), [rules]);

  /** Every distinct family, largest first — drives both the "Group: Related family"
   * ordering and the at-a-glance family strip above the list. Largest-first matters
   * because a 7-rule family is far more interesting to look at than a 2-rule one. */
  const families = useMemo(() => {
    const byId = new Map<string, RuleVariationGroup>();
    for (const cluster of clusterMap.values()) byId.set(clusterIdentity(cluster), cluster);
    return [...byId.entries()]
      .map(([id, cluster]) => ({ id, cluster }))
      .sort((a, b) => b.cluster.members.length - a.cluster.members.length || a.id.localeCompare(b.id));
  }, [clusterMap]);

  /** Sentinel group key for rules that belong to no family, so they still render
   * (collected under one trailing group) rather than silently disappearing. */
  const NO_FAMILY = "__nofamily__";

  const keyFor = (rule: CanonicalRule): string => {
    if (groupBy === "category") return rule.category || "Uncategorized";
    if (groupBy === "family") {
      const cluster = clusterMap.get(rule.rule_id);
      return cluster ? clusterIdentity(cluster) : NO_FAMILY;
    }
    return rule.rule_type || "uncategorized";
  };

  const labelFor = (key: string): string => {
    if (groupBy === "type") return ruleTypeLabel(key);
    if (groupBy === "family") {
      if (key === NO_FAMILY) return "No related rules";
      const match = families.find((f) => f.id === key);
      return match ? clusterLabel(match.cluster) : key;
    }
    return key;
  };

  // Group keys present across the *full* (unfiltered) rule set, so the group list — and its
  // order — stays stable as search/filters narrow which rules appear within each group.
  const allGroupKeys = useMemo(() => {
    if (groupBy === "none") return [];
    const present = new Set(rules.map(keyFor));
    if (groupBy === "type") {
      const known = RULE_TYPES.filter((t) => present.has(t));
      const extra = [...present].filter((t) => !RULE_TYPES.includes(t)).sort();
      return [...known, ...extra];
    }
    if (groupBy === "family") {
      // Biggest families first (they carry the most "these decide the same thing
      // differently" signal), unfamilied rules always last.
      const ordered = families.map((f) => f.id).filter((id) => present.has(id));
      return present.has(NO_FAMILY) ? [...ordered, NO_FAMILY] : ordered;
    }
    return [...present].sort((a, b) => {
      const aFallback = a === "Uncategorized" || a === "Ungrouped";
      const bFallback = b === "Uncategorized" || b === "Ungrouped";
      if (aFallback !== bFallback) return aFallback ? 1 : -1;
      return a.localeCompare(b);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rules, groupBy, families]);

  const searched = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return rules;
    return rules.filter(
      (r) =>
        r.title.toLowerCase().includes(q) ||
        r.description.toLowerCase().includes(q) ||
        r.rule_id.toLowerCase().includes(q) ||
        r.category.toLowerCase().includes(q) ||
        (r.group_label ?? "").toLowerCase().includes(q) ||
        r.tags.some((t) => t.toLowerCase().includes(q))
    );
  }, [rules, search]);

  const filtered = useMemo(() => {
    const hasEffect = filters.effects.length > 0;
    const hasType = filters.ruleTypes.length > 0;
    const hasCategory = filters.categories.length > 0;
    const hasJurisdiction = filters.jurisdictions.length > 0;
    const hasUnit = filters.organizationalUnits.length > 0;
    const hasProcess = filters.processes.length > 0;
    const hasOwner = filters.owners.length > 0;
    // Family focus is applied first and independently of the facet filters: it's a
    // "show me only this decision's variants" lens, not another facet.
    const base = focusedFamily
      ? searched.filter((r) => {
          const cluster = clusterMap.get(r.rule_id);
          return !!cluster && clusterIdentity(cluster) === focusedFamily;
        })
      : searched;
    if (!hasEffect && !hasType && !hasCategory && !hasJurisdiction && !hasUnit && !hasProcess && !hasOwner) {
      return base;
    }
    return base.filter((r) => {
      if (hasEffect && !filters.effects.includes(r.effect.type)) return false;
      if (hasType && !filters.ruleTypes.includes(r.rule_type)) return false;
      if (hasCategory && !filters.categories.includes(r.category)) return false;
      if (hasJurisdiction && !r.scope.jurisdictions.some((j) => filters.jurisdictions.includes(j))) return false;
      if (hasUnit && !r.scope.organizational_units.some((u) => filters.organizationalUnits.includes(u))) return false;
      if (hasProcess && !r.scope.processes.some((p) => filters.processes.includes(p))) return false;
      if (hasOwner && !filters.owners.includes(r.authority.owner)) return false;
      return true;
    });
  }, [searched, filters, focusedFamily, clusterMap]);

  const sorted = useMemo(() => {
    const arr = [...filtered];
    arr.sort((a, b) => {
      switch (sortBy) {
        case "priority":
          return b.priority - a.priority;
        case "ruleId":
          return a.rule_id.localeCompare(b.rule_id);
        case "effectiveFrom":
          return b.effective_from.localeCompare(a.effective_from);
        default:
          return a.title.localeCompare(b.title);
      }
    });
    return arr;
  }, [filtered, sortBy]);

  const policyGroups = useMemo<PolicyGroup[]>(() => {
    if (groupBy === "none") {
      return [{ key: "__all__", label: "", rules: sorted }];
    }
    const map = new Map<string, CanonicalRule[]>();
    for (const rule of sorted) {
      const key = keyFor(rule);
      if (!map.has(key)) map.set(key, []);
      map.get(key)!.push(rule);
    }
    return allGroupKeys.filter((k) => map.has(k)).map((k) => ({ key: k, label: labelFor(k), rules: map.get(k)! }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sorted, groupBy, allGroupKeys]);

  /** Display-ready chips for the family strip. Colors come from the same
   * `clusterColor` used by the row bands, so a chip and its rows always read as
   * the same family at a glance. */
  const familyChips = useMemo(
    () =>
      families.map((f) => ({
        id: f.id,
        label: clusterLabel(f.cluster),
        color: clusterColor(f.cluster),
        count: f.cluster.members.length,
      })),
    [families]
  );

  const facetOptions = useMemo<PolicyFacetOptions>(() => {
    const effects = new Set<string>();
    const ruleTypes = new Set<string>();
    const categories = new Set<string>();
    const jurisdictions = new Set<string>();
    const organizationalUnits = new Set<string>();
    const processes = new Set<string>();
    const owners = new Set<string>();
    for (const r of rules) {
      effects.add(r.effect.type);
      if (r.rule_type) ruleTypes.add(r.rule_type);
      if (r.category) categories.add(r.category);
      r.scope.jurisdictions.forEach((j) => jurisdictions.add(j));
      r.scope.organizational_units.forEach((u) => organizationalUnits.add(u));
      r.scope.processes.forEach((p) => processes.add(p));
      if (r.authority.owner) owners.add(r.authority.owner);
    }
    const sortArr = (s: Set<string>) => [...s].sort((a, b) => a.localeCompare(b));
    return {
      effects: sortArr(effects),
      ruleTypes: sortArr(ruleTypes),
      categories: sortArr(categories),
      jurisdictions: sortArr(jurisdictions),
      organizationalUnits: sortArr(organizationalUnits),
      processes: sortArr(processes),
      owners: sortArr(owners),
    };
  }, [rules]);

  const selectedVersion = versions.find((v) => v.id === versionId);
  // Looked up from the full unfiltered `rules` (not `sorted`) so narrowing the search/filters
  // never blanks the inspector out from under a rule the user is actively reading.
  const selectedRule = useMemo(() => rules.find((r) => r.rule_id === selectedRuleId) ?? null, [rules, selectedRuleId]);
  const canRevise = !!selectedVersion?.is_active;

  const handleToggleGroup = (key: string) => {
    setCollapsedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const handleSelectRule = (rule: CanonicalRule) => {
    setSelectedRuleId(rule.rule_id);
    setMobileInspectorOpen(true);
  };

  const handleViewHistory = (rule: CanonicalRule) => {
    setSelectedRuleId(rule.rule_id);
    setInspectorTab("history");
    setMobileInspectorOpen(true);
  };

  const emptyMessage =
    rules.length === 0
      ? "This version has no rules yet."
      : focusedFamily
        ? "No policies in this family match the current search and filters."
        : "No policies match the current search and filters.";

  const inspector = (
    <PolicyInspector
      rule={selectedRule}
      allRules={rules}
      aggregateLimits={aggregateLimits}
      publishedVersion={selectedVersion ?? null}
      versions={versions}
      policySetKey={policySetKey}
      activeTabKey={inspectorTab}
      onTabChange={setInspectorTab}
      onRevise={canRevise ? setReviseTarget : undefined}
      onSelectRule={handleSelectRule}
      onClose={!isDesktop ? () => setMobileInspectorOpen(false) : undefined}
    />
  );

  return (
    <>
      <div className="page-header-row">
        <Title level={3} style={{ margin: 0 }}>
          Policies
        </Title>
        <Space wrap>
          <Select
            value={versionId || undefined}
            onChange={setVersionId}
            style={{ minWidth: 170 }}
            placeholder="Select version"
            options={versions.map((v) => ({
              value: v.id,
              label: `v${v.version_number}${v.is_active ? " (active)" : ""}`,
            }))}
          />
        </Space>
      </div>
      <Paragraph type="secondary">
        Approved policy rules for this project — search, filter, and group them, then select one to see its full
        detail. To change what appears here, go to the <strong>Review</strong> tab: draft or AI-extract rules,
        approve them, then publish a new version.
      </Paragraph>

      {error && <Alert type="error" showIcon message={error} />}

      {versions.length === 0 ? (
        <Card>
          <Empty
            description={
              <Space direction="vertical" size={4}>
                <Text>No published policies yet for this project.</Text>
                <Text type="secondary">
                  Upload a document in <strong>Documents</strong>, extract rules with AI or add them by hand, then
                  approve and publish them in <strong>Review</strong> — they'll show up here, organized by type.
                </Text>
                {onNavigate && (
                  <Space>
                    <a onClick={() => onNavigate("documents")}>Go to Documents →</a>
                    <a onClick={() => onNavigate("review")}>Go to Review →</a>
                  </Space>
                )}
              </Space>
            }
          />
        </Card>
      ) : (
        <>
          {selectedVersion && (
            <Space size={10} wrap>
              <Tag color="purple">v{selectedVersion.version_number}</Tag>
              {selectedVersion.is_active && <Tag color="green">ACTIVE</Tag>}
              <Text type="secondary">
                effective {selectedVersion.effective_from}
                {selectedVersion.effective_to ? ` → ${selectedVersion.effective_to}` : ""}
              </Text>
            </Space>
          )}

          {loading ? (
            <Text type="secondary">Loading…</Text>
          ) : (
            <div className={`policies-workspace policies-workspace--${isDesktop ? "desktop" : "narrow"}`}>
              <div className="policies-workspace-list">
                <PoliciesToolbar
                  search={search}
                  onSearchChange={setSearch}
                  groupBy={groupBy}
                  onGroupByChange={setGroupBy}
                  sortBy={sortBy}
                  onSortByChange={setSortBy}
                  density={density}
                  onDensityChange={setDensity}
                  filters={filters}
                  onFiltersChange={setFilters}
                  facetOptions={facetOptions}
                  resultCount={sorted.length}
                  totalCount={rules.length}
                  families={familyChips}
                  focusedFamily={focusedFamily}
                  onFocusFamily={setFocusedFamily}
                />
                <PolicyList
                  groups={policyGroups}
                  showGroupHeaders={groupBy !== "none"}
                  collapsedGroups={collapsedGroups}
                  onToggleGroup={handleToggleGroup}
                  selectedRuleId={selectedRule?.rule_id}
                  density={density}
                  searchQuery={search}
                  onSelectRule={handleSelectRule}
                  onReviseRule={canRevise ? setReviseTarget : undefined}
                  onViewHistory={handleViewHistory}
                  emptyMessage={emptyMessage}
                  clusterMap={clusterMap}
                  focusedFamily={focusedFamily}
                  onFocusFamily={setFocusedFamily}
                />
              </div>
              {isDesktop && <div className="policies-workspace-inspector">{inspector}</div>}
            </div>
          )}
        </>
      )}

      {!isDesktop && (
        <Drawer
          open={mobileInspectorOpen && !!selectedRule}
          onClose={() => setMobileInspectorOpen(false)}
          placement="right"
          width="100%"
          closable={false}
          styles={{ body: { padding: 0 } }}
          className="policy-inspector-drawer"
        >
          {inspector}
        </Drawer>
      )}

      {reviseTarget && (
        <EditRuleModal
          mode="revise"
          policySetKey={policySetKey}
          sourceRule={reviseTarget}
          allRules={rules}
          onClose={() => setReviseTarget(null)}
          onApplied={() => {
            message.success(
              `Revision drafted for ${reviseTarget.rule_id} — find it in the Review tab to approve and publish.`
            );
            onNavigate?.("review");
          }}
        />
      )}
    </>
  );
}
