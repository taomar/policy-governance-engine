import { useCallback, useEffect, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Col,
  Empty,
  Row,
  Segmented,
  Select,
  Space,
  Spin,
  Statistic,
  Tag,
  Tooltip,
  Typography,
} from "antd";
import {
  HistoryOutlined,
  PlayCircleOutlined,
  ThunderboltOutlined,
  WarningOutlined,
} from "@ant-design/icons";
import {
  aiApi,
  api,
  policyTestApi,
  PolicyPlatformApiError,
  type PolicySet,
  type PolicyTestListItem,
  type QualityFinding,
  type QualityReport,
  type QualityRunSummary,
} from "../api";
import { EvaluationTargetBanner, useEvaluationTarget } from "./EvaluationTarget";

const { Title, Text, Paragraph } = Typography;

const SEVERITY_COLOR: Record<string, string> = {
  high: "red",
  medium: "gold",
  low: "default",
};

const SEVERITY_ORDER: Record<string, number> = { high: 0, medium: 1, low: 2 };

function formatCategory(cat: string): string {
  return cat
    .split("_")
    .map((w) => w[0].toUpperCase() + w.slice(1))
    .join(" ");
}

/**
 * Quality view — surfaces both deterministic checks (duplicate rule_ids,
 * ambiguity, conflicting effects, expired rules, review backlog, …) and an
 * AI-review pass (conflicts, gaps, and risks a rules-based check can't
 * catch) for the active version of a policy set. Built for a policy
 * administrator to answer "are my extracted policies actually good?"
 * without reading raw JSON or backend logs.
 */
