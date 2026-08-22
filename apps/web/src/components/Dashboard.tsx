import { useEffect, useState } from "react";
import { Alert, Button, Tag, Typography } from "antd";
import {
  ArrowRightOutlined,
  AuditOutlined,
  CheckCircleOutlined,
  ExperimentOutlined,
  EyeOutlined,
  FileTextOutlined,
  FolderOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
  ThunderboltOutlined,
  UploadOutlined,
  WarningOutlined,
} from "@ant-design/icons";
import {
  api,
  type PolicySet,
  type ProjectPortfolioInsight,
} from "../api";
import { ACTOR_ROLE_LABELS, useActor } from "../ActorContext";
import { canAccessPage, ROLE_LABELS, ROLES, type Role } from "../rbac";
import { getSession } from "../auth";
import { describeApiFailure, UNKNOWN_COUNT, type LoadState } from "../loadState";
import { projectRowClauses, routeClauses } from "../projectRegisterRow";
import { recordScaleLabel } from "../policyRecordFacts";
import { reviewWorkByDocument, reviewWorkReason } from "../projectRegisterGroups";
import { distinctLabelsByKey } from "../distinctNames";
import { projectNavTarget } from "../projectNav";

const { Title, Text } = Typography;

interface Summary {
  policySetCount: number;
  activeVersionCount: number | null;
  pendingCandidateCount: number | null;
  /**
   * The same queue counted in the unit it is decided in. Null is absent, not
   * zero: a server that does not serve the policy figure has told us nothing
   * about how many policies are waiting, and reporting none over a queue
   * holding hundreds of rules would be a measurement nobody took.
   */
  pendingPolicyCount: number | null;
  documentCount: number;
  publishedRuleCount: number | null;
  liveCandidateCount: number | null;
  directRouteCount: number | null;
  readingRouteCount: number | null;
  regressionGuardCount: number | null;
  validationCount: number | null;
  highFindingCount: number | null;
}

interface ProjectReadiness {
  project: PolicySet;
  insight: ProjectPortfolioInsight;
}

/**
 * How many rows the dashboard shows from a collection that has no upper bound.
 *
 * WHY THE DASHBOARD BOUNDS ITS LISTS AT ALL
 *
 * This page had two unbounded lists on it: the documents holding review work,
 * and one row per project. Their height was therefore a function of how much
 * the instance contains, and everything laid out beside them inherited that
 * height. The dashboard is a briefing — it says what is happening and where to
 * go — and the register is the enumeration. A briefing that grows without limit
 * is the register, rendered twice and worse.
 *
 * So the dashboard's height is O(1) in portfolio size, and every list states
 * exactly how many rows it is not showing with a way to reach them. Six is what
 * a reader takes in without scrolling and without the panel becoming a list to
 * search. It is a display constant, not a threshold: nothing behaves
 * differently above or below it, and no project, name, count or document is
 * special to it.
 */
const PREVIEW_ROWS = 6;

/**
 * Characters a project name gets in a readiness row before it is shortened.
 *
 * Sized to the narrowest this column becomes rather than to the widest, so a
 * label does not change shape on a resize. The CSS clamp on the same element
 * stays as the last line of defence; this exists so that what survives the cut
 * is the part that tells one project from another. See `distinctNames`.
 */
const READINESS_NAME_BUDGET = 58;

interface ToolLink {
  label: string;
  description: string;
  icon: React.ReactNode;
  /** Navigate to a top-level page, OR set to "ask-ai" to open the Ask AI drawer directly. */
  page: string;
}

/**
 * Role-specific toolkits keyed by RBAC role (the real authority) rather than
 * the legacy ActorRole persona.  Each role sees actions it can actually perform
 * — derived from what `rbac.ts` allows — so the interface never invites a user
 * into a 403.
 */
