import { useEffect, useState } from "react";
import { Alert, Button, Card, Form, Input, Modal, Select, Space, Tag, Typography } from "antd";
import {
  CheckOutlined,
  CloseOutlined,
  HistoryOutlined,
  PlayCircleOutlined,
  PlusOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons";
import dayjs from "dayjs";
import {
  policyTestApi,
  PolicyPlatformApiError,
  type CreatePolicyTestRequest,
  type EvaluationStatus,
  type PolicyTestKind,
  type PolicyTestListItem,
  type PolicyTestRun,
} from "../api";
import { useActor } from "../ActorContext";

const { Title, Text, Paragraph } = Typography;

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
  const [proposing, setProposing] = useState(false);
  const [runningId, setRunningId] = useState<string | null>(null);
  const [reviewingId, setReviewingId] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [runHistory, setRunHistory] = useState<Record<string, PolicyTestRun[]>>({});
  const [createOpen, setCreateOpen] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [createSaving, setCreateSaving] = useState(false);
  const [form] = Form.useForm();

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
      await policyTestApi.propose(policySetKey, reasoningEffort);
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
  const pendingFiltered = filtered.filter((t) => t.test.review_status === "pending_review");
  const activeFiltered = filtered.filter((t) => t.test.review_status === "active");
  const rejectedFiltered = filtered.filter((t) => t.test.review_status === "rejected");
  const latestRuns = tests.filter((t) => t.latest_run);

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

    return (
      <Card
        key={t.id}
        size="small"
        className={`finding-card tests-test-card${isPending ? " tests-test-card--pending" : ""}`}
      >
        <div className="tests-card-topline">
          <Space size={8} wrap>
            <Tag>{TEST_KIND_LABELS[t.test_kind]}</Tag>
            {t.proposed_by === "ai" && (
              <Tag icon={<ThunderboltOutlined />} color="purple">
                AI-proposed
              </Tag>
            )}
            {isPending && <Tag color="gold">Review before active</Tag>}
            {t.review_status === "rejected" && <Tag>Rejected</Tag>}
            {run ? <Tag color={RUN_STATUS_COLOR[run.status] ?? "default"}>{run.status.toUpperCase()}</Tag> : <Tag>Never run</Tag>}
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
            {run && run.status !== "pass" && (
              <Paragraph type="danger" className="tests-run-explanation">
                {run.explanation}
              </Paragraph>
            )}
          </div>

          <div className="tests-card-actions">
            {isPending ? (
              <Space>
                <Button
                  size="small"
                  icon={<CheckOutlined />}
                  onClick={() => handleReview(t.id, "accept")}
                  loading={reviewingId === t.id}
                >
                  Accept
                </Button>
                <Button
                  size="small"
                  danger
                  icon={<CloseOutlined />}
                  onClick={() => handleReview(t.id, "reject")}
                  loading={reviewingId === t.id}
                >
                  Reject
                </Button>
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
          <div className="section-eyebrow">Policy assurance</div>
          <Title level={3} style={{ margin: 0 }}>
            Tests
          </Title>
        </div>
        <Button icon={<PlusOutlined />} onClick={openCreate}>
          Add test manually
        </Button>
      </div>

      <Paragraph type="secondary" className="tests-page-intro">
        Named, saved checks for this policy set — separate from one-off Evaluate experiments. AI can draft candidates,
        but only accepted tests become active, and every result is decided by the deterministic evaluator.
      </Paragraph>

      {error && <Alert type="error" showIcon message={error} closable onClose={() => setError(null)} />}

      <div className="tests-summary-grid">
        <Card size="small" className="tests-summary-card">
          <Text type="secondary">Saved tests</Text>
          <strong>{tests.length}</strong>
        </Card>
        <Card size="small" className="tests-summary-card">
          <Text type="secondary">Awaiting review</Text>
          <strong>{pendingReview.length}</strong>
        </Card>
        <Card size="small" className="tests-summary-card">
          <Text type="secondary">Latest runs</Text>
          <strong>{latestRuns.length}</strong>
        </Card>
        <Card size="small" className="tests-summary-card">
          <Text type="secondary">Failed latest run</Text>
          <strong>{tests.filter((t) => t.latest_run?.status === "fail" || t.latest_run?.status === "error").length}</strong>
        </Card>
      </div>

      <div className="tests-control-grid">
        <Card className="tests-ai-panel">
          <div className="section-eyebrow">
            <ThunderboltOutlined /> AI proposal helper
          </div>
          <Title level={4} className="tests-panel-title">
            Draft reviewable tests from the current policy set
          </Title>
          <Paragraph type="secondary" className="tests-panel-copy">
            The AI creates candidate tests only. Review and accept them before they count, run on publish, or appear in
            Quality failures.
          </Paragraph>
          <Space wrap>
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
            <Button type="primary" icon={<ThunderboltOutlined />} onClick={handlePropose} loading={proposing}>
              {proposing ? "Proposing…" : "Propose tests with AI"}
            </Button>
          </Space>
          <Text type="secondary" className="tests-field-note">
            Higher effort asks for more careful coverage; it does not change how pass/fail is judged.
          </Text>
        </Card>

        <Card className="tests-filter-panel">
          <div className="section-eyebrow">View tests by kind</div>
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
                onClick={() => setKindFilter(k)}
              >
                <span>{TEST_KIND_LABELS[k]}</span>
                <small>{TEST_KIND_HELP[k]}</small>
              </button>
            ))}
          </div>
        </Card>
      </div>

      <div className="tests-main-grid">
        <div className="tests-list-column">
          {!loading && tests.length === 0 && (
            <Card className="tests-empty-state">
              <div className="section-eyebrow">How policy tests work</div>
              <Title level={4}>Save expected outcomes, then let the evaluator prove them</Title>
              <div className="tests-flow">
                <div>
                  <span>Given these facts</span>
                  <code>{'{"amount": 50, "subject.jurisdiction": "US"}'}</code>
                </div>
                <strong>→</strong>
                <div>
                  <span>Expect this status</span>
                  <Tag color="blue">SATISFIED</Tag>
                </div>
                <strong>→</strong>
                <div>
                  <span>Deterministic evaluator decides</span>
                  <Tag color="green">PASS</Tag>
                </div>
              </div>
              <div className="tests-empty-notes">
                <div>
                  <strong>AI helps draft.</strong>
                  <Text type="secondary"> Proposals stay in review until you accept them.</Text>
                </div>
                <div>
                  <strong>Publish re-runs active tests.</strong>
                  <Text type="secondary"> Failures surface in Quality → Failed policy tests.</Text>
                </div>
                <div>
                  <strong>Kinds explain intent.</strong>
                  <Text type="secondary"> Positive, negative, boundary, missing fact, scope, date, exception, precedence.</Text>
                </div>
              </div>
              <Space wrap>
                <Button type="primary" icon={<ThunderboltOutlined />} onClick={handlePropose} loading={proposing}>
                  Propose reviewable tests
                </Button>
                <Button icon={<PlusOutlined />} onClick={openCreate}>
                  Create one manually
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
                  <div className="section-eyebrow">AI proposals</div>
                  <Title level={4}>Review before they count</Title>
                </div>
                <Tag color="gold">{pendingFiltered.length} pending</Tag>
              </div>
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
          <Card className="tests-guide-card">
            <div className="section-eyebrow">What counts as a test?</div>
            <Title level={4}>A named policy scenario with expected evaluator output</Title>
            <Paragraph type="secondary">
              Each test stores input facts and the status you expect. Running it compares the server evaluator's actual
              response with that expectation.
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
            <div className="section-eyebrow">Lifecycle</div>
            <div className="tests-lifecycle">
              <div>
                <strong>1. Draft</strong>
                <Text type="secondary"> Add manually or ask AI to propose candidates.</Text>
              </div>
              <div>
                <strong>2. Review</strong>
                <Text type="secondary"> Accept proposals you trust; reject the rest.</Text>
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
