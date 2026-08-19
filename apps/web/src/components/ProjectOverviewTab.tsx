import { useEffect, useState, type ReactNode } from "react";
import { Alert, Button, Space, Tag, Typography } from "antd";
import {
  ArrowRightOutlined,
  CalendarOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  EditOutlined,
  FileTextOutlined,
  SafetyCertificateOutlined,
  SyncOutlined,
  WarningOutlined,
} from "@ant-design/icons";
import { api, PolicyPlatformApiError, type ApprovedPolicyVersion, type PolicyIndexBuildResult, type PolicyIndexState, type PolicySet } from "../api";
import { ActivityPanel } from "./ActivityPanel";
import { NotesPanel } from "./NotesPanel";
import { PolicySetSummaryPanel } from "./PolicySetSummaryPanel";
import { routeCell } from "../projectRegisterRow";
import { policyUnitCount, recordScaleLabel } from "../policyRecordFacts";

const { Text } = Typography;

export interface Stats {
  documentCount: number;
  activeVersion: ApprovedPolicyVersion | null;
  versionCount: number;
  pendingCandidateCount: number;
  approvedCandidateCount: number;
  /* The same two queues counted in the unit they are decided in. A policy is
   * what a reviewer approves and publishes; the candidates are its contents,
   * and one policy commonly holds several. Both are counted here, from the
   * records themselves, so neither number has to be inferred from the other. */
  pendingPolicyCount: number;
  approvedPolicyCount: number;
  /* Both routes are counted from what each rule actually carries. Neither is
   * derived by subtracting the other from the total: a rule recording no mode
   * belongs to neither, and folding it into a route would assert a
   * routing decision the data does not contain. See `projectRegisterRow`. */
  directRouteCount: number;
  readingRouteCount: number;
  liveRuleCount: number;
  sourceGroundedRuleCount: number;
}

/**
 * One node of the project's lifecycle flow.
 *
 * `key` and `nav` are deliberately separate. `key` is the node's own identity —
 * React reconciles the flow row by it, so two siblings must never share one, or a
 * re-render can drop one of the pair or let it inherit the other's state. `nav` is
 * where a click on the node goes. They differ because two distinct stages —
 * "awaiting review" and "approved, not yet live" — are both worked from the Review
 * tab, so they share a *destination* while remaining two separate steps a reviewer
 * needs counted apart. Overloading one field for both is what once gave two steps
 * the key "review"; `nav` carries the destination so `key` is free to be unique.
 */
export interface OverviewStep {
  key: string;
  nav: string;
  label: string;
  value: number | undefined;
  detail: string | undefined;
  icon: ReactNode;
  tone: string;
  attention?: boolean;
}

/**
 * The lifecycle a project moves through, as the row the overview draws: documents
 * in → candidates awaiting review → approved but not yet live → rules published.
 * Each step counts in policy units first (the unit a reviewer decides in), with the
 * rule tally underneath. Pure and exported so the sequence and its keys can be
 * asserted without rendering the tab.
 */
export function buildOverviewSteps(stats: Stats | null, pending: number): OverviewStep[] {
  return [
    {
      key: "documents",
      nav: "documents",
      label: "Documents uploaded",
      value: stats?.documentCount,
      detail: undefined,
      icon: <FileTextOutlined />,
      tone: "info",
    },
    {
      key: "awaiting-review",
      nav: "review",
      label: pending > 0 ? "Awaiting review" : "Nothing pending review",
      // Policies lead, because a policy is what a reviewer decides. The rule
      // count stays underneath it: it is what a policy is made of, and a
      // reviewer sizing the job wants both. Joined, never summed -- they count
      // different things.
      value: stats?.pendingPolicyCount,
      detail: stats ? recordScaleLabel(stats.pendingPolicyCount, pending) : undefined,
      icon: <ClockCircleOutlined />,
      tone: pending > 0 ? "attention" : "neutral",
      attention: pending > 0,
    },
    {
      key: "approved-not-live",
      nav: "review",
      label: "Approved, not yet live",
      value: stats?.approvedPolicyCount,
      detail: stats
        ? recordScaleLabel(stats.approvedPolicyCount, stats.approvedCandidateCount)
        : undefined,
      icon: <SafetyCertificateOutlined />,
      tone: stats?.approvedCandidateCount ? "brand" : "neutral",
      attention: (stats?.approvedCandidateCount ?? 0) > 0,
    },
    {
      key: "policies",
      nav: "policies",
      label: "Rules published (active)",
      value: stats?.activeVersion?.rule_count ?? 0,
      detail: undefined,
      icon: <CheckCircleOutlined />,
      tone: "success",
    },
  ];
}

