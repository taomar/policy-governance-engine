import { useState } from "react";
import { Alert, Button, Card, Empty, Input, Segmented, Space, Spin, Tag, Timeline, Tooltip, Typography } from "antd";
import { ExperimentOutlined, ThunderboltOutlined } from "@ant-design/icons";
import {
  aiApi,
  PolicyPlatformApiError,
  type CanonicalRule,
  type DraftFromTextResult,
  type DraftTraceStep,
  type ScenarioEvaluation,
} from "../api";

const { Text, Paragraph } = Typography;
const { TextArea } = Input;

const EXAMPLES = [
  "Workers under 18 may not be assigned to night shifts between 11pm and 6am.",
  "Any expense over 5,000 SAR requires written approval from the finance controller before it is incurred.",
  "An employee who has completed one year of continuous service is entitled to 21 days of paid annual leave.",
];

const STATUS_COLOR: Record<DraftTraceStep["status"], string> = {
  done: "green",
  skipped: "gray",
  failed: "red",
};

const EFFECT_COLOR: Record<string, string> = {
  allow: "green",
  deny: "red",
  require_action: "orange",
  informational: "blue",
};

const APPLIES_COLOR: Record<ScenarioEvaluation["applies"], string> = {
  yes: "green",
  no: "default",
  uncertain: "orange",
};

function str(value: unknown): string {
  return value === null || value === undefined ? "" : String(value);
}

/** Renders one pipeline step's own items in that step's own vocabulary.
 * Deliberately not normalized into a single shape: the point of showing the
 * trace is that a reviewer sees what the *agent* said (subject/modality/
 * predicate) separately from what the *platform* derived from it (rule type,
 * effect, condition). Flattening the two would hide exactly the boundary this
 * panel exists to make visible. */
function TraceItems({ step }: { step: DraftTraceStep }) {
  if (step.items.length === 0) return null;

  if (step.key === "formulate") {
    return (
      <Space direction="vertical" size={6} style={{ width: "100%", marginTop: 6 }}>
        {step.items.map((item, i) => (
          <div key={i} className="ai-trace-item">
            <Paragraph style={{ margin: 0, fontSize: 12 }} italic>
              “{str(item.source_text)}”
            </Paragraph>
            <Space size={[4, 4]} wrap style={{ marginTop: 4 }}>
              {item.rule_type ? <Tag color="purple">{str(item.rule_type)}</Tag> : null}
              {item.modality ? <Tag>{str(item.modality)}</Tag> : null}
              {Array.isArray(item.ambiguity)
                ? item.ambiguity.map((a) => (
                    <Tag color="orange" key={String(a)}>
                      {String(a)}
                    </Tag>
                  ))
                : null}
            </Space>
            {item.subject ? (
              <Text type="secondary" style={{ fontSize: 11, display: "block" }}>
                {str(item.subject)} · {str(item.predicate)}
              </Text>
            ) : null}
          </div>
        ))}
      </Space>
    );
  }

  if (step.key === "derive") {
    return (
      <Space direction="vertical" size={6} style={{ width: "100%", marginTop: 6 }}>
        {step.items.map((item, i) => (
          <div key={i} className="ai-trace-item">
            <Text strong style={{ fontSize: 12 }}>
              {str(item.title)}
            </Text>
            <Space size={[4, 4]} wrap style={{ marginTop: 4 }}>
              <Tag color={EFFECT_COLOR[str(item.effect_type)] ?? "default"}>{str(item.effect_type)}</Tag>
              <Tag>{str(item.rule_type)}</Tag>
              {item.machine_executable ? (
                <Tag color="green">machine executable</Tag>
              ) : (
                <Tooltip title="No trusted fact model was supplied, so the condition is a placeholder. The rule is still reviewable and publishable — it just cannot be auto-evaluated yet.">
                  <Tag color="gold">needs human judgment</Tag>
                </Tooltip>
              )}
            </Space>
            <Text type="secondary" style={{ fontSize: 11, display: "block", marginTop: 2 }}>
              condition: {str(item.condition)}
            </Text>
          </div>
        ))}
      </Space>
    );
  }

  return (
    <Space direction="vertical" size={4} style={{ width: "100%", marginTop: 6 }}>
      {step.items.map((item, i) => (
        <Text key={i} type="secondary" style={{ fontSize: 11 }}>
          {str(item.item)} — {str(item.reason)}
        </Text>
      ))}
    </Space>
  );
}

interface AiRuleComposerProps {
  policySetKey: string;
  /** Loads one generated draft into the structured controls next to this
   * panel. The composer never saves: the human submits from the form, so the
   * review queue keeps a single, human-operated entry point. */
  onLoadRule: (rule: CanonicalRule) => void;
  loadedRuleId?: string | null;
}

