import { useEffect, useMemo, useState } from "react";
import { Alert, App, Button, Checkbox, Descriptions, Drawer, Input, Segmented, Select, Slider, Tabs, Tag, Typography } from "antd";
import {
  CheckCircleOutlined,
  ExperimentOutlined,
  HistoryOutlined,
  ArrowLeftOutlined,
  ArrowRightOutlined,
  PlayCircleOutlined,
  ReadOutlined,
  SafetyCertificateOutlined,
  SearchOutlined,
  StopOutlined,
  ThunderboltOutlined,
  WarningOutlined,
} from "@ant-design/icons";
import {
  aiApi,
  api,
  policyTestApi,
  PolicyPlatformApiError,
  type ApprovedPolicyVersion,
  type CanonicalRule,
  type Clause,
  type PolicyTestListItem,
  type PolicyTestBatch,
  type PolicyTestGroundingMode,
} from "../api";
import { useActor } from "../ActorContext";
import { PolicyEffectBadge } from "./PolicyEffectBadge";
import { PolicyInspector } from "./PolicyInspector";
import { JsonView } from "./JsonView";
import { ruleDecisionSummary } from "../ruleDisplay";
import { resolveClausesById } from "../clauseCache";
import { DETERMINISTIC_LABEL } from "../ruleExecutability";

const { Title, Text, Paragraph } = Typography;
const { TextArea } = Input;

type ReasoningEffort = "low" | "medium" | "high";

const GROUNDING_LABEL: Record<PolicyTestGroundingMode, string> = {
  json_only: "Complete policy JSON only",
  json_search: "Policy JSON + hybrid Azure AI Search",
};

function actualStatus(batch: PolicyTestBatch, testId: string): string {
  const item = batch.tests.find((entry) => entry.test.id === testId);
  return item?.latest_run?.actual_response_json?.overall_status ?? "NO RESULT";
}

