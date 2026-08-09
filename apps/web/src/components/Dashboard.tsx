import { useEffect, useState } from "react";
import { Alert, Button, Tag, Typography } from "antd";
import {
  ArrowRightOutlined,
  CheckCircleOutlined,
  FileTextOutlined,
  FolderOutlined,
  PlayCircleOutlined,
  SafetyCertificateOutlined,
  ThunderboltOutlined,
  UploadOutlined,
} from "@ant-design/icons";
import { api, PolicyPlatformApiError } from "../api";
import { ACTOR_ROLE_LABELS, useActor, type ActorRole } from "../ActorContext";

const { Title, Text } = Typography;

interface Summary {
  policySetCount: number;
  activeVersionCount: number;
  pendingCandidateCount: number;
  documentCount: number;
}

interface ToolLink {
  label: string;
  description: string;
  icon: React.ReactNode;
  /** Navigate to a top-level page, OR set to "ask-ai" to open the Ask AI drawer directly. */
  page: string;
}

/**
 * Role-specific toolkits. Each role sees the actions most relevant to how they
 * actually work day-to-day, instead of one generic list for everyone. Review, Compare,
 * and Quality now live as tabs inside a project's workspace (not standalone pages), so
 * every toolkit action that touches them routes through "Open a project" first.
 *  - system_admin:    brings source documents in and stands up projects
 *  - policy_composer: drafts/reviews candidate rules, leans on Ask AI + Quality
 *  - policy_manager:  approves, publishes versions, and exports for downstream use
 */
const ROLE_TOOLKITS: Record<ActorRole, ToolLink[]> = {
  system_admin: [
    {
      label: "Upload source documents",
      description: "Bring in new HR/IT/finance policy PDFs or DOCX files for AI extraction.",
      icon: <UploadOutlined />,
      page: "document-inbox",
    },
    {
      label: "Create or organize projects",
      description: "Stand up a new project (key, owner, description) before importing rules.",
      icon: <FolderOutlined />,
      page: "projects",
    },
    {
      label: "Review extraction quality",
      description: "Open a project's Quality tab to check completeness/consistency on extracted rules.",
      icon: <SafetyCertificateOutlined />,
      page: "projects",
    },
  ],
  policy_composer: [
    {
      label: "Draft & review candidate rules",
      description: "Open a project's Review Queue: approve, reject, or ask the AI to suggest a rewrite.",
      icon: <CheckCircleOutlined />,
      page: "projects",
    },
    {
      label: "Ask AI about any policy",
      description: "Ground quotes, compare versions, or get a plain-language explanation — verbatim, always.",
      icon: <ThunderboltOutlined />,
      page: "ask-ai",
    },
    {
      label: "Check rule quality",
      description: "Spot ambiguous, low-confidence, or inconsistent rules before they're approved.",
      icon: <SafetyCertificateOutlined />,
      page: "projects",
    },
  ],
  policy_manager: [
    {
      label: "Publish approved versions",
      description: "Open a project's Review Queue to bundle approved rules into a new published version.",
      icon: <CheckCircleOutlined />,
      page: "projects",
    },
    {
      label: "Browse & export projects",
      description: "Inspect version history and export rules as JSON, JSONL, or CSV from any project.",
      icon: <FolderOutlined />,
      page: "projects",
    },
    {
      label: "Run evaluations",
      description: "Test how published rules apply against sample facts before rollout.",
      icon: <PlayCircleOutlined />,
      page: "evaluate",
    },
  ],
};

