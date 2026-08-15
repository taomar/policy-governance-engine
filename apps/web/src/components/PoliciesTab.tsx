import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Drawer,
  Empty,
  Grid,
  Pagination,
  Segmented,
  Select,
  Space,
  Tag,
  Typography,
  message,
} from "antd";
import { DownloadOutlined, FileSearchOutlined, LayoutOutlined, UnorderedListOutlined } from "@ant-design/icons";
import {
  api,
  downloadBlob,
  PolicyPlatformApiError,
  type AggregateLimit,
  type ApprovedPolicyVersion,
  type AssembledPolicy,
  type CanonicalRule,
  type PolicyTestListItem,
  policyTestApi,
} from "../api";
import { EditRuleModal } from "./EditRuleModal";
import { buildVariationClusters, clusterColor, clusterIdentity, clusterLabel, type RuleVariationGroup } from "../ruleDisplay";
import { PolicyInspector } from "./PolicyInspector";
import { PublishedPolicyCard } from "./PublishedPolicyCard";
import type { PolicySightingView } from "./policyTabPanes";
import { RuleCard } from "./RuleCard";
import { PublishedRecordActions } from "./PublishedRecordActions";
import {
  buildPublishedPolicyCards,
  listProvisionHistory,
  listVersionPolicies,
  publishedCardsAnsweringNarrowing,
  unplacedPublishedRules,
} from "../publishedPolicyCards";
import {
  PoliciesToolbar,
  EMPTY_POLICY_FILTERS,
  type PolicyFacetOptions,
  type PolicyFilters,
} from "./PoliciesToolbar";

const { Title, Text } = Typography;

type PoliciesWorkspaceMode = "list" | "split" | "detail";

/** How many policies are drawn at once. A whole policy is a much taller thing
 *  than a row, so the list is paged rather than virtualized — the same choice
 *  the review queue makes, and for the same reason: a card's height depends on
 *  how much the document said, which a windowing calculation cannot know in
 *  advance without measuring every card first. */
const PAGE_SIZE = 20;

interface PoliciesTabProps {
  policySetKey: string;
  onNavigate?: (page: string) => void;
}

/**
 * Read-oriented view of a project's *published* policies. A published version is a sealed
 * snapshot, so nothing here decides anything: no approve, no reject, no edit, no drafting.
 * What it does offer is the same reading the review queue offers, because a policy does not
 * change shape when it is approved — the document's own sections, each holding all its rules,
 * with the passage they were read from beside them.
 *
 * It used to list rules individually, grouped by the kind of rule each one was. That is a
 * label this system assigns rather than a structure the document has, and it broke every
 * multi-rule policy into pieces filed under headings the source never wrote. Grouping is now
 * by the document's own provisions, which the publish step already records on each rule.
 *
 * Defaults to the active published version; older versions can be selected to see how
 * policies looked at an earlier point in time.
 */
