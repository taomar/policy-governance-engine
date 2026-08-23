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
import { CheckOutlined, PlusOutlined, SolutionOutlined } from "@ant-design/icons";
import dayjs from "dayjs";
import {
  api,
  policyAttestationApi,
  PolicyPlatformApiError,
  type ApprovedPolicyVersion,
  type CreatePolicyAttestationCampaignRequest,
  type PolicyAttestation,
  type PolicyAttestationStatus,
} from "../api";
import { useActor } from "../ActorContext";
import { actorRoleRefusalText } from "../actorRole";

const { Title, Text, Paragraph } = Typography;

const STATUS_COLOR: Record<PolicyAttestationStatus, string> = {
  pending: "blue",
  acknowledged: "green",
  overdue: "red",
};

const STATUS_LABEL: Record<PolicyAttestationStatus, string> = {
  pending: "Pending",
  acknowledged: "Acknowledged",
  overdue: "Overdue",
};

interface CampaignFormValues {
  policy_version_id: string;
  due_date: dayjs.Dayjs;
  employees_raw: string;
}

/** Parses one "Name, identifier" (or just "Name") pair per line into assignees. */
function parseEmployeesRaw(raw: string): { name: string; identifier: string | null }[] {
  return raw
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line.length > 0)
    .map((line) => {
      const [name, identifier] = line.split(",").map((part) => part.trim());
      return { name, identifier: identifier || null };
    })
    .filter((e) => e.name.length > 0);
}

/**
 * Manager oversight view for employee attestation tracking (ISO 37301 §7.3,
 * ADR-0012). A Policy Manager launches a "campaign" — one published version's
 * acknowledgment obligation assigned to a batch of employees sharing a due
 * date — then watches pending/acknowledged/overdue counts here. Employees
 * themselves never see this tab; they acknowledge via the separate, no-login
 * "My Attestations" self-service page (see MyAttestationsPage), since
 * personnel are explicitly not one of this app's 3 governance actors.
 */