/**
 * "Describe it, and watch it become a rule."
 *
 * The left half of the drafting workspace: a plain-language box, and the live
 * derivation trail of what the platform did with it. It calls the same policy
 * formulator agent and the same deterministic mapper that document extraction
 * uses, so a rule authored here is structurally identical to an extracted one
 * — it simply cites no clause, because the author is the source.
 *
 * The trace is not decoration. A reviewer approving a rule needs to see where
 * the agent's judgement stopped and the platform's deterministic derivation
 * began, and the two-step timeline is that boundary made visible.
 */
export function AiRuleComposer({ policySetKey, onLoadRule, loadedRuleId }: AiRuleComposerProps) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<DraftFromTextResult | null>(null);

  // Advisory test of a generated draft, before it is saved. Uses the
  // advisory-only endpoint deliberately: the deterministic engine evaluates
  // *published* rules, and this rule does not exist yet.
  const [testFor, setTestFor] = useState<CanonicalRule | null>(null);
  const [scenario, setScenario] = useState("");
  const [effort, setEffort] = useState<"low" | "medium" | "high">("low");
  const [testing, setTesting] = useState(false);
  const [testError, setTestError] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<ScenarioEvaluation | null>(null);

  const generate = async () => {
    setBusy(true);
    setError(null);
    setResult(null);
    setTestFor(null);
    setTestResult(null);
    try {
      const res = await aiApi.draftFromText(policySetKey, text);
      setResult(res);
      // One rule is the overwhelmingly common case for a single typed
      // statement — load it straight into the controls so the user sees the
      // form fill itself, which is the whole point of the flow. Multiple
      // rules stay unloaded so the user picks deliberately.
      if (res.rules.length === 1) onLoadRule(res.rules[0]);
    } catch (e) {
      setError(e instanceof PolicyPlatformApiError ? e.detail : String(e));
    } finally {
      setBusy(false);
    }
  };

  const runTest = async () => {
    if (!testFor) return;
    setTesting(true);
    setTestError(null);
    try {
      setTestResult(await aiApi.evaluateScenario(testFor, scenario.trim(), effort));
    } catch (e) {
      setTestError(e instanceof PolicyPlatformApiError ? e.detail : String(e));
    } finally {
      setTesting(false);
    }
  };

  return (
    <Card
      size="small"
      className="ai-composer-card"
      title={
        <Space size={6}>
          <ThunderboltOutlined />
          <span>Draft with AI</span>
        </Space>
      }
    >
      <Paragraph type="secondary" style={{ fontSize: 12, marginBottom: 8 }}>
        Describe the policy in your own words. The same agent that reads source documents will
        formulate it, and the controls on the right fill in from the result — review and change
        anything before you save.
      </Paragraph>

      <TextArea
        rows={5}
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder={EXAMPLES[0]}
        disabled={busy}
        onPressEnter={(e) => {
          if ((e.ctrlKey || e.metaKey) && text.trim()) {
            e.preventDefault();
            void generate();
          }
        }}
      />

      <Space size={[6, 6]} wrap style={{ marginTop: 8 }}>
        <Text type="secondary" style={{ fontSize: 11 }}>
          Try:
        </Text>
        {EXAMPLES.map((ex, i) => (
          <Tooltip title={ex} key={i}>
            <Tag
              style={{ cursor: "pointer", margin: 0 }}
              onClick={() => !busy && setText(ex)}
            >
              example {i + 1}
            </Tag>
          </Tooltip>
        ))}
      </Space>

      <Button
        type="primary"
        icon={<ThunderboltOutlined />}
        onClick={generate}
        loading={busy}
        disabled={!text.trim()}
        block
        style={{ marginTop: 12 }}
      >
        {busy ? "Formulating…" : "Generate rule"}
      </Button>

      {error && <Alert type="error" showIcon message={error} style={{ marginTop: 12 }} />}

      {busy && (
        <div style={{ textAlign: "center", padding: "20px 0" }}>
          <Spin />
          <Text type="secondary" style={{ display: "block", marginTop: 8, fontSize: 12 }}>
            Reading your statement and formulating a canonical policy…
          </Text>
        </div>
      )}

      {!busy && !result && !error && (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          style={{ marginTop: 12 }}
          description={
            <Text type="secondary" style={{ fontSize: 12 }}>
              The extraction trail appears here
            </Text>
          }
        />
      )}

      {result && (
        <div style={{ marginTop: 14 }}>
          <Text strong style={{ fontSize: 12, textTransform: "uppercase", letterSpacing: 0.5 }}>
            Extraction trail
          </Text>
          <Timeline
            style={{ marginTop: 12 }}
            items={result.trace.map((step) => ({
              color: STATUS_COLOR[step.status],
              children: (
                <div>
                  <Text strong style={{ fontSize: 12 }}>
                    {step.label}
                  </Text>
                  <Text type="secondary" style={{ fontSize: 11, display: "block" }}>
                    {step.detail}
                  </Text>
                  <TraceItems step={step} />
                </div>
              ),
            }))}
          />

          {result.rules.length === 0 ? (
            <Alert
              type="warning"
              showIcon
              message="No rule could be formulated from that statement"
              description="The agent read the text but found no policy-bearing obligation, permission, prohibition or definition in it. Try stating who it applies to, what they must or may do, and under what condition."
            />
          ) : (
            <>
              <Text strong style={{ fontSize: 12, textTransform: "uppercase", letterSpacing: 0.5 }}>
                Generated {result.rules.length === 1 ? "rule" : `rules (${result.rules.length})`}
              </Text>
              <Space direction="vertical" size={8} style={{ width: "100%", marginTop: 8 }}>
                {result.rules.map((rule) => {
                  const isLoaded = loadedRuleId === rule.rule_id;
                  return (
                    <div key={rule.rule_id} className="ai-generated-rule">
                      <Text strong style={{ fontSize: 12 }}>
                        {rule.title}
                      </Text>
                      <Space size={[4, 4]} wrap style={{ marginTop: 6 }}>
                        <Tag color={EFFECT_COLOR[rule.effect.type] ?? "default"}>{rule.effect.type}</Tag>
                        <Tag>{rule.rule_type}</Tag>
                      </Space>
                      <Space size={6} style={{ marginTop: 8 }} wrap>
                        <Button
                          size="small"
                          type={isLoaded ? "default" : "primary"}
                          onClick={() => onLoadRule(rule)}
                        >
                          {isLoaded ? "Reload into form" : "Load into form"}
                        </Button>
                        <Button
                          size="small"
                          icon={<ExperimentOutlined />}
                          onClick={() => {
                            setTestFor(rule);
                            setTestResult(null);
                            setTestError(null);
                          }}
                        >
                          Test
                        </Button>
                      </Space>
                    </div>
                  );
                })}
              </Space>
            </>
          )}

          <Alert
            type="info"
            showIcon
            style={{ marginTop: 12 }}
            message="This draft cites no source document"
            description="Rules extracted from an uploaded document carry clause-level evidence. A rule you author here has none, because there is no source text to point at — you are the source. It is saved as a candidate and still goes through the normal review."
          />
        </div>
      )}

      {testFor && (
        <section className="ai-draft-test">
          <div className="ai-draft-test__header">Test: {testFor.title}</div>
          <div className="ai-draft-test__body">
          <Paragraph type="secondary" style={{ fontSize: 11, marginBottom: 8 }}>
            Advisory only. This asks the AI how the draft would apply to a situation; it does not
            run the deterministic engine, which evaluates published rules.
          </Paragraph>
          <TextArea
            rows={3}
            value={scenario}
            onChange={(e) => setScenario(e.target.value)}
            placeholder="A 17-year-old worker is scheduled for a shift starting at midnight."
          />
          <Space style={{ marginTop: 8 }} wrap>
            <Segmented
              size="small"
              value={effort}
              onChange={(v) => setEffort(v as "low" | "medium" | "high")}
              options={["low", "medium", "high"]}
            />
            <Button size="small" type="primary" onClick={runTest} loading={testing} disabled={!scenario.trim()}>
              Run test
            </Button>
          </Space>
          {testError && <Alert type="error" showIcon message={testError} style={{ marginTop: 8 }} />}
          {testResult && (
            <div style={{ marginTop: 10 }}>
              <Space size={6} wrap>
                <Text type="secondary" style={{ fontSize: 11 }}>
                  Applies:
                </Text>
                <Tag color={APPLIES_COLOR[testResult.applies]}>{testResult.applies}</Tag>
              </Space>
              <Paragraph style={{ fontSize: 12, marginTop: 8, marginBottom: 4 }}>
                <Text strong>Predicted outcome: </Text>
                {testResult.predicted_outcome}
              </Paragraph>
              <Paragraph type="secondary" style={{ fontSize: 11, marginBottom: 4 }}>
                {testResult.reasoning}
              </Paragraph>
              {testResult.missing_facts.length > 0 && (
                <Space size={[4, 4]} wrap>
                  <Text type="secondary" style={{ fontSize: 11 }}>
                    Missing facts:
                  </Text>
                  {testResult.missing_facts.map((f) => (
                    <Tag key={f} color="orange">
                      {f}
                    </Tag>
                  ))}
                </Space>
              )}
            </div>
          )}
          </div>
        </section>
      )}
    </Card>
  );
}
