/**
 * "Test scenario" tab for a single, already-published rule — runs the REAL
 * deterministic evaluation engine (`evaluator.engine.evaluate_policy`) against
 * facts an AI conservatively infers from a plain-English scenario.
 *
 * This is architecturally distinct from `EditRuleModal.tsx`'s "AI Evaluate"
 * tab, which is advisory-only AI reasoning that never touches the real
 * engine (see `ai_scenario_eval.py`). Here, AI only does two things — infer
 * facts, and explain an already-decided result in plain language — while the
 * verdict itself always comes from the same evaluator that production
 * evaluations use. See `ai_scenario_engine.py`'s module docstring for the
 * full rationale (including why results are intentionally NOT written to the
 * evaluation audit trail: this is an exploratory reviewer check, not a
 * production calling-system event).
 */
import { useEffect, useState } from "react";
import { Alert, Button, Descriptions, Input, Select, Space, Tag, Tooltip, Typography } from "antd";
import { ExperimentOutlined, InfoCircleOutlined } from "@ant-design/icons";
import {
  aiApi,
  PolicyPlatformApiError,
  type CanonicalRule,
  type EvaluationStatus,
  type RuleScenarioTestResult,
} from "../api";
import { DETERMINISTIC_LABEL, DETERMINISTIC_REASON } from "../ruleExecutability";

const { Text, Paragraph } = Typography;
const { TextArea } = Input;

const STATUS_COLOR: Record<EvaluationStatus, string> = {
  SATISFIED: "green",
  NOT_SATISFIED: "red",
  NOT_APPLICABLE: "default",
  INDETERMINATE: "gold",
  ERROR: "red",
};

type ReasoningEffort = "low" | "medium" | "high";

interface RuleScenarioTesterProps {
  policySetKey: string;
  rule: CanonicalRule;
}

