import { useEffect, useMemo, useState } from "react";
import {
  Alert,
  Button,
  Card,
  DatePicker,
  Empty,
  Form,
  Input,
  Modal,
  Segmented,
  Select,
  Space,
  Tag,
  Typography,
  message,
} from "antd";
import { CheckOutlined, CloseOutlined, FileProtectOutlined, PlusOutlined } from "@ant-design/icons";
import dayjs from "dayjs";
import {
  api,
  policyExceptionApi,
  PolicyPlatformApiError,
  type CanonicalRule,
  type CreatePolicyExceptionRequest,
  type PolicyException,
  type PolicyExceptionDecision,
} from "../api";
import { useActor } from "../ActorContext";

const { Title, Text, Paragraph } = Typography;

const DECISION_COLOR: Record<PolicyExceptionDecision, string> = {
  pending: "gold",
  granted: "green",
  denied: "red",
};

const DECISION_LABEL: Record<PolicyExceptionDecision, string> = {
  pending: "Pending",
  granted: "Granted",
  denied: "Denied",
};

interface CreateFormValues {
  rule_id?: string;
  requester: string;
  justification: string;
  expiry_date?: dayjs.Dayjs;
}

/**
 * Exceptions view — ad hoc, human-requested, time-bounded waivers of a rule
 * (or the whole policy set) for one particular case (ADR-0009). Distinct
 * from the standing, automatically-evaluated exceptions embedded directly
 * in a rule's own definition (see RuleCard's "Exceptions" section): those
 * are baked into the rule and the deterministic evaluator applies them to
 * every matching case; a `PolicyException` here is a one-off waiver a
 * policy manager grants or denies for a specific requester's situation, and
 * is never itself evaluated by the engine.
 *
 * Fits the existing 3-actor model: any actor can request one, only a
 * policy manager can grant/deny it — mirroring the review gate already
 * used in `ReviewQueue`/`PolicyTestsPage`.
 */