export function PoliciesTab({ policySetKey, onNavigate }: PoliciesTabProps) {
  const screens = Grid.useBreakpoint();
  const isDesktop = !!screens.lg;

  const [versions, setVersions] = useState<ApprovedPolicyVersion[]>([]);
  const [versionId, setVersionId] = useState<string>("");
  const [rules, setRules] = useState<CanonicalRule[]>([]);
  const [policies, setPolicies] = useState<AssembledPolicy[]>([]);
  const [aggregateLimits, setAggregateLimits] = useState<AggregateLimit[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [search, setSearch] = useState("");
  const [filters, setFilters] = useState<PolicyFilters>(EMPTY_POLICY_FILTERS);
  const [page, setPage] = useState(1);
  /** When set, the list is narrowed to a single variation family (by
   * `clusterIdentity`) — the "show me only these related rules" affordance,
   * since family members are otherwise scattered across the document. */
  const [focusedFamily, setFocusedFamily] = useState<string | null>(null);

  const [selectedRuleId, setSelectedRuleId] = useState<string | null>(null);
  /** The rule whose detail is open inside its policy. Distinct from the
   *  selection, which drives the inspector: a reader can be looking at one
   *  rule in place while the panel still shows the one they arrived on. */
  const [expandedRuleId, setExpandedRuleId] = useState<string | null>(null);
  const [inspectorTab, setInspectorTab] = useState("overview");
  const [mobileInspectorOpen, setMobileInspectorOpen] = useState(false);
  const [reviseTarget, setReviseTarget] = useState<CanonicalRule | null>(null);
  const [workspaceMode, setWorkspaceMode] = useState<PoliciesWorkspaceMode>("split");
  const [inspectorFullscreen, setInspectorFullscreen] = useState(false);
  const [selectedExportIds, setSelectedExportIds] = useState<Set<string>>(new Set());
  /** The set's tests, loaded once for the page so every policy's Tests tab
   *  reads the same answer. `null` while unknown — a failed load must not read
   *  as "this set has no tests", which is a claim about coverage. */
  const [tests, setTests] = useState<PolicyTestListItem[] | null>(null);
  const [testsLoading, setTestsLoading] = useState(false);
  /** One policy's sightings, kept by provision key and fetched when its History
   *  tab is first opened. Keyed rather than held singly because several cards
   *  are on the page at once and each is a different policy. */
  const [historyByKey, setHistoryByKey] = useState<Record<string, PolicySightingView[]>>({});
  const [historyLoadingKeys, setHistoryLoadingKeys] = useState<ReadonlySet<string>>(new Set());

  const requestHistory = useCallback(
    (provisionKey: string) => {
      if (!policySetKey || !provisionKey) return;
      setHistoryLoadingKeys((current) => {
        if (current.has(provisionKey)) return current;
        const next = new Set(current);
        next.add(provisionKey);
        return next;
      });
      listProvisionHistory(policySetKey, provisionKey)
        .then((sightings) => {
          setHistoryByKey((current) => ({ ...current, [provisionKey]: sightings }));
        })
        .catch(() => {
          // Left absent rather than stored as an empty list. The pane says
          // "not loaded" for absent and "no other version was found" for empty,
          // and a failed request establishes neither.
        })
        .finally(() => {
          setHistoryLoadingKeys((current) => {
            if (!current.has(provisionKey)) return current;
            const next = new Set(current);
            next.delete(provisionKey);
            return next;
          });
        });
    },
    [policySetKey],
  );

  useEffect(() => {
    if (!policySetKey) {
      setTests(null);
      return;
    }
    let cancelled = false;
    setTestsLoading(true);
    policyTestApi
      .list(policySetKey)
      .then((rows) => {
        if (!cancelled) setTests(rows);
      })
      .catch(() => {
        if (!cancelled) setTests(null);
      })
      .finally(() => {
        if (!cancelled) setTestsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [policySetKey]);

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
      setPolicies([]);
      setAggregateLimits([]);
      return;
    }
    setLoading(true);
    Promise.all([
      api.getVersionRules(policySetKey, versionId),
      api.getVersionAggregateLimits(policySetKey, versionId),
      // A policy's own boundaries are recorded at publish time, so this is a
      // read of what the version already knows rather than anything inferred
      // here. It is fetched separately so a failure to group still leaves the
      // rules readable rather than blanking the page.
      listVersionPolicies(policySetKey, versionId).catch(() => [] as AssembledPolicy[]),
    ])
      .then(([rs, aggs, ps]) => {
        setRules(rs);
        setAggregateLimits(aggs);
        setPolicies(ps);
      })
      .catch((e) => setError(e instanceof PolicyPlatformApiError ? e.detail : String(e)))
      .finally(() => setLoading(false));
  }, [policySetKey, versionId]);

  useEffect(() => {
    setSelectedExportIds(new Set());
  }, [versionId]);

  // How far the review pipeline has actually got. Used only to make the empty
  // state truthful: this tab reads *published* versions, and approving a
  // candidate is a review decision that deliberately does not publish it.
  // Without this the tab told a user who had already extracted and approved
  // rules to go extract and approve rules — which reads as "your approvals did
  // nothing" and hides the one action that would actually help.
  const [pipeline, setPipeline] = useState<{ approved: number; pending: number } | null>(null);

  useEffect(() => {
    // Only needed while there is nothing published; once a version exists the
    // list itself is the answer.
    if (versions.length > 0) return;
    let cancelled = false;
    Promise.all([
      api.listCandidateRules(policySetKey, "approved"),
      api.listCandidateRules(policySetKey, "candidate"),
    ])
      .then(([approved, pending]) => {
        if (!cancelled) setPipeline({ approved: approved.length, pending: pending.length });
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [policySetKey, versions.length]);

  // Paging is over a list whose contents and order change with the version and
  // with every narrowing, so a page number held across either would land the
  // reader somewhere they did not ask to be — often past the end.
  useEffect(() => {
    setPage(1);
  }, [versionId, search, filters, focusedFamily]);

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

  /** The rules that answer the current narrowing, in the order the version
   *  serves them. Not re-sorted: a policy's rules are read in the order the
   *  document states them, and reordering them by an attribute would take the
   *  one arrangement the source actually chose and replace it with one it
   *  didn't. */
  const shownRules = filtered;

  /** Every policy this version publishes, whole.
   *
   *  Built from all of the version's rules, before any narrowing runs, so a
   *  card always holds every rule its policy states. Building them from the
   *  narrowed set instead produced cards that looked like whole policies and
   *  were not: a reader who searched for one term got a policy showing three
   *  of its nine rules with the other six silently absent, and nothing on
   *  screen distinguishes that from a policy that only has three. */
  const allCards = useMemo(
    () => buildPublishedPolicyCards(policies, rules),
    [policies, rules],
  );

  const matchedRuleIds = useMemo(
    () => new Set(shownRules.map((rule) => rule.rule_id)),
    [shownRules],
  );

  /** The policies the narrowing answers, each still whole.
   *
   *  A search selects policies; it never subsets one. This is the same rule the
   *  review queue follows, and it has to be the same rule, because the two
   *  surfaces are meant to read alike and a fragment on one of them is a
   *  different claim about the document than a whole policy on the other. */
  const cards = useMemo(
    () => publishedCardsAnsweringNarrowing(allCards, matchedRuleIds),
    [allCards, matchedRuleIds],
  );

  /** Rules the version serves that no policy claims — always rendered, below
   *  the policies, so a grouping gap loses a rule from its policy but never
   *  from the page. */
  const unplaced = useMemo(() => unplacedPublishedRules(policies, shownRules), [policies, shownRules]);

  const pagedCards = useMemo(
    () => cards.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE),
    [cards, page]
  );

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

  const handleSelectRule = (rule: CanonicalRule) => {
    setSelectedRuleId(rule.rule_id);
    if (isDesktop) {
      // Selecting a record while scanning in list-only mode is an explicit
      // request to inspect it; restore the split without forcing full focus.
      if (workspaceMode === "list") setWorkspaceMode("split");
    } else {
      setMobileInspectorOpen(true);
    }
  };

  const handleViewHistory = (rule: CanonicalRule) => {
    setSelectedRuleId(rule.rule_id);
    setInspectorTab("history");
    if (isDesktop) {
      if (workspaceMode === "list") setWorkspaceMode("split");
    } else {
      setMobileInspectorOpen(true);
    }
  };

  const changeWorkspaceMode = (mode: PoliciesWorkspaceMode) => {
    setInspectorFullscreen(false);
    setWorkspaceMode(mode);
  };

  const hideInspector = () => {
    setInspectorFullscreen(false);
    setWorkspaceMode("list");
  };

  const toggleExportSelection = (ruleIds: readonly string[]) => {
    setSelectedExportIds((current) => {
      const next = new Set(current);
      const allSelected = ruleIds.length > 0 && ruleIds.every((id) => next.has(id));
      for (const id of ruleIds) {
        if (allSelected) next.delete(id);
        else next.add(id);
      }
      return next;
    });
  };

  const selectAllShownForExport = () => {
    toggleExportSelection(shownRules.map((rule) => rule.rule_id));
  };

  const downloadJsonl = (scope: "selected" | "all") => {
    const exportRules =
      scope === "all" ? rules : rules.filter((rule) => selectedExportIds.has(rule.rule_id));
    if (exportRules.length === 0) {
      message.warning("Select at least one policy to export.");
      return;
    }
    const jsonl = exportRules.map((rule) => JSON.stringify(rule)).join("\n") + "\n";
    const filename = `${policySetKey}-v${selectedVersion?.version_number ?? "unknown"}-${scope}-policies.jsonl`;
    downloadBlob(new Blob([jsonl], { type: "application/x-ndjson;charset=utf-8" }), filename);
    message.success(`${exportRules.length} complete polic${exportRules.length === 1 ? "y" : "ies"} exported to ${filename}.`);
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
      onHide={isDesktop ? hideInspector : undefined}
      onToggleFullscreen={isDesktop ? () => setInspectorFullscreen((value) => !value) : undefined}
      isFullscreen={inspectorFullscreen}
    />
  );

  return (
    <>
      <div className="page-header-row policies-page-header">
        <div>
          <Title level={3}>Published policies</Title>
          <Text type="secondary">Select a read-only decision record to inspect its logic, scope, source, and history.</Text>
        </div>
        <Space wrap className="policies-page-actions">
          {isDesktop && versions.length > 0 && (
            <Segmented
              className="policies-view-switcher"
              value={workspaceMode}
              onChange={(value) => changeWorkspaceMode(value as PoliciesWorkspaceMode)}
              aria-label="Policy workspace layout"
              options={[
                {
                  value: "list",
                  label: (
                    <span className="policies-view-option">
                      <UnorderedListOutlined /> List
                    </span>
                  ),
                },
                {
                  value: "split",
                  label: (
                    <span className="policies-view-option">
                      <LayoutOutlined /> Split
                    </span>
                  ),
                },
                {
                  value: "detail",
                  label: (
                    <span className="policies-view-option">
                      <FileSearchOutlined /> Detail
                    </span>
                  ),
                },
              ]}
            />
          )}
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

      {error && <Alert type="error" showIcon message={error} />}

      {versions.length === 0 ? (
        <Card>
          {pipeline && pipeline.approved > 0 ? (
            // The user's approvals landed; only the publish step is missing.
            // Say exactly that, because "no policies yet" is actively
            // misleading when 7 rules are sitting approved and ready.
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description={
                <Space direction="vertical" size={8} style={{ maxWidth: 560 }}>
                  <Text strong>
                    {pipeline.approved} approved rule{pipeline.approved === 1 ? " is" : "s are"} waiting to be
                    published.
                  </Text>
                  <Text type="secondary">
                    Approving a rule records your review decision. It does not change the live policy — this tab shows
                    only <strong>published versions</strong>, which are immutable, numbered snapshots. Publish a
                    version in <strong>Review</strong> to turn your {pipeline.approved} approved rule
                    {pipeline.approved === 1 ? "" : "s"} into v1 and it will appear here.
                  </Text>
                  {pipeline.pending > 0 && (
                    <Text type="secondary">
                      {pipeline.pending} other rule{pipeline.pending === 1 ? "" : "s"} still awaiting review. Anything
                      you have not approved is left out of the published version.
                    </Text>
                  )}
                  {onNavigate && (
                    <Button type="primary" onClick={() => onNavigate("review")}>
                      Go to Review to publish →
                    </Button>
                  )}
                </Space>
              }
            />
          ) : (
            <Empty
              description={
                <Space direction="vertical" size={4}>
                  <Text>No published policies yet for this project.</Text>
                  <Text type="secondary">
                    {pipeline && pipeline.pending > 0 ? (
                      <>
                        {pipeline.pending} candidate rule{pipeline.pending === 1 ? "" : "s"} extracted and awaiting
                        review. Approve the ones you want in <strong>Review</strong>, then publish a version — they'll
                        show up here, organized by type.
                      </>
                    ) : (
                      <>
                        Upload a document in <strong>Documents</strong>, extract rules with AI or add them by hand,
                        then approve and publish them in <strong>Review</strong> — they'll show up here, organized by
                        type.
                      </>
                    )}
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
          )}
        </Card>
      ) : (
        <>
          {selectedVersion && (
            <Space size={10} wrap className="policy-version-strip">
              <Tag color="purple">v{selectedVersion.version_number}</Tag>
              {selectedVersion.is_active && <Tag color="green">ACTIVE</Tag>}
              <Text strong>{rules.length} rules</Text>
              <Text type="secondary">
                effective {selectedVersion.effective_from}
                {selectedVersion.effective_to ? ` → ${selectedVersion.effective_to}` : ""}
              </Text>
            </Space>
          )}

          {loading ? (
            <Text type="secondary">Loading…</Text>
          ) : (
            <div
              className={`policies-workspace policies-workspace--${isDesktop ? "desktop" : "narrow"}${
                isDesktop ? ` policies-workspace--${workspaceMode}` : ""
              }`}
            >
              {(!isDesktop || workspaceMode !== "detail") && <div className="policies-workspace-list">
                <PoliciesToolbar
                  search={search}
                  onSearchChange={setSearch}
                  filters={filters}
                  onFiltersChange={setFilters}
                  facetOptions={facetOptions}
                  policyCount={cards.length}
                  resultCount={shownRules.length}
                  totalCount={rules.length}
                  families={familyChips}
                  focusedFamily={focusedFamily}
                  onFocusFamily={setFocusedFamily}
                />
                <div className="policy-export-bar">
                  <Checkbox
                    checked={shownRules.length > 0 && shownRules.every((rule) => selectedExportIds.has(rule.rule_id))}
                    indeterminate={
                      shownRules.some((rule) => selectedExportIds.has(rule.rule_id)) &&
                      !shownRules.every((rule) => selectedExportIds.has(rule.rule_id))
                    }
                    onChange={selectAllShownForExport}
                  >
                    Select all {shownRules.length} shown
                  </Checkbox>
                  <span className="policy-export-count">{selectedExportIds.size} selected</span>
                  <span className="policy-export-spacer" />
                  <Button
                    size="small"
                    icon={<DownloadOutlined />}
                    disabled={selectedExportIds.size === 0}
                    onClick={() => downloadJsonl("selected")}
                  >
                    Export selected JSONL
                  </Button>
                  <Button size="small" icon={<DownloadOutlined />} onClick={() => downloadJsonl("all")}>
                    Export all {rules.length} JSONL
                  </Button>
                </div>
                <div className="published-policy-list" data-testid="published-policy-list">
                  {cards.length === 0 && unplaced.length === 0 ? (
                    <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={emptyMessage} />
                  ) : (
                    <>
                      {pagedCards.map((card) => {
                        const ids = card.rules.map((entry) => entry.rule_id);
                        const selectedCount = ids.filter((id) => selectedExportIds.has(id)).length;
                        return (
                          <PublishedPolicyCard
                            key={card.policy.key}
                            card={card}
                            open={ids.some((id) => id === selectedRuleId)}
                            selectedForExport={ids.length > 0 && selectedCount === ids.length}
                            indeterminateForExport={selectedCount > 0 && selectedCount < ids.length}
                            aggregateLimits={aggregateLimits}
                            expandedRuleId={expandedRuleId}
                            onToggleExportSelection={() => toggleExportSelection(ids)}
                            onOpen={() => {
                              const first = card.rules[0];
                              if (first) handleSelectRule(first.rule);
                            }}
                            onSelectRule={handleSelectRule}
                            onToggleRule={(rule) =>
                              setExpandedRuleId((prev) => (prev === rule.rule_id ? null : rule.rule_id))
                            }
                            onRevise={canRevise ? setReviseTarget : undefined}
                            onViewHistory={handleViewHistory}
                            tests={tests}
                            testsLoading={testsLoading}
                            history={historyByKey[card.policy.key] ?? null}
                            historyLoading={historyLoadingKeys.has(card.policy.key)}
                            onRequestHistory={requestHistory}
                          />
                        );
                      })}

                      {cards.length > PAGE_SIZE && (
                        <div className="candidate-pagination">
                          <Pagination
                            current={page}
                            pageSize={PAGE_SIZE}
                            total={cards.length}
                            onChange={setPage}
                            showSizeChanger={false}
                            showTotal={(total, range) =>
                              `${range[0]}–${range[1]} of ${total} polic${total === 1 ? "y" : "ies"}`
                            }
                          />
                        </div>
                      )}

                      {unplaced.length > 0 && (
                        <section className="published-policy-unplaced" data-testid="published-unplaced">
                          <Text type="secondary">
                            {/* A rule the version serves but no policy claims is a
                                gap in the grouping, not a reason to drop it. It is
                                shown on its own and labelled as such. */}
                            {unplaced.length === 1
                              ? "1 rule of this version is not recorded against a section of its source document, so it is shown on its own."
                              : `${unplaced.length} rules of this version are not recorded against a section of their source document, so they are shown on their own.`}
                          </Text>
                          {unplaced.map((rule) => (
                            <RuleCard
                              key={rule.rule_id}
                              rule={rule}
                              hideNotes
                              aggregateLimits={aggregateLimits}
                              onRevise={canRevise ? setReviseTarget : undefined}
                              headerActions={
                                <PublishedRecordActions
                                  rule={rule}
                                  onRevise={canRevise ? setReviseTarget : undefined}
                                  onViewHistory={handleViewHistory}
                                />
                              }
                            />
                          ))}
                        </section>
                      )}
                    </>
                  )}
                </div>
              </div>}
              {isDesktop && workspaceMode !== "list" && (
                <>
                  {inspectorFullscreen && (
                    <button
                      type="button"
                      className="policy-inspector-backdrop"
                      onClick={() => setInspectorFullscreen(false)}
                      aria-label="Restore policy workspace"
                    />
                  )}
                  <div
                    className={`policies-workspace-inspector${
                      inspectorFullscreen ? " policies-workspace-inspector--fullscreen" : ""
                    }`}
                  >
                    {inspector}
                  </div>
                </>
              )}
            </div>
          )}
        </>
      )}

      {!isDesktop && (
        <Drawer
          open={mobileInspectorOpen && !!selectedRule}
          onClose={() => setMobileInspectorOpen(false)}
          placement="right"
          size="100%"
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
