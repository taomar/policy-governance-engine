import { Alert, Descriptions, Space, Table, Tag, Tooltip, Typography } from "antd";
import { InfoCircleOutlined } from "@ant-design/icons";
import type { EvaluationResponse, QualityFinding } from "../api";
import { evaluationRuleIds, findingsForRuleIds } from "../qualityFindingLinks";

const { Title, Paragraph } = Typography;

export const EVALUATION_STATUS_COLOR: Record<string, string> = {
  SATISFIED: "green",
  NOT_SATISFIED: "red",
  NOT_APPLICABLE: "default",
  INDETERMINATE: "gold",
  ERROR: "red",
};

/**
 * Renders one `EvaluationResponse` — overall verdict, actions, breaches,
 * advice, and the per-rule results table. Shared by `EvaluatePage` (a fresh,
 * ad hoc test run) and `DecisionLogPage` (a historical record read back from
 * the decision log) so the two places a reviewer looks at an evaluation
 * outcome render it identically.
 */
export function EvaluationResultView({
  response,
  qualityFindings = [],
}: {
  response: EvaluationResponse;
  qualityFindings?: readonly QualityFinding[];
}) {
  const linkedFindings = findingsForRuleIds(qualityFindings, evaluationRuleIds(response));
  return (
    <>
      <Descriptions size="small" column={2} bordered style={{ marginBottom: 20 }}>
        <Descriptions.Item label="Overall status">
          <Tag color={EVALUATION_STATUS_COLOR[response.overall_status] ?? "default"}>{response.overall_status}</Tag>
        </Descriptions.Item>
        <Descriptions.Item label="Outcome">{response.outcome ?? "—"}</Descriptions.Item>
        <Descriptions.Item label="Route that decided" span={2}>
          <Tag color="blue">FEEL evaluator</Tag>
        </Descriptions.Item>
        {response.required_actions.length > 0 && (
          <Descriptions.Item label="Allowed / required actions" span={2}>
            <Space wrap>
              {response.required_actions.map((a) => (
                <Tag color="green" key={a}>
                  {a}
                </Tag>
              ))}
            </Space>
          </Descriptions.Item>
        )}
        {(response.denied_actions?.length ?? 0) > 0 && (
          <Descriptions.Item label="Denied actions" span={2}>
            <Space wrap>
              {response.denied_actions!.map((a) => (
                <Tag color="red" key={a}>
                  {a}
                </Tag>
              ))}
            </Space>
          </Descriptions.Item>
        )}
        <Descriptions.Item label="Result hash" span={2}>
          <code>{response.result_hash}</code>
        </Descriptions.Item>
        {response.missing_facts.length > 0 && (
          <Descriptions.Item label="Missing facts" span={2}>
            {response.missing_facts.join(", ")}
          </Descriptions.Item>
        )}
        {response.triggered_exceptions.length > 0 && (
          <Descriptions.Item label="Triggered exceptions" span={2}>
            {response.triggered_exceptions.join(", ")}
          </Descriptions.Item>
        )}
      </Descriptions>

      {linkedFindings.length > 0 && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 20 }}
          title="Known quality finding covers rules in this result"
          description={
            <Space orientation="vertical" size={4}>
              {linkedFindings.map((finding, index) => (
                <span key={`${finding.category}-${finding.matched_rule_ids.join("-")}-${index}`}>
                  <Tag color={finding.severity === "high" ? "red" : finding.severity === "medium" ? "gold" : "default"}>
                    {finding.severity}
                  </Tag>{" "}
                  <strong>{finding.category.replace(/_/g, " ")}</strong> on {finding.matched_rule_ids.join(", ")}
                  {finding.summary ? ` — ${finding.summary}` : ""}
                </span>
              ))}
            </Space>
          }
        />
      )}

      {(response.aggregate_breaches?.length ?? 0) > 0 && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 20 }}
          title="Aggregate limit breached"
          description={
            <ul style={{ margin: 0, paddingLeft: 20 }}>
              {response.aggregate_breaches!.map((b) => (
                <li key={b.aggregate_id}>
                  <strong>{b.description}</strong>: combined total {b.total} exceeds max {b.max_value} (rules:{" "}
                  {b.contributing_rule_ids.join(", ")})
                </li>
              ))}
            </ul>
          }
        />
      )}

      {(response.advice_notes?.length ?? 0) > 0 && (
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 20 }}
          title="Advice"
          description={
            <>
              <Paragraph type="secondary" style={{ margin: "0 0 8px" }}>
                Non-blocking guidance from the rules that decided this outcome — informational only, does not change
                the decision.
              </Paragraph>
              <ul style={{ margin: 0, paddingLeft: 20 }}>
                {response.advice_notes!.map((note) => (
                  <li key={note}>{note}</li>
                ))}
              </ul>
            </>
          }
        />
      )}

      <Title level={5}>Rule results</Title>
      <Table
        size="small"
        rowKey="rule_id"
        pagination={false}
        dataSource={response.rule_results}
        columns={[
          { title: "Rule", dataIndex: "rule_id" },
          {
            title: "Status",
            dataIndex: "status",
            render: (s: string, row) => (
              <Space size={4}>
                <Tag color={EVALUATION_STATUS_COLOR[s] ?? "default"}>{s}</Tag>
                {row.not_applicable_reason && (
                  <Tooltip title={row.not_applicable_reason}>
                    <InfoCircleOutlined style={{ color: "#8c8c8c" }} />
                  </Tooltip>
                )}
              </Space>
            ),
          },
          {
            title: "Effect",
            dataIndex: "effect_action",
            render: (v, row) => {
              if (!v) return "—";
              const color =
                row.effect_type === "deny"
                  ? "red"
                  : row.effect_type === "allow"
                    ? "green"
                    : row.effect_type === "informational"
                      ? "default"
                      : "blue";
              return <Tag color={color}>{v}</Tag>;
            },
          },
          {
            title: "Overridden by",
            dataIndex: "overridden_by",
            render: (v: string | null | undefined) =>
              v ? (
                <Tooltip title="A higher-precedence rule on the opposite allow/deny axis won.">
                  <Tag color="default">{v}</Tag>
                </Tooltip>
              ) : (
                "—"
              ),
          },
          {
            title: "Missing facts",
            dataIndex: "missing_facts",
            render: (v: string[]) => v.join(", ") || "—",
          },
          {
            title: "Exceptions",
            dataIndex: "triggered_exceptions",
            render: (v: string[]) => v.join(", ") || "—",
          },
          {
            title: "Advice",
            dataIndex: "advice",
            render: (v: string[] | undefined) =>
              v && v.length > 0 ? (
                <Tooltip title={v.join("; ")}>
                  <Tag color="blue">
                    {v.length} note{v.length > 1 ? "s" : ""}
                  </Tag>
                </Tooltip>
              ) : (
                "—"
              ),
          },
        ]}
      />
    </>
  );
}

export default EvaluationResultView;