export function PolicyExceptionsPage({ policySetKey }: { policySetKey: string }) {
  const { actor } = useActor();
  const isManager = actor.role === "policy_manager";

  const [rows, setRows] = useState<PolicyException[]>([]);
  const [rules, setRules] = useState<CanonicalRule[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<"all" | PolicyExceptionDecision>("all");

  const [createOpen, setCreateOpen] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [createSaving, setCreateSaving] = useState(false);
  const [form] = Form.useForm<CreateFormValues>();

  const [decidingId, setDecidingId] = useState<string | null>(null);
  const [decideTarget, setDecideTarget] = useState<{ row: PolicyException; decision: "granted" | "denied" } | null>(
    null
  );
  const [decideNotes, setDecideNotes] = useState("");

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [exceptionRows, versions] = await Promise.all([
        policyExceptionApi.list(policySetKey),
        api.listPolicyVersions(policySetKey),
      ]);
      setRows(exceptionRows);
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

  const filteredRows = useMemo(
    () => (filter === "all" ? rows : rows.filter((r) => r.decision === filter)),
    [rows, filter]
  );

  const counts = useMemo(
    () => ({
      all: rows.length,
      pending: rows.filter((r) => r.decision === "pending").length,
      granted: rows.filter((r) => r.decision === "granted").length,
      denied: rows.filter((r) => r.decision === "denied").length,
    }),
    [rows]
  );

  const openCreate = () => {
    form.resetFields();
    form.setFieldsValue({ requester: actor.name || "" });
    setCreateError(null);
    setCreateOpen(true);
  };

  const handleCreate = async () => {
    let values: CreateFormValues;
    try {
      values = await form.validateFields();
    } catch {
      return;
    }
    setCreateSaving(true);
    setCreateError(null);
    try {
      const body: CreatePolicyExceptionRequest = {
        rule_id: values.rule_id || null,
        requester: values.requester,
        justification: values.justification,
        expiry_date: values.expiry_date ? values.expiry_date.format("YYYY-MM-DD") : null,
      };
      await policyExceptionApi.create(policySetKey, body);
      message.success("Exception request submitted — awaiting a policy manager's decision");
      setCreateOpen(false);
      await load();
    } catch (e) {
      setCreateError(e instanceof PolicyPlatformApiError ? e.detail : String(e));
    } finally {
      setCreateSaving(false);
    }
  };

  const openDecide = (row: PolicyException, decision: "granted" | "denied") => {
    setDecideTarget({ row, decision });
    setDecideNotes("");
  };

  const handleDecide = async () => {
    if (!decideTarget) return;
    setDecidingId(decideTarget.row.id);
    try {
      await policyExceptionApi.decide(decideTarget.row.id, {
        decision: decideTarget.decision,
        decided_by: actor.name || "unknown",
        decision_notes: decideNotes.trim() || null,
      });
      message.success(decideTarget.decision === "granted" ? "Exception granted" : "Exception denied");
      setDecideTarget(null);
      await load();
    } catch (e) {
      message.error(e instanceof PolicyPlatformApiError ? e.detail : String(e));
    } finally {
      setDecidingId(null);
    }
  };

  return (
    <div className="policy-exceptions-page">
      <div className="page-header-row">
        <div>
          <Title level={4} style={{ marginBottom: 4 }}>
            Exceptions
          </Title>
          <Paragraph type="secondary" style={{ marginBottom: 0, maxWidth: 720 }}>
            Ad hoc, time-bounded waivers of a rule — or the whole policy — for one particular
            case (e.g. "waive the 3-day advance-notice rule for this request due to a family
            emergency"). Distinct from a rule's own built-in exceptions: this is a one-off human
            request a policy manager grants or denies, never evaluated automatically.
          </Paragraph>
        </div>
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
          Request exception
        </Button>
      </div>

      {error && <Alert type="error" message={error} showIcon style={{ marginTop: 16 }} />}

      <Segmented
        style={{ marginTop: 16 }}
        value={filter}
        onChange={(v) => setFilter(v as typeof filter)}
        options={[
          { label: `All (${counts.all})`, value: "all" },
          { label: `Pending (${counts.pending})`, value: "pending" },
          { label: `Granted (${counts.granted})`, value: "granted" },
          { label: `Denied (${counts.denied})`, value: "denied" },
        ]}
      />

      <div style={{ marginTop: 16 }}>
        {!loading && filteredRows.length === 0 ? (
          <Empty description="No exception requests here yet" style={{ marginTop: 32 }} />
        ) : (
          <Space direction="vertical" size={12} style={{ width: "100%" }}>
            {filteredRows.map((row) => {
              const rule = row.rule_id ? rulesById.get(row.rule_id) : null;
              return (
                <Card key={row.id} size="small" className="policy-exception-card" loading={loading}>
                  <div className="policy-exception-card-header">
                    <div>
                      <Space size={8} wrap>
                        <Tag color={DECISION_COLOR[row.decision]} icon={<FileProtectOutlined />}>
                          {DECISION_LABEL[row.decision]}
                        </Tag>
                        {row.is_expired && <Tag color="default">Expired</Tag>}
                      </Space>
                      <br />
                      <Text strong style={{ marginTop: 4, display: "inline-block" }}>
                        {rule ? rule.title : row.rule_id ? row.rule_id : "Whole policy set"}
                      </Text>
                      <br />
                      <Text type="secondary">
                        Requested by {row.requester} on {dayjs(row.created_at).format("MMM D, YYYY")}
                        {row.expiry_date && <> · expires {dayjs(row.expiry_date).format("MMM D, YYYY")}</>}
                      </Text>
                    </div>
                    {isManager && row.decision === "pending" && (
                      <Space>
                        <Button
                          size="small"
                          icon={<CheckOutlined />}
                          loading={decidingId === row.id}
                          onClick={() => openDecide(row, "granted")}
                        >
                          Grant
                        </Button>
                        <Button
                          size="small"
                          danger
                          icon={<CloseOutlined />}
                          loading={decidingId === row.id}
                          onClick={() => openDecide(row, "denied")}
                        >
                          Deny
                        </Button>
                      </Space>
                    )}
                  </div>
                  <Paragraph style={{ marginTop: 8, marginBottom: row.decision_notes ? 4 : 0 }}>
                    {row.justification}
                  </Paragraph>
                  {row.decision_notes && (
                    <Text type="secondary">
                      Decision by {row.decided_by}: {row.decision_notes}
                    </Text>
                  )}
                </Card>
              );
            })}
          </Space>
        )}
      </div>

      <Modal
        title="Request an exception"
        open={createOpen}
        onCancel={() => setCreateOpen(false)}
        onOk={handleCreate}
        confirmLoading={createSaving}
        okText="Submit request"
        width={560}
        destroyOnHidden
      >
        {createError && <Alert type="error" message={createError} showIcon style={{ marginBottom: 16 }} />}
        <Form form={form} layout="vertical">
          <Form.Item
            name="rule_id"
            label="Rule (optional)"
            extra="Leave blank to request an exception to the whole policy set."
          >
            <Select
              showSearch
              allowClear
              placeholder="Select a specific rule, or leave blank"
              options={ruleOptions}
              optionFilterProp="label"
            />
          </Form.Item>
          <Form.Item name="requester" label="Requested by" rules={[{ required: true, message: "Required" }]}>
            <Input placeholder="Your name" />
          </Form.Item>
          <Form.Item
            name="justification"
            label="Justification"
            rules={[{ required: true, message: "Explain why this exception is needed" }]}
          >
            <Input.TextArea rows={3} placeholder="Why this specific case should be waived, and for how long" />
          </Form.Item>
          <Form.Item name="expiry_date" label="Expires on (optional)">
            <DatePicker style={{ width: "100%" }} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={decideTarget?.decision === "granted" ? "Grant this exception?" : "Deny this exception?"}
        open={!!decideTarget}
        onCancel={() => setDecideTarget(null)}
        onOk={handleDecide}
        confirmLoading={!!decidingId}
        okText={decideTarget?.decision === "granted" ? "Grant" : "Deny"}
        okButtonProps={{ danger: decideTarget?.decision === "denied" }}
        destroyOnHidden
      >
        <Paragraph type="secondary">
          {decideTarget?.row.justification}
        </Paragraph>
        <Input.TextArea
          rows={2}
          placeholder="Decision notes (optional)"
          value={decideNotes}
          onChange={(e) => setDecideNotes(e.target.value)}
        />
      </Modal>
    </div>
  );
}
