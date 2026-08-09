import { useEffect, useState } from "react";
import { Alert, Button, Space, Tag, Typography } from "antd";
import {
  ArrowRightOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  EditOutlined,
  FileTextOutlined,
  SafetyCertificateOutlined,
} from "@ant-design/icons";
import { api, PolicyPlatformApiError, type ApprovedPolicyVersion, type PolicySet } from "../api";
import { ActivityPanel } from "./ActivityPanel";
import { NotesPanel } from "./NotesPanel";
import { PolicySetSummaryPanel } from "./PolicySetSummaryPanel";

const { Text } = Typography;

interface Stats {
  documentCount: number;
  activeVersion: ApprovedPolicyVersion | null;
  versionCount: number;
  candidateCount: number;
  pendingCandidateCount: number;
  approvedCandidateCount: number;
  rejectedCandidateCount: number;
  executableRuleCount: number;
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
          candidateCount: candidates.length,
          pendingCandidateCount: candidates.filter((candidate) =>
            ["candidate", "changes_requested"].includes(candidate.review_status),
          ).length,
          approvedCandidateCount: candidates.filter((candidate) => candidate.review_status === "approved").length,
          rejectedCandidateCount: candidates.filter((candidate) => candidate.review_status === "rejected").length,
          executableRuleCount: activeRules.filter((rule) => rule.machine_executable).length,
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
  const hasRaciConfigured =
    !!policySet.accountable_owner ||
    !!policySet.delegate_approver ||
    !!policySet.escalation_contact ||
    policySet.consulted_parties.length > 0 ||
    policySet.informed_parties.length > 0;
  const governanceConfiguredCount = raciEntries.filter((entry) => !entry.isDefault).length;
  const decisionProgress = stats?.candidateCount
    ? Math.round(((stats.candidateCount - stats.pendingCandidateCount) / stats.candidateCount) * 100)
    : 100;
  const steps = [
    {
      key: "documents",
      label: "Documents uploaded",
      value: stats?.documentCount,
      icon: <FileTextOutlined />,
      tone: "#2563eb",
    },
    {
      key: "review",
      label: pending > 0 ? "Awaiting review" : "Nothing pending review",
      value: pending,
      icon: <ClockCircleOutlined />,
      tone: pending > 0 ? "#d97706" : "#9ca3af",
      attention: pending > 0,
    },
    {
      key: "review",
      label: "Approved, not yet live",
      value: stats?.approvedCandidateCount ?? 0,
      icon: <SafetyCertificateOutlined />,
      tone: stats?.approvedCandidateCount ? "#5b4db1" : "#9ca3af",
      attention: (stats?.approvedCandidateCount ?? 0) > 0,
    },
    {
      key: "policies",
      label: "Rules published (active)",
      value: stats?.activeVersion?.rule_count ?? 0,
      icon: <CheckCircleOutlined />,
      tone: "#059669",
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
              <span className="project-flow-icon" style={{ background: `${step.tone}1a`, color: step.tone }}>
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

      <div className="project-overview-grid">
        <section className="project-overview-panel project-state-panel">
          <div className="project-overview-panel__header">
            <div>
              <Text strong>Published state</Text>
              <Text type="secondary">What is live and enforceable now</Text>
            </div>
            {stats?.activeVersion ? <Tag color="green">Active v{stats.activeVersion.version_number}</Tag> : <Tag color="gold">Not published</Tag>}
          </div>
          <div className="project-overview-panel__body">
            {stats?.activeVersion ? (
              <>
                <dl className="project-state-grid">
                  <div>
                    <dt>Live rules</dt>
                    <dd>{stats.activeVersion.rule_count}</dd>
                  </div>
                  <div>
                    <dt>Machine-executable</dt>
                    <dd>{stats.executableRuleCount}</dd>
                  </div>
                  <div>
                    <dt>Source-grounded</dt>
                    <dd>{stats.sourceGroundedRuleCount}</dd>
                  </div>
                  <div>
                    <dt>Published versions</dt>
                    <dd>{stats.versionCount}</dd>
                  </div>
                </dl>
                <div className="project-state-meta">
                  <span>
                    <Text type="secondary">Effective</Text>
                    <Text>
                      {stats.activeVersion.effective_from}
                      {stats.activeVersion.effective_to ? ` → ${stats.activeVersion.effective_to}` : " → open-ended"}
                    </Text>
                  </span>
                  <span>
                    <Text type="secondary">Approved by</Text>
                    <Text>{stats.activeVersion.approved_by}</Text>
                  </span>
                  <span>
                    <Text type="secondary">Review decisions</Text>
                    <Text>{decisionProgress}% complete</Text>
                  </span>
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
          </div>
        </section>

        <section className="project-overview-panel">
          <div className="project-overview-panel__header">
            <div>
              <Text strong>
                <SafetyCertificateOutlined /> Governance &amp; ownership
              </Text>
              <Text type="secondary">{governanceConfiguredCount} of {raciEntries.length} primary roles configured</Text>
            </div>
            {onEditProject && (
              <Button type="text" size="small" icon={<EditOutlined />} onClick={onEditProject}>
                Configure
              </Button>
            )}
          </div>
          <div className="project-overview-panel__body">
            <div className="governance-grid">
              {raciEntries.map((entry) => (
                <div key={entry.label} className="governance-item">
                  <Text type="secondary" className="governance-label">
                    {entry.label}
                  </Text>
                  <Text className={entry.isDefault ? "governance-value-default" : undefined}>{entry.value}</Text>
                </div>
              ))}
            </div>
            {(policySet.consulted_parties.length > 0 || policySet.informed_parties.length > 0) && (
              <Space direction="vertical" size={10} style={{ marginTop: 16 }}>
                {policySet.consulted_parties.length > 0 && (
                  <div>
                    <Text type="secondary" className="governance-label">
                      Consulted (RACI "C")
                    </Text>
                    <br />
                    <Space size={4} wrap style={{ marginTop: 4 }}>
                      {policySet.consulted_parties.map((p) => (
                        <Tag key={p} bordered={false} className="fact-tag">
                          {p}
                        </Tag>
                      ))}
                    </Space>
                  </div>
                )}
                {policySet.informed_parties.length > 0 && (
                  <div>
                    <Text type="secondary" className="governance-label">
                      Informed (RACI "I")
                    </Text>
                    <br />
                    <Space size={4} wrap style={{ marginTop: 4 }}>
                      {policySet.informed_parties.map((p) => (
                        <Tag key={p} bordered={false} className="fact-tag">
                          {p}
                        </Tag>
                      ))}
                    </Space>
                  </div>
                )}
              </Space>
            )}
            {!hasRaciConfigured && (
              <div className="governance-empty-note">
                <Text type="secondary">Add accountable ownership and escalation before the next review cycle.</Text>
              </div>
            )}
            <div className="project-review-schedule">
              <span>
                <Text type="secondary">Last reviewed</Text>
                <Text>{policySet.last_reviewed_at ? new Date(policySet.last_reviewed_at).toLocaleDateString() : "Not recorded"}</Text>
              </span>
              <span>
                <Text type="secondary">Next review due</Text>
                <Text type={policySet.is_review_overdue ? "danger" : undefined}>
                  {policySet.review_due_date ?? "Not scheduled"}
                </Text>
              </span>
            </div>
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
