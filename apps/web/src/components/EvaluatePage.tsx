import { useEffect, useState } from "react";
import {
  Alert,
  AutoComplete,
  Button,
  Card,
  Checkbox,
  Col,
  Descriptions,
  Form,
  Input,
  InputNumber,
  Row,
  Select,
  Space,
  Table,
  Tag,
  Tooltip,
  Typography,
} from "antd";
import { InfoCircleOutlined, PlayCircleOutlined, UserOutlined } from "@ant-design/icons";
import {
  api,
  PolicyPlatformApiError,
  principalToFacts,
  type ApprovedPolicyVersion,
  type CanonicalRule,
  type EvaluationResponse,
  type PolicySet,
  type PrincipalContext,
} from "../api";

const { Title, Text, Paragraph } = Typography;
const { TextArea } = Input;

const STATUS_COLOR: Record<string, string> = {
  SATISFIED: "green",
  NOT_SATISFIED: "red",
  NOT_APPLICABLE: "default",
  INDETERMINATE: "gold",
  ERROR: "red",
};

interface FactField {
  name: string;
  data_type: string;
  required: boolean;
}

interface ScopeOptions {
  jurisdictions: string[];
  organizational_units: string[];
  personas: string[];
  processes: string[];
}

const EMPTY_SCOPE_OPTIONS: ScopeOptions = {
  jurisdictions: [],
  organizational_units: [],
  personas: [],
  processes: [],
};

