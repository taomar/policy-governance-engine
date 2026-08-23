/**
 * "What changed?" for a candidate the delta engine classified as `changed`.
 *
 * A `Changed` badge tells a reviewer that this rule continues one from a
 * previous extraction with different semantics — but not what moved. Without
 * this panel the only way to find out is to dig the superseded predecessor out
 * of history and read two payloads side by side.
 *
 * The field diff shown here is computed on the server from the two stored
 * payloads and is exact. The narrative underneath it is an LLM reading of that
 * same diff, labelled as such and rendered only when present: if the model is
 * unavailable the reviewer still gets the facts, which is the half that matters.
 *
 * Semantic and wording changes are kept visually distinct on purpose. Listing a
 * retitle next to a changed eligibility threshold would imply they carry
 * comparable weight; they do not.
 */
import { useState } from "react";
import { Alert, Button, Space, Spin, Tag, Tooltip, Typography } from "antd";
import { BulbOutlined, SwapOutlined } from "@ant-design/icons";
import { aiApi, type RuleChangeExplanation } from "../api";

const { Text, Paragraph } = Typography;

/** Field names as a reviewer would say them, not as the schema spells them. */
const FIELD_LABEL: Record<string, string> = {
  rule_type: "Rule type",
  scope: "Who it applies to",
  condition: "Condition",
  effect: "Effect",
  priority: "Priority",
  exceptions: "Exceptions",
  required_facts: "Required facts",
  advice: "Advice",
  is_explicit_override: "Explicit override",
  machine_executable: "Evaluated by comparison",
  title: "Title",
  description: "Description",
};

function renderValue(value: unknown): string {
  if (value === null || value === undefined) return "— not set —";
  if (typeof value === "string") return value || "— empty —";
  if (typeof value === "boolean" || typeof value === "number") return String(value);
  return JSON.stringify(value, null, 2);
}

function ChangeList({ changes, tone }: { changes: RuleChangeExplanation["semantic_changes"]; tone: "semantic" | "wording" }) {
  return (
    <div className={`change-list change-list-${tone}`}>
      {changes.map((c) => (
        <div key={c.field} className="change-row">
          <Text strong className="change-field">
            {FIELD_LABEL[c.field] ?? c.field}
          </Text>
          <div className="change-values">
            <pre className="change-before">{renderValue(c.before)}</pre>
            <SwapOutlined className="change-arrow" />
            <pre className="change-after">{renderValue(c.after)}</pre>
          </div>
        </div>
      ))}
    </div>
  );
}

export function RuleChangeExplainer({ candidateId }: { candidateId: string }) {
  const [data, setData] = useState<RuleChangeExplanation | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await aiApi.explainChange(candidateId));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load the change explanation.");
    } finally {
      setLoading(false);
    }
  };

  if (!data && !loading && !error) {
    return (
      <Tooltip title="Show exactly which fields differ from the previous extraction of this rule, with a plain-English reading of the impact">
        <Button size="small" icon={<SwapOutlined />} onClick={load}>
          What changed?
        </Button>
      </Tooltip>
    );
  }

  if (loading) {
    return (
      <Space size={8}>
        <Spin size="small" />
        <Text type="secondary">Comparing against the previous extraction…</Text>
      </Space>
    );
  }

  if (error) {
    return <Alert type="error" showIcon title={error} action={<Button size="small" onClick={load}>Retry</Button>} />;
  }

  if (!data) return null;

  if (!data.comparable) {
    return <Alert type="info" showIcon title={data.reason ?? "Nothing to compare against."} />;
  }

  const nothingChanged = data.semantic_changes.length === 0 && data.wording_changes.length === 0;

  return (
    <div className="rule-change-explainer">
      <Space size={8} wrap style={{ marginBottom: 10 }}>
        <Text strong style={{ fontSize: 13 }}>
          Compared against
        </Text>
        {data.baseline_run_reference && <Text code style={{ fontSize: 11 }}>{data.baseline_run_reference}</Text>}
        {data.baseline_review_status && (
          <Tag style={{ margin: 0, fontSize: 10 }}>was {data.baseline_review_status}</Tag>
        )}
        <Button size="small" type="text" onClick={load}>
          Refresh
        </Button>
      </Space>

      {nothingChanged && (
        <Alert
          type="success"
          showIcon
          title="No field differences — this rule is identical to the previous extraction."
        />
      )}

      {data.semantic_changes.length > 0 && (
        <>
          <Text strong className="change-section-title change-section-semantic">
            Behaviour changed ({data.semantic_changes.length})
          </Text>
          <Paragraph type="secondary" style={{ fontSize: 12, margin: "2px 0 8px" }}>
            These fields are what the evaluator executes — a change here changes outcomes.
          </Paragraph>
          <ChangeList changes={data.semantic_changes} tone="semantic" />
        </>
      )}

      {data.wording_changes.length > 0 && (
        <>
          <Text strong className="change-section-title change-section-wording">
            Wording only ({data.wording_changes.length})
          </Text>
          <Paragraph type="secondary" style={{ fontSize: 12, margin: "2px 0 8px" }}>
            Regenerated by the model. Behaviour is unaffected.
          </Paragraph>
          <ChangeList changes={data.wording_changes} tone="wording" />
        </>
      )}

      {data.narrative && (
        <Alert
          type="info"
          className="change-narrative"
          icon={<BulbOutlined />}
          showIcon
          title="AI reading of the diff above"
          description={<Paragraph style={{ margin: 0, whiteSpace: "pre-wrap" }}>{data.narrative}</Paragraph>}
        />
      )}
    </div>
  );
}
