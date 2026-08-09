import { useEffect, useState } from "react";
import { Alert, Button, Tag, Typography } from "antd";
import {
  ArrowRightOutlined,
  CheckCircleOutlined,
  ExperimentOutlined,
  FileTextOutlined,
  FolderOutlined,
  PlayCircleOutlined,
  SafetyCertificateOutlined,
  ThunderboltOutlined,
  UploadOutlined,
  WarningOutlined,
} from "@ant-design/icons";
import {
  api,
  PolicyPlatformApiError,
  type PolicySet,
  type ProjectPortfolioInsight,
} from "../api";
import { ACTOR_ROLE_LABELS, useActor, type ActorRole } from "../ActorContext";

const { Title, Text } = Typography;

interface Summary {
  policySetCount: number;
  activeVersionCount: number | null;
  pendingCandidateCount: number | null;
  documentCount: number;
  publishedRuleCount: number | null;
  executableRuleCount: number | null;
  regressionGuardCount: number | null;
  validationCount: number | null;
  highFindingCount: number | null;
}

interface ProjectReadiness {
  project: PolicySet;
  insight: ProjectPortfolioInsight;
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
  const [readiness, setReadiness] = useState<ProjectReadiness[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const load = async () => {
      try {
        const [policySets, documents] = await Promise.all([
          api.listPolicySets(),
          api.listDocuments(),
        ]);
        const base: Summary = {
          policySetCount: policySets.length,
          activeVersionCount: null,
          pendingCandidateCount: null,
          documentCount: documents.length,
          publishedRuleCount: null,
          executableRuleCount: null,
          regressionGuardCount: null,
          validationCount: null,
          highFindingCount: null,
        };
        setSummary(base);

        try {
          const insights = await api.getProjectPortfolioSummary();
          const byKey = new Map(policySets.map((project) => [project.key, project]));
          const joined = insights.flatMap((insight) => {
            const project = byKey.get(insight.key);
            return project ? [{ project, insight }] : [];
          });
          joined.sort(
            (a, b) =>
              (b.insight.latest_quality_high ?? -1) - (a.insight.latest_quality_high ?? -1) ||
              b.insight.review_pending - a.insight.review_pending,
          );
          setReadiness(joined);
          setSummary({
            ...base,
            activeVersionCount: insights.filter((item) => item.active_version_number !== null).length,
            pendingCandidateCount: insights.reduce((total, item) => total + item.review_pending, 0),
            publishedRuleCount: insights.reduce((total, item) => total + item.active_rule_count, 0),
            executableRuleCount: insights.reduce((total, item) => total + item.machine_executable_count, 0),
            regressionGuardCount: insights.reduce((total, item) => total + item.regression_test_count, 0),
            validationCount: insights.reduce((total, item) => total + item.test_count, 0),
            highFindingCount: insights.reduce((total, item) => total + (item.latest_quality_high ?? 0), 0),
          });
        } catch (caught) {
          setError(
            `Portfolio loaded, but readiness insights are unavailable: ${
              caught instanceof PolicyPlatformApiError ? caught.detail : String(caught)
            }`,
          );
        }
      } catch (e) {
        setError(e instanceof PolicyPlatformApiError ? e.detail : String(e));
      }
    };
    void load();
  }, []);

  const toolkit = ROLE_TOOLKITS[actor.role];

  const goToTool = (page: string) => {
    if (page === "ask-ai") onOpenAskAi?.();
    else onNavigate(page);
  };

  const pending = summary?.pendingCandidateCount;
  const published = summary?.publishedRuleCount;
  const executable = summary?.executableRuleCount;
  const executablePercent =
    published && executable !== null && executable !== undefined
      ? Math.round((executable / published) * 100)
      : null;
  const pressure = [
    {
      label: "Awaiting review",
      value: pending,
      detail: "candidate decisions",
      icon: <FileTextOutlined />,
      tone: pending && pending > 0 ? "attention" : "neutral",
    },
    {
      label: "High findings",
      value: summary?.highFindingCount,
      detail: "latest active-version checks",
      icon: <WarningOutlined />,
      tone: summary?.highFindingCount ? "risk" : "neutral",
    },
    {
      label: "Machine-ready",
      value:
        published === null || published === undefined || executable === null || executable === undefined
          ? null
          : `${executable}/${published}`,
      detail: executablePercent === null ? "coverage unavailable" : `${executablePercent}% of published rules`,
      icon: <CheckCircleOutlined />,
      tone: executablePercent !== null && executablePercent < 50 ? "attention" : "neutral",
    },
    {
      label: "Regression guards",
      value: summary?.regressionGuardCount,
      detail:
        summary?.validationCount === null || summary?.validationCount === undefined
          ? "validation unavailable"
          : `${summary.validationCount} saved scenarios`,
      icon: <ExperimentOutlined />,
      tone: "neutral",
    },
  ];

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
                : pending === null
                  ? "Review workload unavailable"
                : pending > 0
                  ? `${pending} candidate rule${pending === 1 ? "" : "s"} need a decision`
                  : "Review queues are clear"}
            </Title>
            <Text type="secondary">
              Inspect the source, condition, outcome, and exceptions before approving anything for publication.
            </Text>
          </div>
          <div className="dashboard-pressure-strip" aria-label="Portfolio assurance status">
            {pressure.map((item) => (
              <div key={item.label} className={`is-${item.tone}`}>
                <span className="dashboard-pressure-icon">{item.icon}</span>
                <span>
                  <small>{item.label}</small>
                  <strong>{item.value ?? "—"}</strong>
                  <em>{item.detail}</em>
                </span>
              </div>
            ))}
          </div>
          <Button type="primary" icon={<ArrowRightOutlined />} onClick={() => onNavigate("projects")}>
            Open project register
          </Button>
        </section>

        <section className="dashboard-portfolio" aria-label="Portfolio register">
          <div className="dashboard-panel-heading">
            <Text strong>Project readiness</Text>
            <Text type="secondary">
              {summary
                ? `${summary.policySetCount} projects · ${summary.activeVersionCount ?? "—"} live · ${summary.documentCount} sources`
                : "Loading portfolio…"}
            </Text>
          </div>
          <div className="dashboard-readiness-list" role="list">
            {readiness.map(({ project, insight }) => {
              const coverage = insight.active_rule_count
                ? Math.round((insight.machine_executable_count / insight.active_rule_count) * 100)
                : 0;
              return (
              <button
                key={project.key}
                type="button"
                role="listitem"
                className="dashboard-readiness-row"
                onClick={() => onNavigate("projects")}
              >
                <span className="dashboard-metric-icon"><FolderOutlined /></span>
                <span className="dashboard-readiness-copy">
                  <strong>{project.name}</strong>
                  <small>
                    {insight.active_version_number ? `v${insight.active_version_number}` : "not published"} ·{" "}
                    {insight.active_rule_count} rules · {coverage}% machine-ready
                  </small>
                </span>
                <span className="dashboard-readiness-signals">
                  {(insight.latest_quality_high ?? 0) > 0 && (
                    <Tag color="red">{insight.latest_quality_high} high</Tag>
                  )}
                  {insight.review_pending > 0 && <Tag color="gold">{insight.review_pending} review</Tag>}
                  {insight.regression_test_count > 0 && <Tag>{insight.regression_test_count} guards</Tag>}
                </span>
                <ArrowRightOutlined className="dashboard-metric-arrow" />
              </button>
              );
            })}
            {summary && readiness.length === 0 && (
              <div className="dashboard-readiness-empty">
                <Text type="secondary">No project readiness evidence is available yet.</Text>
              </div>
            )}
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
