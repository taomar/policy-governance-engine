/**
 * "Test scenario" tab for a single, already-published rule.
 *
 * TWO ROUTES, TWO DECIDERS, ONE WAY IN
 *
 * A rule states its test either as a comparison between named quantities or in
 * words. The first is computed by `evaluator.engine.evaluate_policy` against
 * facts an AI conservatively infers from a plain-English case. The second is
 * read by a judge against that same case — which is the reason the route
 * exists, and the route most policy text arrives on.
 *
 * This component asks whichever decider the record calls for, and the record
 * alone chooses: a rule whose comparison the engine can compute goes to the
 * engine, and everything else goes to the judge. It is not a preference a
 * caller can pass in, because a caller that guessed wrong would send a rule to
 * a decider that refuses it — `ai_scenario_engine.py` short-circuits before it
 * reads any case, and the reader would see a refusal where they asked a
 * question.
 *
 * WHY THE JUDGED ANSWER CARRIES NO NUMBER
 *
 * A judged answer has three states: it applies, it does not, or the case as
 * described does not settle it. That third state is what a confidence figure
 * is reaching for, said in a form a reviewer can act on — describe more of the
 * case. A number would be worse than useless here: `contracts/correlation.py`
 * records why the specification bans them (a model asked for a probability
 * supplies one, and `0.91` reads as measurement when it is invention), and
 * beside a computed answer a percentage would read as the judged route
 * apologising for itself. Both routes decide. They decide differently.
 *
 * Results are deliberately NOT written to the evaluation audit trail on either
 * route: this is an exploratory check by a reviewer, not a production calling
 * -system event. See `ai_scenario_engine.py` and `ai_scenario_eval.py`.
 */
import { useEffect, useState } from "react";
import { Alert, Button, Descriptions, Input, Select, Space, Tag, Tooltip, Typography } from "antd";
import { ExperimentOutlined, InfoCircleOutlined, ReadOutlined } from "@ant-design/icons";
import {
  aiApi,
  PolicyPlatformApiError,
  type CanonicalRule,
  type EvaluationStatus,
  type RuleScenarioTestResult,
  type ScenarioEvaluation,
} from "../api";
import { DETERMINISTIC_LABEL, engineDecidesRule } from "../ruleExecutability";

const { Text, Paragraph } = Typography;
const { TextArea } = Input;

const STATUS_COLOR: Record<EvaluationStatus, string> = {
  SATISFIED: "green",
  NOT_SATISFIED: "red",
  NOT_APPLICABLE: "default",
  INDETERMINATE: "gold",
  ERROR: "red",
};

/**
 * The three answers a judge can return, in the words a reviewer reads.
 *
 * `uncertain` is an answer about the case, not about the rule: the rule was
 * read, and what it needs to decide was not described. Wording it as a
 * property of the rule would report a route as a defect.
 */
