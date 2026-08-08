import { useEffect, useMemo, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Empty,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Select,
  Space,
  Tag,
  Typography,
  message,
} from "antd";
import { BarChartOutlined, DeleteOutlined, EditOutlined, PlusOutlined } from "@ant-design/icons";
import {
  api,
  PolicyPlatformApiError,
  type AggregateLimitContribution,
  type AggregateLimitResponse,
  type CanonicalRule,
} from "../api";

const { Title, Text, Paragraph } = Typography;

interface LimitFormValues {
  aggregate_key: string;
  description: string;
  max_value: number;
  period?: string;
  contributing_rules: AggregateLimitContribution[];
}

/**
 * Authoring UI for cross-rule "combined cap" limits (OMG DMN Collect+SUM —
 * see contracts/policy.py::AggregateLimit / ADR-0008). Grounding example:
 * two different leave-entitlement rules (60 days pregnancy + 15 days/year
 * sick-family) whose days jointly may not exceed 70/year. These are
 * policy-set-scoped drafts a Policy Manager maintains directly (no
 * per-item review step, unlike candidate rules) and are snapshotted
 * verbatim into the next published version — see
 * `publish_approved_candidates` in api/routers/candidate_rules.py.
 *
 * Before this component the feature was display-only: PolicyInspector's
 * "Counts toward a combined cap" section could show an existing limit on a
 * rule, and the deterministic evaluator already enforced it end to end
 * (`_evaluate_aggregate_limits` in evaluator/engine.py), but there was no
 * way to create, edit, or delete one anywhere in the product — only via a
 * raw API call.
 */