function displayFactValue(value: unknown): string {
  if (typeof value === "string") return value;
  if (value === null) return "null";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function displayEvaluationStatus(value: string): string {
  return value.replaceAll("_", " ");
}

export function PolicyValidationLab({
  policySetKey,
  mode = "tests",
}: {
  policySetKey: string;
  mode?: "tests" | "regression";
}) {
  const { message } = App.useApp();
  const { actor } = useActor();
  const [versions, setVersions] = useState<ApprovedPolicyVersion[]>([]);
  const [versionId, setVersionId] = useState<string | null>(null);
  const [runVersionId, setRunVersionId] = useState<string | null>(null);
  const [suiteVersionId, setSuiteVersionId] = useState<string | null>(null);
  const [rules, setRules] = useState<CanonicalRule[]>([]);
  const [rulesByVersionId, setRulesByVersionId] = useState<Record<string, CanonicalRule[]>>({});
  const [batches, setBatches] = useState<PolicyTestBatch[]>([]);
  const [regressionTests, setRegressionTests] = useState<PolicyTestListItem[]>([]);
  const [retiredRegressionTests, setRetiredRegressionTests] = useState<PolicyTestListItem[]>([]);
  const [selectedRuleIds, setSelectedRuleIds] = useState<Set<string>>(new Set());
  const [activeBatchId, setActiveBatchId] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [ruleTypeFilter, setRuleTypeFilter] = useState("all");
  const [effectFilter, setEffectFilter] = useState("all");
  const [groundingMode, setGroundingMode] = useState<PolicyTestGroundingMode>("json_only");
  const [authoringMode, setAuthoringMode] = useState<"generated" | "authored">("generated");
  const [authoredScenario, setAuthoredScenario] = useState("");
  const [testsPerPolicy, setTestsPerPolicy] = useState(3);
  const [reasoningEffort, setReasoningEffort] = useState<ReasoningEffort>("medium");
  const [guidance, setGuidance] = useState("");
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [running, setRunning] = useState(false);
  const [activating, setActivating] = useState(false);
  const [suiteRunning, setSuiteRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searchEnabled, setSearchEnabled] = useState(false);
  const [policyPreview, setPolicyPreview] = useState<CanonicalRule | null>(null);
  const [policyPreviewTab, setPolicyPreviewTab] = useState("overview");
  const [testPreview, setTestPreview] = useState<PolicyTestListItem | null>(null);
  const [previewSourceClauses, setPreviewSourceClauses] = useState<Clause[]>([]);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [publishedVersions, batchHistory, allTests, aiStatus] = await Promise.all([
        api.listPolicyVersions(policySetKey),
        policyTestApi.listBatches(policySetKey),
        policyTestApi.list(policySetKey),
        aiApi.status(),
      ]);
      const ordered = [...publishedVersions].sort((a, b) => b.version_number - a.version_number);
      const active = ordered.find((version) => version.is_active) ?? ordered[0] ?? null;
      setVersions(ordered);
      setVersionId((current) =>
        current && ordered.some((version) => version.id === current) ? current : active?.id ?? null,
      );
      setRunVersionId((current) =>
        current && ordered.some((version) => version.id === current) ? current : active?.id ?? null,
      );
      setSuiteVersionId((current) =>
        current && ordered.some((version) => version.id === current) ? current : active?.id ?? null,
      );
      setBatches(batchHistory);
      setRegressionTests(allTests.filter((item) => item.test.is_active));
      setRetiredRegressionTests(
        allTests.filter((item) => !item.test.is_active && item.test.review_status === "rejected"),
      );
      setSearchEnabled(aiStatus.search_enabled);
      if (!activeBatchId && batchHistory.length > 0) setActiveBatchId(batchHistory[0].id);
    } catch (caught) {
      setError(caught instanceof PolicyPlatformApiError ? caught.detail : String(caught));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [policySetKey]);

  useEffect(() => {
    if (!versionId) {
      setRules([]);
      return;
    }
    let cancelled = false;
    setLoading(true);
    api
      .getVersionRules(policySetKey, versionId)
      .then((versionRules) => {
        if (cancelled) return;
        setRules(versionRules);
        setRulesByVersionId((current) => ({ ...current, [versionId]: versionRules }));
        setSelectedRuleIds(new Set());
      })
      .catch((caught) => {
        if (!cancelled) setError(caught instanceof PolicyPlatformApiError ? caught.detail : String(caught));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [policySetKey, versionId]);

  useEffect(() => {
    const referencedVersionIds = Array.from(
      new Set(
        [
          ...batches.flatMap((batch) => [
            batch.policy_version_id,
            ...batch.tests.flatMap((item) =>
              item.latest_run?.policy_version_id ? [item.latest_run.policy_version_id] : [],
            ),
          ]),
          ...regressionTests.flatMap((item) =>
            item.latest_run?.policy_version_id ? [item.latest_run.policy_version_id] : [],
          ),
          ...retiredRegressionTests.flatMap((item) =>
            item.latest_run?.policy_version_id ? [item.latest_run.policy_version_id] : [],
          ),
        ].filter(Boolean),
      ),
    );
    if (referencedVersionIds.length === 0) return;
    let cancelled = false;
    void Promise.all(
      referencedVersionIds.map(async (referencedVersionId) => [
        referencedVersionId,
        await api.getVersionRules(policySetKey, referencedVersionId),
      ] as const),
    )
      .then((entries) => {
        if (!cancelled) {
          setRulesByVersionId((current) => ({ ...current, ...Object.fromEntries(entries) }));
        }
      })
      .catch((caught) => {
        if (!cancelled) setError(caught instanceof PolicyPlatformApiError ? caught.detail : String(caught));
      });
    return () => {
      cancelled = true;
    };
  }, [batches, policySetKey, regressionTests, retiredRegressionTests]);

  const selectedVersion = versions.find((version) => version.id === versionId) ?? null;
  const executableRules = useMemo(
    () => rules.filter((rule) => rule.machine_executable && rule.rule_type !== "definition"),
    [rules],
  );
  const excludedDefinitionCount = rules.filter((rule) => rule.rule_type === "definition").length;
  const excludedDocumentationCount = rules.filter(
    (rule) => rule.rule_type !== "definition" && !rule.machine_executable,
  ).length;
  const ruleTypeOptions = useMemo(
    () => Array.from(new Set(executableRules.map((rule) => rule.rule_type))).sort(),
    [executableRules],
  );
  const visibleRules = useMemo(() => {
    const query = search.trim().toLowerCase();
    return executableRules.filter((rule) => {
      if (ruleTypeFilter !== "all" && rule.rule_type !== ruleTypeFilter) return false;
      if (effectFilter !== "all" && rule.effect.type !== effectFilter) return false;
      if (!query) return true;
      return (
        rule.title.toLowerCase().includes(query) ||
        rule.rule_id.toLowerCase().includes(query) ||
        rule.effect.action.toLowerCase().includes(query)
      );
    });
  }, [executableRules, search, ruleTypeFilter, effectFilter]);
  const exactRulesForVersion = (requestedVersionId: string | null | undefined): CanonicalRule[] | null => {
    if (!requestedVersionId) return null;
    if (rulesByVersionId[requestedVersionId]) return rulesByVersionId[requestedVersionId];
    return versionId === requestedVersionId ? rules : null;
  };
  const activeBatch = batches.find((batch) => batch.id === activeBatchId) ?? null;
  const executed = activeBatch?.status === "executed";
  const passingTests = activeBatch?.tests.filter((item) => item.latest_run?.status === "pass") ?? [];
  const failingTests = activeBatch?.tests.filter((item) => item.latest_run?.status === "fail") ?? [];
  const erroredTests = activeBatch?.tests.filter((item) => item.latest_run?.status === "error") ?? [];
  const activePassing = passingTests.filter((item) => item.test.review_status === "active");
  const runTargetVersion = versions.find((version) => version.id === runVersionId) ?? null;
  const latestProofVersionId =
    activeBatch?.tests.find((item) => item.latest_run?.policy_version_id)?.latest_run?.policy_version_id ??
    activeBatch?.policy_version_id ??
    null;
  const latestProofVersion =
    versions.find((version) => version.id === latestProofVersionId) ?? null;
  const allCurrentRunsPass =
    !!activeBatch && activeBatch.tests.length > 0 && passingTests.length === activeBatch.tests.length;
  const regressionPassing = regressionTests.filter((item) => item.latest_run?.status === "pass").length;
  const regressionFailing = regressionTests.filter((item) => item.latest_run?.status === "fail").length;
  const regressionErrors = regressionTests.filter((item) => item.latest_run?.status === "error").length;
  const regressionNeverRun = regressionTests.filter((item) => !item.latest_run).length;
  const previewRun = testPreview?.latest_run ?? null;
  const previewBatch = batches.find((batch) =>
    batch.tests.some((item) => item.test.id === testPreview?.test.id),
  ) ?? null;
  const previewRunVersion = versions.find((version) => version.id === previewRun?.policy_version_id) ?? null;
  const previewVersionId =
    previewRun?.policy_version_id ?? previewBatch?.policy_version_id ?? versionId;
  const previewRules = exactRulesForVersion(previewVersionId);
  const previewExpectation = previewRun?.expected_assertions_json ?? null;
  const previewResponse = previewRun?.actual_response_json ?? null;
  const previewRule =
    previewRules?.find((rule) => rule.rule_id === testPreview?.test.expected_rule_id) ?? null;
  const policyPreviewVersionId = testPreview ? previewVersionId : versionId;
  const policyPreviewRules = exactRulesForVersion(policyPreviewVersionId) ?? [];
  const policyPreviewVersion =
    versions.find((version) => version.id === policyPreviewVersionId) ?? null;
  const previewRuleResult = previewResponse?.rule_results.find(
    (result) => result.rule_id === testPreview?.test.expected_rule_id,
  );
  const previewActualRuleStatus =
    previewRuleResult?.status ??
    (previewRule &&
    testPreview?.test.expected_rule_status === "NOT_APPLICABLE" &&
    !previewResponse?.applicable_rules.includes(previewRule.rule_id)
      ? "NOT_APPLICABLE"
      : "NOT RETURNED");

  useEffect(() => {
    if (!previewRule) {
      setPreviewSourceClauses([]);
      return;
    }
    let cancelled = false;
    const versionIds = previewRule.evidence.map((evidence) => evidence.document_version_id);
    void resolveClausesById(versionIds).then((clausesById) => {
      if (cancelled) return;
      setPreviewSourceClauses(
        previewRule.evidence
          .map((evidence) => (evidence.clause_id ? clausesById.get(evidence.clause_id) : undefined))
          .filter((clause): clause is Clause => !!clause),
      );
    });
    return () => {
      cancelled = true;
    };
  }, [previewRule]);

  useEffect(() => {
    if (activeBatch) {
      const latestExecutedVersionId = activeBatch.tests.find(
        (item) => item.latest_run?.policy_version_id,
      )?.latest_run?.policy_version_id;
      setRunVersionId(latestExecutedVersionId ?? activeBatch.policy_version_id);
    }
  }, [activeBatchId, activeBatch]);

  const toggleRule = (ruleId: string) => {
    setSelectedRuleIds((current) => {
      const next = new Set(current);
      if (next.has(ruleId)) next.delete(ruleId);
      else if (next.size < 12) next.add(ruleId);
      else message.warning("Select at most 12 policies for one validation batch.");
      return next;
    });
  };

  const requireActor = (action: string): boolean => {
    if (actor.name.trim()) return true;
    message.warning(`Set your name in the application header before ${action}.`);
    return false;
  };

  const generate = async () => {
    if (selectedRuleIds.size === 0) {
      message.warning("Select at least one policy the engine evaluates by comparison.");
      return;
    }
    if (!requireActor("generating a validation batch")) return;
    if (authoringMode === "authored" && selectedRuleIds.size !== 1) {
      message.warning("Select exactly one policy for a reviewer-authored scenario.");
      return;
    }
    if (authoringMode === "authored" && !authoredScenario.trim()) {
      message.warning("Write the scenario statement you want to test.");
      return;
    }
    setGenerating(true);
    setError(null);
    try {
      const batch = await policyTestApi.generateBatch(policySetKey, {
        rule_ids: Array.from(selectedRuleIds),
        tests_per_policy: authoringMode === "authored" ? 1 : testsPerPolicy,
        policy_version_id: versionId ?? undefined,
        scenario_text: authoringMode === "authored" ? authoredScenario.trim() : undefined,
        grounding_mode: groundingMode,
        reasoning_effort: reasoningEffort,
        guidance,
        created_by: actor.name,
      });
      setBatches((current) => [batch, ...current.filter((item) => item.id !== batch.id)]);
      setActiveBatchId(batch.id);
      message.success(
        authoringMode === "authored"
          ? "Your scenario was translated into facts and its expectation was sealed."
          : `${batch.tests.length} blind scenarios generated and expectations sealed.`,
      );
    } catch (caught) {
      setError(caught instanceof PolicyPlatformApiError ? caught.detail : String(caught));
    } finally {
      setGenerating(false);
    }
  };

  const runBatch = async () => {
    if (!activeBatch) return;
    if (!requireActor("running validation evidence")) return;
    setRunning(true);
    setError(null);
    try {
      const updated = await policyTestApi.runBatch(activeBatch.id, actor.name, runVersionId ?? undefined);
      setBatches((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      const version = versions.find((item) => item.id === runVersionId);
      message.success(
        `Blind run complete against v${version?.version_number ?? "?"}. Expected and actual outcomes are now revealed.`,
      );
    } catch (caught) {
      setError(caught instanceof PolicyPlatformApiError ? caught.detail : String(caught));
    } finally {
      setRunning(false);
    }
  };

  const activatePassing = async () => {
    if (!activeBatch) return;
    if (!requireActor("adding regression guards")) return;
    const targets = passingTests.filter((item) => item.test.review_status === "pending_review");
    if (targets.length === 0) return;
    setActivating(true);
    setError(null);
    try {
      for (const item of targets) {
        await policyTestApi.review(item.test.id, "accept", actor.name, `Accepted from blind batch ${activeBatch.id}`);
      }
      await load();
      message.success(
        `${targets.length} verified scenario${targets.length === 1 ? "" : "s"} added to the regression suite. They will re-run automatically against every future published version and surface failures under Quality; they do not block publishing.`,
      );
    } catch (caught) {
      setError(caught instanceof PolicyPlatformApiError ? caught.detail : String(caught));
    } finally {
      setActivating(false);
    }
  };

  const runRegressionSuite = async () => {
    if (regressionTests.length === 0 || !suiteVersionId) return;
    if (!requireActor("running the regression suite")) return;
    setSuiteRunning(true);
    setError(null);
    try {
      for (const item of regressionTests) {
        await policyTestApi.run(item.test.id, actor.name, suiteVersionId);
      }
      await load();
      const version = versions.find((item) => item.id === suiteVersionId);
      message.success(`Regression suite completed against v${version?.version_number ?? "?"}.`);
    } catch (caught) {
      setError(caught instanceof PolicyPlatformApiError ? caught.detail : String(caught));
    } finally {
      setSuiteRunning(false);
    }
  };

  const setRegressionGuardActive = async (item: PolicyTestListItem, active: boolean) => {
    if (!requireActor(active ? "reactivating a regression guard" : "retiring a regression guard")) return;
    setError(null);
    try {
      await policyTestApi.review(
        item.test.id,
        active ? "accept" : "reject",
        actor.name,
        active ? "Reactivated from Regression workspace" : "Retired from Regression workspace",
      );
      await load();
      message.success(active ? "Regression guard reactivated." : "Regression guard retired.");
    } catch (caught) {
      setError(caught instanceof PolicyPlatformApiError ? caught.detail : String(caught));
    }
  };

  const openTestPreview = async (item: PolicyTestListItem) => {
    setTestPreview(item);
    try {
      const runs = await policyTestApi.listRuns(item.test.id);
      setTestPreview((current) =>
        current?.test.id === item.test.id ? { ...current, runs } : current,
      );
    } catch {
      // Latest run remains visible; history is supplementary.
    }
  };

  return (
    <div className="validation-lab">
      {mode === "regression" ? (
        <>
          <header className="page-header-row validation-lab-header validation-regression-header">
            <div>
              <Title level={3}>Regression suite</Title>
              <Text type="secondary">
                Manage active scenario guards, run the complete suite against any published policy version, and inspect
                immutable evidence from every run.
              </Text>
            </div>
            <div className={`validation-regression-header-state${regressionFailing + regressionErrors > 0 ? " is-risk" : ""}`}>
              <span>
                {regressionFailing + regressionErrors > 0 ? <WarningOutlined /> : <SafetyCertificateOutlined />}
              </span>
              <div>
                <strong>{regressionTests.length} active guards</strong>
                <small>
                  {regressionFailing + regressionErrors > 0
                    ? `${regressionFailing + regressionErrors} need review`
                    : "No failing guard evidence"}
                </small>
              </div>
            </div>
          </header>

          {error && <Alert type="error" showIcon message={error} closable onClose={() => setError(null)} />}
          {!actor.name.trim() && (
            <div className="validation-actor-warning">
              <WarningOutlined />
              <span>Set your name in the application header to run or manage regression evidence.</span>
            </div>
          )}

          <section className="validation-surface validation-regression-suite is-workspace">
            <div className="validation-regression-brief">
              <div className="validation-regression-brief-heading">
                <span className="validation-regression-brief-icon"><SafetyCertificateOutlined /></span>
                <div>
                  <Title level={4}>Continuous behavior proof for published policies</Title>
                  <Text type="secondary">
                    Every active guard is a previously verified scenario. Publishing re-runs it automatically; manual
                    suite runs compare the same committed expectations against any retained version.
                  </Text>
                </div>
              </div>
              <dl aria-label="Regression evidence summary">
                <div>
                  <dt>Active guards</dt>
                  <dd>{regressionTests.length}</dd>
                </div>
                <div className={regressionPassing > 0 ? "is-pass" : undefined}>
                  <dt>Passing</dt>
                  <dd>{regressionPassing}</dd>
                </div>
                <div className={regressionFailing > 0 ? "is-fail" : undefined}>
                  <dt>Failing</dt>
                  <dd>{regressionFailing}</dd>
                </div>
                <div className={regressionErrors > 0 ? "is-error" : undefined}>
                  <dt>Errors</dt>
                  <dd>{regressionErrors}</dd>
                </div>
                <div>
                  <dt>Never run</dt>
                  <dd>{regressionNeverRun}</dd>
                </div>
                <div>
                  <dt>Retired</dt>
                  <dd>{retiredRegressionTests.length}</dd>
                </div>
              </dl>
            </div>
            <div className="validation-surface-header">
              <div>
                <Text strong><SafetyCertificateOutlined /> Active guard evidence</Text>
                <Text type="secondary">
                  Committed expectations, latest versioned outcome, and immutable run history
                </Text>
              </div>
              <div className="validation-suite-actions">
                <Select
                  value={suiteVersionId ?? undefined}
                  onChange={setSuiteVersionId}
                  options={versions.map((version) => ({
                    value: version.id,
                    label: `Run suite against v${version.version_number}${version.is_active ? " · active" : ""}`,
                  }))}
                />
                <Button
                  type="primary"
                  icon={<PlayCircleOutlined />}
                  loading={suiteRunning}
                  disabled={regressionTests.length === 0 || !suiteVersionId || !actor.name.trim()}
                  onClick={runRegressionSuite}
                >
                  Run suite now
                </Button>
              </div>
            </div>
            {regressionTests.length > 0 ? (
              <div className="validation-suite-register">
                <div className="validation-suite-head">
                  <span>Scenario guard</span>
                  <span>Policy</span>
                  <span>Last result</span>
                  <span>Version</span>
                  <span>Last run</span>
                  <span>Actions</span>
                </div>
                {regressionTests.map((item) => {
                  const latest = item.latest_run;
                  const version = versions.find((entry) => entry.id === latest?.policy_version_id);
                  const evidenceRules = latest?.policy_version_id
                    ? exactRulesForVersion(latest.policy_version_id)
                    : null;
                  const rule = evidenceRules?.find((entry) => entry.rule_id === item.test.expected_rule_id);
                  const decision = rule ? ruleDecisionSummary(rule) : null;
                  return (
                    <div
                      key={item.test.id}
                      className="validation-suite-row"
                    >
                      <span>
                        <strong>{item.test.name}</strong>
                        <small>{item.test.scenario_text || item.test.description}</small>
                      </span>
                      <span>
                        <strong>
                          {rule?.title ??
                            (evidenceRules ? item.test.expected_rule_id : "Policy record loading…") ??
                            "Policy subset"}
                        </strong>
                        <small>
                          {decision?.text ??
                            `${item.test.expected_rule_id ?? "Multiple policies"} · v${version?.version_number ?? "?"}`}
                        </small>
                      </span>
                      <Tag color={!latest ? "default" : latest.status === "pass" ? "green" : latest.status === "fail" ? "red" : "orange"}>
                        {latest?.status.toUpperCase() ?? "NEVER RUN"}
                      </Tag>
                      <span>v{version?.version_number ?? "—"}</span>
                      <span>{latest ? new Date(latest.run_at).toLocaleString() : "—"}</span>
                      <span className="validation-suite-row-actions">
                        <Button
                          type="link"
                          size="small"
                          icon={<ReadOutlined />}
                          onClick={() => void openTestPreview(item)}
                        >
                          Review evidence
                        </Button>
                        <Button
                          type="text"
                          size="small"
                          danger
                          icon={<StopOutlined />}
                          disabled={!actor.name.trim()}
                          onClick={() => void setRegressionGuardActive(item, false)}
                        >
                          Retire
                        </Button>
                      </span>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="validation-suite-empty">
                <CheckCircleOutlined />
                <span>
                  <strong>No active regression guards yet</strong>
                  <small>
                    Open Tests, run a blind batch, then add passing scenarios. Verified guards appear here and re-run on
                    every future publish.
                  </small>
                </span>
              </div>
            )}
            {retiredRegressionTests.length > 0 && (
              <details className="validation-retired-register">
                <summary>
                  <HistoryOutlined /> Retired guard history <Tag>{retiredRegressionTests.length}</Tag>
                </summary>
                <Text type="secondary">
                  Retired guards remain in immutable history but no longer run automatically after publication.
                </Text>
                <div>
                  {retiredRegressionTests.map((item) => (
                    <div key={item.test.id}>
                      <span>
                        <strong>{item.test.name}</strong>
                        <small>{item.test.scenario_text || item.test.description}</small>
                      </span>
                      <span className="validation-retired-actions">
                        <Button type="link" size="small" icon={<ReadOutlined />} onClick={() => void openTestPreview(item)}>
                          Review evidence
                        </Button>
                        <Button
                          type="text"
                          size="small"
                          disabled={!actor.name.trim()}
                          onClick={() => void setRegressionGuardActive(item, true)}
                        >
                          Reactivate
                        </Button>
                      </span>
                    </div>
                  ))}
                </div>
              </details>
            )}
          </section>
        </>
      ) : (
        <>
      <header className="page-header-row validation-lab-header">
        <div>
          <Title level={3}>Policy validation lab</Title>
          <Text type="secondary">
            Select exact published policies, generate sealed scenarios, run them blind through the deterministic engine,
            then reveal and preserve the comparison.
          </Text>
        </div>
        <div className="validation-version-control">
          <span>Generate from</span>
          <Select
            value={versionId ?? undefined}
            onChange={setVersionId}
            options={versions.map((version) => ({
              value: version.id,
              label: `v${version.version_number}${version.is_active ? " · active" : ""} · ${version.rule_count} rules`,
            }))}
          />
        </div>
      </header>

      {error && <Alert type="error" showIcon message={error} closable onClose={() => setError(null)} />}

      <div className="validation-steps" aria-label="Validation workflow">
        <div className={selectedRuleIds.size > 0 ? "is-complete" : "is-current"}>
          <strong>1</strong><span>Select policies</span>
        </div>
        <div className={activeBatch ? "is-complete" : selectedRuleIds.size > 0 ? "is-current" : ""}>
          <strong>2</strong><span>Generate & seal</span>
        </div>
        <div className={executed ? "is-complete" : activeBatch ? "is-current" : ""}>
          <strong>3</strong><span>Run blind</span>
        </div>
        <div className={executed ? "is-current" : ""}>
          <strong>4</strong><span>Reveal & preserve</span>
        </div>
      </div>

      <div className="validation-config-grid validation-workbench">
        <section className="validation-workbench-pane validation-policy-selector">
          <div className="validation-workbench-header">
            <div>
              <Text strong>Policies under test</Text>
              <Text type="secondary">
                {selectedRuleIds.size} selected · {executableRules.length} testable · {excludedDefinitionCount} definitions excluded ·{" "}
                {excludedDocumentationCount} not testable by the deterministic engine
              </Text>
            </div>
            <Button
              size="small"
              onClick={() => setSelectedRuleIds(new Set(executableRules.slice(0, 12).map((rule) => rule.rule_id)))}
              disabled={executableRules.length === 0}
            >
              Select deterministic
            </Button>
          </div>
          <div className="validation-workbench-body">
            <div className="validation-policy-filters">
              <Input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                prefix={<SearchOutlined />}
                placeholder="Find a policy by title, ID, or action"
                allowClear
              />
              <Select
                value={ruleTypeFilter}
                onChange={setRuleTypeFilter}
                options={[
                  { value: "all", label: "All policy types" },
                  ...ruleTypeOptions.map((value) => ({ value, label: value.replaceAll("_", " ") })),
                ]}
              />
              <Select
                value={effectFilter}
                onChange={setEffectFilter}
                options={[
                  { value: "all", label: "All effects" },
                  { value: "allow", label: "Allow" },
                  { value: "deny", label: "Deny" },
                  { value: "require_action", label: "Require action" },
                  { value: "informational", label: "Informational" },
                ]}
              />
              <Button
                onClick={() => {
                  setSearch("");
                  setRuleTypeFilter("all");
                  setEffectFilter("all");
                }}
                disabled={!search && ruleTypeFilter === "all" && effectFilter === "all"}
              >
                Clear
              </Button>
            </div>
            <Text type="secondary" className="validation-filter-summary">
              Showing {visibleRules.length} testable policies from published v{selectedVersion?.version_number ?? "—"}.
              This lab runs the policies whose test the source states as a comparison; the rest are decided by reading.
            </Text>
            <div className="validation-rule-list">
              {visibleRules.map((rule) => (
                <div
                  key={rule.rule_id}
                  className={`validation-rule-row${rule.machine_executable ? "" : " is-disabled"}`}
                  role="button"
                  tabIndex={0}
                  onClick={() => {
                    setPolicyPreviewTab("overview");
                    setPolicyPreview(rule);
                  }}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      setPolicyPreviewTab("overview");
                      setPolicyPreview(rule);
                    }
                  }}
                >
                  <Checkbox
                    checked={selectedRuleIds.has(rule.rule_id)}
                    disabled={!rule.machine_executable}
                    onChange={() => toggleRule(rule.rule_id)}
                    onClick={(event) => event.stopPropagation()}
                  />
                  <span className="validation-rule-copy">
                    <strong>{rule.title}</strong>
                    <small>
                      {rule.rule_id} · {rule.rule_type} · {rule.required_facts.length} facts · {rule.evidence.length} sources
                    </small>
                    <em>{ruleDecisionSummary(rule).text}</em>
                  </span>
                  <PolicyEffectBadge effect={rule.effect} size="small" />
                  <Tag color={rule.machine_executable ? "green" : "default"}>
                    {rule.machine_executable ? DETERMINISTIC_LABEL.yes : DETERMINISTIC_LABEL.no}
                  </Tag>
                </div>
              ))}
              {!loading && visibleRules.length === 0 && <Text type="secondary">No matching policies.</Text>}
            </div>
          </div>
        </section>

        <section className="validation-workbench-pane validation-generator">
          <div className="validation-workbench-header">
            <div>
              <Text strong>Scenario generator</Text>
              <Text type="secondary">The expected answer is committed and hidden before execution</Text>
            </div>
            <ThunderboltOutlined />
          </div>
          <div className="validation-workbench-body">
            {!actor.name.trim() && (
              <div className="validation-actor-warning">
                <WarningOutlined />
                <span>Set your name in the application header before generating or running validation evidence.</span>
              </div>
            )}
            <Text strong>How should scenarios be created?</Text>
            <Segmented
              block
              value={authoringMode}
              onChange={(value) => setAuthoringMode(value as typeof authoringMode)}
              options={[
                { value: "generated", label: "Generate combinations" },
                { value: "authored", label: "Use my scenario statement" },
              ]}
            />
            <Text strong>Grounding available to the LLM</Text>
            <Segmented
              block
              value={groundingMode}
              onChange={(value) => setGroundingMode(value as PolicyTestGroundingMode)}
              options={[
                { value: "json_only", label: "Full policy JSON" },
                {
                  value: "json_search",
                  label: "JSON + hybrid Search",
                  disabled: !searchEnabled,
                },
              ]}
            />
            <Paragraph type="secondary" className="validation-mode-help">
              {groundingMode === "json_only"
                ? "The model sees the complete canonical JSON for only the selected policies."
                : "The model sees complete selected policy JSON plus hybrid keyword/vector passages scoped to their source documents."}
            </Paragraph>

            {authoringMode === "generated" ? (
              <div className="validation-test-count">
                <div>
                  <span>Tests per selected policy</span>
                  <strong>{testsPerPolicy}</strong>
                </div>
                <Slider
                  min={0}
                  max={10}
                  step={1}
                  value={testsPerPolicy}
                  onChange={setTestsPerPolicy}
                  marks={{ 0: "0", 3: "3", 5: "5", 10: "10" }}
                  tooltip={{ formatter: (value) => `${value} tests per policy` }}
                />
                <Text type="secondary">
                  {selectedRuleIds.size === 0
                    ? "Select policies to calculate the batch size."
                    : `${selectedRuleIds.size} policies × ${testsPerPolicy} tests = ${selectedRuleIds.size * testsPerPolicy} blind scenarios`}
                </Text>
              </div>
            ) : (
              <label className="validation-authored-scenario">
                <span>Your scenario statement</span>
                <TextArea
                  value={authoredScenario}
                  onChange={(event) => setAuthoredScenario(event.target.value)}
                  autoSize={{ minRows: 4, maxRows: 8 }}
                  placeholder="Example: A device has required three repairs in the last 12 months and is no longer under warranty."
                />
                <Text type="secondary">
                  Select exactly one policy. Your wording is preserved; AI only maps it to that policy's facts and seals
                  the expected result before the deterministic run.
                </Text>
              </label>
            )}
            <div className="validation-generator-options">
              <label>
                <span>Reasoning</span>
                <Select
                  value={reasoningEffort}
                  onChange={setReasoningEffort}
                  options={[
                    { value: "low", label: "Low" },
                    { value: "medium", label: "Medium" },
                    { value: "high", label: "High" },
                  ]}
                />
              </label>
            </div>
            <TextArea
              value={guidance}
              onChange={(event) => setGuidance(event.target.value)}
              autoSize={{ minRows: 3, maxRows: 6 }}
              placeholder="Optional steer: exact risk, threshold, exception, persona, or boundary to cover"
            />
            <div className="validation-generate-footer">
              <span>
                <small>{authoringMode === "generated" ? "Batch size" : "Custom validation"}</small>
                <strong>
                  {authoringMode === "generated"
                    ? `${selectedRuleIds.size * testsPerPolicy} scenarios`
                    : "1 scenario"}
                </strong>
                <em>
                  {selectedRuleIds.size} polic{selectedRuleIds.size === 1 ? "y" : "ies"} · v
                  {selectedVersion?.version_number ?? "—"}
                </em>
              </span>
              <Button
                type="primary"
                icon={<ThunderboltOutlined />}
                loading={generating}
                disabled={
                  selectedRuleIds.size === 0 ||
                  !versionId ||
                  !actor.name.trim() ||
                  (authoringMode === "generated" && testsPerPolicy === 0) ||
                  (authoringMode === "authored" && (selectedRuleIds.size !== 1 || !authoredScenario.trim()))
                }
                onClick={generate}
              >
                {authoringMode === "generated" ? "Generate scenarios" : "Prepare scenario"}
              </Button>
            </div>
          </div>
        </section>
      </div>

      {activeBatch && (
        <section className="validation-run-report">
          <header
            className={`validation-run-masthead${
              !executed ? " is-sealed" : allCurrentRunsPass ? " is-pass" : " is-review"
            }`}
          >
            <span className="validation-run-emblem">
              {!executed ? (
                <ExperimentOutlined />
              ) : allCurrentRunsPass ? (
                <CheckCircleOutlined />
              ) : (
                <WarningOutlined />
              )}
            </span>
            <div className="validation-run-title">
              <Title level={4}>
                {!executed
                  ? "Blind validation ready"
                  : allCurrentRunsPass
                    ? "All scenarios matched"
                    : `${failingTests.length + erroredTests.length} scenario${failingTests.length + erroredTests.length === 1 ? "" : "s"} need review`}
              </Title>
              <Text type="secondary">
                Batch {activeBatch.id} · generated from v{activeBatch.version_number} ·{" "}
                {GROUNDING_LABEL[activeBatch.grounding_mode]}
              </Text>
            </div>
            <dl className="validation-run-metrics">
              <div><dt>Policies</dt><dd>{activeBatch.selected_rule_ids.length}</dd></div>
              <div><dt>Scenarios</dt><dd>{activeBatch.tests.length}</dd></div>
              <div><dt>Pass</dt><dd className="is-pass">{passingTests.length}</dd></div>
              <div><dt>Fail</dt><dd className={failingTests.length ? "is-fail" : ""}>{failingTests.length}</dd></div>
            </dl>
            <div className="validation-run-actions">
              <Select
                value={runVersionId ?? undefined}
                onChange={setRunVersionId}
                className="validation-run-version"
                options={versions.map((version) => ({
                  value: version.id,
                  label: `Run against v${version.version_number}${version.is_active ? " · active" : ""}`,
                }))}
              />
              <Button
                type="primary"
                icon={<PlayCircleOutlined />}
                loading={running}
                disabled={!actor.name.trim()}
                onClick={runBatch}
              >
                {executed ? "Run again" : "Run blind batch"}
              </Button>
            </div>
          </header>
          <div className="validation-run-guard">
            <span>
              <strong>{executed ? `Current proof · v${latestProofVersion?.version_number ?? "?"}` : "Expectations sealed"}</strong>
              <small>
                {executed
                  ? "A pass proves current behavior. Regression suite membership adds automatic future-publish reruns and Quality alerts; it never blocks publishing."
                  : "The engine receives scenario facts without expected answers. Expectations reveal only after execution."}
              </small>
            </span>
            {executed && passingTests.length > activePassing.length ? (
              <Button
                icon={<CheckCircleOutlined />}
                loading={activating}
                disabled={!actor.name.trim()}
                onClick={activatePassing}
              >
                Add {passingTests.length - activePassing.length} passing to regression suite
              </Button>
            ) : executed && activePassing.length > 0 ? (
              <Tag color="green">{activePassing.length} active regression guard{activePassing.length === 1 ? "" : "s"}</Tag>
            ) : null}
          </div>
          <div className="validation-run-body">
            <div className="validation-run-context">
              <span>Latest proof <strong>v{latestProofVersion?.version_number ?? "—"}</strong></span>
              <span>Next run target <strong>v{runTargetVersion?.version_number ?? "—"}</strong></span>
              <span>Selected policies <strong>{activeBatch.selected_rule_ids.length}</strong></span>
              <span>Grounding <strong>{activeBatch.grounding_mode === "json_only" ? "Full JSON" : "JSON + hybrid Search"}</strong></span>
              <span>Commitment <strong>SHA-256</strong></span>
            </div>
            {activeBatch.grounding_context.hits.length > 0 && (
              <details className="validation-grounding">
                <summary>
                  {activeBatch.grounding_context.hits.length} hybrid Search passages ·{" "}
                  {activeBatch.grounding_context.search_index}
                </summary>
                <div>
                  {activeBatch.grounding_context.hits.map((hit) => (
                    <span key={hit.id ?? hit.clause_id ?? hit.body}>
                      <Text code copyable={{ text: hit.id ?? "" }}>{hit.id}</Text>
                      <Text type="secondary">{hit.heading} · {hit.section_heading || hit.clause_number}</Text>
                    </span>
                  ))}
                </div>
              </details>
            )}
            <div className="validation-register" aria-label="Blind validation scenarios">
              <div className="validation-register-head" aria-hidden="true">
                <span>#</span>
                <span>Scenario evidence</span>
                <span>Expected → actual</span>
                <span>Result</span>
              </div>
              {activeBatch.selected_rule_ids.flatMap((ruleId) => {
                const groupItems = activeBatch.tests.filter((item) => item.test.expected_rule_id === ruleId);
                const groupRunVersionId = groupItems.find((item) => item.latest_run)?.latest_run?.policy_version_id;
                const groupVersionId = groupRunVersionId ?? activeBatch.policy_version_id;
                const groupVersion = versions.find((version) => version.id === groupVersionId);
                const groupRules = exactRulesForVersion(groupVersionId);
                const targetRule = groupRules?.find((rule) => rule.rule_id === ruleId);
                const passed = groupItems.filter((item) => item.latest_run?.status === "pass").length;
                return [
                  <div className="validation-register-group" key={`group:${ruleId}`}>
                    <span>
                      <strong>{targetRule?.title ?? (groupRules ? ruleId : "Policy record loading…")}</strong>
                      <small>
                        {ruleId} · {groupItems.length} scenarios · policy from v{groupVersion?.version_number ?? "?"}
                      </small>
                    </span>
                    <Tag color={!executed ? "default" : passed === groupItems.length ? "green" : "gold"}>
                      {!executed ? "SEALED" : `${passed}/${groupItems.length} pass`}
                    </Tag>
                  </div>,
                  ...groupItems.map((item) => {
                    const test = item.test;
                    const run = item.latest_run;
                    const index = activeBatch.tests.findIndex((entry) => entry.test.id === test.id);
                    const expectedStatus = run
                      ? displayEvaluationStatus(
                          run.expected_assertions_json?.expected_overall_status ??
                            test.expected_overall_status ??
                            "Any status",
                        )
                      : "Sealed";
                    const actualRunStatus = run
                      ? displayEvaluationStatus(actualStatus(activeBatch, test.id))
                      : "—";
                    const statusesMatch = run?.status === "pass";
                    return (
                      <button
                        key={test.id}
                        type="button"
                        className={`validation-register-row${run ? ` is-${run.status}` : ""}`}
                        onClick={() => void openTestPreview(item)}
                      >
                        <span className="validation-register-index">{index + 1}</span>
                        <span className="validation-register-scenario">
                          <strong>{test.name}</strong>
                          <small>{test.scenario_text || test.description}</small>
                          <span className="validation-register-facts">
                            {Object.entries(test.input_facts).map(([fact, value]) => (
                              <span key={fact}>
                                <code>{fact}</code>
                                <b>=</b>
                                <em>{displayFactValue(value)}</em>
                              </span>
                            ))}
                          </span>
                        </span>
                        <span
                          className={`validation-register-comparison${
                            !run ? "" : statusesMatch ? " is-match" : " is-mismatch"
                          }`}
                        >
                          <span>
                            <small>Expected</small>
                            <em>{expectedStatus}</em>
                          </span>
                          <ArrowRightOutlined />
                          <span>
                            <small>Actual</small>
                            <em>{actualRunStatus}</em>
                          </span>
                          {statusesMatch && <CheckCircleOutlined className="validation-register-match-icon" />}
                        </span>
                        <span>
                          <Tag color={!run ? "default" : run.status === "pass" ? "green" : run.status === "fail" ? "red" : "orange"}>
                            {!run ? "SEALED" : run.status.toUpperCase()}
                          </Tag>
                        </span>
                      </button>
                    );
                  }),
                ];
              })}
            </div>
          </div>
        </section>
      )}

      <section className="validation-surface validation-history">
        <div className="validation-surface-header">
          <div>
            <Text strong><HistoryOutlined /> Validation history</Text>
            <Text type="secondary">Every generated batch, grounding set, commitment, and engine run is retained</Text>
          </div>
          <Button size="small" onClick={() => void load()}>Refresh</Button>
        </div>
        <div className="validation-surface-body validation-history-body">
          <div className="validation-history-list">
          {batches.map((batch) => {
            const passCount = batch.tests.filter((item) => item.latest_run?.status === "pass").length;
            const failCount = batch.tests.filter((item) => item.latest_run?.status === "fail").length;
            const latestRun = batch.tests.find((item) => item.latest_run)?.latest_run;
            const latestRunVersion = versions.find((version) => version.id === latestRun?.policy_version_id);
            return (
              <button
                key={batch.id}
                type="button"
                className={batch.id === activeBatchId ? "is-active" : ""}
                onClick={() => setActiveBatchId(batch.id)}
              >
                <span>
                  <strong>{new Date(batch.created_at).toLocaleString()}</strong>
                  <small>
                    generated from v{batch.version_number}
                    {latestRunVersion ? ` · last run v${latestRunVersion.version_number}` : ""} ·{" "}
                    {GROUNDING_LABEL[batch.grounding_mode]} · {batch.selected_rule_ids.length} policies
                  </small>
                </span>
                <span>{batch.tests.length} scenarios</span>
                <Tag color={batch.status === "executed" ? "green" : "gold"}>{batch.status}</Tag>
                {batch.status === "executed" && <span>{passCount} pass · {failCount} fail</span>}
              </button>
            );
          })}
          {!loading && batches.length === 0 && (
            <div className="validation-history-empty">
              <ExperimentOutlined />
              <Text type="secondary">No validation batches yet. Select policies above to create the first one.</Text>
            </div>
          )}
          </div>
        </div>
      </section>
        </>
      )}

      <Drawer
        open={policyPreview !== null}
        onClose={() => setPolicyPreview(null)}
        size="min(920px, 100vw)"
        title={
          testPreview ? (
            <div className="validation-policy-drawer-title">
              <Button
                type="text"
                size="small"
                icon={<ArrowLeftOutlined />}
                onClick={() => setPolicyPreview(null)}
              >
                Back to validation scenario
              </Button>
              <strong>Read-only policy record</strong>
            </div>
          ) : (
            "Read-only policy record"
          )
        }
        closable={!testPreview}
        className="validation-readonly-drawer"
        styles={{ body: { padding: 0 } }}
      >
        <PolicyInspector
          rule={policyPreview}
          allRules={policyPreviewRules}
          publishedVersion={policyPreviewVersion}
          versions={versions}
          policySetKey={policySetKey}
          activeTabKey={policyPreviewTab}
          onTabChange={setPolicyPreviewTab}
          readOnly
          recordLabel="policy"
        />
      </Drawer>

      <Drawer
        open={testPreview !== null && policyPreview === null}
        onClose={() => {
          setPolicyPreview(null);
          setTestPreview(null);
        }}
        size="min(820px, 100vw)"
        title="Read-only validation scenario"
        className="validation-readonly-drawer"
      >
        {testPreview && (
          <div className="validation-test-detail">
            <section className="validation-test-policy-summary">
              <div>
                <span>Policy under test</span>
                <strong>{previewRule?.title ?? testPreview.test.expected_rule_id ?? "Selected policy subset"}</strong>
                <small>
                  {testPreview.test.expected_rule_id ?? "subset"} · {previewRule?.rule_type ?? "rule"} · generated from
                  v{previewBatch?.version_number ?? "?"}
                </small>
              </div>
              {previewRule && (
                <>
                  <div className="validation-test-policy-badges">
                    <PolicyEffectBadge effect={previewRule.effect} />
                    <Tag>{previewRule.machine_executable ? DETERMINISTIC_LABEL.yes : DETERMINISTIC_LABEL.no}</Tag>
                    <Tag>{previewRule.evidence.length} source citation{previewRule.evidence.length === 1 ? "" : "s"}</Tag>
                  </div>
                  <div className="validation-test-policy-decision">
                    <span>When</span>
                    <strong>{ruleDecisionSummary(previewRule).condition}</strong>
                    <span>Then</span>
                    <strong>{ruleDecisionSummary(previewRule).action}</strong>
                  </div>
                  <div className="validation-test-policy-meta">
                    <span>Effective {previewRule.effective_from} → {previewRule.effective_to ?? "open-ended"}</span>
                    <span>
                      Source{" "}
                      {previewRule.evidence[0]
                        ? `${previewRule.evidence[0].section ?? "document"} · p.${previewRule.evidence[0].page ?? "?"}`
                        : "not linked"}
                    </span>
                    <Button
                      size="small"
                      onClick={() => {
                        setPolicyPreviewTab("overview");
                        setPolicyPreview(previewRule);
                      }}
                    >
                      Open full policy record
                    </Button>
                  </div>
                  <div className="validation-test-policy-text">
                    <span>Full source policy text</span>
                    {previewSourceClauses.length > 0 ? (
                      previewSourceClauses.map((clause) => (
                        <blockquote key={clause.id}>
                          <cite>
                            {clause.section ?? "Source document"} · p.{clause.page ?? "?"} · clause {clause.clause_ref}
                          </cite>
                          <p>{clause.text}</p>
                        </blockquote>
                      ))
                    ) : (
                      <blockquote>
                        <cite>Canonical source text</cite>
                        <p>
                          {previewRule.formulation?.canonical?.source_text ??
                            previewRule.description ??
                            "No verbatim source text is linked to this policy."}
                        </p>
                      </blockquote>
                    )}
                  </div>
                </>
              )}
            </section>

            <div className={`validation-test-verdict is-${previewRun?.status ?? "sealed"}`}>
              {previewRun?.status === "pass" ? <CheckCircleOutlined /> : <ExperimentOutlined />}
              <span>
                <strong>
                  {!previewRun
                    ? "Expected result remains sealed"
                    : previewRun.status === "pass"
                      ? "All committed assertions matched"
                      : previewRun.status === "fail"
                        ? "One or more committed assertions did not match"
                        : "The evaluator could not complete this scenario"}
                </strong>
                <small>
                  {previewRun?.explanation ??
                    "Run this batch to reveal the committed expectation and compare every assertion."}
                </small>
              </span>
            </div>

            {previewRun && (
              <div className="validation-assertion-register">
                <div className="validation-assertion-head">
                  <span>Assertion</span><span>Expected</span><span>Actual</span><span>Match</span>
                </div>
                <div>
                  <span>Overall status</span>
                  <strong>{previewExpectation?.expected_overall_status}</strong>
                  <strong>{previewResponse?.overall_status}</strong>
                  <Tag color={previewExpectation?.expected_overall_status === previewResponse?.overall_status ? "green" : "red"}>
                    {previewExpectation?.expected_overall_status === previewResponse?.overall_status ? "MATCH" : "MISMATCH"}
                  </Tag>
                </div>
                {testPreview.test.expected_rule_id && (
                  <div>
                    <span>Selected rule status</span>
                    <strong>{previewExpectation?.expected_rule_status ?? "Any result"}</strong>
                    <strong>{previewActualRuleStatus}</strong>
                    <Tag color={previewExpectation?.expected_rule_status === previewActualRuleStatus ? "green" : "red"}>
                      {previewExpectation?.expected_rule_status === previewActualRuleStatus ? "MATCH" : "MISMATCH"}
                    </Tag>
                  </div>
                )}
                <div>
                  <span>Evaluation date</span>
                  <strong>{previewExpectation?.evaluation_timestamp?.slice(0, 10) ?? "Run time"}</strong>
                  <strong>{previewResponse?.evaluation_timestamp?.slice(0, 10) ?? "—"}</strong>
                  <Tag>CONTEXT</Tag>
                </div>
              </div>
            )}

            <Descriptions column={1} size="small" bordered>
              <Descriptions.Item label="Scenario statement">
                {testPreview.test.scenario_text || testPreview.test.description}
              </Descriptions.Item>
              <Descriptions.Item label="Test kind">{testPreview.test.test_kind.replace("_", " ")}</Descriptions.Item>
              <Descriptions.Item label="Tested version">
                v{previewRunVersion?.version_number ?? "—"} · {previewRun?.policy_version_id ?? "not run"}
              </Descriptions.Item>
              <Descriptions.Item label="Expectation commitment">
                <Text code copyable={{ text: testPreview.test.expectation_hash ?? "" }}>
                  {testPreview.test.expectation_hash}
                </Text>
              </Descriptions.Item>
              <Descriptions.Item label="Regression suite">
                {testPreview.test.is_active
                  ? "Active — automatically re-runs on every future publish"
                  : "Not active — this scenario only runs when requested"}
              </Descriptions.Item>
            </Descriptions>
            <Tabs
              items={[
                {
                  key: "facts",
                  label: "Facts sent",
                  children: <JsonView value={testPreview.test.input_facts} downloadName={`${testPreview.test.name}-facts.json`} maxHeight={420} />,
                },
                ...(testPreview.latest_run
                  ? [
                      {
                        key: "actual",
                        label: "Evaluator response",
                        children: <JsonView value={testPreview.latest_run.actual_response_json} downloadName={`${testPreview.test.name}-actual.json`} maxHeight={520} />,
                      },
                      {
                        key: "expected",
                        label: "Committed expectation",
                        children: <JsonView value={testPreview.latest_run.expected_assertions_json} downloadName={`${testPreview.test.name}-expected.json`} maxHeight={420} />,
                      },
                      {
                        key: "history",
                        label: `Run history (${testPreview.runs.length})`,
                        children: (
                          <div className="validation-test-run-history">
                            {testPreview.runs.map((run) => {
                              const version = versions.find((item) => item.id === run.policy_version_id);
                              return (
                                <div key={run.id}>
                                  <Tag color={run.status === "pass" ? "green" : run.status === "fail" ? "red" : "orange"}>
                                    {run.status.toUpperCase()}
                                  </Tag>
                                  <span>
                                    <strong>v{version?.version_number ?? "?"}</strong>
                                    <small>
                                      {new Date(run.run_at).toLocaleString()} · {run.run_trigger} · {run.triggered_by}
                                    </small>
                                  </span>
                                  <Text type="secondary">{run.explanation}</Text>
                                </div>
                              );
                            })}
                          </div>
                        ),
                      },
                    ]
                  : []),
              ]}
            />
          </div>
        )}
      </Drawer>
    </div>
  );
}