export function EvaluatePage() {
  const [policySets, setPolicySets] = useState<PolicySet[]>([]);
  const [selectedKey, setSelectedKey] = useState<string>("");
  const [versions, setVersions] = useState<ApprovedPolicyVersion[]>([]);
  const [selectedVersionId, setSelectedVersionId] = useState<string>("active");
  const [factFields, setFactFields] = useState<FactField[]>([]);
  const [factValues, setFactValues] = useState<Record<string, string>>({});
  const [scopeOptions, setScopeOptions] = useState<ScopeOptions>(EMPTY_SCOPE_OPTIONS);
  const [principal, setPrincipal] = useState<PrincipalContext>({});
  const [useAdvancedJson, setUseAdvancedJson] = useState(false);
  const [factsJson, setFactsJson] = useState("{}");
  const [correlationId, setCorrelationId] = useState("");
  const [response, setResponse] = useState<EvaluationResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api
      .listPolicySets()
      .then((sets) => {
        setPolicySets(sets);
        if (sets.length > 0) setSelectedKey(sets[0].key);
      })
      .catch((e) => setError(e instanceof PolicyPlatformApiError ? e.detail : String(e)));
  }, []);

  useEffect(() => {
    if (!selectedKey) return;
    setError(null);
    setPrincipal({});
    api
      .listPolicyVersions(selectedKey)
      .then((v) => {
        setVersions(v);
        setSelectedVersionId("active");
      })
      .catch((e) => setError(e instanceof PolicyPlatformApiError ? e.detail : String(e)));
  }, [selectedKey]);

  // Build the dynamic facts form + "who is asking" scope suggestions from the
  // union of required_facts / scope values across the target version's rules.
  useEffect(() => {
    if (!selectedKey) return;
    const loadFacts = async () => {
      try {
        let versionId = selectedVersionId;
        if (versionId === "active") {
          const active = versions.find((v) => v.is_active);
          if (!active) return;
          versionId = active.id;
        }
        const rules: CanonicalRule[] = await api.getVersionRules(selectedKey, versionId);
        const seen = new Map<string, FactField>();
        const jurisdictions = new Set<string>();
        const organizationalUnits = new Set<string>();
        const personas = new Set<string>();
        const processes = new Set<string>();
        for (const rule of rules) {
          for (const f of rule.required_facts) {
            if (!seen.has(f.name)) seen.set(f.name, f);
          }
          for (const j of rule.scope?.jurisdictions ?? []) if (j !== "*") jurisdictions.add(j);
          for (const o of rule.scope?.organizational_units ?? []) if (o !== "*") organizationalUnits.add(o);
          for (const p of rule.scope?.personas ?? []) if (p !== "*") personas.add(p);
          for (const p of rule.scope?.processes ?? []) if (p !== "*") processes.add(p);
        }
        setFactFields(Array.from(seen.values()));
        setScopeOptions({
          jurisdictions: Array.from(jurisdictions),
          organizational_units: Array.from(organizationalUnits),
          personas: Array.from(personas),
          processes: Array.from(processes),
        });
      } catch (e) {
        setError(e instanceof PolicyPlatformApiError ? e.detail : String(e));
      }
    };
    if (versions.length > 0) void loadFacts();
  }, [selectedKey, selectedVersionId, versions]);

  const handleEvaluate = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      let facts: Record<string, unknown>;
      if (useAdvancedJson) {
        facts = JSON.parse(factsJson);
      } else {
        facts = {};
        for (const f of factFields) {
          const raw = factValues[f.name];
          if (raw === undefined || raw === "") continue;
          if (f.data_type === "number") facts[f.name] = Number(raw);
          else if (f.data_type === "boolean") facts[f.name] = raw === "true";
          else facts[f.name] = raw;
        }
      }
      // Principal-derived reserved keys (subject.*/context.*) merge in first;
      // an explicitly-entered fact of the same name (unlikely, but possible
      // in advanced JSON mode) takes precedence.
      const mergedFacts = { ...principalToFacts(principal), ...facts };
      const result = await api.evaluate({
        policy_set_id: selectedKey,
        use_active_version: selectedVersionId === "active",
        policy_version_id: selectedVersionId === "active" ? undefined : selectedVersionId,
        facts: mergedFacts,
        correlation_id: correlationId || undefined,
      });
      setResponse(result);
    } catch (e) {
      setError(e instanceof PolicyPlatformApiError ? e.detail : String(e));
    } finally {
      setLoading(false);
    }
  };

  if (policySets.length === 0) {
    return (
      <>
        <Title level={3}>Evaluate</Title>
        <Text type="secondary">Create a policy set first (Policy Sets page).</Text>
      </>
    );
  }

  return (
    <>
      <div className="page-header-row">
        <Title level={3} style={{ margin: 0 }}>
          Evaluate
        </Title>
        <Select
          value={selectedKey}
          onChange={setSelectedKey}
          style={{ minWidth: 220 }}
          options={policySets.map((ps) => ({ value: ps.key, label: ps.name }))}
        />
      </div>

      {error && <Alert type="error" showIcon message={error} />}

      <Card
        title={
          <Space>
            <UserOutlined />
            Who is asking
            <Tooltip title="Rules whose scope restricts to specific personas, organizational units, jurisdictions, or processes (XACML Target) are only applicable when they match here. Leave a dimension blank for 'unspecified' — an unspecified principal never satisfies a rule that restricts on that dimension (safe default: absence of identity never grants access).">
              <InfoCircleOutlined style={{ color: "#8c8c8c" }} />
            </Tooltip>
          </Space>
        }
        style={{ marginBottom: 16 }}
      >
        <Paragraph type="secondary" style={{ marginTop: -8, marginBottom: 16 }}>
          Optional principal context, used only to check scope-restricted rules. Facts below still drive whether a
          rule's condition is satisfied.
        </Paragraph>
        <Row gutter={16}>
          <Col span={6}>
            <Form.Item label="Persona / role">
              <AutoComplete
                allowClear
                value={principal.persona ?? undefined}
                onChange={(v) => setPrincipal((prev) => ({ ...prev, persona: v || undefined }))}
                options={scopeOptions.personas.map((p) => ({ value: p }))}
                placeholder="e.g. executive, manager"
                filterOption={(input, option) => (option?.value ?? "").toLowerCase().includes(input.toLowerCase())}
              />
            </Form.Item>
          </Col>
          <Col span={6}>
            <Form.Item label="Organizational unit">
              <AutoComplete
                allowClear
                value={principal.organizational_unit ?? undefined}
                onChange={(v) => setPrincipal((prev) => ({ ...prev, organizational_unit: v || undefined }))}
                options={scopeOptions.organizational_units.map((o) => ({ value: o }))}
                placeholder="e.g. HR, Finance, IT"
                filterOption={(input, option) => (option?.value ?? "").toLowerCase().includes(input.toLowerCase())}
              />
            </Form.Item>
          </Col>
          <Col span={6}>
            <Form.Item label="Jurisdiction">
              <AutoComplete
                allowClear
                value={principal.jurisdiction ?? undefined}
                onChange={(v) => setPrincipal((prev) => ({ ...prev, jurisdiction: v || undefined }))}
                options={scopeOptions.jurisdictions.map((j) => ({ value: j }))}
                placeholder="e.g. US, EU, UK"
                filterOption={(input, option) => (option?.value ?? "").toLowerCase().includes(input.toLowerCase())}
              />
            </Form.Item>
          </Col>
          <Col span={6}>
            <Form.Item label="Process">
              <AutoComplete
                allowClear
                value={principal.process ?? undefined}
                onChange={(v) => setPrincipal((prev) => ({ ...prev, process: v || undefined }))}
                options={scopeOptions.processes.map((p) => ({ value: p }))}
                placeholder="e.g. leave-request"
                filterOption={(input, option) => (option?.value ?? "").toLowerCase().includes(input.toLowerCase())}
              />
            </Form.Item>
          </Col>
        </Row>
      </Card>

      <Card>
        <Form layout="vertical" onSubmitCapture={handleEvaluate}>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item label="Policy version">
                <Select
                  value={selectedVersionId}
                  onChange={setSelectedVersionId}
                  options={[
                    { value: "active", label: "Active version (current)" },
                    ...versions.map((v) => ({
                      value: v.id,
                      label: `v${v.version_number} ${v.is_active ? "(active)" : ""} — effective ${v.effective_from}`,
                    })),
                  ]}
                />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item label="Correlation id">
                <Input value={correlationId} onChange={(e) => setCorrelationId(e.target.value)} />
              </Form.Item>
            </Col>
            <Col span={24}>
              <Checkbox checked={useAdvancedJson} onChange={(e) => setUseAdvancedJson(e.target.checked)}>
                Advanced (raw JSON facts) mode
              </Checkbox>
            </Col>
          </Row>

          {useAdvancedJson ? (
            <Form.Item label="Facts (JSON object)" style={{ marginTop: 16 }}>
              <TextArea rows={8} value={factsJson} onChange={(e) => setFactsJson(e.target.value)} spellCheck={false} />
            </Form.Item>
          ) : (
            <div style={{ marginTop: 16 }}>
              <Paragraph type="secondary" style={{ marginBottom: 8 }}>
                Facts (auto-generated from required facts of the selected version's rules)
              </Paragraph>
              {factFields.length === 0 && (
                <Text type="secondary">No required facts found — this version may have no rules yet.</Text>
              )}
              <Row gutter={16}>
                {factFields.map((f) => (
                  <Col span={8} key={f.name}>
                    <Form.Item
                      label={
                        <span>
                          {f.name}
                          {f.required && <Text type="danger"> *</Text>} <Text type="secondary">({f.data_type})</Text>
                        </span>
                      }
                    >
                      {f.data_type === "boolean" ? (
                        <Select
                          allowClear
                          value={factValues[f.name] || undefined}
                          onChange={(v) => setFactValues((prev) => ({ ...prev, [f.name]: v ?? "" }))}
                          options={[
                            { value: "true", label: "true" },
                            { value: "false", label: "false" },
                          ]}
                        />
                      ) : f.data_type === "number" ? (
                        <InputNumber
                          style={{ width: "100%" }}
                          value={factValues[f.name] ? Number(factValues[f.name]) : undefined}
                          onChange={(v) => setFactValues((prev) => ({ ...prev, [f.name]: v === null ? "" : String(v) }))}
                        />
                      ) : (
                        <Input
                          type={f.data_type === "date" ? "date" : "text"}
                          value={factValues[f.name] ?? ""}
                          onChange={(e) => setFactValues((prev) => ({ ...prev, [f.name]: e.target.value }))}
                        />
                      )}
                    </Form.Item>
                  </Col>
                ))}
              </Row>
            </div>
          )}

          <Button type="primary" icon={<PlayCircleOutlined />} htmlType="submit" loading={loading}>
            {loading ? "Evaluating…" : "Run Evaluation"}
          </Button>
        </Form>
      </Card>

      {response && (
        <Card title="Evaluation Result">
          <Descriptions size="small" column={2} bordered style={{ marginBottom: 20 }}>
            <Descriptions.Item label="Overall status">
              <Tag color={STATUS_COLOR[response.overall_status] ?? "default"}>{response.overall_status}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="Outcome">{response.outcome ?? "—"}</Descriptions.Item>
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

          {(response.aggregate_breaches?.length ?? 0) > 0 && (
            <Alert
              type="warning"
              showIcon
              style={{ marginBottom: 20 }}
              message="Aggregate limit breached"
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
              message="Advice"
              description={
                <>
                  <Paragraph type="secondary" style={{ margin: "0 0 8px" }}>
                    Non-blocking guidance from the rules that decided this outcome — informational only, does not
                    change the decision.
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
                    <Tag color={STATUS_COLOR[s] ?? "default"}>{s}</Tag>
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
                  const color = row.effect_type === "deny" ? "red" : row.effect_type === "allow" ? "green" : "blue";
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
        </Card>
      )}
    </>
  );
}