export function QualityPage({ policySetKey }: { policySetKey?: string } = {}) {
  const scoped = Boolean(policySetKey);
  const [policySets, setPolicySets] = useState<PolicySet[]>([]);
  const [selectedKey, setSelectedKey] = useState(policySetKey ?? "");
  const [report, setReport] = useState<QualityReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [severityFilter, setSeverityFilter] = useState<string>("all");
  const [sourceFilter, setSourceFilter] = useState<string>("all");
  const [scope, setScope] = useState<"published" | "candidates">("published");
  const [failingTests, setFailingTests] = useState<PolicyTestListItem[]>([]);
  const [failingLoading, setFailingLoading] = useState(false);
  const [failingError, setFailingError] = useState<string | null>(null);
  const [history, setHistory] = useState<QualityRunSummary[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [viewingRunId, setViewingRunId] = useState<string | null>(null);

  const evaluationTarget = useEvaluationTarget(selectedKey);

  // Disabling the button is what turns an unexplained server error into an
  // answered question: the banner above already states *why* there is nothing to
  // run against, so the control stays consistent with the explanation.
  const runDisabled =
    scope === "published" ? !evaluationTarget.version : evaluationTarget.candidateCount === 0;

  useEffect(() => {
    if (scoped) return; // scope is fixed by the embedding project; no picker/list needed
    api
      .listPolicySets()
      .then((sets) => {
        setPolicySets(sets);
        if (sets.length > 0) setSelectedKey(sets[0].key);
      })
      .catch((e) => setError(e instanceof PolicyPlatformApiError ? e.detail : String(e)));
  }, [scoped]);

  // "Failed policy tests" (Section 9.9's Findings center queue) — sourced from
  // PolicyTest/PolicyTestRun, kept as its own independent fetch rather than
  // folded into `report`/`findings` above so it never disturbs the existing
  // AI-quality-report rendering. Loads automatically (no button) since it's a
  // plain read, unlike the AI quality pass which is triggered on demand.
  useEffect(() => {
    if (!selectedKey) return;
    setFailingLoading(true);
    setFailingError(null);
    policyTestApi
      .listFailing(selectedKey)
      .then(setFailingTests)
      .catch((e) => setFailingError(e instanceof PolicyPlatformApiError ? e.detail : String(e)))
      .finally(() => setFailingLoading(false));
  }, [selectedKey]);

  const loadHistory = useCallback(() => {
    if (!selectedKey) return;
    setHistoryLoading(true);
    setHistoryError(null);
    aiApi
      .getQualityHistory(selectedKey, scope, 25)
      .then(setHistory)
      .catch((e) => setHistoryError(e instanceof PolicyPlatformApiError ? e.detail : String(e)))
      .finally(() => setHistoryLoading(false));
  }, [selectedKey, scope]);

  useEffect(loadHistory, [loadHistory]);

  const runEvaluation = async () => {
    if (!selectedKey) return;
    setLoading(true);
    setError(null);
    setReport(null);
    setViewingRunId(null);
    try {
      const result = scope === "published" ? await aiApi.getQuality(selectedKey) : await aiApi.getCandidateQuality(selectedKey);
      setReport(result);
      // The run has been persisted server-side; refresh so the new entry — and
      // therefore the comparison against the previous one — is visible without
      // a page reload.
      loadHistory();
    } catch (e) {
      setError(e instanceof PolicyPlatformApiError ? e.detail : String(e));
    } finally {
      setLoading(false);
    }
  };

  const openHistoricRun = async (runId: string) => {
    if (!selectedKey) return;
    setLoading(true);
    setError(null);
    try {
      const detail = await aiApi.getQualityRun(selectedKey, runId);
      setReport(detail);
      setViewingRunId(runId);
    } catch (e) {
      setError(e instanceof PolicyPlatformApiError ? e.detail : String(e));
    } finally {
      setLoading(false);
    }
  };

  const findings = (report?.findings ?? [])
    .filter((f) => severityFilter === "all" || f.severity === severityFilter)
    .filter((f) => sourceFilter === "all" || f.source === sourceFilter)
    .slice()
    .sort((a, b) => SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity]);

  const counts = (report?.findings ?? []).reduce(
    (acc, f) => {
      acc[f.severity] = (acc[f.severity] ?? 0) + 1;
      return acc;
    },
    {} as Record<string, number>
  );

  return (
    <>
      <div className="page-header-row">
        <Title level={3} style={{ margin: 0 }}>
          Quality
        </Title>
        {!scoped && (
          <Select
            value={selectedKey}
            onChange={setSelectedKey}
            style={{ minWidth: 220 }}
            options={policySets.map((ps) => ({ value: ps.key, label: ps.name }))}
          />
        )}
      </div>
      <Paragraph type="secondary">
        Quality answers one question: <Text strong>are these rules safe to rely on?</Text> It runs deterministic
        checks (duplicate IDs, ambiguity, conflicting effects, expired rules, review backlog) plus an AI review
        pass, and reports every finding with its severity and a recommendation. Nothing is silently "fixed" for
        you — you decide what to act on.
      </Paragraph>

      {error && <Alert type="error" showIcon message={error} />}
      {!scoped && policySets.length === 0 && <Text type="secondary">Create a policy set first.</Text>}

      {selectedKey && (
        <>
          <Card size="small" className="eval-launch-card">
            <div className="eval-launch-choice">
              <Text strong className="eval-launch-question">
                What should be checked?
              </Text>
              <Segmented
                value={scope}
                onChange={(v) => {
                  setScope(v as typeof scope);
                  setReport(null);
                }}
                options={[
                  { value: "published", label: "The published version" },
                  { value: "candidates", label: "Rules still in review" },
                ]}
              />
            </div>

            <EvaluationTargetBanner
              scope={scope}
              target={evaluationTarget}
              actionLabel="Quality evaluation"
              emptyHint={
                scope === "published"
                  ? "Quality checks the version currently in force. Approve rules in Review and publish a version, then run this to confirm the published set is sound."
                  : "This checks rules before they are published. Extract a document or draft a rule, then run this to catch problems while they are still cheap to fix."
              }
            />

            <div className="eval-launch-actions">
              <Button
                type="primary"
                size="large"
                icon={<PlayCircleOutlined />}
                onClick={runEvaluation}
                loading={loading}
                disabled={runDisabled}
              >
                {loading ? "Evaluating…" : "Run quality evaluation"}
              </Button>
              <Text type="secondary" className="eval-launch-note">
                Read-only. Running this never changes a rule, an approval, or a published version.
              </Text>
            </div>
          </Card>

          <Card
            size="small"
            className="quality-history-card"
            title={
              <span className="quality-history-title">
                <HistoryOutlined /> Evaluation history
              </span>
            }
            extra={
              <Button size="small" type="text" onClick={loadHistory} loading={historyLoading}>
                Refresh
              </Button>
            }
          >
            <Paragraph type="secondary" className="quality-history-intro">
              A single evaluation tells you how many findings exist today. Only the
              sequence tells you whether the policy set is improving — each row is
              compared against the run before it.
            </Paragraph>
            {historyError && <Alert type="error" showIcon message={historyError} />}
            {historyLoading && history.length === 0 && <Spin size="small" />}
            {!historyLoading && history.length === 0 && !historyError && (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description={`No ${scope === "published" ? "published-version" : "candidate"} evaluations recorded yet — run one above.`}
              />
            )}
            {history.length > 0 && (
              <div className="quality-history-list">
                {history.map((run, idx) => {
                  // `history` is newest-first, so the previous run in time is the
                  // *next* element. Comparing against it is what makes a number
                  // mean something.
                  const prior = history[idx + 1];
                  const delta = prior ? run.finding_count - prior.finding_count : null;
                  const isOpen = viewingRunId === run.id;
                  return (
                    <button
                      key={run.id}
                      type="button"
                      className={`quality-history-row${isOpen ? " is-open" : ""}`}
                      onClick={() => openHistoricRun(run.id)}
                    >
                      <span className="quality-history-when">
                        {new Date(run.run_at).toLocaleString()}
                      </span>
                      <span className="quality-history-meta">
                        {run.rule_count} rules
                        {run.version_number !== null && ` · v${run.version_number}`}
                        {run.ai_review_used ? " · AI review" : " · deterministic only"}
                      </span>
                      <span className="quality-history-counts">
                        <Tag color="red">{run.high_count} high</Tag>
                        <Tag color="gold">{run.medium_count} med</Tag>
                        <Tag>{run.low_count} low</Tag>
                      </span>
                      {delta === null ? (
                        <Tag className="quality-history-delta">baseline</Tag>
                      ) : (
                        <Tooltip title={`Previous run had ${prior.finding_count} findings`}>
                          <Tag
                            className="quality-history-delta"
                            color={delta < 0 ? "green" : delta > 0 ? "red" : undefined}
                          >
                            {delta === 0 ? "no change" : `${delta > 0 ? "+" : ""}${delta}`}
                          </Tag>
                        </Tooltip>
                      )}
                    </button>
                  );
                })}
              </div>
            )}
          </Card>

          {viewingRunId && report && (
            <Alert
              type="info"
              showIcon
              message="Viewing a past evaluation"
              description="These findings are from a stored run and reflect the rules as they were at that time — they are not a live check of the current state."
              action={
                <Button size="small" onClick={runEvaluation}>
                  Run a fresh evaluation
                </Button>
              }
            />
          )}

          {report && (
            <>
              <Row gutter={[16, 16]}>
                <Col xs={12} lg={6}>
                  <Card>
                    <Statistic
                      title={report.scope === "candidates" ? "Candidate rules evaluated" : `Rules in version ${report.version_number}`}
                      value={report.rule_count}
                    />
                  </Card>
                </Col>
                <Col xs={12} lg={6}>
                  <Card>
                    <Statistic title="High severity" value={counts.high ?? 0} valueStyle={{ color: "#cf222e" }} />
                  </Card>
                </Col>
                <Col xs={12} lg={6}>
                  <Card>
                    <Statistic title="Medium severity" value={counts.medium ?? 0} valueStyle={{ color: "#9a6700" }} />
                  </Card>
                </Col>
                <Col xs={12} lg={6}>
                  <Card>
                    <Statistic title="Low severity" value={counts.low ?? 0} valueStyle={{ color: "#57606a" }} />
                  </Card>
                </Col>
              </Row>

              <div className="page-header-row">
                <Title level={5} style={{ margin: 0 }}>
                  Findings ({findings.length})
                </Title>
                <Space>
                  <Select
                    value={severityFilter}
                    onChange={setSeverityFilter}
                    style={{ width: 150 }}
                    options={[
                      { value: "all", label: "All severities" },
                      { value: "high", label: "High" },
                      { value: "medium", label: "Medium" },
                      { value: "low", label: "Low" },
                    ]}
                  />
                  <Select
                    value={sourceFilter}
                    onChange={setSourceFilter}
                    style={{ width: 160 }}
                    options={[
                      { value: "all", label: "All sources" },
                      { value: "deterministic", label: "Deterministic" },
                      { value: "ai_review", label: "AI review" },
                    ]}
                  />
                </Space>
              </div>

              <Space direction="vertical" style={{ width: "100%" }} size={12}>
                {findings.map((f: QualityFinding, i: number) => (
                  <Card key={i} size="small" className="finding-card">
                    <Space size={8} wrap style={{ marginBottom: 8 }}>
                      <Tag color={SEVERITY_COLOR[f.severity] ?? "default"}>{f.severity.toUpperCase()}</Tag>
                      <Tag>{formatCategory(f.category)}</Tag>
                      <Tag
                        icon={f.source === "ai_review" ? <ThunderboltOutlined /> : undefined}
                        color={f.source === "ai_review" ? "purple" : "blue"}
                      >
                        {f.source === "ai_review" ? "AI review" : "Deterministic"}
                      </Tag>
                    </Space>
                    <Text>{f.finding}</Text>
                    {f.affected_rule_ids.length > 0 && (
                      <div style={{ marginTop: 8 }}>
                        <Space size={6} wrap>
                          {f.affected_rule_ids.map((rid) => (
                            <Tag key={rid} bordered={false} className="fact-tag">
                              {rid}
                            </Tag>
                          ))}
                        </Space>
                      </div>
                    )}
                    {f.recommendation && (
                      <Paragraph type="secondary" style={{ marginTop: 8, marginBottom: 0 }}>
                        <strong>Recommendation:</strong> {f.recommendation}
                      </Paragraph>
                    )}
                  </Card>
                ))}
                {findings.length === 0 && <Text type="secondary">No findings match this filter.</Text>}
              </Space>
            </>
          )}

          <div className="page-header-row" style={{ marginTop: 24 }}>
            <Title level={5} style={{ margin: 0 }}>
              Failed policy tests ({failingTests.length})
            </Title>
          </div>
          <Paragraph type="secondary" style={{ marginTop: -8 }}>
            Saved PolicyTest cases whose most recent run against the active version did not pass. Tests that have
            never been run are not counted here — see the Tests tab to run or review them.
          </Paragraph>
          {failingError && <Alert type="error" showIcon message={failingError} style={{ marginBottom: 12 }} />}
          <Space direction="vertical" style={{ width: "100%" }} size={12}>
            {failingTests.map((item) => (
              <Card key={item.test.id} size="small" className="finding-card">
                <Space size={8} wrap style={{ marginBottom: 8 }}>
                  <Tag icon={<WarningOutlined />} color="error">
                    {(item.latest_run?.status ?? "fail").toUpperCase()}
                  </Tag>
                  <Tag>{formatCategory(item.test.test_kind)}</Tag>
                  {item.test.proposed_by === "ai" && <Tag color="purple">AI-proposed</Tag>}
                </Space>
                <Text strong>{item.test.name}</Text>
                {item.test.description && (
                  <Paragraph type="secondary" style={{ marginTop: 4, marginBottom: 0 }}>
                    {item.test.description}
                  </Paragraph>
                )}
                {item.latest_run?.explanation && (
                  <Paragraph type="secondary" style={{ marginTop: 8, marginBottom: 0 }}>
                    <strong>Why:</strong> {item.latest_run.explanation}
                  </Paragraph>
                )}
              </Card>
            ))}
            {!failingLoading && failingTests.length === 0 && (
              <Text type="secondary">No failing policy tests for this policy set.</Text>
            )}
          </Space>
        </>
      )}
    </>
  );
}
