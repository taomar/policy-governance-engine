import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Alert,
  Badge,
  Button,
  Card,
  Collapse,
  Empty,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Space,
  Spin,
  Statistic,
  Steps,
  Table,
  Tag,
  Tooltip,
  Typography,
  message,
} from "antd";
import {
  BarChartOutlined,
  BulbOutlined,
  CheckCircleOutlined,
  DeleteOutlined,
  ExperimentOutlined,
  InfoCircleOutlined,
  NodeIndexOutlined,
  ThunderboltOutlined,
  WarningOutlined,
} from "@ant-design/icons";
import {
  api,
  PolicyPlatformApiError,
  type AggregateEligibilityResponse,
  type AggregateLimitResponse,
  type CanonicalRule,
  type PreviewAggregateLimitResponse,
  type PreviewContribution,
  type ProposedAggregateLimit,
  type RuleEligibility,
} from "../api";
import { EvaluationTargetBanner, useEvaluationTarget } from "./EvaluationTarget";

const { Title, Text, Paragraph } = Typography;

/**
 * Discovery-first authoring for cross-rule combined caps (OMG DMN Collect+SUM —
 * see contracts/policy.py::AggregateLimit).
 *
 * This replaces a plain CRUD form whose real problem was not its looks. In that
 * form `amount_fact` was a free-text box and the rule picker listed every rule
 * in the version, including rules that structurally cannot contribute. Because
 * `_evaluate_aggregate_limits` skips a contribution *silently* when the rule is
 * not SATISFIED or the fact is not numeric, you could author a cap, save it,
 * publish it, and never learn that it counts nothing. Nothing in the product
 * said so.
 *
 * So the page is built around the three questions that were unanswerable:
 *
 *  1. Which rules could contribute at all? Answered deterministically by
 *     `GET .../aggregate-limits/eligibility` before anything else is offered.
 *     It is the gate, not a hint — if fewer than two rules qualify there is no
 *     honest cap to build, and the page says why per rule.
 *  2. Which rules *should* share a cap? That is genuine discovery work and is
 *     where the AI is used — but only over the eligible set, and every proposal
 *     is re-validated server-side against real rule ids and each rule's own
 *     declared numeric facts.
 *  3. What would it actually do? Answered by running the draft through the real
 *     evaluator before saving. A cap nothing contributed to is reported as
 *     `inert`, never as "within limits".
 *
 * Back-trace is carried by `contributing_rules`, which names every source rule
 * and is snapshotted verbatim into the published version — so it survives
 * publication rather than living only in this UI.
 */

const BLOCKER_COPY: Record<string, { label: string; detail: string }> = {
  not_machine_executable: {
    label: "Not machine-executable",
    detail:
      "The evaluator returns NOT_APPLICABLE for this rule before it reads the scope or condition, so the rule can never reach SATISFIED — and only a SATISFIED rule contributes to a cap.",
  },
  no_numeric_fact: {
    label: "No numeric fact declared",
    detail:
      "The rule declares no fact with a numeric type, so there is no value for the evaluator to add up. Any amount fact chosen for it would be invented, and an unrecognised fact is counted as zero without warning.",
  },
};

type Verdict = PreviewAggregateLimitResponse["verdict"];

const VERDICT_COPY: Record<
  Verdict,
  { type: "success" | "warning" | "error"; title: string; detail: string }
> = {
  breached: {
    type: "error",
    title: "Cap breached with these amounts",
    detail:
      "The contributing rules together exceeded the ceiling, so the evaluator raised a breach. This is the cap doing its job.",
  },
  within_limit: {
    type: "success",
    title: "Within the cap",
    detail:
      "Rules contributed real amounts and the total stayed under the ceiling. The cap is wired up correctly.",
  },
  inert: {
    type: "warning",
    title: "Nothing contributed — this cap would do nothing",
    detail:
      "No rule contributed a numeric amount, so the total is zero and the ceiling can never be reached. This is not a pass: saving it would add a limit that silently never fires.",
  },
};