const JUDGED_VERDICT: Record<ScenarioEvaluation["applies"], { label: string; color: string }> = {
  yes: { label: "This rule applies to the case", color: "green" },
  no: { label: "This rule stands aside from the case", color: "blue" },
  uncertain: { label: "The case as described does not settle it", color: "gold" },
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
  const [judged, setJudged] = useState<ScenarioEvaluation | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // One derivation of who decides, taken from the record and shared with every
  // other surface that asks (see `engineDecidesRule`). Two copies of this
  // question is what let a rule be offered a decider that would refuse it.
  const engineDecides = engineDecidesRule(rule);

  // Switching rules while this tab is open should not show a stale answer
  // from a different rule under the new title/condition.
  useEffect(() => {
    setResult(null);
    setJudged(null);
    setError(null);
    setScenario("");
  }, [rule.rule_id]);

  const run = async () => {
    setLoading(true);
    setError(null);
    try {
      if (engineDecides) {
        setJudged(null);
        setResult(await aiApi.testRuleScenario(policySetKey, rule.rule_id, scenario.trim(), reasoningEffort));
      } else {
        setResult(null);
        setJudged(await aiApi.evaluateScenario(rule, scenario.trim(), reasoningEffort));
      }
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
        type="info"
        showIcon
        message={
          engineDecides
            ? "The engine computes this rule's comparison"
            : "A judge reads this rule against your case"
        }
        description={
          engineDecides ? (
            <span>
              The rule states its test as a comparison between named quantities. AI translates your
              case into those quantities, taking only what you stated, and the same evaluator that
              production evaluations use settles the outcome from them.
            </span>
          ) : (
            <span>
              The rule states what it requires in words rather than as a comparison between named
              quantities, so it is served as <Text code>ai_ready</Text> and settled by a judge
              reading the record — the source sentence, the facts it names, and the outcome it
              states — against the case you describe.
            </span>
          )
        }
        style={{ marginBottom: 16 }}
      />
      <Paragraph>
        <Text strong>Describe a case in plain English</Text>
      </Paragraph>
      <TextArea
        rows={3}
        value={scenario}
        onChange={(e) => setScenario(e.target.value)}
        placeholder="e.g. An employee in the US submits an expense of $75 for a client dinner"
      />
      <Space style={{ marginTop: 12, marginBottom: 16 }}>
        <Text type="secondary">Reasoning effort</Text>
        <Select<ReasoningEffort>
          value={reasoningEffort}
          onChange={setReasoningEffort}
          style={{ width: 120 }}
          options={[
            { value: "low", label: "Low" },
            { value: "medium", label: "Medium" },
            { value: "high", label: "High" },
          ]}
        />
        <Button
          type="primary"
          icon={engineDecides ? <ExperimentOutlined /> : <ReadOutlined />}
          onClick={run}
          loading={loading}
          disabled={!scenario.trim()}
          data-testid="scenario-run"
        >
          {loading
            ? engineDecides
              ? "Computing…"
              : "Reading…"
            : engineDecides
              ? "Run the engine on this case"
              : "Put this case to the judge"}
        </Button>
      </Space>

      {error && <Alert type="error" showIcon message={error} style={{ marginBottom: 16 }} />}

      {judged && (
        <div className="scenario-test-result" data-testid="scenario-answer">
          <Space style={{ marginBottom: 12 }} wrap>
            <Tag
              color={JUDGED_VERDICT[judged.applies].color}
              className="scenario-test-verdict-tag"
              data-testid="scenario-verdict"
            >
              {JUDGED_VERDICT[judged.applies].label}
            </Tag>
            <Tag>Reasoning effort: {judged.reasoning_effort}</Tag>
          </Space>

          {judged.predicted_outcome && (
            <Paragraph>
              <Text strong>What the rule requires here: </Text>
              {judged.predicted_outcome}
            </Paragraph>
          )}

          <Paragraph>{judged.reasoning}</Paragraph>

          {judged.missing_facts.length > 0 && (
            <Paragraph>
              <Text strong>What the case would have to state for this to be settled: </Text>
              <Space wrap>
                {judged.missing_facts.map((f) => (
                  <Tag key={f} color="gold">
                    {f}
                  </Tag>
                ))}
              </Space>
            </Paragraph>
          )}

          <Text type="secondary" style={{ fontSize: 12 }} data-testid="scenario-decided-by">
            Read by a judge against the record on screen · not saved to the audit trail
            (exploratory check only)
          </Text>
        </div>
      )}

      {result && (
        <div className="scenario-test-result" data-testid="scenario-answer">
          <Space style={{ marginBottom: 12 }} wrap>
            <Tag
              color={rr ? STATUS_COLOR[rr.status] : "default"}
              className="scenario-test-verdict-tag"
              data-testid="scenario-verdict"
            >
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
            {result.testability_reason && <Tag>{DETERMINISTIC_LABEL.no}</Tag>}
          </Space>

          <Paragraph>{result.explanation}</Paragraph>

          {result.missing_facts.length > 0 && (
            <Paragraph>
              <Text strong>What the case would have to state for this to be settled: </Text>
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
                Quantities the AI read out of your case (used as-is by the engine)
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

          <Text type="secondary" style={{ fontSize: 12 }} data-testid="scenario-decided-by">
            Computed by the engine {new Date(result.evaluation_timestamp).toLocaleString()} · result
            hash{" "}
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