import { useEffect, useMemo, useState } from "react";
import { Alert, Button, Card, Form, Input, Modal, Popconfirm, Progress, Select, Space, Tag, Tooltip, Typography } from "antd";
import {
  CheckOutlined,
  CloseOutlined,
  ExperimentOutlined,
  HistoryOutlined,
  PlayCircleOutlined,
  PlusOutlined,
  QuestionCircleOutlined,
  ThunderboltOutlined,
  WarningOutlined,
} from "@ant-design/icons";
import dayjs from "dayjs";
import {
  api,
  policyTestApi,
  PolicyPlatformApiError,
  type CreatePolicyTestRequest,
  type EvaluationStatus,
  type PolicyTestKind,
  type PolicyTestListItem,
  type PolicyTestRun,
} from "../api";
import { useActor } from "../ActorContext";
import { EvaluationTargetBanner, useEvaluationTarget } from "./EvaluationTarget";

const { Title, Text, Paragraph } = Typography;
const { TextArea } = Input;

const TEST_KIND_LABELS: Record<PolicyTestKind, string> = {
  positive: "Positive",
  negative: "Negative",
  boundary: "Boundary",
  missing_fact: "Missing fact",
  scope: "Scope",
  effective_date: "Effective date",
  exception: "Exception",
  precedence: "Precedence",
};

const TEST_KIND_HELP: Record<PolicyTestKind, string> = {
  positive: "A normal request that should satisfy the policy.",
  negative: "A request that should not satisfy the policy.",
  boundary: "Values at limits, dates, thresholds, or exact edges.",
  missing_fact: "Required inputs are absent, so missing facts are expected.",
  scope: "Persona, jurisdiction, organization, or process targeting.",
  effective_date: "Checks behavior for a specific evaluation date.",
  exception: "Proves an exception changes the outcome as intended.",
  precedence: "Conflicting rules where the higher-precedence result must win.",
};

const STATUS_HELP: Record<EvaluationStatus, string> = {
  SATISFIED: "A policy/rule condition matched.",
  NOT_SATISFIED: "The policy was evaluated and did not match.",
  NOT_APPLICABLE: "The rule is outside this request's scope.",
  INDETERMINATE: "The evaluator needs missing or ambiguous facts.",
  ERROR: "The evaluator is expected to raise an error.",
};

const TEST_KIND_ORDER: PolicyTestKind[] = [
  "positive",
  "negative",
  "boundary",
  "missing_fact",
  "scope",
  "effective_date",
  "exception",
  "precedence",
];

const STATUS_OPTIONS: EvaluationStatus[] = ["SATISFIED", "NOT_SATISFIED", "NOT_APPLICABLE", "INDETERMINATE", "ERROR"];

/**
 * What accepting a proposal actually does, stated in the reviewer's terms and
 * kept in one place so the button, the confirmation and the section header can
 * never drift apart from each other or from the backend.
 *
 * Verified against `policy_tests.review_policy_test` (accept sets
 * review_status="active"/is_active=True) and the two things that read
 * `is_active`: `run_active_tests_for_version` (the on-publish re-run) and
 * `list_failing_policy_tests` (the Quality → Failed policy tests list).
 *
 * The "never blocks a publish" clause is deliberate and load-bearing: the
 * on-publish re-run in `publish_approved_candidates` happens *after* the
 * version is already committed and is wrapped in a best-effort try/except, so
 * an accepted-but-failing test reports a problem without ever holding up a
 * release. Reviewers who assume otherwise would over-think every accept.
 */
const ACCEPT_CONSEQUENCE = "Runs automatically on every publish from now on. A failure shows up under Quality → Failed policy tests. It never blocks a publish.";
const REJECT_CONSEQUENCE = "Kept in the record for history, but never runs and never affects Quality.";

/**
 * A pending proposal's verification state.
 *
 * The reviewer's real question is "is the AI's expected status actually what
 * the engine returns?". That is not a judgement call — the deterministic
 * evaluator answers it exactly. `unchecked` therefore means "no evidence yet",
 * not "fine"; it is ordered last so the reviewer sees decidable work first.
 */
type VerificationState = "disagrees" | "errored" | "confirmed" | "unchecked";

const VERIFICATION_ORDER: Record<VerificationState, number> = {
  disagrees: 0,
  errored: 1,
  confirmed: 2,
  unchecked: 3,
};

function verificationOf(item: PolicyTestListItem): VerificationState {
  const run = item.latest_run;
  if (!run) return "unchecked";
  if (run.status === "pass") return "confirmed";
  if (run.status === "error") return "errored";
  return "disagrees";
}

const VERIFICATION_TAG: Record<VerificationState, { label: string; color: string }> = {
  disagrees: { label: "Evaluator disagrees", color: "red" },
  errored: { label: "Could not run", color: "orange" },
  confirmed: { label: "Evaluator agrees", color: "green" },
  unchecked: { label: "Not checked yet", color: "default" },
};

/**
 * A confirmed check means the AI's expected status matched the engine, so the
 * expectation is safe to lock in. A disagreement is deliberately NOT framed as
 * "the AI was wrong": the same evidence is equally consistent with the policy
 * itself being wrong, and pre-judging that would train reviewers to reject real
 * findings.
 */
