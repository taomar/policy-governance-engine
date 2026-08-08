import { Checkbox, Col, Form, Row, Select, Space, Tooltip, Typography } from "antd";
import { InfoCircleOutlined } from "@ant-design/icons";
import type { PolicyScope } from "../api";

const { Text } = Typography;

/**
 * Shared scope/precedence editor used by both the "draft a new rule" form
 * (ReviewQueue) and "edit an existing rule" form (EditRuleModal). Lets a
 * human author/reviewer set the same XACML Target-matching dimensions
 * (jurisdictions/organizational units/personas/processes) the AI extraction
 * pipeline populates from source text, plus the Section 15.4 precedence
 * fields (explicit override, same-version supersession).
 */
export function ScopeFieldsEditor({
  scope,
  onScopeChange,
  isExplicitOverride,
  onIsExplicitOverrideChange,
  supersedesRuleIds,
  onSupersedesRuleIdsChange,
  supersedeCandidates,
}: {
  scope: PolicyScope;
  onScopeChange: (scope: PolicyScope) => void;
  isExplicitOverride: boolean;
  onIsExplicitOverrideChange: (v: boolean) => void;
  supersedesRuleIds: string[];
  onSupersedesRuleIdsChange: (v: string[]) => void;
  /** Other rules in this policy set (the rule being edited/revised already excluded by the
   * caller) offered as pickable options for "Supersedes rule IDs" — without this, the field
   * is a blind free-type box with no way to discover a real rule ID/title to reference. */
  supersedeCandidates?: { rule_id: string; title: string }[];
}) {
  const supersedeOptions = (supersedeCandidates ?? []).map((r) => ({
    value: r.rule_id,
    label: `${r.title} (${r.rule_id})`,
  }));
  const dimensionField = (label: string, key: keyof PolicyScope, placeholder: string) => (
    <Col span={6}>
      <Form.Item label={label}>
        <Select
          mode="tags"
          value={scope[key]}
          onChange={(v) => onScopeChange({ ...scope, [key]: v })}
          placeholder={placeholder}
          tokenSeparators={[",", " "]}
        />
      </Form.Item>
    </Col>
  );

  return (
    <div style={{ marginBottom: 8 }}>
      <Space size={6} style={{ marginBottom: 4 }}>
        <Text strong>Scope — who/where this rule applies to</Text>
        <Tooltip title="Restricts this rule to specific jurisdictions, organizational units, personas, or processes (an XACML-style Target). Leave a field empty to apply to everyone/everywhere on that dimension — the safe default every rule starts with.">
          <InfoCircleOutlined style={{ color: "#8c8c8c" }} />
        </Tooltip>
      </Space>
      <Row gutter={16}>
        {dimensionField("Jurisdictions", "jurisdictions", "e.g. SA, US (blank = any)")}
        {dimensionField("Organizational units", "organizational_units", "e.g. HR, Finance (blank = any)")}
        {dimensionField("Personas", "personas", "e.g. employee, executive (blank = any)")}
        {dimensionField("Processes", "processes", "e.g. leave_request (blank = any)")}
      </Row>
      <Row gutter={16}>
        <Col span={14}>
          <Form.Item
            label={
              <Space size={6}>
                <span>Supersedes rule IDs</span>
                <Tooltip title="Other rule IDs (same policy set) that this rule explicitly replaces. Used for the precedence engine's same-version supersession check.">
                  <InfoCircleOutlined style={{ color: "#8c8c8c" }} />
                </Tooltip>
              </Space>
            }
          >
            <Select
              mode="tags"
              value={supersedesRuleIds}
              onChange={onSupersedesRuleIdsChange}
              options={supersedeOptions}
              placeholder={
                supersedeOptions.length > 0
                  ? "Pick a rule this replaces, or type an ID (e.g. RULE-OLD-001)"
                  : "e.g. RULE-OLD-001"
              }
              tokenSeparators={[",", " "]}
              filterOption={(input, option) =>
                (option?.label ?? "").toLowerCase().includes(input.toLowerCase()) ||
                (option?.value ?? "").toString().toLowerCase().includes(input.toLowerCase())
              }
            />
          </Form.Item>
        </Col>
        <Col span={10}>
          <Form.Item label=" ">
            <Checkbox checked={isExplicitOverride} onChange={(e) => onIsExplicitOverrideChange(e.target.checked)}>
              Explicit override{" "}
              <Tooltip title="Check this only when the source text (or the reviewer's intent) explicitly states this rule deliberately overrides otherwise-applicable rules — e.g. executives may override the standard threshold.">
                <InfoCircleOutlined style={{ color: "#8c8c8c" }} />
              </Tooltip>
            </Checkbox>
          </Form.Item>
        </Col>
      </Row>
    </div>
  );
}
