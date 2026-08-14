import { useEffect, useState } from "react";
import { Alert, Button, Space, Tag, Typography } from "antd";
import {
  ArrowRightOutlined,
  CalendarOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  EditOutlined,
  FileTextOutlined,
  SafetyCertificateOutlined,
  WarningOutlined,
} from "@ant-design/icons";
import { api, PolicyPlatformApiError, type ApprovedPolicyVersion, type PolicySet } from "../api";
import { ActivityPanel } from "./ActivityPanel";
import { NotesPanel } from "./NotesPanel";
import { PolicySetSummaryPanel } from "./PolicySetSummaryPanel";
import { routeCell } from "../projectRegisterRow";

const { Text } = Typography;

interface Stats {
  documentCount: number;
  activeVersion: ApprovedPolicyVersion | null;
  versionCount: number;
  pendingCandidateCount: number;
  approvedCandidateCount: number;
  /* Both routes are counted from what each rule actually carries. Neither is
   * derived by subtracting the other from the total: a rule recording no mode
   * belongs to neither, and folding it into "decided by reading" would assert a
   * routing decision the data does not contain. See `projectRegisterRow`. */
  directRouteCount: number;
  readingRouteCount: number;
  liveRuleCount: number;
  sourceGroundedRuleCount: number;
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
        setStats({
          documentCount: documents.length,
          activeVersion,
          versionCount: versions.length,
          pendingCandidateCount: candidates.filter((candidate) =>
            ["candidate", "changes_requested"].includes(candidate.review_status),
          ).length,
          approvedCandidateCount: candidates.filter((candidate) => candidate.review_status === "approved").length,
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
  const steps = [
    {
      key: "documents",
      label: "Documents uploaded",
      value: stats?.documentCount,
      icon: <FileTextOutlined />,
      tone: "info",
    },
    {
      key: "review",
      label: pending > 0 ? "Awaiting review" : "Nothing pending review",
      value: pending,
      icon: <ClockCircleOutlined />,
      tone: pending > 0 ? "attention" : "neutral",
      attention: pending > 0,
    },
    {
      key: "review",
      label: "Approved, not yet live",
      value: stats?.approvedCandidateCount ?? 0,
      icon: <SafetyCertificateOutlined />,
      tone: stats?.approvedCandidateCount ? "brand" : "neutral",
      attention: (stats?.approvedCandidateCount ?? 0) > 0,
    },
    {
      key: "policies",
      label: "Rules published (active)",
      value: stats?.activeVersion?.rule_count ?? 0,
      icon: <CheckCircleOutlined />,
      tone: "success",
    },
  ];

  return (
    <>
      {error && <Alert type="error" showIcon message={error} style={{ marginBottom: 16 }} />}

      <div className="project-flow project-flow--overview">
        {steps.map((step, idx) => (
          <div key={step.key} style={{ display: "contents" }}>
            <div
              className={`project-flow-step${step.attention ? " project-flow-step-attn" : ""}`}
              onClick={() => onNavigate(step.key)}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") onNavigate(step.key);
              }}
            >
              <span className={`project-flow-icon project-flow-icon--${step.tone}`}>
                {step.icon}
              </span>
              <div>
                <div className="project-flow-value">{step.value ?? "…"}</div>
                <div className="project-flow-label">{step.label}</div>
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
                            under "decided by reading" and stated a routing
                            decision the data does not carry. */}
                        {stats.readingRouteCount} polic
                        {stats.readingRouteCount === 1 ? "y is" : "ies are"} decided by reading
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
                          ? "Every live policy is linked to source evidence"
                          : `${liveRuleCount - stats.sourceGroundedRuleCount} policies lack source evidence`}
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