const VERIFICATION_VERDICT: Record<VerificationState, { headline: string; detail: string }> = {
  confirmed: {
    headline: "The evaluator returned what this test expects",
    detail: "The expectation matches real engine behaviour, so accepting it locks in behaviour that already holds today.",
  },
  disagrees: {
    headline: "The evaluator returned something else",
    detail:
      "Either the expectation is wrong, or the policy does not behave the way it was meant to. Worth reading before you decide — accepting it now would create a test that fails on every publish.",
  },
  errored: {
    headline: "This case could not be evaluated",
    detail: "The engine raised an error instead of returning a status. The test needs fixing before it can guard anything.",
  },
  unchecked: {
    headline: "Nobody has checked this prediction yet",
    detail: "The expected status below is the AI's guess. Run it against the evaluator to find out whether it actually holds.",
  },
};

/**
 * Concrete business questions a reviewer already has in their head, mapped to the
 * test kind that answers each one. The kind names are engine vocabulary
 * ("boundary", "precedence") and mean nothing to a policy owner on their own, so
 * every kind is introduced through the real question it settles rather than
 * through its definition.
 */
const TEST_KIND_BUSINESS_QUESTION: Record<PolicyTestKind, string> = {
  positive: "Does someone who clearly qualifies actually get approved?",
  negative: "Does someone who clearly does not qualify get refused?",
  boundary: "What happens to the person sitting exactly on the limit?",
  missing_fact: "What do we answer when we do not have all the information?",
  scope: "Does this policy correctly leave other regions or departments alone?",
  effective_date: "Was the answer different before this policy took effect?",
  exception: "Does the documented exception really change the outcome?",
  precedence: "When two policies disagree, does the right one win?",
};

/** Ready-made steers, so the guidance box is not an empty box with no idea what to type. */
const GUIDANCE_PRESETS: { label: string; text: string }[] = [
  {
    label: "Focus on money",
    text: "Prioritise rules involving pay, allowances, thresholds and monetary caps. Include boundary tests exactly at each amount.",
  },
  {
    label: "Focus on leave & time",
    text: "Prioritise rules about leave entitlement, notice periods, tenure and durations. Test the exact day counts at each limit.",
  },
  {
    label: "Focus on termination & exit",
    text: "Prioritise rules about termination, resignation, end-of-service and final settlement, including the exceptions that change the outcome.",
  },
  {
    label: "Stress the edges",
    text: "Concentrate on boundary and missing-fact cases. For every numeric or date threshold, test just below, exactly on, and just above it.",
  },
  {
    label: "Find contradictions",
    text: "Concentrate on precedence and exception cases where two rules could produce conflicting outcomes for the same facts.",
  },
];

const RUN_STATUS_COLOR: Record<string, string> = {
  pass: "green",
  fail: "red",
  error: "volcano",
};

/**
 * Tests view — named, saved `PolicyTest` cases for this policy set (Section
 * 21.6 / 11.6), distinct from the ad hoc Evaluate page. Azure OpenAI may
 * propose candidate tests here, but the real deterministic evaluator always
 * decides pass/fail server-side; publishing a new version automatically
 * re-runs every active test (Section 9.11 step 6), and any that fail surface
 * in the Quality page's "Failed policy tests" section (Section 9.9).
 */