export function RuleScenarioTester({ policySetKey, rule }: RuleScenarioTesterProps) {
  const [scenario, setScenario] = useState("");
  const [reasoningEffort, setReasoningEffort] = useState<ReasoningEffort>("low");
  const [result, setResult] = useState<RuleScenarioTestResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const mappingStatuses = Array.from(
    new Set(rule.formulation?.dmn_decisions.map((decision) => decision.dmn_mapping_status) ?? []),
  );
  const formulationRequirements = Array.from(
    new Set(rule.formulation?.dmn_decisions.flatMap((decision) => decision.requirements) ?? []),
  );

  // Switching rules while this tab is open should not show a stale result
  // from a different rule under the new title/condition.
  useEffect(() => {
    setResult(null);
    setError(null);
    setScenario("");
  }, [rule.rule_id]);

  const run = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await aiApi.testRuleScenario(policySetKey, rule.rule_id, scenario.trim(), reasoningEffort);
      setResult(res);
    } catch (e) {
      setError(e instanceof PolicyPlatformApiError ? e.detail : String(e));
    } finally {
      setLoading(false);
    }
  };

  const factEntries = result ? Object.entries(result.inferred_facts) : [];
  const rr = result?.rule_result ?? null;

  return (
    <div className="inspector-pane">
      <Alert
        type={rule.machine_executable ? "success" : "warning"}
        showIcon
        message={
          rule.machine_executable
            ? "Runs the real deterministic engine"
            : DETERMINISTIC_REASON
        }
        description={
          rule.machine_executable ? (
            "AI only translates your scenario into facts (never inventing anything you didn't state) and explains the outcome in plain language. The verdict itself comes from the same evaluation engine production evaluations use — this is not AI guesswork."
          ) : (
            <span>
              The evaluator intentionally returns <Tag>NOT_APPLICABLE</Tag> before reading any scenario facts because{" "}
              <Text code>machine_executable=false</Text>. The DMN projection is{" "}
              <Text code>{mappingStatuses.join(", ") || "not mapped"}</Text>
              {formulationRequirements.length > 0 && (
                <>
                  {" "}
                  and requires{" "}
                  {formulationRequirements.map((requirement) => (
                    <Tag key={requirement} color="gold">
                      {requirement}
                    </Tag>
                  ))}
                </>
              )}
              . Use <Text strong>Revise</Text> above to publish a version with formal facts and a condition before
              testing scenarios.
            </span>
          )
        }
        style={{ marginBottom: 16 }}
      />
      <Paragraph>
        <Text strong>Describe a scenario in plain English</Text>
      </Paragraph>
      <TextArea
        rows={3}
        value={scenario}
        onChange={(e) => setScenario(e.target.value)}
        placeholder="e.g. An employee in the US submits an expense of $75 for a client dinner"
        disabled={!rule.machine_executable}
      />
      <Space style={{ marginTop: 12, marginBottom: 16 }}>
        <Text type="secondary">Reasoning effort</Text>
        <Select<ReasoningEffort>
          value={reasoningEffort}
          onChange={setReasoningEffort}
          style={{ width: 120 }}
          disabled={!rule.machine_executable}
          options={[
            { value: "low", label: "Low" },
            { value: "medium", label: "Medium" },
            { value: "high", label: "High" },
          ]}
        />
        <Button
          type="primary"
          icon={<ExperimentOutlined />}
          onClick={run}
          loading={loading}
          disabled={!scenario.trim() || !rule.machine_executable}
        >
          {rule.machine_executable ? (loading ? "Running…" : "Test with real engine") : "Needs a fact mapping"}
        </Button>
      </Space>

      {error && <Alert type="error" showIcon message={error} style={{ marginBottom: 16 }} />}

      {result && (
        <div className="scenario-test-result">
          <Space style={{ marginBottom: 12 }} wrap>
            <Tag color={rr ? STATUS_COLOR[rr.status] : "default"} className="scenario-test-verdict-tag">
              {rr ? rr.status : "NO RESULT"}
            </Tag>
            {rr?.effect_action && (
              <Tag
                color={
                  rr.effect_type === "deny"
                    ? "red"
                    : rr.effect_type === "allow"
                      ? "green"
                      : rr.effect_type === "informational"
                        ? "default"
                        : "blue"
                }
              >
                {rr.effect_action}
              </Tag>
            )}
            {result.not_in_effect && (
              <Tooltip title="This rule exists in the active approved version, but its effective date window doesn't include today (not yet effective, or expired) — the real engine skips it entirely, so no verdict is available.">
                <Tag color="default">
                  <InfoCircleOutlined /> Outside effective date range
                </Tag>
              </Tooltip>
            )}
            <Tag>Reasoning effort: {result.reasoning_effort}</Tag>
            {result.testability_reason && <Tag color="gold">{DETERMINISTIC_LABEL.no}</Tag>}
          </Space>

          <Paragraph>{result.explanation}</Paragraph>

          {result.missing_facts.length > 0 && (
            <Paragraph>
              <Text strong>Missing facts (this rule couldn't be fully decided): </Text>
              <Space wrap>
                {result.missing_facts.map((f) => (
                  <Tag key={f} color="gold">
                    {f}
                  </Tag>
                ))}
              </Space>
            </Paragraph>
          )}

          {factEntries.length > 0 && (
            <>
              <Text type="secondary" className="section-eyebrow">
                Facts the AI inferred from your scenario (used as-is by the real engine)
              </Text>
              <Descriptions size="small" column={1} bordered style={{ marginTop: 8, marginBottom: 12 }}>
                {factEntries.map(([k, v]) => (
                  <Descriptions.Item key={k} label={k}>
                    {typeof v === "object" ? JSON.stringify(v) : String(v)}
                  </Descriptions.Item>
                ))}
              </Descriptions>
            </>
          )}

          {result.assumptions.length > 0 && (
            <Paragraph>
              <Text strong>Assumptions made: </Text>
              <ul style={{ marginTop: 4, marginBottom: 0 }}>
                {result.assumptions.map((a, i) => (
                  <li key={i}>
                    <Text type="secondary">{a}</Text>
                  </li>
                ))}
              </ul>
            </Paragraph>
          )}

          <Text type="secondary" style={{ fontSize: 12 }}>
            Evaluated {new Date(result.evaluation_timestamp).toLocaleString()} · result hash{" "}
            <Text code copyable={{ text: result.result_hash }} style={{ fontSize: 12 }}>
              {result.result_hash.slice(0, 12)}…
            </Text>{" "}
            · not saved to the audit trail (exploratory check only)
          </Text>
        </div>
      )}
    </div>
  );
}