export function PolicyAttestationsPage({ policySetKey }: { policySetKey: string }) {
  const { actor } = useActor();
  const isManager = actor.role === "policy_manager";

  const [rows, setRows] = useState<PolicyAttestation[]>([]);
  const [versions, setVersions] = useState<ApprovedPolicyVersion[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<"all" | PolicyAttestationStatus>("all");

  const [createOpen, setCreateOpen] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [createSaving, setCreateSaving] = useState(false);
  const [form] = Form.useForm<CampaignFormValues>();

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [attestationRows, versionRows] = await Promise.all([
        policyAttestationApi.list(policySetKey),
        api.listPolicyVersions(policySetKey),
      ]);
      setRows(attestationRows);
      setVersions(versionRows);
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

  const versionOptions = useMemo(
    () =>
      versions.map((v) => ({
        value: v.id,
        label: `Version ${v.version_number}${v.is_active ? " (active)" : ""} — ${dayjs(v.effective_from).format(
          "MMM D, YYYY"
        )}`,
      })),
    [versions]
  );

  const filteredRows = useMemo(
    () => (filter === "all" ? rows : rows.filter((r) => r.status === filter)),
    [rows, filter]
  );

  const counts = useMemo(
    () => ({
      all: rows.length,
      pending: rows.filter((r) => r.status === "pending").length,
      acknowledged: rows.filter((r) => r.status === "acknowledged").length,
      overdue: rows.filter((r) => r.status === "overdue").length,
    }),
    [rows]
  );

  const openCreate = () => {
    form.resetFields();
    const active = versions.find((v) => v.is_active) ?? versions[0];
    form.setFieldsValue({
      policy_version_id: active?.id,
      due_date: dayjs().add(14, "day"),
    });
    setCreateError(null);
    setCreateOpen(true);
  };

  const handleCreate = async () => {
    let values: CampaignFormValues;
    try {
      values = await form.validateFields();
    } catch {
      return;
    }
    const employees = parseEmployeesRaw(values.employees_raw);
    if (employees.length === 0) {
      setCreateError("Enter at least one employee (one per line: \"Name, email\" or just \"Name\").");
      return;
    }
    setCreateSaving(true);
    setCreateError(null);
    try {
      const body: CreatePolicyAttestationCampaignRequest = {
        policy_version_id: values.policy_version_id,
        employees,
        due_date: values.due_date.format("YYYY-MM-DD"),
        assigned_by: actor.name || "unknown",
        actor_role: actor.role,
      };
      const created = await policyAttestationApi.createCampaign(policySetKey, body);
      message.success(`Campaign launched — ${created.length} employee${created.length === 1 ? "" : "s"} assigned`);
      setCreateOpen(false);
      await load();
    } catch (e) {
      setCreateError(e instanceof PolicyPlatformApiError ? e.detail : String(e));
    } finally {
      setCreateSaving(false);
    }
  };

  return (
    <div className="policy-exceptions-page">
      <div className="page-header-row">
        <div>
          <Title level={4} style={{ marginBottom: 4 }}>
            Attestations
          </Title>
          <Paragraph type="secondary" style={{ marginBottom: 0, maxWidth: 720 }}>
            Track each employee's obligation to read and acknowledge a specific published version of
            this policy (ISO 37301 §7.3). There's no automated reminder delivery in this local build —
            the Overdue filter is how a Policy Manager checks who still needs to be chased.
          </Paragraph>
        </div>
        {isManager && (
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={openCreate}
            disabled={versions.length === 0}
            title={versions.length === 0 ? "Publish a version before launching a campaign" : undefined}
          >
            New campaign
          </Button>
        )}
      </div>

      {error && <Alert type="error" title={error} showIcon style={{ marginTop: 16 }} />}
      {!isManager && (
        <Alert
          type="info"
          showIcon
          title={actorRoleRefusalText({
            required_role: "policy_manager",
            action: "launch_attestation_campaign",
          })}
          style={{ marginTop: 16 }}
        />
      )}

      <Segmented
        style={{ marginTop: 16 }}
        value={filter}
        onChange={(v) => setFilter(v as typeof filter)}
        options={[
          { label: `All (${counts.all})`, value: "all" },
          { label: `Pending (${counts.pending})`, value: "pending" },
          { label: `Acknowledged (${counts.acknowledged})`, value: "acknowledged" },
          { label: `Overdue (${counts.overdue})`, value: "overdue" },
        ]}
      />

      <div style={{ marginTop: 16 }}>
        {!loading && filteredRows.length === 0 ? (
          <Empty description="No attestations here yet" style={{ marginTop: 32 }} />
        ) : (
          <Space orientation="vertical" size={12} style={{ width: "100%" }}>
            {filteredRows.map((row) => (
              <Card key={row.id} size="small" className="policy-exception-card" loading={loading}>
                <div className="policy-exception-card-header">
                  <div>
                    <Space size={8} wrap>
                      <Tag color={STATUS_COLOR[row.status]} icon={<SolutionOutlined />}>
                        {STATUS_LABEL[row.status]}
                      </Tag>
                      <Tag color="default">Version {row.version_number}</Tag>
                    </Space>
                    <br />
                    <Text strong style={{ marginTop: 4, display: "inline-block" }}>
                      {row.employee_name}
                      {row.employee_identifier && (
                        <Text type="secondary" style={{ fontWeight: 400 }}>
                          {" "}
                          ({row.employee_identifier})
                        </Text>
                      )}
                    </Text>
                    <br />
                    <Text type="secondary">
                      Assigned by {row.assigned_by} · due {dayjs(row.due_date).format("MMM D, YYYY")}
                    </Text>
                  </div>
                </div>
                {row.acknowledged_at && (
                  <Paragraph style={{ marginTop: 8, marginBottom: 0 }}>
                    <Text type="secondary">
                      Acknowledged {dayjs(row.acknowledged_at).format("MMM D, YYYY h:mm A")}
                      {row.acknowledgment_notes && <>: {row.acknowledgment_notes}</>}
                    </Text>
                  </Paragraph>
                )}
              </Card>
            ))}
          </Space>
        )}
      </div>

      <Modal
        title="Launch attestation campaign"
        open={createOpen}
        onCancel={() => setCreateOpen(false)}
        onOk={handleCreate}
        confirmLoading={createSaving}
        okText="Launch campaign"
        okButtonProps={{ icon: <CheckOutlined /> }}
        width={600}
        destroyOnHidden
      >
        {createError && <Alert type="error" title={createError} showIcon style={{ marginBottom: 16 }} />}
        <Form form={form} layout="vertical">
          <Form.Item
            name="policy_version_id"
            label="Published version to acknowledge"
            rules={[{ required: true, message: "Required" }]}
          >
            <Select options={versionOptions} placeholder="Select a published version" />
          </Form.Item>
          <Form.Item name="due_date" label="Due date" rules={[{ required: true, message: "Required" }]}>
            <DatePicker style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item
            name="employees_raw"
            label="Employees"
            rules={[{ required: true, message: "Enter at least one employee" }]}
            extra='One per line: "Name, email" (email optional, but is what employees can search by).'
          >
            <Input.TextArea rows={6} placeholder={"Dana Employee, dana@example.com\nSam Staff"} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