export function policyIndexRepairable(state: PolicyIndexState): boolean {
  return state.freshness === "stale" && state.last_attempt !== "skipped";
}

export function describePolicyIndexState(state: PolicyIndexState): {
  title: string;
  detail: string;
  tone: "success" | "warning" | "error" | "info";
  statusLabel: string;
} {
  if (state.freshness === "nothing_to_index") {
    return {
      title: "There is nothing to index yet",
      detail: "This project has no active published policy package, so project-wide case search has no published policies to index.",
      tone: "info",
      statusLabel: "Nothing to index",
    };
  }
  if (state.last_attempt === "skipped") {
    return {
      title: "Policy search is not configured here",
      detail: "The last build was skipped because Search is not available on this server. This is a configuration state, not a broken project index.",
      tone: "info",
      statusLabel: "Search not configured",
    };
  }
  if (state.freshness === "current") {
    if (state.last_attempt === "failed") {
      return {
        title: "The current index is still usable",
        detail: `The last rebuild attempt failed, but the recorded index still matches the active published version and contains ${state.document_count} policy document${state.document_count === 1 ? "" : "s"}.`,
        tone: "success",
        statusLabel: "Current despite failed attempt",
      };
    }
    return {
      title: "The project-wide case index is up to date",
      detail: `Published v${state.indexed_version_number ?? state.active_version_number ?? "—"} is indexed with ${state.document_count} policy document${state.document_count === 1 ? "" : "s"}.`,
      tone: "success",
      statusLabel: "Current",
    };
  }
  if (state.freshness === "stale") {
    if (state.last_attempt === "never_attempted") {
      return {
        title: "The project-wide case index has never been built",
        detail: "Testing cases across this project will not work until the active published version is indexed.",
        tone: "warning",
        statusLabel: "Never built",
      };
    }
    if (state.last_attempt === "failed") {
      return {
        title: "The last index rebuild failed and the index is stale",
        detail: "Project-wide case testing will not use this index until a rebuild succeeds.",
        tone: "error",
        statusLabel: "Failed and stale",
      };
    }
    return {
      title: "The project-wide case index is stale",
      detail: `The active published version is v${state.active_version_number ?? "—"}, but the recorded index is for v${state.indexed_version_number ?? "—"}.`,
      tone: "warning",
      statusLabel: "Stale",
    };
  }
  return {
    title: "The recorded policy index state is unknown",
    detail: "The app could not derive whether the index matches the active published version from the recorded build state.",
    tone: "warning",
    statusLabel: "Unknown",
  };
}

function rebuildResultMessage(result: PolicyIndexBuildResult): { type: "success" | "info" | "error"; message: string; description: string } {
  if (result.state === "built") {
    return {
      type: "success",
      message: "Policy index rebuilt",
      description: `Indexed ${result.document_count} policy document${result.document_count === 1 ? "" : "s"} for v${result.version_number ?? "—"}. The state below has been refreshed from the server.`,
    };
  }
  if (result.state === "skipped") {
    return {
      type: "info",
      message: "Policy index rebuild was skipped",
      description: result.error ?? "Search is not configured on this server, so there is no index to rebuild.",
    };
  }
  return {
    type: "error",
    message: "Policy index rebuild failed",
    description: result.error ?? "The server recorded the failed attempt and the state below has been refreshed.",
  };
}

/**
 * Project landing tab — "what's the state of this project right now". Rather than a
 * generic stat-card grid, this renders the actual policy lifecycle (documents in →
 * candidates awaiting review → rules published) as one connected flow, so a non-expert
 * user sees where their project sits in the process and can jump straight to the tab
 * that moves it forward.
 */