export function PolicyTestsPage({ policySetKey }: { policySetKey: string }) {
  const { actor } = useActor();
  const [tests, setTests] = useState<PolicyTestListItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [kindFilter, setKindFilter] = useState<string>("all");
  const [reasoningEffort, setReasoningEffort] = useState<"low" | "medium" | "high">("medium");
  const [guidance, setGuidance] = useState("");
  const [howOpen, setHowOpen] = useState(false);
  const [proposing, setProposing] = useState(false);
  const [runningId, setRunningId] = useState<string | null>(null);
  const [reviewingId, setReviewingId] = useState<string | null>(null);
  const [bulkVerify, setBulkVerify] = useState<{ done: number; total: number } | null>(null);
  const [bulkAccept, setBulkAccept] = useState<{ done: number; total: number } | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [runHistory, setRunHistory] = useState<Record<string, PolicyTestRun[]>>({});
  const [createOpen, setCreateOpen] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [createSaving, setCreateSaving] = useState(false);
  const [form] = Form.useForm();

  const evaluationTarget = useEvaluationTarget(policySetKey);
  const [executableCount, setExecutableCount] = useState<{ executable: number; total: number } | null>(null);

  /**
   * How many rules in the target version the engine will actually execute.
   *
   * `_evaluate_rule` returns NOT_APPLICABLE immediately for any rule with
   * machine_executable=false, before scope or condition are considered. A
   * policy set where that is true of every rule cannot return SATISFIED for
   * anything, so every test predicting SATISFIED is guaranteed to fail. That is
   * a property of the policy set rather than of any individual test, so it is
   * reported once at the top of the page instead of being rediscovered by the
   * reviewer one failed proposal at a time.
   */
  useEffect(() => {
    const version = evaluationTarget.version;
    if (!version) {
      setExecutableCount(null);
      return;
    }
    let cancelled = false;
    api
      .getVersionRules(policySetKey, version.id)
      .then((rules) => {
        if (cancelled) return;
        setExecutableCount({
          executable: rules.filter((r) => r.machine_executable).length,
          total: rules.length,
        });
      })
      .catch(() => {
        // Advisory context only — a failure here must never block test review.
        if (!cancelled) setExecutableCount(null);
      });
    return () => {
      cancelled = true;
    };
  }, [policySetKey, evaluationTarget.version]);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await policyTestApi.list(policySetKey);
      setTests(data);
    } catch (e) {
      setError(e instanceof PolicyPlatformApiError ? e.detail : String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    setExpandedId(null);
    setRunHistory({});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [policySetKey]);

  const handlePropose = async () => {
    setProposing(true);
    setError(null);
    try {
      await policyTestApi.propose(policySetKey, reasoningEffort, guidance);
      await load();
    } catch (e) {
      setError(e instanceof PolicyPlatformApiError ? e.detail : String(e));
    } finally {
      setProposing(false);
    }
  };

  const handleReview = async (testId: string, decision: "accept" | "reject") => {
    setReviewingId(testId);
    setError(null);
    try {
      await policyTestApi.review(testId, decision, actor.name || "unknown");
      await load();
    } catch (e) {
      setError(e instanceof PolicyPlatformApiError ? e.detail : String(e));
    } finally {
      setReviewingId(null);
    }
  };

  /**
   * Run every unreviewed proposal against the real evaluator without accepting
   * any of them, so the reviewer can see which predictions actually hold before
   * deciding anything.
   *
   * This is safe precisely because `is_active` gates *counting*, not
   * *executing*: `execute_test_by_id` runs any test by id, while the on-publish
   * re-run and the Quality "failing tests" list both filter `is_active=True`.
   * A run recorded here therefore shows up in the proposal's own history and
   * nowhere else.
   *
   * Runs are issued one at a time rather than with `Promise.all` — each one is
   * a full policy evaluation on the server, and a burst of them from a large
   * proposal batch is a self-inflicted load spike for no latency benefit that
   * the reviewer would notice.
   */
  const handleVerifyAll = async (items: PolicyTestListItem[]) => {
    const targets = items.filter((i) => i.test.review_status === "pending_review");
    if (targets.length === 0) return;
    setError(null);
    setBulkVerify({ done: 0, total: targets.length });
    const failures: string[] = [];
    try {
      for (const [index, item] of targets.entries()) {
        try {
          await policyTestApi.run(item.test.id, actor.name || "unknown");
        } catch (e) {
          failures.push(`${item.test.name}: ${e instanceof PolicyPlatformApiError ? e.detail : String(e)}`);
        }
        setBulkVerify({ done: index + 1, total: targets.length });
      }
      await load();
      if (failures.length > 0) {
        setError(`${failures.length} of ${targets.length} checks could not run. ${failures[0]}`);
      }
    } finally {
      setBulkVerify(null);
    }
  };

  /**
   * Accept only those proposals the evaluator has already confirmed. Anything
   * unchecked or disagreeing is deliberately left behind — a bulk action must
   * never be a way to activate a test nobody has evidence for.
   */
  const handleAcceptConfirmed = async (items: PolicyTestListItem[]) => {
    const targets = items.filter((i) => i.test.review_status === "pending_review" && verificationOf(i) === "confirmed");
    if (targets.length === 0) return;
    setError(null);
    setBulkAccept({ done: 0, total: targets.length });
    const failures: string[] = [];
    try {
      for (const [index, item] of targets.entries()) {
        try {
          await policyTestApi.review(item.test.id, "accept", actor.name || "unknown");
        } catch (e) {
          failures.push(`${item.test.name}: ${e instanceof PolicyPlatformApiError ? e.detail : String(e)}`);
        }
        setBulkAccept({ done: index + 1, total: targets.length });
      }
      await load();
      if (failures.length > 0) {
        setError(`${failures.length} of ${targets.length} could not be accepted. ${failures[0]}`);
      }
    } finally {
      setBulkAccept(null);
    }
  };

  const refreshHistory = async (testId: string) => {
    try {
      const runs = await policyTestApi.listRuns(testId);
      setRunHistory((prev) => ({ ...prev, [testId]: runs }));
    } catch (e) {
      setError(e instanceof PolicyPlatformApiError ? e.detail : String(e));
    }
  };

  const handleRun = async (testId: string) => {
    setRunningId(testId);
    setError(null);
    try {
      await policyTestApi.run(testId, actor.name || "unknown");
      await load();
      if (expandedId === testId) await refreshHistory(testId);
    } catch (e) {
      setError(e instanceof PolicyPlatformApiError ? e.detail : String(e));
    } finally {
      setRunningId(null);
    }
  };

  const toggleHistory = async (testId: string) => {
    if (expandedId === testId) {
      setExpandedId(null);
      return;
    }
    setExpandedId(testId);
    if (!runHistory[testId]) await refreshHistory(testId);
  };

  const openCreate = () => {
    form.resetFields();
    setCreateError(null);
    setCreateOpen(true);
  };

  const handleCreate = async () => {
    try {
      const values = await form.validateFields();
      setCreateSaving(true);
      setCreateError(null);

      let inputFacts: Record<string, unknown> = {};
      try {
        inputFacts = values.input_facts ? JSON.parse(values.input_facts) : {};
      } catch {
        setCreateError('Input facts must be valid JSON, e.g. {"amount": 50}');
        setCreateSaving(false);
        return;
      }

      const expectedMissingFacts: string[] | undefined = values.expected_missing_facts
        ? String(values.expected_missing_facts)
            .split(",")
            .map((s: string) => s.trim())
            .filter(Boolean)
        : undefined;

      const body: CreatePolicyTestRequest = {
        name: values.name,
        description: values.description ?? "",
        test_kind: values.test_kind,
        input_facts: inputFacts,
        expected_overall_status: values.expected_overall_status,
        expected_rule_id: values.expected_rule_id || null,
        expected_rule_status: values.expected_rule_status || null,
        expected_missing_facts: expectedMissingFacts && expectedMissingFacts.length > 0 ? expectedMissingFacts : null,
      };

      await policyTestApi.create(policySetKey, body);
      setCreateOpen(false);
      await load();
    } catch (e) {
      if (e instanceof PolicyPlatformApiError) setCreateError(e.detail);
      else if (e && typeof e === "object" && "errorFields" in e) {
        // antd form validation error — already shown inline per-field
      } else {
        setCreateError(String(e));
      }
    } finally {
      setCreateSaving(false);
    }
  };

  const filtered = tests.filter((t) => kindFilter === "all" || t.test.test_kind === kindFilter);
  const pendingReview = tests.filter((t) => t.test.review_status === "pending_review");
  const activeFiltered = filtered.filter((t) => t.test.review_status === "active");
  const rejectedFiltered = filtered.filter((t) => t.test.review_status === "rejected");
  const latestRuns = tests.filter((t) => t.latest_run);

  /**
   * Proposals are ordered by what the evaluator found rather than by when they
   * were created: disagreements first (they either expose a mispredicted
   * expectation or a real policy problem, and both need a person), then
   * confirmed ones that can be accepted in a batch, then anything still
   * unchecked. A flat creation-ordered list gives a reviewer with dozens of
   * proposals no way to tell those three situations apart.
   */
  const pendingFiltered = useMemo(() => {
    const items = filtered.filter((t) => t.test.review_status === "pending_review");
    return [...items].sort((a, b) => {
      const byState = VERIFICATION_ORDER[verificationOf(a)] - VERIFICATION_ORDER[verificationOf(b)];
      return byState !== 0 ? byState : a.test.name.localeCompare(b.test.name);
    });
  }, [filtered]);

  const pendingTally = pendingFiltered.reduce(
    (acc, item) => {
      acc[verificationOf(item)] += 1;
      return acc;
    },
    { disagrees: 0, errored: 0, confirmed: 0, unchecked: 0 } as Record<VerificationState, number>
  );

  /**
   * Scoped to accepted tests on purpose. Proposals can now be dry-run while
   * still pending, so counting every failing latest run here would report
   * unaccepted drafts as if they were live quality problems — which is exactly
   * the confusion `list_failing_policy_tests` avoids server-side by filtering
   * on `is_active`.
   */
  const failingActiveCount = tests.filter(
    (t) => t.test.is_active && (t.latest_run?.status === "fail" || t.latest_run?.status === "error")
  ).length;

  const counts = tests.reduce(
    (acc, t) => {
      acc[t.test.test_kind] = (acc[t.test.test_kind] ?? 0) + 1;
      return acc;
    },
    {} as Record<string, number>
  );

  const renderTestCard = (item: PolicyTestListItem) => {
    const t = item.test;
    const run = item.latest_run;
    const history = runHistory[t.id] ?? [];
    const isPending = t.review_status === "pending_review";
    const verification = verificationOf(item);
    const busy = bulkVerify !== null || bulkAccept !== null;

    return (
      <Card
        key={t.id}
        size="small"
        className={`finding-card tests-test-card${isPending ? ` tests-test-card--${verification}` : ""}`}
      >
        <div className="tests-card-topline">
          <Space size={8} wrap>
            <Tag>{TEST_KIND_LABELS[t.test_kind]}</Tag>
            {t.proposed_by === "ai" && (
              <Tag icon={<ThunderboltOutlined />} color="purple">
                AI-proposed
              </Tag>
            )}
            {t.review_status === "rejected" && <Tag>Rejected</Tag>}
            {isPending ? (
              <Tag color={VERIFICATION_TAG[verification].color}>{VERIFICATION_TAG[verification].label}</Tag>
            ) : run ? (
              <Tag color={RUN_STATUS_COLOR[run.status] ?? "default"}>{run.status.toUpperCase()}</Tag>
            ) : (
              <Tag>Never run</Tag>
            )}
          </Space>
        </div>

        <div className="tests-card-body">
          <div className="tests-card-main">
            <Text strong className="tests-card-title">
              {t.name}
            </Text>
            {t.description && (
              <Paragraph type="secondary" className="tests-card-description">
                {t.description}
              </Paragraph>
            )}
            <div className="tests-expectation">
              <span>Given facts</span>
              <code>{JSON.stringify(t.input_facts)}</code>
              <span>expect</span>
              <Tag color="blue">{t.expected_overall_status}</Tag>
            </div>
            {(t.expected_rule_id || t.expected_rule_status || t.expected_missing_facts?.length) && (
              <div className="tests-assertions">
                {t.expected_rule_id && <Tag>Rule {t.expected_rule_id}</Tag>}
                {t.expected_rule_status && <Tag>Rule status {t.expected_rule_status}</Tag>}
                {t.expected_missing_facts?.map((fact) => (
                  <Tag key={fact}>Missing {fact}</Tag>
                ))}
              </div>
            )}
            {run && run.status !== "pass" && !isPending && (
              <Paragraph type="danger" className="tests-run-explanation">
                {run.explanation}
              </Paragraph>
            )}

            {isPending && (
              <div className={`tests-verdict tests-verdict--${verification}`}>
                <div className="tests-verdict-head">
                  {verification === "confirmed" && <CheckOutlined />}
                  {(verification === "disagrees" || verification === "errored") && <WarningOutlined />}
                  {verification === "unchecked" && <ExperimentOutlined />}
                  <strong>{VERIFICATION_VERDICT[verification].headline}</strong>
                </div>
                <Text type="secondary">{VERIFICATION_VERDICT[verification].detail}</Text>
                {run && run.status !== "pass" && <div className="tests-verdict-explanation">{run.explanation}</div>}
              </div>
            )}
          </div>

          <div className="tests-card-actions">
            {isPending ? (
              <Space direction="vertical" size={6} style={{ width: "100%" }}>
                <Tooltip title="Runs this case against the live evaluator without accepting it. Nothing becomes active and Quality is unaffected.">
                  <Button
                    size="small"
                    icon={<ExperimentOutlined />}
                    onClick={() => handleRun(t.id)}
                    loading={runningId === t.id}
                    disabled={busy}
                    block
                  >
                    {run ? "Check again" : "Check prediction"}
                  </Button>
                </Tooltip>
                <Popconfirm
                  title="Accept this test?"
                  description={<div className="tests-confirm-copy">{ACCEPT_CONSEQUENCE}</div>}
                  okText="Accept"
                  cancelText="Cancel"
                  onConfirm={() => handleReview(t.id, "accept")}
                >
                  <Button size="small" type="primary" icon={<CheckOutlined />} loading={reviewingId === t.id} disabled={busy} block>
                    Accept
                  </Button>
                </Popconfirm>
                <Popconfirm
                  title="Reject this test?"
                  description={<div className="tests-confirm-copy">{REJECT_CONSEQUENCE}</div>}
                  okText="Reject"
                  okButtonProps={{ danger: true }}
                  cancelText="Cancel"
                  onConfirm={() => handleReview(t.id, "reject")}
                >
                  <Button size="small" danger icon={<CloseOutlined />} loading={reviewingId === t.id} disabled={busy} block>
                    Reject
                  </Button>
                </Popconfirm>
              </Space>
            ) : (
              t.is_active && (
                <Button
                  size="small"
                  type="primary"
                  icon={<PlayCircleOutlined />}
                  onClick={() => handleRun(t.id)}
                  loading={runningId === t.id}
                >
                  Run now
                </Button>
              )
            )}
            <Button size="small" type="link" icon={<HistoryOutlined />} onClick={() => toggleHistory(t.id)}>
              {expandedId === t.id ? "Hide history" : "History"}
            </Button>
          </div>
        </div>

        {expandedId === t.id && (
          <div className="tests-history">
            {history.length === 0 && <Text type="secondary">No runs yet.</Text>}
            <Space direction="vertical" style={{ width: "100%" }} size={6}>
              {history.map((r) => (
                <div key={r.id} className="tests-history-row">
                  <Space size={6} wrap>
                    <Tag color={RUN_STATUS_COLOR[r.status] ?? "default"}>{r.status.toUpperCase()}</Tag>
                    <Text type="secondary">{dayjs(r.run_at).format("YYYY-MM-DD HH:mm:ss")}</Text>
                    <Tag>{r.run_trigger === "on_publish" ? "on publish" : "manual"}</Tag>
                    <Text type="secondary">by {r.triggered_by}</Text>
                  </Space>
                  {r.status !== "pass" && (
                    <div>
                      <Text type="danger">{r.explanation}</Text>
                    </div>
                  )}
                </div>
              ))}
            </Space>
          </div>
        )}
      </Card>
    );
  };

  return (
    <div className="tests-workspace">
      <div className="page-header-row">
        <div>
          <Title level={3}>Tests</Title>
        </div>
        <Button icon={<PlusOutlined />} onClick={openCreate}>
          Add test manually
        </Button>
      </div>

      <Paragraph type="secondary" className="tests-page-intro">
        A test writes down a real situation and the answer this policy set <Text strong>should</Text> give — then
        proves it. If a future edit quietly changes that answer, the test fails and tells you before anyone is
        affected.
      </Paragraph>

      <EvaluationTargetBanner
        scope="published"
        target={evaluationTarget}
        actionLabel="Tests"
        emptyHint="Tests run against the version currently in force, so there has to be one. Approve rules in Review and publish a version, then come back and draft tests against it."
      />

      <Card size="small" className="explainer-card tests-how-card">
        <button type="button" className="explainer-toggle" onClick={() => setHowOpen((v) => !v)}>
          <span>
            <QuestionCircleOutlined /> How a policy test works
          </span>
          <Text type="secondary">{howOpen ? "Hide" : "Show"}</Text>
        </button>
        {howOpen && (
          <div className="tests-how-body">
            <div className="tests-how-flow">
              <div className="tests-how-step">
                <span className="tests-how-num">1</span>
                <Text strong>Describe a real situation</Text>
                <Text type="secondary">
                  "An employee in Saudi Arabia with 3 years of service resigns."
                </Text>
              </div>
              <div className="tests-how-step">
                <span className="tests-how-num">2</span>
                <Text strong>State the answer you expect</Text>
                <Text type="secondary">
                  "They should be entitled to end-of-service benefit." → <Tag color="blue">SATISFIED</Tag>
                </Text>
              </div>
              <div className="tests-how-step">
                <span className="tests-how-num">3</span>
                <Text strong>The evaluator decides — not the AI</Text>
                <Text type="secondary">
                  The same engine that answers live requests runs the case and compares. →{" "}
                  <Tag color="green">PASS</Tag>
                </Text>
              </div>
            </div>
            <div className="tests-how-notes">
              <div>
                <Text strong>Why bother?</Text>
                <Text type="secondary">
                  {" "}
                  Policies get re-extracted, edited and re-published. A test is how you find out that a change
                  broke something, instead of hearing it from the person it affected.
                </Text>
              </div>
              <div>
                <Text strong>Where results show up.</Text>
                <Text type="secondary">
                  {" "}
                  Publishing re-runs every active test automatically. Anything that fails appears under Quality →
                  Failed policy tests.
                </Text>
              </div>
              <div>
                <Text strong>AI drafts, you decide.</Text>
                <Text type="secondary">
                  {" "}
                  Proposals sit in review and do nothing until you accept them. You can run one against the real
                  evaluator while it is still a proposal — that is the fastest way to tell a correct expectation from a
                  wrong one. Pass or fail is never judged by the AI.
                </Text>
              </div>
            </div>
          </div>
        )}
      </Card>

      {error && <Alert type="error" showIcon message={error} closable onClose={() => setError(null)} />}

      {executableCount && executableCount.total > 0 && executableCount.executable === 0 && (
        <Alert
          type="warning"
          showIcon
          message="No published rule can be decided by the deterministic engine yet"
          description={
            <span>
              None of the {executableCount.total} published rules has a fact mapping, so the engine returns{" "}
              <Tag>NOT_APPLICABLE</Tag> for each of them before reading scope or condition — which means this policy set
              cannot return <Tag>SATISFIED</Tag> for anything, and a test expecting it will fail every time. That is a
              configuration gap on our side, not a judgement about the policies: a rule can state its terms perfectly
              and still have no attribute mapped onto them. Treat <Tag>NOT_APPLICABLE</Tag> as the correct expectation
              here until a fact model is configured.
            </span>
          }
        />
      )}

      {executableCount && executableCount.total > 0 && executableCount.executable > 0 && executableCount.executable < executableCount.total && (
        <Alert
          type="info"
          showIcon
          message={`${executableCount.executable} of ${executableCount.total} published rules have a fact mapping`}
          description="The rest always evaluate to NOT_APPLICABLE in the deterministic engine, whatever their scope or condition says, because nothing maps their terms onto readable attributes. Tests aimed at those rules can only assert NOT_APPLICABLE — that is a limit of this engine, not a statement that the rules are unclear."
        />
      )}

      <dl className="tests-summary-strip">
        <div>
          <dt>Saved tests</dt>
          <dd>{tests.length}</dd>
        </div>
        <div>
          <dt>Awaiting review</dt>
          <dd>{pendingReview.length}</dd>
        </div>
        <div>
          <dt>Latest runs</dt>
          <dd>{latestRuns.length}</dd>
        </div>
        <div>
          <dt>Failing now</dt>
          <dd>{failingActiveCount}</dd>
        </div>
      </dl>

      <div className="tests-control-grid">
        <Card className="tests-ai-panel">
          <Title level={4} className="tests-panel-title">
            <ThunderboltOutlined /> Draft tests with AI
          </Title>
          <Paragraph type="secondary" className="tests-panel-copy">
            It reads the {evaluationTarget.version ? `${evaluationTarget.version.rule_count} published rules` : "published rules"} and
            proposes cases for review. Leave the box empty for broad coverage, or steer it at the areas you actually
            worry about.
          </Paragraph>

          <TextArea
            value={guidance}
            onChange={(e) => setGuidance(e.target.value)}
            className="tests-guidance-input"
            autoSize={{ minRows: 3, maxRows: 8 }}
            maxLength={1000}
            showCount
            placeholder={
              "e.g. Focus on end-of-service benefit for employees who resign before 5 years, and test the exact tenure boundaries."
            }
            aria-label="Guidance for the AI test proposer"
          />

          <div className="tests-guidance-presets">
            {GUIDANCE_PRESETS.map((p) => (
              <button
                key={p.label}
                type="button"
                className="tests-guidance-preset"
                onClick={() => setGuidance(p.text)}
              >
                {p.label}
              </button>
            ))}
            {guidance && (
              <button type="button" className="tests-guidance-preset tests-guidance-clear" onClick={() => setGuidance("")}>
                Clear
              </button>
            )}
          </div>

          <Space wrap className="tests-guidance-actions">
            <Button
              type="primary"
              icon={<ThunderboltOutlined />}
              onClick={handlePropose}
              loading={proposing}
              disabled={!evaluationTarget.version}
            >
              {proposing ? "Drafting tests…" : "Generate tests"}
            </Button>
            <Select
              value={reasoningEffort}
              onChange={(v) => setReasoningEffort(v as typeof reasoningEffort)}
              style={{ width: 160 }}
              aria-label="Reasoning effort"
              options={[
                { value: "low", label: "Low effort" },
                { value: "medium", label: "Medium effort" },
                { value: "high", label: "High effort" },
              ]}
            />
          </Space>
          <Text type="secondary" className="tests-field-note">
            Higher effort asks for more careful coverage. Neither the guidance nor the effort changes how pass/fail
            is judged — that is always the deterministic evaluator.
          </Text>
        </Card>

        <Card className="tests-filter-panel">
          <Text strong className="tests-filter-title">Filter by test kind</Text>
          <Select
            value={kindFilter}
            onChange={setKindFilter}
            className="tests-kind-filter"
            options={[
              { value: "all", label: `All kinds (${tests.length})` },
              ...TEST_KIND_ORDER.map((k) => ({ value: k, label: `${TEST_KIND_LABELS[k]} (${counts[k] ?? 0})` })),
            ]}
          />
          <div className="tests-kind-chips">
            {TEST_KIND_ORDER.map((k) => (
              <button
                key={k}
                type="button"
                className={`tests-kind-chip${kindFilter === k ? " tests-kind-chip--active" : ""}`}
                onClick={() => setKindFilter(kindFilter === k ? "all" : k)}
                title={TEST_KIND_HELP[k]}
              >
                <span>
                  {TEST_KIND_LABELS[k]}
                  <em className="tests-kind-count">{counts[k] ?? 0}</em>
                </span>
                <small>{TEST_KIND_BUSINESS_QUESTION[k]}</small>
              </button>
            ))}
          </div>
        </Card>
      </div>

      <div className="tests-main-grid">
        <div className="tests-list-column">
          {!loading && tests.length === 0 && (
            <Card className="tests-empty-state">
              <Title level={4}>Nothing is guarding this policy set</Title>
              <Paragraph type="secondary">
                Right now, a re-extraction or an edit could change what these policies answer and nobody would
                notice. A handful of tests covering the outcomes that matter most is usually enough to catch that.
              </Paragraph>
              <div className="tests-empty-notes">
                <div>
                  <strong>Fastest start.</strong>
                  <Text type="secondary">
                    {" "}
                    Describe what you care about in the box above and let the AI draft the cases, then accept the
                    ones you agree with.
                  </Text>
                </div>
                <div>
                  <strong>Prefer to be precise?</strong>
                  <Text type="secondary"> Write one yourself with exact facts and the status you expect.</Text>
                </div>
              </div>
              <Space wrap>
                <Button
                  type="primary"
                  icon={<ThunderboltOutlined />}
                  onClick={handlePropose}
                  loading={proposing}
                  disabled={!evaluationTarget.version}
                >
                  Generate tests with AI
                </Button>
                <Button icon={<PlusOutlined />} onClick={openCreate}>
                  Create one manually
                </Button>
                <Button type="link" onClick={() => setHowOpen(true)}>
                  How does a test work?
                </Button>
              </Space>
            </Card>
          )}

          {loading && <Text type="secondary">Loading tests…</Text>}

          {!loading && tests.length > 0 && filtered.length === 0 && (
            <Card>
              <Text type="secondary">No tests match this kind filter.</Text>
            </Card>
          )}

          {pendingFiltered.length > 0 && (
            <section className="tests-section">
              <div className="tests-section-header">
                <div>
                  <div className="section-eyebrow">AI proposals · nothing here runs yet</div>
                  <Title level={4}>Check the prediction, then decide</Title>
                </div>
                <Tag color="gold">{pendingFiltered.length} awaiting a decision</Tag>
              </div>

              <Card size="small" className="tests-triage-bar">
                <div className="tests-triage-explain">
                  <Text strong>Accepting a proposal has a real effect.</Text>{" "}
                  <Text type="secondary">{ACCEPT_CONSEQUENCE}</Text>
                </div>

                <div className="tests-triage-tally">
                  <span className="tests-tally tests-tally--disagrees">
                    <strong>{pendingTally.disagrees}</strong> evaluator disagrees
                  </span>
                  <span className="tests-tally tests-tally--errored">
                    <strong>{pendingTally.errored}</strong> could not run
                  </span>
                  <span className="tests-tally tests-tally--confirmed">
                    <strong>{pendingTally.confirmed}</strong> evaluator agrees
                  </span>
                  <span className="tests-tally tests-tally--unchecked">
                    <strong>{pendingTally.unchecked}</strong> not checked
                  </span>
                </div>

                <div className="tests-triage-actions">
                  <Tooltip title="Runs every proposal below against the live evaluator. Nothing is accepted and Quality is untouched — this only tells you which expectations actually hold.">
                    <Button
                      icon={<ExperimentOutlined />}
                      onClick={() => handleVerifyAll(pendingFiltered)}
                      loading={bulkVerify !== null}
                      disabled={bulkAccept !== null}
                    >
                      Check all {pendingFiltered.length}
                    </Button>
                  </Tooltip>
                  <Popconfirm
                    title={`Accept ${pendingTally.confirmed} verified test${pendingTally.confirmed === 1 ? "" : "s"}?`}
                    description={
                      <div className="tests-confirm-copy">
                        Only proposals the evaluator already agreed with will be accepted. {ACCEPT_CONSEQUENCE}
                      </div>
                    }
                    okText="Accept them"
                    cancelText="Cancel"
                    onConfirm={() => handleAcceptConfirmed(pendingFiltered)}
                    disabled={pendingTally.confirmed === 0}
                  >
                    <Button
                      type="primary"
                      icon={<CheckOutlined />}
                      loading={bulkAccept !== null}
                      disabled={pendingTally.confirmed === 0 || bulkVerify !== null}
                    >
                      Accept {pendingTally.confirmed} verified
                    </Button>
                  </Popconfirm>
                </div>

                {(bulkVerify || bulkAccept) && (
                  <div className="tests-triage-progress">
                    <Progress
                      percent={Math.round(
                        (((bulkVerify ?? bulkAccept)!.done / Math.max((bulkVerify ?? bulkAccept)!.total, 1)) * 100)
                      )}
                      size="small"
                      status="active"
                    />
                    <Text type="secondary">
                      {bulkVerify
                        ? `Checking ${bulkVerify.done} of ${bulkVerify.total} against the evaluator…`
                        : `Accepting ${bulkAccept!.done} of ${bulkAccept!.total}…`}
                    </Text>
                  </div>
                )}
              </Card>

              <div className="tests-card-grid">{pendingFiltered.map(renderTestCard)}</div>
            </section>
          )}

          {activeFiltered.length > 0 && (
            <section className="tests-section">
              <div className="tests-section-header">
                <div>
                  <div className="section-eyebrow">Accepted tests</div>
                  <Title level={4}>Active checks that run on publish</Title>
                </div>
                <Tag color="green">{activeFiltered.length} active</Tag>
              </div>
              <div className="tests-card-grid">{activeFiltered.map(renderTestCard)}</div>
            </section>
          )}

          {rejectedFiltered.length > 0 && (
            <section className="tests-section">
              <div className="tests-section-header">
                <div>
                  <div className="section-eyebrow">Inactive history</div>
                  <Title level={4}>Rejected proposals</Title>
                </div>
                <Tag>{rejectedFiltered.length} rejected</Tag>
              </div>
              <div className="tests-card-grid">{rejectedFiltered.map(renderTestCard)}</div>
            </section>
          )}
        </div>

        <aside className="tests-side-column">
          {/* These two panels are reference material — what a test is, and the
              lifecycle it moves through. They were permanently resident, which
              on an empty policy set meant ~940px of documentation sat beside a
              screen that had nothing to show yet. Reference should be available
              on demand; <details> gives that without state or a library. */}
          <details className="tests-guide-disclosure">
            <summary>How tests work — what counts as a test, and the lifecycle</summary>
            <div className="tests-guide-disclosure__body">
              <Card className="tests-guide-card">
                <Text strong>What counts as a test?</Text>
                <Title level={4}>A named policy scenario with expected evaluator output</Title>
                <Paragraph type="secondary">
                  Each test stores input facts and the status you expect. Running it compares the server evaluator's
                  actual response with that expectation.
                </Paragraph>
                <div className="tests-status-list">
                  {STATUS_OPTIONS.map((status) => (
                    <div key={status}>
                      <Tag color="blue">{status}</Tag>
                      <Text type="secondary">{STATUS_HELP[status]}</Text>
                    </div>
                  ))}
                </div>
              </Card>

              <Card className="tests-guide-card">
                <Text strong>Lifecycle</Text>
                <div className="tests-lifecycle">
                  <div>
                    <strong>1. Draft</strong>
                    <Text type="secondary"> Add manually or ask AI to propose candidates.</Text>
                  </div>
                  <div>
                    <strong>2. Review</strong>
                    <Text type="secondary"> Check each prediction against the evaluator, then accept or reject it.</Text>
                  </div>
                  <div>
                    <strong>3. Guard</strong>
                    <Text type="secondary"> Active tests run manually and automatically on publish.</Text>
                  </div>
                  <div>
                    <strong>4. Triage</strong>
                    <Text type="secondary"> Failed active tests are shown in the Quality tab.</Text>
                  </div>
                </div>
              </Card>
            </div>
          </details>
        </aside>
      </div>

      <Modal
        title="Add a manual policy test"
        open={createOpen}
        onCancel={() => setCreateOpen(false)}
        onOk={handleCreate}
        okText="Create saved test"
        confirmLoading={createSaving}
        destroyOnClose
        width={760}
      >
        {createError && <Alert type="error" showIcon message={createError} style={{ marginBottom: 12 }} />}
        <Alert
          type="info"
          showIcon
          className="tests-modal-help"
          message="You are saving a reusable evaluator check, not running an ad hoc evaluation."
          description="Provide the facts the evaluator should receive and the status you expect it to return."
        />
        <Form layout="vertical" form={form} initialValues={{ test_kind: "positive", expected_overall_status: "SATISFIED" }}>
          <Form.Item
            label="Name"
            name="name"
            extra="Use a scenario name a reviewer can recognize in Quality failures."
            rules={[{ required: true, message: "Enter a name" }]}
          >
            <Input placeholder="e.g. Small expense auto-approves" />
          </Form.Item>
          <Form.Item
            label="Description"
            name="description"
            extra="Optional: explain the policy behavior this test protects."
          >
            <Input.TextArea rows={2} placeholder="e.g. Employees below the approval threshold should be satisfied." />
          </Form.Item>
          <Form.Item
            label="Test kind"
            name="test_kind"
            extra="The kind tells reviewers what risk this test covers; it does not change evaluator behavior."
            rules={[{ required: true }]}
          >
            <Select options={TEST_KIND_ORDER.map((k) => ({ value: k, label: `${TEST_KIND_LABELS[k]} — ${TEST_KIND_HELP[k]}` }))} />
          </Form.Item>
          <Form.Item
            label="Input facts (JSON)"
            name="input_facts"
            extra='Facts are the request attributes sent to the evaluator, same shape as Evaluate. Include scope facts such as "subject.jurisdiction" when they matter.'
            rules={[{ required: true, message: "Enter input facts as JSON" }]}
          >
            <Input.TextArea
              rows={5}
              placeholder={'{\n  "amount": 50,\n  "subject.jurisdiction": "US",\n  "context.process": "expense"\n}'}
              style={{ fontFamily: "monospace" }}
            />
          </Form.Item>
          <Form.Item
            label="Expected overall status"
            name="expected_overall_status"
            extra="The deterministic evaluator must return this status for the test to pass."
            rules={[{ required: true }]}
          >
            <Select options={STATUS_OPTIONS.map((s) => ({ value: s, label: `${s} — ${STATUS_HELP[s]}` }))} />
          </Form.Item>
          <Form.Item
            label="Expected rule ID (optional)"
            name="expected_rule_id"
            extra="Use when the scenario must prove a specific rule, exception, or precedence winner fired."
          >
            <Input placeholder="e.g. RULE-001" />
          </Form.Item>
          <Form.Item
            label="Expected rule status (optional)"
            name="expected_rule_status"
            extra="If you pinned a rule ID, optionally assert that rule's status too."
          >
            <Select allowClear options={STATUS_OPTIONS.map((s) => ({ value: s, label: `${s} — ${STATUS_HELP[s]}` }))} />
          </Form.Item>
          <Form.Item
            label="Expected missing facts (optional, comma-separated)"
            name="expected_missing_facts"
            extra="For missing-fact tests, list the fact names the evaluator should report as missing."
          >
            <Input placeholder="amount, manager_approved" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