interface PreviewState {
  proposal: ProposedAggregateLimit;
  facts: Record<string, number | null>;
  result: PreviewAggregateLimitResponse | null;
  running: boolean;
  error: string | null;
}

function errText(e: unknown): string {
  return e instanceof PolicyPlatformApiError ? e.detail : String(e);
}

export function AggregateLimitsPage({ policySetKey }: { policySetKey: string }) {
  const evaluationTarget = useEvaluationTarget(policySetKey);

  const [limits, setLimits] = useState<AggregateLimitResponse[]>([]);
  const [rules, setRules] = useState<CanonicalRule[]>([]);
  const [eligibility, setEligibility] = useState<AggregateEligibilityResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [guidance, setGuidance] = useState("");
  const [discovering, setDiscovering] = useState(false);
  const [proposals, setProposals] = useState<ProposedAggregateLimit[] | null>(null);
  const [skipped, setSkipped] = useState<string[]>([]);
  const [discoverError, setDiscoverError] = useState<string | null>(null);

  const [preview, setPreview] = useState<PreviewState | null>(null);
  const [saving, setSaving] = useState(false);
  const [detailOpen, setDetailOpen] = useState<string[]>([]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [limitRows, versions] = await Promise.all([
        api.listAggregateLimits(policySetKey),
        api.listPolicyVersions(policySetKey),
      ]);
      setLimits(limitRows);
      const active = versions.find((v) => v.is_active) ?? versions[0];
      if (!active) {
        setRules([]);
        setEligibility(null);
        return;
      }
      // Settled, not all: a policy set with no published version legitimately
      // has no eligibility report, and losing the rule list with it would leave
      // the page unable to name a single rule in the saved caps below.
      const [ruleList, report] = await Promise.allSettled([
        api.getVersionRules(policySetKey, active.id),
        api.getAggregateEligibility(policySetKey),
      ]);
      setRules(ruleList.status === "fulfilled" ? ruleList.value : []);
      setEligibility(report.status === "fulfilled" ? report.value : null);
    } catch (e) {
      setError(errText(e));
    } finally {
      setLoading(false);
    }
  }, [policySetKey]);

  useEffect(() => {
    load();
  }, [load]);

  const rulesById = useMemo(() => new Map(rules.map((r) => [r.rule_id, r])), [rules]);
  const titleFor = useCallback(
    (ruleId: string) => rulesById.get(ruleId)?.title ?? ruleId,
    [rulesById]
  );

  const canDiscover = Boolean(eligibility?.can_build_limit);

  const currentStep = useMemo(() => {
    if (!eligibility?.can_build_limit) return 0;
    if (proposals === null) return 1;
    return 2;
  }, [eligibility, proposals]);

  const handleDiscover = async () => {
    setDiscovering(true);
    setDiscoverError(null);
    try {
      const result = await api.proposeAggregateLimits(policySetKey, {
        reasoning_effort: "medium",
        guidance: guidance.trim(),
      });
      setProposals(result.proposals);
      setSkipped(result.skipped);
      setEligibility(result.eligibility);
      if (result.proposals.length === 0) {
        message.info("No rule group qualified for a shared cap");
      } else {
        message.success(`Found ${result.proposals.length} candidate combined cap(s)`);
      }
    } catch (e) {
      setDiscoverError(errText(e));
    } finally {
      setDiscovering(false);
    }
  };

  const openPreview = (proposal: ProposedAggregateLimit) => {
    // Seed one input per contributing rule's amount fact — the reviewer should
    // not have to work out which fact names matter.
    const facts: Record<string, number | null> = {};
    proposal.contributing_rules.forEach((c) => {
      facts[c.amount_fact] = null;
    });
    setPreview({ proposal, facts, result: null, running: false, error: null });
  };

  const runPreview = async () => {
    if (!preview) return;
    setPreview({ ...preview, running: true, error: null });
    try {
      const factPayload: Record<string, unknown> = {};
      Object.entries(preview.facts).forEach(([k, v]) => {
        if (v !== null && v !== undefined) factPayload[k] = v;
      });
      const result = await api.previewAggregateLimit(policySetKey, {
        contributing_rules: preview.proposal.contributing_rules.map((c) => ({
          rule_id: c.rule_id,
          amount_fact: c.amount_fact,
        })),
        max_value: preview.proposal.max_value,
        description: preview.proposal.description,
        facts: factPayload,
      });
      setPreview((prev) => (prev ? { ...prev, result, running: false } : prev));
    } catch (e) {
      const detail = errText(e);
      setPreview((prev) => (prev ? { ...prev, running: false, error: detail } : prev));
    }
  };

  const saveProposal = async (proposal: ProposedAggregateLimit) => {
    setSaving(true);
    try {
      await api.createAggregateLimit(policySetKey, {
        aggregate_key: proposal.aggregate_key,
        description: proposal.description,
        contributing_rules: proposal.contributing_rules.map((c) => ({
          rule_id: c.rule_id,
          amount_fact: c.amount_fact,
        })),
        aggregator: "SUM",
        max_value: proposal.max_value,
        period: proposal.period,
      });
      message.success("Combined cap saved — it takes effect on the next publish");
      setProposals((prev) => prev?.filter((p) => p.aggregate_key !== proposal.aggregate_key) ?? null);
      setPreview(null);
      await load();
    } catch (e) {
      message.error(errText(e));
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (aggregateKey: string) => {
    try {
      await api.deleteAggregateLimit(policySetKey, aggregateKey);
      message.success("Combined cap deleted — takes effect on the next publish");
      await load();
    } catch (e) {
      message.error(errText(e));
    }
  };

  const orderedEligibility = useMemo(() => {
    if (!eligibility) return [];
    return [
      ...eligibility.rules.filter((r) => r.eligible),
      ...eligibility.rules.filter((r) => !r.eligible),
    ];
  }, [eligibility]);

  return (
    <div className="aggregate-limits-page">
      <div className="aggregate-page-head">
        <Title level={4} style={{ marginBottom: 4 }}>
          Combined caps
        </Title>
        <Paragraph type="secondary" className="aggregate-page-lede">
          A ceiling that <Text strong>several rules share</Text>. Each rule stays within its own limit,
          but together they must not exceed a combined total — something no single rule can express,
          because no rule can see another rule's outcome.
        </Paragraph>
      </div>

      <EvaluationTargetBanner
        scope="published"
        target={evaluationTarget}
        actionLabel="Combined caps are evaluated against"
        emptyHint="Publish a version before building a combined cap."
      />

      {error && <Alert type="error" message={error} showIcon style={{ marginTop: 16 }} />}

      <Steps
        className="aggregate-steps"
        current={currentStep}
        size="small"
        items={[
          {
            title: "Check what can contribute",
            description: "Deterministic — no AI",
            icon: <NodeIndexOutlined />,
          },
          {
            title: "Discover shared pools",
            description: "AI over eligible rules only",
            icon: <BulbOutlined />,
          },
          {
            title: "Preview, then save",
            description: "Runs the real evaluator",
            icon: <ExperimentOutlined />,
          },
        ]}
      />

      {loading && !eligibility && (
        <div className="aggregate-loading">
          <Spin />
        </div>
      )}

      {/* ---------------- Step 1 — eligibility gate ---------------- */}
      {eligibility && (
        <Card
          size="small"
          className="aggregate-section"
          title={
            <Space>
              <NodeIndexOutlined />
              <span>Which published rules can contribute?</span>
            </Space>
          }
        >
          <Paragraph type="secondary" className="aggregate-section-lede">
            A rule can only count toward a shared cap if the evaluator can actually add it up. Both ways
            that fails are silent — the contribution is skipped, nothing is logged, and the cap looks
            configured while doing nothing. So this is checked first, deterministically, before any cap
            is offered.
          </Paragraph>

          <div className="aggregate-stat-row">
            <Statistic title="Rules in the published version" value={eligibility.total_rules} />
            <Statistic
              title="Can contribute"
              value={eligibility.eligible_count}
              valueStyle={eligibility.eligible_count === 0 ? { color: "#a8071a" } : undefined}
            />
            <Statistic title="Cannot contribute" value={eligibility.blocked_count} />
          </div>

          {eligibility.can_build_limit ? (
            <Alert
              type="success"
              showIcon
              className="aggregate-gate-alert"
              message={`${eligibility.eligible_count} rules can contribute to a shared cap`}
              description="Each is machine-executable and declares at least one numeric fact the evaluator can sum."
            />
          ) : (
            <Alert
              type="warning"
              showIcon
              className="aggregate-gate-alert"
              message={
                eligibility.eligible_count === 0
                  ? "No rule in this published version can contribute to a combined cap"
                  : "Only one rule can contribute — a combined cap needs at least two"
              }
              description={
                <>
                  <Paragraph style={{ marginBottom: 8 }}>
                    A cap built over these rules would save and publish cleanly and then never fire,
                    because the evaluator would skip every contribution without reporting anything. That
                    is why authoring is closed here rather than merely discouraged.
                  </Paragraph>
                  <Space size={[8, 8]} wrap>
                    {Object.entries(eligibility.blocker_totals)
                      .filter(([, count]) => count > 0)
                      .map(([code, count]) => (
                        <Tooltip key={code} title={BLOCKER_COPY[code]?.detail}>
                          <Tag color="orange" icon={<InfoCircleOutlined />}>
                            {count} × {BLOCKER_COPY[code]?.label ?? code}
                          </Tag>
                        </Tooltip>
                      ))}
                  </Space>
                </>
              }
            />
          )}

          <Collapse
            ghost
            activeKey={detailOpen}
            onChange={(k) => setDetailOpen(Array.isArray(k) ? k : [k])}
            className="aggregate-eligibility-collapse"
            items={[
              {
                key: "detail",
                label: (
                  <Text strong>
                    Per-rule detail
                    <Text type="secondary" style={{ fontWeight: 400 }}>
                      {" "}
                      — why each rule can or cannot contribute
                    </Text>
                  </Text>
                ),
                children: (
                  <Table<RuleEligibility>
                    size="small"
                    rowKey="rule_id"
                    dataSource={orderedEligibility}
                    pagination={orderedEligibility.length > 12 ? { pageSize: 12 } : false}
                    columns={[
                      {
                        title: "Rule",
                        dataIndex: "title",
                        render: (_v, row) => (
                          <div>
                            <Text>{row.title}</Text>
                            <br />
                            <Text type="secondary" className="entity-id-row">
                              {row.rule_id}
                            </Text>
                          </div>
                        ),
                      },
                      {
                        title: "Can contribute",
                        dataIndex: "eligible",
                        width: 140,
                        render: (eligible: boolean) =>
                          eligible ? (
                            <Badge status="success" text="Yes" />
                          ) : (
                            <Badge status="default" text="No" />
                          ),
                      },
                      {
                        title: "Numeric facts the evaluator could sum",
                        dataIndex: "numeric_facts",
                        render: (facts: RuleEligibility["numeric_facts"]) =>
                          facts.length === 0 ? (
                            <Text type="secondary">none declared</Text>
                          ) : (
                            <Space size={[4, 4]} wrap>
                              {facts.map((f) => (
                                <Tag key={f.name} className="fact-tag">
                                  {f.name}
                                  <Text type="secondary"> · {f.data_type}</Text>
                                </Tag>
                              ))}
                            </Space>
                          ),
                      },
                      {
                        title: "Why not",
                        dataIndex: "blockers",
                        render: (blockers: string[]) =>
                          blockers.length === 0 ? (
                            <Text type="secondary">—</Text>
                          ) : (
                            <Space size={[4, 4]} wrap>
                              {blockers.map((b) => (
                                <Tooltip key={b} title={BLOCKER_COPY[b]?.detail}>
                                  <Tag color="orange">{BLOCKER_COPY[b]?.label ?? b}</Tag>
                                </Tooltip>
                              ))}
                            </Space>
                          ),
                      },
                    ]}
                  />
                ),
              },
            ]}
          />
        </Card>
      )}

      {/* ---------------- Step 2 — discovery ---------------- */}
      <Card
        size="small"
        className="aggregate-section"
        title={
          <Space>
            <BulbOutlined />
            <span>Find rules that draw on one shared pool</span>
          </Space>
        }
      >
        <Paragraph type="secondary" className="aggregate-section-lede">
          Spotting that several separately-written rules are really drawing on one finite pool is the
          hard part, and the part worth automating. The model only ever sees rules that passed the check
          above, and may only pick an amount fact from that rule's own declared facts — so a proposal
          cannot reference a rule or a fact that does not exist.
        </Paragraph>

        <Space direction="vertical" size={12} style={{ width: "100%" }}>
          <Input.TextArea
            rows={2}
            value={guidance}
            onChange={(e) => setGuidance(e.target.value)}
            placeholder="Optional steer, e.g. “look for shared annual leave ceilings” or “focus on monetary allowances”"
            disabled={!canDiscover || discovering}
          />
          <Space wrap>
            <Button
              type="primary"
              icon={<ThunderboltOutlined />}
              loading={discovering}
              disabled={!canDiscover}
              onClick={handleDiscover}
            >
              {proposals === null ? "Find combined caps" : "Search again"}
            </Button>
            {guidance && !discovering && <Button onClick={() => setGuidance("")}>Clear steer</Button>}
            {!canDiscover && (
              <Text type="secondary">
                Needs at least two rules that can contribute — see the check above.
              </Text>
            )}
          </Space>
        </Space>

        {discoverError && (
          <Alert type="error" message={discoverError} showIcon style={{ marginTop: 12 }} />
        )}

        {skipped.length > 0 && (
          <Alert
            type="info"
            showIcon
            style={{ marginTop: 12 }}
            message={`${skipped.length} proposal(s) rejected during validation`}
            description={
              <ul className="aggregate-skipped-list">
                {skipped.map((s) => (
                  <li key={s}>{s}</li>
                ))}
              </ul>
            }
          />
        )}

        {proposals !== null && proposals.length === 0 && !discovering && (
          <Empty
            className="aggregate-empty"
            description="No group of rules was found to share a single finite pool. That is a valid answer — most rule sets have none."
          />
        )}

        {proposals && proposals.length > 0 && (
          <Space direction="vertical" size={12} style={{ width: "100%", marginTop: 16 }}>
            {proposals.map((proposal) => (
              <article key={proposal.aggregate_key} className="aggregate-proposal-card">
                <div className="aggregate-card-head">
                  <div>
                    <Text strong>{proposal.description || proposal.aggregate_key}</Text>
                    <br />
                    <Text type="secondary" className="entity-id-row">
                      {proposal.aggregate_key}
                    </Text>
                  </div>
                  <Space size={[4, 4]} wrap>
                    <Tag color="geekblue" icon={<BarChartOutlined />}>
                      max {proposal.max_value}
                      {proposal.period ? ` / ${proposal.period}` : ""}
                    </Tag>
                    <Tooltip
                      title={
                        proposal.max_value_confidence === "stated"
                          ? "This ceiling appears in the source text."
                          : "The rules imply a shared ceiling but never state the number. This figure is the model's suggestion — check it before saving."
                      }
                    >
                      <Tag
                        color={proposal.max_value_confidence === "stated" ? "green" : "orange"}
                        icon={
                          proposal.max_value_confidence === "stated" ? (
                            <CheckCircleOutlined />
                          ) : (
                            <WarningOutlined />
                          )
                        }
                      >
                        {proposal.max_value_confidence === "stated"
                          ? "ceiling from source"
                          : "ceiling needs checking"}
                      </Tag>
                    </Tooltip>
                  </Space>
                </div>

                {proposal.rationale && (
                  <Paragraph className="aggregate-rationale">
                    <Text type="secondary">Why these rules share a pool: </Text>
                    {proposal.rationale}
                  </Paragraph>
                )}

                <div className="aggregate-backtrace">
                  <Text strong className="aggregate-backtrace-label">
                    Contributing rules
                  </Text>
                  {proposal.contributing_rules.map((c) => (
                    <div key={c.rule_id} className="aggregate-backtrace-row">
                      <div className="aggregate-backtrace-rule">
                        <Text>{titleFor(c.rule_id)}</Text>
                        <Text type="secondary" className="entity-id-row">
                          {c.rule_id}
                        </Text>
                      </div>
                      <Tag className="fact-tag">{c.amount_fact}</Tag>
                      {c.why && (
                        <Text type="secondary" className="aggregate-backtrace-why">
                          {c.why}
                        </Text>
                      )}
                    </div>
                  ))}
                </div>

                <Space style={{ marginTop: 12 }} wrap>
                  <Button
                    type="primary"
                    icon={<ExperimentOutlined />}
                    onClick={() => openPreview(proposal)}
                  >
                    Preview what it would do
                  </Button>
                  <Popconfirm
                    title="Save this combined cap?"
                    description={
                      <div className="aggregate-confirm-copy">
                        It will be evaluated on every request against this policy set from the next
                        publish onward. A breach is reported in the evaluation response; it does not
                        block the request.
                      </div>
                    }
                    okText="Save cap"
                    onConfirm={() => saveProposal(proposal)}
                  >
                    <Button loading={saving}>Save without previewing</Button>
                  </Popconfirm>
                </Space>
              </article>
            ))}
          </Space>
        )}
      </Card>

      {/* ---------------- Saved caps, with back-trace ---------------- */}
      <Card
        size="small"
        className="aggregate-section"
        title={
          <Space>
            <BarChartOutlined />
            <span>Saved combined caps</span>
            <Badge count={limits.length} showZero color="#8c8c8c" />
          </Space>
        }
      >
        {limits.length === 0 ? (
          <Empty
            className="aggregate-empty"
            description="No combined caps saved yet — nothing in this policy set shares a ceiling."
          />
        ) : (
          <Space direction="vertical" size={12} style={{ width: "100%" }}>
            {limits.map((row) => (
              <article key={row.id} className="aggregate-limit-card">
                <div className="aggregate-card-head">
                  <div>
                    <Text strong>{row.description || row.aggregate_key}</Text>
                    <br />
                    <Text
                      type="secondary"
                      className="entity-id-row"
                      copyable={{ text: row.aggregate_key }}
                    >
                      {row.aggregate_key}
                    </Text>
                  </div>
                  <Space>
                    <Tag color="geekblue" icon={<BarChartOutlined />}>
                      max {row.max_value}
                      {row.period ? ` / ${row.period}` : ""}
                    </Tag>
                    <Popconfirm
                      title="Delete this combined cap?"
                      description="Contributing rules stop sharing this ceiling from the next publish."
                      onConfirm={() => handleDelete(row.aggregate_key)}
                      okText="Delete"
                      okButtonProps={{ danger: true }}
                    >
                      <Button size="small" danger icon={<DeleteOutlined />}>
                        Delete
                      </Button>
                    </Popconfirm>
                  </Space>
                </div>
                <div className="aggregate-backtrace">
                  <Text strong className="aggregate-backtrace-label">
                    Back-trace to individual rules
                  </Text>
                  {row.contributing_rules.map((c) => (
                    <div key={c.rule_id} className="aggregate-backtrace-row">
                      <div className="aggregate-backtrace-rule">
                        <Text>{titleFor(c.rule_id)}</Text>
                        <Text type="secondary" className="entity-id-row">
                          {c.rule_id}
                        </Text>
                      </div>
                      <Tag className="fact-tag">{c.amount_fact}</Tag>
                    </div>
                  ))}
                </div>
              </article>
            ))}
          </Space>
        )}
      </Card>

      {/* ---------------- Preview ---------------- */}
      <Modal
        title="Preview: what would this cap actually do?"
        open={preview !== null}
        onCancel={() => setPreview(null)}
        width={760}
        footer={
          preview && (
            <Space>
              <Button onClick={() => setPreview(null)}>Close</Button>
              <Button
                icon={<ExperimentOutlined />}
                type={preview.result ? "default" : "primary"}
                loading={preview.running}
                onClick={runPreview}
              >
                {preview.result ? "Run again" : "Run preview"}
              </Button>
              <Popconfirm
                title="Save this combined cap?"
                description={
                  <div className="aggregate-confirm-copy">
                    It will be evaluated on every request against this policy set from the next publish
                    onward.
                  </div>
                }
                okText="Save cap"
                onConfirm={() => saveProposal(preview.proposal)}
              >
                <Button type="primary" loading={saving}>
                  Save cap
                </Button>
              </Popconfirm>
            </Space>
          )
        }
      >
        {preview && (
          <>
            <Paragraph type="secondary">
              This runs the draft cap through the <Text strong>real evaluator</Text>, not a simulation —
              the same code path a published cap takes. Supply an amount for each contributing rule and
              see exactly what gets counted.
            </Paragraph>

            <Form layout="vertical">
              {preview.proposal.contributing_rules.map((c) => (
                <Form.Item
                  key={c.amount_fact}
                  label={
                    <Space size={4}>
                      <Text>{titleFor(c.rule_id)}</Text>
                      <Tag className="fact-tag">{c.amount_fact}</Tag>
                    </Space>
                  }
                  style={{ marginBottom: 12 }}
                >
                  <InputNumber
                    style={{ width: "100%" }}
                    value={preview.facts[c.amount_fact]}
                    placeholder="amount contributed by this rule"
                    onChange={(v) =>
                      setPreview((prev) =>
                        prev ? { ...prev, facts: { ...prev.facts, [c.amount_fact]: v } } : prev
                      )
                    }
                  />
                </Form.Item>
              ))}
            </Form>

            {preview.error && <Alert type="error" message={preview.error} showIcon />}

            {preview.result && (
              <>
                <Alert
                  className="aggregate-verdict"
                  type={VERDICT_COPY[preview.result.verdict].type}
                  showIcon
                  message={VERDICT_COPY[preview.result.verdict].title}
                  description={VERDICT_COPY[preview.result.verdict].detail}
                />
                <div className="aggregate-stat-row" style={{ marginTop: 16 }}>
                  <Statistic title="Counted total" value={preview.result.total} />
                  <Statistic title="Ceiling" value={preview.result.max_value} />
                  <Statistic
                    title="Rules that contributed"
                    value={`${preview.result.contributing_count} / ${preview.result.contributions.length}`}
                    valueStyle={
                      preview.result.contributing_count === 0 ? { color: "#d46b08" } : undefined
                    }
                  />
                </div>
                <Table<PreviewContribution>
                  size="small"
                  className="aggregate-preview-table"
                  rowKey="rule_id"
                  pagination={false}
                  dataSource={preview.result.contributions}
                  columns={[
                    {
                      title: "Rule",
                      dataIndex: "rule_id",
                      render: (id: string) => <Text>{titleFor(id)}</Text>,
                    },
                    { title: "Status", dataIndex: "rule_status", width: 140 },
                    {
                      title: "Counted",
                      dataIndex: "contributed",
                      width: 110,
                      render: (contributed: boolean, row) =>
                        contributed ? (
                          <Badge status="success" text={String(row.amount)} />
                        ) : (
                          <Badge status="default" text="0" />
                        ),
                    },
                    { title: "Why", dataIndex: "reason" },
                  ]}
                />
              </>
            )}
          </>
        )}
      </Modal>
    </div>
  );
}