export function ProjectOverviewTab({
  policySet,
  onNavigate,
  onEditProject,
}: {
  policySet: PolicySet;
  onNavigate: (page: string) => void;
  /** Opens the project's Edit modal (RACI/ownership fields live there) — omitted hides the "Configure" action. */
  onEditProject?: () => void;
}) {
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [policyIndexState, setPolicyIndexState] = useState<PolicyIndexState | null>(null);
  const [policyIndexError, setPolicyIndexError] = useState<string | null>(null);
  const [policyIndexLoading, setPolicyIndexLoading] = useState(false);
  const [rebuildingPolicyIndex, setRebuildingPolicyIndex] = useState(false);
  const [rebuildResult, setRebuildResult] = useState<PolicyIndexBuildResult | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setError(null);
      try {
        const [documents, versions, candidates] = await Promise.all([
          api.listDocuments(policySet.key),
          api.listPolicyVersions(policySet.key),
          api.listCandidateRules(policySet.key),
        ]);
        const activeVersion = versions.find((v) => v.is_active) ?? null;
        const activeRules = activeVersion
          ? await api.getVersionRules(policySet.key, activeVersion.id)
          : [];
        if (cancelled) return;
        const pendingCandidates = candidates.filter((candidate) =>
          ["candidate", "changes_requested"].includes(candidate.review_status),
        );
        const approvedCandidates = candidates.filter((candidate) => candidate.review_status === "approved");
        setStats({
          documentCount: documents.length,
          activeVersion,
          versionCount: versions.length,
          pendingCandidateCount: pendingCandidates.length,
          approvedCandidateCount: approvedCandidates.length,
          pendingPolicyCount: policyUnitCount(pendingCandidates),
          approvedPolicyCount: policyUnitCount(approvedCandidates),
          directRouteCount: activeRules.filter((rule) => rule.evaluation_mode === "deterministic").length,
          readingRouteCount: activeRules.filter((rule) => rule.evaluation_mode === "ai_ready").length,
          liveRuleCount: activeRules.length,
          sourceGroundedRuleCount: activeRules.filter((rule) => rule.evidence.length > 0).length,
        });
      } catch (e) {
        if (!cancelled) setError(e instanceof PolicyPlatformApiError ? e.detail : String(e));
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [policySet.key]);

  useEffect(() => {
    let cancelled = false;
    setPolicyIndexState(null);
    setPolicyIndexError(null);
    setRebuildResult(null);
    setPolicyIndexLoading(true);
    api
      .getPolicyIndexState(policySet.key)
      .then((state) => {
        if (!cancelled) setPolicyIndexState(state);
      })
      .catch((e) => {
        if (!cancelled) setPolicyIndexError(e instanceof PolicyPlatformApiError ? e.detail : String(e));
      })
      .finally(() => {
        if (!cancelled) setPolicyIndexLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [policySet.key]);

  const pending = stats?.pendingCandidateCount ?? 0;
  const raciEntries: { label: string; value: string; isDefault: boolean }[] = [
    { label: "Owning department", value: policySet.owner || "Not set", isDefault: !policySet.owner },
    {
      label: "Accountable owner",
      value: policySet.accountable_owner || "Not set",
      isDefault: !policySet.accountable_owner,
    },
    {
      label: "Delegate approver",
      value: policySet.delegate_approver || "Not set",
      isDefault: !policySet.delegate_approver,
    },
    {
      label: "Escalation contact",
      value: policySet.escalation_contact || "Not set",
      isDefault: !policySet.escalation_contact,
    },
  ];
  const governanceConfiguredCount = raciEntries.filter((entry) => !entry.isDefault).length;
  const missingGovernanceCount = raciEntries.length - governanceConfiguredCount;
  const liveRuleCount = stats?.activeVersion?.rule_count ?? 0;
  const sourceCoverage = liveRuleCount
    ? Math.round(((stats?.sourceGroundedRuleCount ?? 0) / liveRuleCount) * 100)
    : 0;
  // Routes stated in the same words as the dashboard tile and the register, from
  // the one module that owns that wording.
  const routeSummary = routeCell(
    stats?.liveRuleCount ?? 0,
    stats?.directRouteCount ?? 0,
    stats?.readingRouteCount ?? 0,
  );
  const steps = buildOverviewSteps(stats, pending);
  const policyIndexCopy = policyIndexState ? describePolicyIndexState(policyIndexState) : null;
  const policyIndexCanRebuild = policyIndexState ? policyIndexRepairable(policyIndexState) : false;
  const rebuildNotice = rebuildResult ? rebuildResultMessage(rebuildResult) : null;
  const refreshPolicyIndexState = async () => {
    const state = await api.getPolicyIndexState(policySet.key);
    setPolicyIndexState(state);
  };
  const handleRebuildPolicyIndex = async () => {
    setRebuildingPolicyIndex(true);
    setPolicyIndexError(null);
    setRebuildResult(null);
    try {
      const result = await api.rebuildPolicyIndex(policySet.key);
      setRebuildResult(result);
      await refreshPolicyIndexState();
    } catch (e) {
      setPolicyIndexError(e instanceof PolicyPlatformApiError ? e.detail : String(e));
    } finally {
      setRebuildingPolicyIndex(false);
    }
  };

  return (
    <>
      {error && <Alert type="error" showIcon message={error} style={{ marginBottom: 16 }} />}

      <div className="project-flow project-flow--overview">
        {steps.map((step, idx) => (
          <div key={step.key} style={{ display: "contents" }}>
            <div
              className={`project-flow-step${step.attention ? " project-flow-step-attn" : ""}`}
              onClick={() => onNavigate(step.nav)}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") onNavigate(step.nav);
              }}
            >
              <span className={`project-flow-icon project-flow-icon--${step.tone}`}>
                {step.icon}
              </span>
              <div>
                <div className="project-flow-value">{step.value ?? "…"}</div>
                <div className="project-flow-label">{step.label}</div>
                {step.detail && <div className="project-flow-detail">{step.detail}</div>}
              </div>
            </div>
            {idx < steps.length - 1 && (
              <div className="project-flow-connector">
                <ArrowRightOutlined />
              </div>
            )}
          </div>
        ))}
      </div>

      <div className="project-readiness-docket">
        <section className="project-readiness-section project-readiness-published">
          <header className="project-readiness-heading">
            <span className={`project-readiness-icon${stats?.activeVersion ? " is-live" : " is-warning"}`}>
              {stats?.activeVersion ? <CheckCircleOutlined /> : <WarningOutlined />}
            </span>
            <div>
              <Text strong>
                {stats?.activeVersion
                  ? `Published v${stats.activeVersion.version_number} is active`
                  : "No published policy package"}
              </Text>
              <Text type="secondary">
                {stats?.activeVersion
                  ? "Current enforceability and source-evidence coverage"
                  : "Review candidates and publish an immutable first version"}
              </Text>
            </div>
          </header>
          <div className="project-readiness-body">
            {stats?.activeVersion ? (
              <>
                <dl className="project-readiness-metrics">
                  <div>
                    <dt>Live rules</dt>
                    <dd>{liveRuleCount}</dd>
                  </div>
                  <div>
                    {/* Was `<dt>Deterministic</dt><dd>N</dd>` with the other
                        route derived by subtraction. A bare route name over a
                        numeral reads as a score — "Deterministic 0" is a nought
                        out of ten — and how a source states its own test is the
                        source's property, not a mark this system earns against
                        it. Both routes are counted independently and named as
                        routes. Same wording as the dashboard tile and the
                        register, from one place, so they cannot drift. */}
                    <dt>Decision routes</dt>
                    <dd>{routeSummary.headline}</dd>
                    <small>{routeSummary.detail}</small>
                  </div>
                  <div className={sourceCoverage === 100 ? "is-success" : "is-warning"}>
                    <dt>Source-grounded</dt>
                    <dd>{stats.sourceGroundedRuleCount}</dd>
                    <small>{sourceCoverage}% coverage</small>
                  </div>
                  <div>
                    <dt>Retained versions</dt>
                    <dd>{stats.versionCount}</dd>
                  </div>
                </dl>
                <div className="project-readiness-signals">
                  {/* Neutral, because it is a route rather than a shortfall.
                      This read "N policies require manual handling" under a
                      warning icon whenever fewer than half stated a
                      comparison — which is most documents, and which sent a
                      reader to fix rules that can never become arithmetic. */}
                  <div>
                    <CheckCircleOutlined />
                    <span>
                      <strong>
                        {/* Counted from what the rules record, not derived by
                            subtracting the other route from the total. The
                            subtraction filed every rule with no recorded mode
                            under one route name and stated a routing
                            decision the data does not carry. */}
                        {stats.readingRouteCount} rule
                        {stats.readingRouteCount === 1 ? " is" : "s are"} AI Ready
                      </strong>
                      <small>
                        The source states their test in words rather than as a comparison, so a
                        judge reads the record: the sentence, the facts it names, and the outcome.
                      </small>
                    </span>
                  </div>
                  <div className={sourceCoverage === 100 ? "is-success" : "is-warning"}>
                    {sourceCoverage === 100 ? <FileTextOutlined /> : <WarningOutlined />}
                    <span>
                      <strong>
                        {sourceCoverage === 100
                          ? "Every live rule is linked to source evidence"
                          : `${liveRuleCount - stats.sourceGroundedRuleCount} rules lack source evidence`}
                      </strong>
                      <small>Source links support audit, review, and challenge of the published decision.</small>
                    </span>
                  </div>
                </div>
                <footer className="project-readiness-meta">
                  <span>
                    <small>Effective window</small>
                    <strong>
                      {stats.activeVersion.effective_from}
                      {stats.activeVersion.effective_to ? ` → ${stats.activeVersion.effective_to}` : " → open-ended"}
                    </strong>
                  </span>
                  <span>
                    <small>Approved by</small>
                    <strong>{stats.activeVersion.approved_by}</strong>
                  </span>
                </footer>
                <div className="policy-index-readiness" data-testid="policy-index-readiness">
                  <div className="policy-index-readiness__header">
                    <span className={`project-readiness-icon${policyIndexCopy?.tone === "success" ? " is-live" : policyIndexCopy?.tone === "error" || policyIndexCopy?.tone === "warning" ? " is-warning" : ""}`}>
                      {policyIndexCopy?.tone === "success" ? <CheckCircleOutlined /> : <SyncOutlined />}
                    </span>
                    <div>
                      <Text strong>Project-wide case index</Text>
                      <Text type="secondary">Recorded build state, not a live Azure Search check</Text>
                    </div>
                    {policyIndexCanRebuild && (
                      <Button size="small" onClick={handleRebuildPolicyIndex} loading={rebuildingPolicyIndex}>
                        Rebuild policy index
                      </Button>
                    )}
                  </div>
                  {policyIndexLoading ? (
                    <Text type="secondary">Loading the recorded index state…</Text>
                  ) : policyIndexError ? (
                    <Alert type="error" showIcon message="Could not read the recorded policy index state" description={policyIndexError} />
                  ) : policyIndexState && policyIndexCopy ? (
                    <Space orientation="vertical" size={8} style={{ width: "100%" }}>
                      <Alert
                        type={policyIndexCopy.tone}
                        showIcon
                        message={policyIndexCopy.title}
                        description={
                          <Space orientation="vertical" size={4}>
                            <Text>{policyIndexCopy.detail}</Text>
                            {policyIndexState.error ? <Text type="secondary">{policyIndexState.error}</Text> : null}
                          </Space>
                        }
                      />
                      {rebuildNotice ? (
                        <Alert
                          type={rebuildNotice.type}
                          showIcon
                          message={rebuildNotice.message}
                          description={rebuildNotice.description}
                        />
                      ) : null}
                      <dl className="policy-index-readiness__facts">
                        <div>
                          <dt>Index state</dt>
                          <dd>{policyIndexCopy.statusLabel}</dd>
                        </div>
                        <div>
                          <dt>Active version</dt>
                          <dd>{policyIndexState.active_version_number ?? "—"}</dd>
                        </div>
                        <div>
                          <dt>Indexed version</dt>
                          <dd>{policyIndexState.indexed_version_number ?? "—"}</dd>
                        </div>
                        <div>
                          <dt>Indexed policies</dt>
                          <dd>{policyIndexState.document_count}</dd>
                        </div>
                      </dl>
                      <Text type="secondary" className="policy-index-readiness__source">
                        Source: {policyIndexState.source}; live probe: {policyIndexState.live_probe ? "yes" : "no"}.
                      </Text>
                    </Space>
                  ) : null}
                </div>
              </>
            ) : (
              <div className="project-state-empty">
                <Text strong>No published version yet</Text>
                <Text type="secondary">Review candidates and publish an immutable first version.</Text>
                <Space>
                  <a onClick={() => onNavigate("documents")}>Upload source →</a>
                  <a onClick={() => onNavigate("review")}>Open Review →</a>
                </Space>
              </div>
            )}
            {!stats?.activeVersion && (
              <div className="policy-index-readiness" data-testid="policy-index-readiness">
                <div className="policy-index-readiness__header">
                  <span className="project-readiness-icon">
                    <SyncOutlined />
                  </span>
                  <div>
                    <Text strong>Project-wide case index</Text>
                    <Text type="secondary">Recorded build state, not a live Azure Search check</Text>
                  </div>
                </div>
                {policyIndexLoading ? (
                  <Text type="secondary">Loading the recorded index state…</Text>
                ) : policyIndexError ? (
                  <Alert type="error" showIcon message="Could not read the recorded policy index state" description={policyIndexError} />
                ) : policyIndexState && policyIndexCopy ? (
                  <Alert type={policyIndexCopy.tone} showIcon message={policyIndexCopy.title} description={policyIndexCopy.detail} />
                ) : null}
              </div>
            )}
          </div>
        </section>

        <section className="project-readiness-section project-readiness-governance">
          <header className="project-readiness-heading">
            <span className={`project-readiness-icon${missingGovernanceCount > 0 ? " is-warning" : " is-live"}`}>
              {missingGovernanceCount > 0 ? <WarningOutlined /> : <SafetyCertificateOutlined />}
            </span>
            <div>
              <Text strong>Governance &amp; ownership</Text>
              <Text type="secondary">
                {governanceConfiguredCount} of {raciEntries.length} primary roles configured
              </Text>
            </div>
            {onEditProject && (
              <Button type="link" size="small" className="project-configure-link" icon={<EditOutlined />} onClick={onEditProject}>
                Configure roles <ArrowRightOutlined />
              </Button>
            )}
          </header>
          <div className="project-readiness-body">
            <div className="governance-role-register">
              {raciEntries.map((entry) => (
                <div key={entry.label} className={entry.isDefault ? "is-missing" : "is-configured"}>
                  <span className="governance-role-icon">
                    {entry.isDefault ? <WarningOutlined /> : <CheckCircleOutlined />}
                  </span>
                  <div>
                    <small>{entry.label}</small>
                    <strong>{entry.value}</strong>
                  </div>
                </div>
              ))}
            </div>
            {(policySet.consulted_parties.length > 0 || policySet.informed_parties.length > 0) && (
              <div className="governance-party-groups">
                {policySet.consulted_parties.length > 0 && (
                  <div>
                    <Text type="secondary" className="governance-label">Consulted (RACI "C")</Text>
                    <Space size={4} wrap>
                      {policySet.consulted_parties.map((party) => <Tag key={party}>{party}</Tag>)}
                    </Space>
                  </div>
                )}
                {policySet.informed_parties.length > 0 && (
                  <div>
                    <Text type="secondary" className="governance-label">Informed (RACI "I")</Text>
                    <Space size={4} wrap>
                      {policySet.informed_parties.map((party) => <Tag key={party}>{party}</Tag>)}
                    </Space>
                  </div>
                )}
              </div>
            )}
            {missingGovernanceCount > 0 && (
              <div className="governance-gap-note">
                <WarningOutlined />
                <span>
                  <strong>{missingGovernanceCount} ownership role{missingGovernanceCount === 1 ? "" : "s"} unassigned</strong>
                  <small>Assign accountable ownership and escalation before the next review cycle.</small>
                </span>
              </div>
            )}
            <footer className="project-governance-schedule">
              <span>
                <CalendarOutlined />
                <span>
                  <small>Last reviewed</small>
                  <strong>{policySet.last_reviewed_at ? new Date(policySet.last_reviewed_at).toLocaleDateString() : "Not recorded"}</strong>
                </span>
              </span>
              <span>
                <ClockCircleOutlined />
                <span>
                  <small>Next review due</small>
                  <strong className={policySet.is_review_overdue ? "is-overdue" : undefined}>
                    {policySet.review_due_date ?? "Not scheduled"}
                  </strong>
                </span>
              </span>
            </footer>
          </div>
        </section>
      </div>

      {stats?.activeVersion && <PolicySetSummaryPanel policySetKey={policySet.key} />}

      <div className="project-overview-lower-grid">
        <ActivityPanel policySetKey={policySet.key} limit={6} />
        <section className="project-overview-panel project-notes-panel">
          <div className="project-overview-panel__header">
            <div>
              <Text strong>Project notes</Text>
              <Text type="secondary">Append-only collaboration record</Text>
            </div>
          </div>
          <div className="project-overview-panel__body">
            <NotesPanel entityType="policy_set" entityId={policySet.key} compact />
          </div>
        </section>
      </div>
    </>
  );
}