const RBAC_TOOLKITS: Record<Role, ToolLink[]> = {
  admin: [
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
  policy_author: [
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
  viewer: [
    {
      label: "Browse published policies",
      description: "Read the approved, immutable rules that are currently in force across projects.",
      icon: <EyeOutlined />,
      page: "projects",
    },
    {
      label: "Run an evaluation",
      description: "Test how published rules apply against a set of facts — deterministic, every time.",
      icon: <PlayCircleOutlined />,
      page: "evaluate",
    },
    {
      label: "Read the decision log",
      description: "See every evaluation result: who asked, what facts, what the rules decided, and why.",
      icon: <AuditOutlined />,
      page: "projects",
    },
  ],
};

/** Framing copy that speaks to the reader's role rather than describing
 *  authoring work a viewer never does. */
const ROLE_FRAMING: Record<Role, { title: string; subtitle: string }> = {
  admin: {
    title: "Policy operations",
    subtitle: "Move source-grounded rules from intake to an immutable published decision.",
  },
  policy_author: {
    title: "Policy operations",
    subtitle: "Move source-grounded rules from intake to an immutable published decision.",
  },
  viewer: {
    title: "Policy dashboard",
    subtitle: "Published policies you can read, and evaluations you can run.",
  },
};

export function Dashboard({
  onNavigate,
  onOpenAskAi,
}: {
  onNavigate: (page: string) => void;
  onOpenAskAi?: () => void;
}) {
  const { actor, role } = useActor();
  const rbacRole = role;
  const [summary, setSummary] = useState<Summary | null>(null);
  // `summary === null` meant both "not asked yet" and "asked and failed", so a
  // refused fetch left both panels below spinning on "Loading…" indefinitely.
  // The failure branch existed for the review queue and was simply unreachable.
  const [dataState, setDataState] = useState<LoadState>("loading");
  const [readiness, setReadiness] = useState<ProjectReadiness[]>([]);
  const [error, setError] = useState<string | null>(null);
  // Bumped by the retry affordances below. A panel that has failed must offer
  // a way forward; otherwise "unavailable" is just a politer dead end.
  const [reloadToken, setReloadToken] = useState(0);
  const retry = () => setReloadToken((token) => token + 1);

  useEffect(() => {
    const load = async () => {
      setDataState("loading");
      setError(null);
      try {
        const [policySets, documents] = await Promise.all([
          api.listPolicySets(),
          api.listDocuments(),
        ]);
        const base: Summary = {
          policySetCount: policySets.length,
          activeVersionCount: null,
          pendingCandidateCount: null,
          pendingPolicyCount: null,
          documentCount: documents.length,
          publishedRuleCount: null,
          liveCandidateCount: null,
          directRouteCount: null,
          readingRouteCount: null,
          regressionGuardCount: null,
          validationCount: null,
          highFindingCount: null,
        };
        setSummary(base);
        setDataState("ready");

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
            // One insight without the policy figure makes the portfolio total
            // unknown rather than short. Summing the ones that have it would
            // quietly report part of the portfolio as all of it.
            pendingPolicyCount: insights.every((item) => typeof item.review_pending_policies === "number")
              ? insights.reduce((total, item) => total + (item.review_pending_policies ?? 0), 0)
              : null,
            publishedRuleCount: insights.reduce((total, item) => total + item.active_rule_count, 0),
            liveCandidateCount: insights.reduce((total, item) => total + item.live_candidate_count, 0),
            directRouteCount: insights.reduce((total, item) => total + item.candidate_direct_count, 0),
            readingRouteCount: insights.reduce((total, item) => total + item.candidate_reading_count, 0),
            regressionGuardCount: insights.reduce((total, item) => total + item.regression_test_count, 0),
            validationCount: insights.reduce((total, item) => total + item.test_count, 0),
            highFindingCount: insights.reduce((total, item) => total + (item.latest_quality_high ?? 0), 0),
          });
        } catch (caught) {
          setError(`Portfolio loaded, but readiness insights are unavailable: ${describeApiFailure(caught)}`);
        }
      } catch (e) {
        // Nothing was loaded. Saying so is the only honest option: leaving the
        // panels on "Loading…" claims a request is still in flight when it has
        // already been refused, and they never resolve.
        setDataState("unavailable");
        setError(describeApiFailure(e));
      }
    };
    void load();
  }, [reloadToken]);

  const toolkit = RBAC_TOOLKITS[rbacRole] ?? [];
  // Filter out toolkit actions that route to surfaces the role cannot reach.
  const visibleToolkit = toolkit.filter((tool) =>
    tool.page === "ask-ai" || canAccessPage(rbacRole, tool.page),
  );
  // If the server sent a role this build doesn't recognise, `toRbacRole` fell
  // back to `"viewer"` silently.  The user deserves to know.
  const session = getSession();
  const roleUnrecognised = session !== null && !(ROLES as readonly string[]).includes(session.role);

  const goToTool = (page: string) => {
    if (page === "ask-ai") onOpenAskAi?.();
    else onNavigate(page);
  };

  const pending = summary?.pendingCandidateCount;
  // The same queue in the unit it is decided in. A policy is what a reviewer
  // approves, publishes and exports; rules are its contents, and one policy
  // commonly holds several -- so the policy figure leads and the rule figure
  // stays beside it. Null is absent: the surface then says what it has, in
  // rules, and names that unit rather than badging a nought nobody measured.
  const pendingPolicies = summary?.pendingPolicyCount ?? null;
  // The queue scoped to the documents it is actually spread across, so the
  // headline count above has somewhere to send a reviewer.
  const reviewWork = reviewWorkByDocument(readiness.map(({ insight }) => insight));
  const shownReviewWork = reviewWork.slice(0, PREVIEW_ROWS);
  const reviewWorkOverflow = reviewWork.length - shownReviewWork.length;
  const shownReadiness = readiness.slice(0, PREVIEW_ROWS);
  const readinessOverflow = readiness.length - shownReadiness.length;
  // Computed over the whole portfolio rather than the shown slice, so a name
  // does not change shape when the panel's contents shift.
  const readinessNames = distinctLabelsByKey(
    readiness,
    ({ project }) => project.key,
    ({ project }) => project.name,
    READINESS_NAME_BUDGET,
  );
  const liveRecords = summary?.liveCandidateCount;
  const directRoute = summary?.directRouteCount;
  const readingRoute = summary?.readingRouteCount;
  const pressure = [
    {
      label: "Awaiting review",
      value: pending === null || pending === undefined ? pending : (pendingPolicies ?? pending),
      detail:
        pending === null || pending === undefined
          ? "candidate decisions"
          : recordScaleLabel(pendingPolicies, pending),
      icon: <FileTextOutlined />,
      tone: pending && pending > 0 ? "attention" : "neutral",
    },
    {
      label: "High findings",
      // Zero findings is good news — say "None" rather than rendering a bare 0
      // that reads as a defect count.
      value: summary?.highFindingCount === 0 ? "None" : summary?.highFindingCount,
      detail: "latest quality checks",
      icon: <WarningOutlined />,
      tone: summary?.highFindingCount ? "risk" : "neutral",
    },
    {
      // Was "Deterministic", valued as executable/published. On an unpublished
      // portfolio that is 0/0, and the row-level version of the same figure
      // rendered the undefined ratio as 0%, which reads as a failing grade for
      // behaving correctly. Routes are reported as counts of the live corpus
      // instead: how the source states a test is the source's property, not a
      // score this system earns against it, and most policy prose states it in
      // words.
      label: "Decision routes",
      value: liveRecords,
      detail:
        liveRecords === null || liveRecords === undefined
          ? "records unavailable"
          : liveRecords === 0
            ? "no records yet"
            : routeClauses(liveRecords, directRoute ?? 0, readingRoute ?? 0).join(", "),
      icon: <CheckCircleOutlined />,
      tone: "neutral",
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

  const framing = ROLE_FRAMING[rbacRole] ?? ROLE_FRAMING.viewer;

  return (
    <div className="dashboard-page">
      <header className="dashboard-page-header">
        <div>
          <Title level={3}>{framing.title}</Title>
          <Text type="secondary">{framing.subtitle}</Text>
        </div>
        <Tag variant="filled" className="dashboard-role-tag">
          {ROLE_LABELS[rbacRole] ?? ACTOR_ROLE_LABELS[actor.role]}
        </Tag>
      </header>

      {error && <Alert type="error" showIcon message={error} />}
      {roleUnrecognised && (
        <Alert
          type="warning"
          showIcon
          message="Your role was not recognised by this build. You have been given read-only access. Sign in again or contact an administrator."
          style={{ marginBottom: 16 }}
        />
      )}

      {/* The two panels below used to be the two cells of a `.dashboard-ledger`
          grid. A grid stretches its cells to the tallest, the right cell was one
          row per project, and so the left cell -- a fixed-size summary -- was
          given the height of however many projects the instance held. That is
          where the empty space came from: it was never the summary's own layout,
          which is why two earlier attempts inside the summary moved the void
          around without shrinking it. A fixed summary and an unbounded list do
          not belong side by side, so they are stacked siblings now and each is
          exactly as tall as its own content. */}
      {/* Authoring-oriented sections are suppressed for roles that cannot act
          on them: showing a review queue to a viewer who cannot approve anything
          reads as a feature gap rather than a privilege boundary. */}
      {rbacRole !== "viewer" && (
      <section className="dashboard-priority" aria-labelledby="review-work-title">
        <div className="dashboard-priority-copy">
          <div className="dashboard-priority-label">
            <FileTextOutlined />
            <Text strong>Review queue</Text>
          </div>
          <Title level={2} id="review-work-title">
            {dataState === "unavailable"
              ? "Review workload unavailable"
              : pending === undefined
                ? "Loading review workload…"
                : pending === null
                  ? "Review workload unavailable"
                  : pending > 0
                    ? `${recordScaleLabel(pendingPolicies, pending)} ${
                        (pendingPolicies ?? pending) === 1 ? "needs" : "need"
                      } a decision`
                    : "Review queues are clear"}
          </Title>
          {dataState === "unavailable" ? (
            <Text type="secondary">
              We could not reach the server, so we do not know what is waiting. This is not a claim that nothing is.
            </Text>
          ) : (
            <Text type="secondary">
              Inspect the source, condition, outcome, and exceptions before approving anything for publication.
            </Text>
          )}
          {dataState === "unavailable" && (
            <Button icon={<ReloadOutlined />} onClick={retry} className="dashboard-retry">
              Try again
            </Button>
          )}
          {reviewWork.length > 0 && (
            /* The count above spans the portfolio, and nobody reviews a
             * portfolio. This says which document to open, ordered by
             * recorded high-severity findings and then by how much is
             * waiting -- both signals the system already holds, rather than
             * a filter vocabulary invented for this panel. */
            <ul className="dashboard-queue-scope">
              {shownReviewWork.map((item) => (
                <li key={item.documentHash ?? item.label}>
                  <strong>{item.label}</strong>
                  <small>{reviewWorkReason(item)}</small>
                </li>
              ))}
              {reviewWorkOverflow > 0 && (
                <li className="dashboard-queue-scope-more">
                  <button type="button" onClick={() => onNavigate("projects")}>
                    {reviewWorkOverflow} more document{reviewWorkOverflow === 1 ? "" : "s"} holding
                    review work
                    <ArrowRightOutlined />
                  </button>
                </li>
              )}
            </ul>
          )}
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
      </section>
      )}

      <section className="dashboard-portfolio" aria-label="Portfolio register">
        <div className="dashboard-panel-heading">
          <Text strong>Project readiness</Text>
          <div className="dashboard-panel-heading-side">
            <Text type="secondary">
              {dataState === "unavailable"
                ? "Portfolio unavailable"
                : summary
                  ? `${summary.policySetCount} projects · ${summary.activeVersionCount ?? UNKNOWN_COUNT} live · ${summary.documentCount} sources`
                  : "Loading portfolio…"}
            </Text>
            {/* The register CTA lives on the panel it opens. It used to sit at
                the bottom of the summary panel, where the grid's stretched cell
                pushed it away from everything it related to. */}
            <Button size="small" icon={<ArrowRightOutlined />} onClick={() => onNavigate("projects")}>
              Open register
            </Button>
          </div>
        </div>
        {dataState === "unavailable" && (
          <div className="dashboard-panel-unavailable">
            <Text type="secondary">
              The project list could not be loaded, so none are shown here. Your projects have not gone anywhere.
            </Text>
            <Button icon={<ReloadOutlined />} onClick={retry}>
              Try again
            </Button>
          </div>
        )}
        <div className="dashboard-readiness-list" role="list">
          {shownReadiness.map(({ project, insight }) => (
            <button
              key={project.key}
              type="button"
              role="listitem"
              className="dashboard-readiness-row"
              // The arrow on this row promised the project it names. It went to
              // the register instead -- the same destination for every row, so
              // the arrow was decoration. It opens the project now.
              onClick={() => onNavigate(projectNavTarget(project.key))}
              title={`Open ${project.name}`}
            >
              <span className="dashboard-metric-icon"><FolderOutlined /></span>
              <span className="dashboard-readiness-copy">
                <strong>{readinessNames.labelFor(project.key)}</strong>
                {readinessNames.hasCollisions && (
                  <span className="dashboard-readiness-key">{project.key}</span>
                )}
                <small>{projectRowClauses(insight).join(" · ")}</small>
              </span>
              <span className="dashboard-readiness-signals">
                {(insight.latest_quality_high ?? 0) > 0 && (
                  <Tag color="red">{insight.latest_quality_high} high</Tag>
                )}
                {/* The review count is no longer repeated as a tag: it now leads the
                    row's own copy. It also carried a warning colour, which told the
                    reader something was wrong with a project for holding exactly the
                    work it is supposed to be holding. */}
                {insight.regression_test_count > 0 && <Tag>{insight.regression_test_count} guards</Tag>}
              </span>
              <ArrowRightOutlined className="dashboard-metric-arrow" />
            </button>
          ))}
          {readinessOverflow > 0 && (
            <button
              type="button"
              className="dashboard-readiness-row dashboard-readiness-more"
              onClick={() => onNavigate("projects")}
            >
              <span className="dashboard-readiness-copy">
                <strong>
                  {readinessOverflow} more project{readinessOverflow === 1 ? "" : "s"} in the register
                </strong>
                <small>Sorted and filterable there; this panel shows the {PREVIEW_ROWS} most pressing.</small>
              </span>
              <ArrowRightOutlined className="dashboard-metric-arrow" />
            </button>
          )}
          {summary && readiness.length === 0 && (
            <div className="dashboard-readiness-empty">
              <Text type="secondary">No project readiness evidence is available yet.</Text>
            </div>
          )}
        </div>
      </section>

      {visibleToolkit.length > 0 && (
      <section className="dashboard-workflow" aria-labelledby="workflow-title">
        <div className="dashboard-section-heading">
          <div>
            <Title level={4} id="workflow-title">
              Your workflow
            </Title>
            <Text type="secondary">Actions matched to the role selected in the header.</Text>
          </div>
          <Text type="secondary">{ROLE_LABELS[rbacRole] ?? ACTOR_ROLE_LABELS[actor.role]}</Text>
        </div>
        <div className="dashboard-workflow-list" role="list">
          {visibleToolkit.map((tool) => (
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
      )}
    </div>
  );
}
