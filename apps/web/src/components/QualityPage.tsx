import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Empty,
  Segmented,
  Select,
  Space,
  Spin,
  Tag,
  Tooltip,
  Typography,
} from "antd";
import {
  HistoryOutlined,
  PlayCircleOutlined,
  RightOutlined,
  ThunderboltOutlined,
  WarningOutlined,
} from "@ant-design/icons";
import {
  aiApi,
  api,
  policyTestApi,
  hasBeenEvaluated,
  PolicyPlatformApiError,
  type PolicySet,
  type PolicyTestListItem,
  type ApprovedPolicyVersion,
  type CanonicalRule,
  type QualityFinding,
  type QualityReport,
  type QualityRunSummary,
} from "../api";
import { EvaluationTargetBanner, useEvaluationTarget } from "./EvaluationTarget";
import { QualityFindingDrawer } from "./QualityFindingDrawer";
import type { QualityRuleRecord } from "./QualityFindingDrawer";

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

function addRuleReference(
  lookup: Map<string, QualityRuleRecord[]>,
  reference: string,
  rule: CanonicalRule,
  recordKey: string,
) {
  const matches = lookup.get(reference) ?? [];
  if (!matches.some((item) => item.key === recordKey)) {
    matches.push({ key: recordKey, rule });
    lookup.set(reference, matches);
  }
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
  // Set when the server reports that this scope has never been evaluated. Held
  // apart from `report` so an unexamined policy set can never be drawn as one
  // that was examined and came back clean.
  const [notEvaluated, setNotEvaluated] = useState<string | null>(null);
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
  const [reportEvaluatedAt, setReportEvaluatedAt] = useState<string | null>(null);
  const [findingPreview, setFindingPreview] = useState<QualityFinding | null>(null);
  const [findingRules, setFindingRules] = useState<CanonicalRule[]>([]);
  const [findingRuleLookup, setFindingRuleLookup] = useState<Map<string, QualityRuleRecord[]>>(new Map());
  const [findingVersions, setFindingVersions] = useState<ApprovedPolicyVersion[]>([]);
  const [findingVersion, setFindingVersion] = useState<ApprovedPolicyVersion | null>(null);
  const [findingContextLoading, setFindingContextLoading] = useState(false);
  const [findingContextError, setFindingContextError] = useState<string | null>(null);

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

  // What the page shows on arrival is the last evaluation somebody asked for,
  // read back from storage. Opening the page used to *perform* an evaluation:
  // a couple of minutes of AI review, and a new row in the history below, for
  // anyone who merely clicked the tab. The trend that history is there to show
  // was partly a record of people looking at it.
  const loadLatest = useCallback(() => {
    if (!selectedKey) return;
    setLoading(true);
    setError(null);
    setViewingRunId(null);
    const read = scope === "published" ? aiApi.readQuality : aiApi.readCandidateQuality;
    read(selectedKey)
      .then((readout) => {
        if (hasBeenEvaluated(readout)) {
          setNotEvaluated(null);
          setReport(readout);
          setReportEvaluatedAt(readout.run_at ?? null);
          setViewingRunId(readout.quality_run_id ?? null);
        } else {
          // Nothing recorded. Say so, and show no counts at all — a zero here
          // would read as a verdict.
          setReport(null);
          setReportEvaluatedAt(null);
          setNotEvaluated(readout.detail);
        }
      })
      .catch((e) => setError(e instanceof PolicyPlatformApiError ? e.detail : String(e)))
      .finally(() => setLoading(false));
  }, [selectedKey, scope]);

  useEffect(loadLatest, [loadLatest]);

  const runEvaluation = async () => {
    if (!selectedKey) return;
    setLoading(true);
    setError(null);
    setReport(null);
    setNotEvaluated(null);
    setViewingRunId(null);
    try {
      // A POST, because this is the expensive, state-changing half: it calls
      // the model and appends to the history. The read above is the cheap half.
      const result =
        scope === "published"
          ? await aiApi.runQuality(selectedKey)
          : await aiApi.runCandidateQuality(selectedKey);
      setReport(result);
      setReportEvaluatedAt(result.run_at ?? new Date().toISOString());
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
    setNotEvaluated(null);
    try {
      const detail = await aiApi.getQualityRun(selectedKey, runId);
      setReport(detail);
      setReportEvaluatedAt(detail.run_at);
      setViewingRunId(runId);
    } catch (e) {
      setError(e instanceof PolicyPlatformApiError ? e.detail : String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    setFindingPreview(null);
    if (!selectedKey || !report) {
      setFindingRules([]);
      setFindingRuleLookup(new Map());
      setFindingVersions([]);
      setFindingVersion(null);
      return;
    }

    let cancelled = false;
    const loadFindingContext = async () => {
      setFindingContextLoading(true);
      setFindingContextError(null);
      try {
        if ((report.scope ?? scope) === "candidates") {
          const [pending, approved] = await Promise.all([
            api.listCandidateRules(selectedKey, "candidate"),
            api.listCandidateRules(selectedKey, "approved"),
          ]);
          if (cancelled) return;
          const candidates = [...pending, ...approved];
          const rules = candidates.map((candidate) => candidate.rule);
          const lookup = new Map<string, QualityRuleRecord[]>();
          candidates.forEach((candidate) => {
            addRuleReference(lookup, candidate.id, candidate.rule, candidate.id);
            addRuleReference(lookup, candidate.rule.rule_id, candidate.rule, candidate.id);
          });
          setFindingRules(rules);
          setFindingRuleLookup(lookup);
          setFindingVersions([]);
          setFindingVersion(null);
          return;
        }

        const versions = await api.listPolicyVersions(selectedKey);
        const version =
          versions.find((item) => item.version_number === report.version_number) ??
          versions.find((item) => item.is_active) ??
          null;
        const rules = version ? await api.getVersionRules(selectedKey, version.id) : [];
        if (cancelled) return;
        setFindingVersions(versions);
        setFindingVersion(version);
        setFindingRules(rules);
        const lookup = new Map<string, QualityRuleRecord[]>();
        rules.forEach((rule, index) =>
          addRuleReference(
            lookup,
            rule.rule_id,
            rule,
            `${version?.id ?? "published"}:${rule.rule_id}:${rule.rule_revision}:${index}`,
          ),
        );
        setFindingRuleLookup(lookup);
      } catch (caught) {
        if (cancelled) return;
        setFindingContextError(caught instanceof PolicyPlatformApiError ? caught.detail : String(caught));
        setFindingRules([]);
        setFindingRuleLookup(new Map());
        setFindingVersions([]);
        setFindingVersion(null);
      } finally {
        if (!cancelled) setFindingContextLoading(false);
      }
    };

    void loadFindingContext();
    return () => {
      cancelled = true;
    };
  }, [report, scope, selectedKey]);

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

  const affectedPolicyCount = useMemo(
    () => new Set((report?.findings ?? []).flatMap((finding) => finding.affected_rule_ids)).size,
    [report],
  );
  const aiFindingCount = (report?.findings ?? []).filter((finding) => finding.source === "ai_review").length;
  const confirmedFindingCount = (report?.findings ?? []).length - aiFindingCount;
  const categoryCounts = (report?.findings ?? []).reduce(
    (acc, finding) => {
      acc[finding.category] = (acc[finding.category] ?? 0) + 1;
      return acc;
    },
    {} as Record<string, number>,
  );
  const leadingCategory = Object.entries(categoryCounts).sort((a, b) => b[1] - a[1])[0];

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
        Quality answers one question: <Text strong>what prevents this exact policy version from being relied on?</Text>{" "}
        Deterministic findings are confirmed structural checks. AI findings are potential gaps, conflicts, or risks
        that must be confirmed against the canonical policies and source evidence before they are treated as defects.
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
                It records the result, so the history below can compare this run against the one before it.
              </Text>
            </div>
            <details className="quality-methodology">
              <summary>How the quality evaluation works and what counts as acceptable</summary>
              <div>
                <article>
                  <strong>Deterministic checks</strong>
                  <span>
                    Confirm duplicate IDs, invalid decision shapes, ambiguity flags, expired rules,
                    conflicting formal effects, and review backlog from stored policy data. Each record is
                    also read against the route it takes: one sent to the engine has to name facts the
                    engine can resolve, and one decided by reading has to say enough for a judge to decide
                    it.
                  </span>
                </article>
                <article>
                  <strong>AI qualitative analysis</strong>
                  <span>
                    Looks for potential gaps, overlaps, missing exceptions, and governance risks using condition, scope,
                    outcome, exception, priority, effective-window, override, and source context. Every result still
                    requires human confirmation.
                  </span>
                </article>
                <article>
                  <strong>Disposition standard</strong>
                  <span>
                    A finding is acceptable only when the scenario is impossible, intentionally manual, or explicitly
                    resolved by scope or precedence. Otherwise assign an owner and correct or formally accept the risk.
                  </span>
                </article>
              </div>
            </details>
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
                  // A trend is meaningful only when both runs used the same
                  // quality method. Prompt/schema upgrades change what can be
                  // discovered, so they establish a new baseline rather than
                  // masquerading as policy improvement or regression.
                  const prior = history
                    .slice(idx + 1)
                    .find(
                      (candidate) =>
                        candidate.scope === run.scope &&
                        candidate.methodology_version === run.methodology_version,
                    );
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
                        {` · method v${run.methodology_version}`}
                      </span>
                      <span className="quality-history-counts">
                        <Tag color="red">{run.high_count} high</Tag>
                        <Tag color="gold">{run.medium_count} med</Tag>
                        <Tag>{run.low_count} low</Tag>
                      </span>
                      {delta === null ? (
                        <Tag className="quality-history-delta">method baseline</Tag>
                      ) : (
                        <Tooltip title={`Previous comparable run had ${prior?.finding_count ?? 0} findings`}>
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
              className="quality-historic-banner"
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

          {notEvaluated && !loading && (
            <Alert
              className="quality-historic-banner"
              type="info"
              showIcon
              message="No evaluation recorded yet"
              description={`${notEvaluated} Until then this page has nothing to report — which is not the same as reporting that there is nothing wrong.`}
              action={
                <Button size="small" type="primary" onClick={runEvaluation} disabled={runDisabled}>
                  Run the first evaluation
                </Button>
              }
            />
          )}

          {report && (
            <>
              <section className="quality-report-summary">
                <div className="quality-report-reading">
                 <strong>
                   {(counts.high ?? 0) > 0
                     ? `${counts.high} high-priority finding${counts.high === 1 ? "" : "s"} need a policy decision`
                     : "No high-priority findings in this evaluation"}
                 </strong>
                 <span>
                   {leadingCategory && leadingCategory[1] > 1
                     ? `${formatCategory(leadingCategory[0])} is the most frequent pattern (${leadingCategory[1]}). `
                     : `${Object.keys(categoryCounts).length} distinct quality pattern${Object.keys(categoryCounts).length === 1 ? "" : "s"}. `}
                   {confirmedFindingCount > 0
                     ? `${confirmedFindingCount} confirmed structural check${confirmedFindingCount === 1 ? "" : "s"} · `
                     : ""}
                   {aiFindingCount > 0
                     ? `${aiFindingCount} potential AI finding${aiFindingCount === 1 ? "" : "s"} require human confirmation.`
                     : "Only deterministic checks contributed findings."}
                 </span>
                </div>
                <dl aria-label="Quality evaluation summary">
                 <div>
                   <dt>{report.scope === "candidates" ? "Candidates checked" : `Rules in v${report.version_number}`}</dt>
                   <dd>{report.rule_count}</dd>
                 </div>
                 <div className={(counts.high ?? 0) > 0 ? "is-high" : undefined}>
                   <dt>High</dt>
                   <dd>{counts.high ?? 0}</dd>
                 </div>
                 <div className={(counts.medium ?? 0) > 0 ? "is-medium" : undefined}>
                   <dt>Medium</dt>
                   <dd>{counts.medium ?? 0}</dd>
                 </div>
                 <div>
                   <dt>Low</dt>
                   <dd>{counts.low ?? 0}</dd>
                 </div>
                 <div>
                   <dt>Policies referenced</dt>
                   <dd>{affectedPolicyCount}</dd>
                 </div>
                 <div>
                   <dt>AI to confirm</dt>
                   <dd>{aiFindingCount}</dd>
                 </div>
                </dl>
              </section>

              <div className="quality-findings-toolbar">
                <Title level={5}>
                  Findings ({findings.length})
                </Title>
                <Space className="quality-findings-filters">
                  <Select
                    value={severityFilter}
                    onChange={setSeverityFilter}
                   className="quality-filter-select"
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
                   className="quality-filter-select"
                    options={[
                      { value: "all", label: "All sources" },
                      { value: "deterministic", label: "Deterministic" },
                      { value: "ai_review", label: "AI review" },
                    ]}
                  />
                </Space>
              </div>

              {findings.length > 0 ? (
               <div className="quality-finding-register">
                 <div className="quality-finding-register-head" aria-hidden="true">
                   <span>Risk</span>
                   <span>What the evaluation found</span>
                   <span>Affected policies</span>
                   <span>Recommended decision</span>
                   <span>Evidence</span>
                 </div>
                 {findings.map((finding: QualityFinding, index: number) => {
                   const affectedRecords = finding.affected_rule_ids.flatMap(
                     (reference) => findingRuleLookup.get(reference) ?? [],
                   );
                   const affectedTitles = affectedRecords.map((record) => record.rule.title);
                   const affectedLabel =
                     affectedRecords.length > finding.affected_rule_ids.length
                       ? `${affectedRecords.length} records`
                       : finding.affected_rule_ids.length > 0
                         ? `${finding.affected_rule_ids.length} polic${finding.affected_rule_ids.length === 1 ? "y" : "ies"}`
                         : "Policy-set level";
                   return (
                     <button
                       key={`${finding.category}:${index}`}
                       type="button"
                       className="quality-finding-row"
                       onClick={() => setFindingPreview(finding)}
                       aria-label={`Review ${formatCategory(finding.category)} finding`}
                     >
                       <span className="quality-finding-row-risk">
                         <Tag color={SEVERITY_COLOR[finding.severity] ?? "default"}>
                           {finding.severity.toUpperCase()}
                         </Tag>
                         <small>
                           {finding.source === "ai_review" ? <ThunderboltOutlined /> : null}
                           {finding.source === "ai_review" ? "Potential · confirm" : "Confirmed check"}
                         </small>
                       </span>
                       <span className="quality-finding-row-copy">
                         {finding.summary && <em>{formatCategory(finding.category)}</em>}
                         <strong>{finding.summary || formatCategory(finding.category)}</strong>
                         <small>{finding.finding}</small>
                       </span>
                       <span className="quality-finding-row-policies">
                         <strong>
                           {affectedLabel}
                         </strong>
                         <small>
                           {affectedTitles.length > 0
                             ? `${affectedTitles.slice(0, 2).join(" · ")}${affectedTitles.length > 2 ? ` +${affectedTitles.length - 2}` : ""}`
                             : finding.affected_rule_ids.slice(0, 2).join(" · ") || "No single record"}
                         </small>
                       </span>
                       <span className="quality-finding-row-action">
                         <strong>Suggested correction</strong>
                         <small>{finding.recommendation || "Review the finding evidence and document the intended behavior."}</small>
                       </span>
                       <span className="quality-finding-row-open">
                         Review evidence <RightOutlined />
                       </span>
                     </button>
                   );
                 })}
               </div>
              ) : (
               <div className="quality-findings-empty">
                 <Text type="secondary">No findings match this filter.</Text>
               </div>
              )}
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
      {selectedKey && (
        <QualityFindingDrawer
          finding={findingPreview}
          onClose={() => setFindingPreview(null)}
          policySetKey={selectedKey}
          reportScope={(report?.scope ?? scope) as "published" | "candidates"}
          runAt={reportEvaluatedAt}
          version={findingVersion}
          versions={findingVersions}
          allRules={findingRules}
          ruleLookup={findingRuleLookup}
          loading={findingContextLoading}
          error={findingContextError}
        />
      )}
    </>
  );
}