export function AggregateLimitsPage({ policySetKey }: { policySetKey: string }) {
  const [limits, setLimits] = useState<AggregateLimitResponse[]>([]);
  const [rules, setRules] = useState<CanonicalRule[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [modalOpen, setModalOpen] = useState(false);
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [modalError, setModalError] = useState<string | null>(null);
  const [form] = Form.useForm<LimitFormValues>();

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [limitRows, versions] = await Promise.all([
        api.listAggregateLimits(policySetKey),
        api.listPolicyVersions(policySetKey),
      ]);
      setLimits(limitRows);
      const active = versions.find((v) => v.is_active) ?? versions[0];
      setRules(active ? await api.getVersionRules(policySetKey, active.id) : []);
    } catch (e) {
      setError(e instanceof PolicyPlatformApiError ? e.detail : String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [policySetKey]);

  const rulesById = useMemo(() => new Map(rules.map((r) => [r.rule_id, r])), [rules]);
  const ruleOptions = useMemo(
    () => rules.map((r) => ({ value: r.rule_id, label: `${r.title} (${r.rule_id})` })),
    [rules]
  );

  const openCreate = () => {
    setEditingKey(null);
    setModalError(null);
    form.resetFields();
    form.setFieldsValue({ contributing_rules: [{ rule_id: "", amount_fact: "" }] } as Partial<LimitFormValues>);
    setModalOpen(true);
  };

  const openEdit = (row: AggregateLimitResponse) => {
    setEditingKey(row.aggregate_key);
    setModalError(null);
    form.setFieldsValue({
      aggregate_key: row.aggregate_key,
      description: row.description,
      max_value: row.max_value,
      period: row.period ?? "",
      contributing_rules:
        row.contributing_rules.length > 0 ? row.contributing_rules : [{ rule_id: "", amount_fact: "" }],
    });
    setModalOpen(true);
  };

  const handleSave = async () => {
    setModalError(null);
    let values: LimitFormValues;
    try {
      values = await form.validateFields();
    } catch {
      return; // inline field errors already shown by the form
    }
    setSaving(true);
    try {
      const payload = {
        description: values.description,
        max_value: values.max_value,
        period: values.period?.trim() ? values.period.trim() : null,
        contributing_rules: values.contributing_rules,
        aggregator: "SUM" as const,
      };
      if (editingKey) {
        await api.updateAggregateLimit(policySetKey, editingKey, payload);
        message.success("Aggregate limit updated — takes effect on next publish");
      } else {
        await api.createAggregateLimit(policySetKey, { ...payload, aggregate_key: values.aggregate_key });
        message.success("Aggregate limit created — takes effect on next publish");
      }
      setModalOpen(false);
      await load();
    } catch (e) {
      setModalError(e instanceof PolicyPlatformApiError ? e.detail : String(e));
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (aggregateKey: string) => {
    try {
      await api.deleteAggregateLimit(policySetKey, aggregateKey);
      message.success("Aggregate limit deleted — takes effect on next publish");
      await load();
    } catch (e) {
      message.error(e instanceof PolicyPlatformApiError ? e.detail : String(e));
    }
  };

  return (
    <div className="aggregate-limits-page">
      <div className="page-header-row">
        <div>
          <Title level={4} style={{ marginBottom: 4 }}>
            Aggregate limits
          </Title>
          <Paragraph type="secondary" style={{ marginBottom: 0, maxWidth: 720 }}>
            Cross-rule combined caps — e.g. two different leave-entitlement rules (60 days
            pregnancy + 15 days/year sick-family) whose days jointly may not exceed 70/year.
            Evaluated after every rule, summing each <Text code>SATISFIED</Text> contributing
            rule's numeric fact. These are drafts you maintain directly here; changes take
            effect the next time you publish a version.
          </Paragraph>
        </div>
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreate} disabled={rules.length < 2}>
          New aggregate limit
        </Button>
      </div>

      {error && <Alert type="error" message={error} showIcon style={{ marginTop: 16 }} />}

      {rules.length < 2 && !loading && !error && (
        <Alert
          type="info"
          showIcon
          message="Need at least 2 rules in the active published version to build a combined cap"
          description="Publish a version with at least two numeric rules first, then come back here to link them under a shared limit."
          style={{ marginTop: 16 }}
        />
      )}

      <div style={{ marginTop: 16 }}>
        {!loading && limits.length === 0 ? (
          <Empty description="No aggregate limits yet" style={{ marginTop: 32 }} />
        ) : (
          <Space direction="vertical" size={12} style={{ width: "100%" }}>
            {limits.map((row) => (
              <Card key={row.id} size="small" className="aggregate-limit-card" loading={loading}>
                <div className="aggregate-limit-card-header">
                  <div>
                    <Text strong>{row.description || row.aggregate_key}</Text>
                    <br />
                    <Text type="secondary" className="entity-id-row" copyable={{ text: row.aggregate_key }}>
                      {row.aggregate_key}
                    </Text>
                  </div>
                  <Space>
                    <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(row)}>
                      Edit
                    </Button>
                    <Popconfirm
                      title="Delete this aggregate limit?"
                      description="Contributing rules will stop sharing this cap the next time you publish."
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
                <Space size={8} wrap style={{ marginTop: 8 }}>
                  <Tag color="geekblue" icon={<BarChartOutlined />}>
                    combined max {row.max_value}
                    {row.period ? ` / ${row.period}` : ""}
                  </Tag>
                </Space>
                <div className="aggregate-limit-contributors">
                  <Text type="secondary">Contributing rules:</Text>{" "}
                  <Space size={4} wrap>
                    {row.contributing_rules.map((c) => (
                      <Tag key={c.rule_id} className="fact-tag">
                        {rulesById.get(c.rule_id)?.title ?? c.rule_id}
                        <Text type="secondary">· {c.amount_fact}</Text>
                      </Tag>
                    ))}
                  </Space>
                </div>
              </Card>
            ))}
          </Space>
        )}
      </div>

      <Modal
        title={editingKey ? "Edit aggregate limit" : "New aggregate limit"}
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={handleSave}
        confirmLoading={saving}
        okText={editingKey ? "Save" : "Create"}
        width={640}
        destroyOnClose
      >
        {modalError && <Alert type="error" message={modalError} showIcon style={{ marginBottom: 16 }} />}
        <Form form={form} layout="vertical">
          <Form.Item
            name="aggregate_key"
            label="Key"
            rules={[{ required: true, message: "Required — a stable slug, e.g. combined-leave-cap" }]}
            extra="A short, stable identifier used by the API. Cannot be changed after creation."
          >
            <Input placeholder="combined-leave-cap" disabled={!!editingKey} />
          </Form.Item>
          <Form.Item name="description" label="Description" rules={[{ required: true, message: "Required" }]}>
            <Input.TextArea
              rows={2}
              placeholder="Combined pregnancy + sick-family leave, capped at 70 days/year"
            />
          </Form.Item>
          <Space.Compact block style={{ marginBottom: 24 }}>
            <Form.Item
              name="max_value"
              label="Combined max"
              rules={[{ required: true, message: "Required" }]}
              style={{ flex: 1, marginBottom: 0 }}
            >
              <InputNumber style={{ width: "100%" }} min={0} placeholder="70" />
            </Form.Item>
            <Form.Item name="period" label="Period (optional)" style={{ flex: 1, marginBottom: 0, marginLeft: 12 }}>
              <Input placeholder="year, quarter, …" />
            </Form.Item>
          </Space.Compact>

          <Form.List name="contributing_rules">
            {(fields, { add, remove }) => (
              <div>
                <Text strong>Contributing rules</Text>
                <div className="aggregate-limit-form-list">
                  {fields.map((field) => (
                    <Space key={field.key} align="baseline" className="aggregate-limit-form-row">
                      <Form.Item
                        name={[field.name, "rule_id"]}
                        rules={[{ required: true, message: "Pick a rule" }]}
                        style={{ marginBottom: 8, width: 320 }}
                      >
                        <Select showSearch placeholder="Select rule" options={ruleOptions} optionFilterProp="label" />
                      </Form.Item>
                      <Form.Item
                        name={[field.name, "amount_fact"]}
                        rules={[{ required: true, message: "Fact name" }]}
                        style={{ marginBottom: 8, width: 200 }}
                      >
                        <Input placeholder="leave.daysRequested" />
                      </Form.Item>
                      {fields.length > 1 && (
                        <Button type="text" danger icon={<DeleteOutlined />} onClick={() => remove(field.name)} />
                      )}
                    </Space>
                  ))}
                </div>
                <Button
                  type="dashed"
                  icon={<PlusOutlined />}
                  onClick={() => add({ rule_id: "", amount_fact: "" })}
                  block
                >
                  Add contributing rule
                </Button>
              </div>
            )}
          </Form.List>
        </Form>
      </Modal>
    </div>
  );
}