export function Dashboard({
  onNavigate,
  onOpenAskAi,
}: {
  onNavigate: (page: string) => void;
  onOpenAskAi?: () => void;
}) {
  const { actor } = useActor();
  const [summary, setSummary] = useState<Summary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const load = async () => {
      try {
        const policySets = await api.listPolicySets();
        let activeVersionCount = 0;
        let pendingCandidateCount = 0;
        for (const ps of policySets) {
          try {
            const versions = await api.listPolicyVersions(ps.key);
            activeVersionCount += versions.filter((v) => v.is_active).length;
            const candidates = await api.listCandidateRules(ps.key, "candidate");
            pendingCandidateCount += candidates.length;
          } catch {
            // ignore per-policy-set errors, keep aggregating others
          }
        }
        const documents = await api.listDocuments();
        setSummary({
          policySetCount: policySets.length,
          activeVersionCount,
          pendingCandidateCount,
          documentCount: documents.length,
        });
      } catch (e) {
        setError(e instanceof PolicyPlatformApiError ? e.detail : String(e));
      }
    };
    void load();
  }, []);

  const portfolio = [
    {
      key: "projects",
      value: summary?.policySetCount,
      label: "Projects",
      icon: <FolderOutlined />,
    },
    {
      key: "projects",
      value: summary?.activeVersionCount,
      label: "Active versions",
      icon: <CheckCircleOutlined />,
    },
    {
      key: "document-inbox",
      value: summary?.documentCount,
      label: "Source documents",
      icon: <FileTextOutlined />,
    },
  ];

  const toolkit = ROLE_TOOLKITS[actor.role];

  const goToTool = (page: string) => {
    if (page === "ask-ai") onOpenAskAi?.();
    else onNavigate(page);
  };

  const pending = summary?.pendingCandidateCount;

  return (
    <div className="dashboard-page">
      <header className="dashboard-page-header">
        <div>
          <Title level={3}>Policy operations</Title>
          <Text type="secondary">Move source-grounded rules from intake to an immutable published decision.</Text>
        </div>
        <Tag bordered={false} className="dashboard-role-tag">
          {ACTOR_ROLE_LABELS[actor.role]}
        </Tag>
      </header>

      {error && <Alert type="error" showIcon message={error} />}

      <div className="dashboard-ledger">
        <section className="dashboard-priority" aria-labelledby="review-work-title">
          <div className="dashboard-priority-copy">
            <div className="dashboard-priority-label">
              <FileTextOutlined />
              <Text strong>Review queue</Text>
            </div>
            <Title level={2} id="review-work-title">
              {pending === undefined
                ? "Loading review workload…"
                : pending > 0
                  ? `${pending} candidate rule${pending === 1 ? "" : "s"} need a decision`
                  : "Review queues are clear"}
            </Title>
            <Text type="secondary">
              Inspect the source, condition, outcome, and exceptions before approving anything for publication.
            </Text>
          </div>
          <Button type="primary" icon={<ArrowRightOutlined />} onClick={() => onNavigate("projects")}>
            Open project register
          </Button>
        </section>

        <section className="dashboard-portfolio" aria-label="Portfolio register">
          <div className="dashboard-panel-heading">
            <Text strong>Portfolio register</Text>
            <Text type="secondary">Current local instance</Text>
          </div>
          <div className="dashboard-metric-list" role="list">
            {portfolio.map((item) => (
              <button
                key={item.label}
                type="button"
                role="listitem"
                className="dashboard-metric-row"
                onClick={() => onNavigate(item.key)}
              >
                <span className="dashboard-metric-icon">{item.icon}</span>
                <span className="dashboard-metric-label">{item.label}</span>
                <strong className="dashboard-metric-value">{item.value ?? "—"}</strong>
                <ArrowRightOutlined className="dashboard-metric-arrow" />
              </button>
            ))}
          </div>
        </section>
      </div>

      <section className="dashboard-workflow" aria-labelledby="workflow-title">
        <div className="dashboard-section-heading">
          <div>
            <Title level={4} id="workflow-title">
              Your workflow
            </Title>
            <Text type="secondary">Actions matched to the role selected in the header.</Text>
          </div>
          <Text type="secondary">{ACTOR_ROLE_LABELS[actor.role]}</Text>
        </div>
        <div className="dashboard-workflow-list" role="list">
          {toolkit.map((tool) => (
            <button key={tool.label} type="button" role="listitem" onClick={() => goToTool(tool.page)}>
              <span className="dashboard-workflow-icon">{tool.icon}</span>
              <span className="dashboard-workflow-copy">
                <strong>{tool.label}</strong>
                <small>{tool.description}</small>
              </span>
              <ArrowRightOutlined className="dashboard-workflow-arrow" />
            </button>
          ))}
        </div>
      </section>
    </div>
  );
}
