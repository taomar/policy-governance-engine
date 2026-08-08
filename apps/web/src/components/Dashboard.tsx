import { useEffect, useState } from "react";
import { Alert, Button, Card, Col, Row, Space, Statistic, Tag, Typography } from "antd";
import {
  BulbOutlined,
  CheckCircleOutlined,
  FileTextOutlined,
  FolderOutlined,
  InboxOutlined,
  PlayCircleOutlined,
  SafetyCertificateOutlined,
  ThunderboltOutlined,
  UploadOutlined,
} from "@ant-design/icons";
import { api, PolicyPlatformApiError } from "../api";
import { ACTOR_ROLE_LABELS, useActor, type ActorRole } from "../ActorContext";

const { Title, Text, Paragraph } = Typography;

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

  const cards = [
    {
      key: "projects",
      value: summary?.policySetCount,
      label: "Projects",
      icon: <FolderOutlined />,
      color: "#7c3aed",
    },
    {
      key: "projects",
      value: summary?.activeVersionCount,
      label: "Active Versions",
      icon: <CheckCircleOutlined />,
      color: "#059669",
    },
    {
      key: "projects",
      value: summary?.pendingCandidateCount,
      label: "Pending Candidate Rules",
      icon: <FileTextOutlined />,
      color: "#d97706",
    },
    {
      key: "document-inbox",
      value: summary?.documentCount,
      label: "Source Documents",
      icon: <FileTextOutlined />,
      color: "#2563eb",
    },
  ];

  const toolkit = ROLE_TOOLKITS[actor.role];

  const goToTool = (page: string) => {
    if (page === "ask-ai") onOpenAskAi?.();
    else onNavigate(page);
  };

  return (
    <>
      <div>
        <Title level={3} style={{ marginBottom: 4 }}>
          Dashboard
        </Title>
        <Text type="secondary">Overview of the deterministic policy platform — local instance.</Text>
      </div>

      {error && <Alert type="error" showIcon message={error} />}

      <Row gutter={[16, 16]}>
        {cards.map((c, idx) => (
          <Col xs={24} sm={12} lg={6} key={idx}>
            <Card hoverable onClick={() => onNavigate(c.key)} className="stat-card">
              <Statistic
                title={c.label}
                value={c.value ?? "…"}
                prefix={<span style={{ color: c.color }}>{c.icon}</span>}
              />
            </Card>
          </Col>
        ))}
      </Row>

      <Card
        title={
          <Space>
            <BulbOutlined />
            <span>Your toolkit</span>
            <Tag color="purple">{ACTOR_ROLE_LABELS[actor.role]}</Tag>
          </Space>
        }
        className="toolkit-card"
      >
        <Paragraph type="secondary" style={{ marginBottom: 16 }}>
          Suggested next actions for someone working as a {ACTOR_ROLE_LABELS[actor.role].toLowerCase()}. Switch role
          via "Acting as" in the header to see a different toolkit.
        </Paragraph>
        <Row gutter={[16, 16]}>
          {toolkit.map((tool) => (
            <Col xs={24} md={8} key={tool.label}>
              <Card hoverable size="small" className="toolkit-tool-card" onClick={() => goToTool(tool.page)}>
                <Space align="start">
                  <span className="toolkit-tool-icon">{tool.icon}</span>
                  <div>
                    <Text strong>{tool.label}</Text>
                    <br />
                    <Text type="secondary" style={{ fontSize: 13 }}>
                      {tool.description}
                    </Text>
                  </div>
                </Space>
              </Card>
            </Col>
          ))}
        </Row>
      </Card>

      <Card title="Quick Links" className="quick-links-card">
        <Space size={10} wrap>
          <Button icon={<FolderOutlined />} onClick={() => onNavigate("projects")}>
            Browse Projects
          </Button>
          <Button icon={<InboxOutlined />} onClick={() => onNavigate("document-inbox")}>
            Document Inbox
          </Button>
          {onOpenAskAi && (
            <Button icon={<ThunderboltOutlined />} onClick={onOpenAskAi}>
              Ask AI
            </Button>
          )}
          <Button icon={<PlayCircleOutlined />} onClick={() => onNavigate("evaluate")}>
            Run an Evaluation
          </Button>
        </Space>
      </Card>
    </>
  );
}
