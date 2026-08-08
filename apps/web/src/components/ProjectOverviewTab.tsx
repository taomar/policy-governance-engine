import { useEffect, useState } from "react";
import { Alert, Card, Space, Typography } from "antd";
import {
  ArrowRightOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  FileTextOutlined,
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
  pendingCandidateCount: number;
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
}: {
  policySet: PolicySet;
  onNavigate: (page: string) => void;
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
          api.listCandidateRules(policySet.key, "candidate"),
        ]);
        if (cancelled) return;
        setStats({
          documentCount: documents.length,
          activeVersion: versions.find((v) => v.is_active) ?? null,
          versionCount: versions.length,
          pendingCandidateCount: candidates.length,
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

      <div className="project-flow">
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

      {stats &&
        (stats.activeVersion ? (
          <Alert
            type="success"
            showIcon
            message={`Active version: v${stats.activeVersion.version_number}`}
            description={`Effective ${stats.activeVersion.effective_from}${
              stats.activeVersion.effective_to ? ` → ${stats.activeVersion.effective_to}` : ""
            } · approved by ${stats.activeVersion.approved_by}`}
            style={{ marginTop: 16 }}
          />
        ) : (
          <Alert
            type="warning"
            showIcon
            message="No published version yet"
            description={
              <Space direction="vertical" size={4}>
                <Text>This project has no published policies yet.</Text>
                <Space>
                  <a onClick={() => onNavigate("documents")}>Upload a document →</a>
                  <a onClick={() => onNavigate("review")}>Go to Review →</a>
                </Space>
              </Space>
            }
            style={{ marginTop: 16 }}
          />
        ))}

      {stats?.activeVersion && <PolicySetSummaryPanel policySetKey={policySet.key} />}

      <div style={{ marginTop: 16 }}>
        <ActivityPanel policySetKey={policySet.key} />
      </div>

      <Card title="Notes on this project" style={{ marginTop: 16 }}>
        <NotesPanel entityType="policy_set" entityId={policySet.key} compact />
      </Card>
    </>
  );
}
