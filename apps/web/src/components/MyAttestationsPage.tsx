import { useMemo, useState } from "react";
import { Alert, Button, Card, Empty, Input, Modal, Space, Tag, Typography, message } from "antd";
import { CheckOutlined, SearchOutlined, SolutionOutlined } from "@ant-design/icons";
import dayjs from "dayjs";
import {
  api,
  policyAttestationApi,
  PolicyPlatformApiError,
  type PolicyAttestation,
  type PolicyAttestationStatus,
  type PolicySet,
} from "../api";

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

/**
 * No-login, self-service page: an employee finds their own attestation
 * obligations across every project by typing their name or identifier (there
 * is no personnel directory or authentication in this app — see
 * ActorContext, which models only the 3 governance actors and explicitly
 * excludes employees). Top-level nav item rather than a per-project tab
 * since one employee may owe acknowledgments across several policy sets at
 * once, and shouldn't have to know which project to look in.
 */
export function MyAttestationsPage() {
  const [query, setQuery] = useState("");
  const [searched, setSearched] = useState(false);
  const [rows, setRows] = useState<PolicyAttestation[]>([]);
  const [policySets, setPolicySets] = useState<PolicySet[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [ackTarget, setAckTarget] = useState<PolicyAttestation | null>(null);
  const [ackNotes, setAckNotes] = useState("");
  const [ackSaving, setAckSaving] = useState(false);

  const policySetById = useMemo(() => new Map(policySets.map((p) => [p.id, p])), [policySets]);

  const runSearch = async () => {
    const q = query.trim();
    if (!q) return;
    setLoading(true);
    setError(null);
    try {
      const [results, sets] = await Promise.all([policyAttestationApi.search(q), api.listPolicySets()]);
      setRows(results);
      setPolicySets(sets);
      setSearched(true);
    } catch (e) {
      setError(e instanceof PolicyPlatformApiError ? e.detail : String(e));
    } finally {
      setLoading(false);
    }
  };

  const openAcknowledge = (row: PolicyAttestation) => {
    setAckTarget(row);
    setAckNotes("");
  };

  const handleAcknowledge = async () => {
    if (!ackTarget) return;
    setAckSaving(true);
    try {
      await policyAttestationApi.acknowledge(ackTarget.id, { acknowledgment_notes: ackNotes.trim() || null });
      message.success("Acknowledged — thank you");
      setAckTarget(null);
      await runSearch();
    } catch (e) {
      message.error(e instanceof PolicyPlatformApiError ? e.detail : String(e));
    } finally {
      setAckSaving(false);
    }
  };

  const sortedRows = useMemo(
    () =>
      [...rows].sort((a, b) => {
        // Outstanding items first (overdue, then pending), acknowledged last.
        const rank = (s: PolicyAttestationStatus) => (s === "overdue" ? 0 : s === "pending" ? 1 : 2);
        return rank(a.status) - rank(b.status) || a.due_date.localeCompare(b.due_date);
      }),
    [rows]
  );

  return (
    <div className="my-attestations-page">
      <Title level={3} style={{ marginBottom: 4 }}>
        My Attestations
      </Title>
      <Paragraph type="secondary" style={{ marginBottom: 0, maxWidth: 640 }}>
        Find and acknowledge policies you've been asked to read and confirm. Search by the name or
        email a Policy Manager assigned your attestation under — there's no login here.
      </Paragraph>

      <Space.Compact style={{ marginTop: 20, maxWidth: 480, width: "100%" }}>
        <Input
          size="large"
          placeholder="Your name or email"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onPressEnter={runSearch}
          allowClear
        />
        <Button size="large" type="primary" icon={<SearchOutlined />} onClick={runSearch} loading={loading}>
          Find my attestations
        </Button>
      </Space.Compact>

      {error && <Alert type="error" title={error} showIcon style={{ marginTop: 16, maxWidth: 640 }} />}

      <div style={{ marginTop: 24 }}>
        {!searched ? (
          <Empty
            description="Search above to see attestations assigned to you"
            style={{ marginTop: 32 }}
          />
        ) : sortedRows.length === 0 ? (
          <Empty description="No attestations found for that name or email" style={{ marginTop: 32 }} />
        ) : (
          <Space orientation="vertical" size={12} style={{ width: "100%", maxWidth: 720 }}>
            {sortedRows.map((row) => {
              const policySet = policySetById.get(row.policy_set_id);
              return (
                <Card key={row.id} size="small" className="policy-exception-card">
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
                        {policySet ? policySet.name : "Policy"}
                      </Text>
                      <br />
                      <Text type="secondary">
                        Assigned by {row.assigned_by} · due {dayjs(row.due_date).format("MMM D, YYYY")}
                      </Text>
                    </div>
                    {row.status !== "acknowledged" && (
                      <Button
                        size="small"
                        type="primary"
                        icon={<CheckOutlined />}
                        onClick={() => openAcknowledge(row)}
                      >
                        Acknowledge
                      </Button>
                    )}
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
              );
            })}
          </Space>
        )}
      </div>

      <Modal
        title="Acknowledge this policy"
        open={!!ackTarget}
        onCancel={() => setAckTarget(null)}
        onOk={handleAcknowledge}
        confirmLoading={ackSaving}
        okText="Confirm acknowledgment"
        destroyOnHidden
      >
        <Paragraph type="secondary">
          Confirming that you've read and understood{" "}
          {ackTarget ? policySetById.get(ackTarget.policy_set_id)?.name ?? "this policy" : "this policy"}
          {ackTarget ? ` (version ${ackTarget.version_number})` : ""}.
        </Paragraph>
        <Input.TextArea
          rows={2}
          placeholder="Notes (optional)"
          value={ackNotes}
          onChange={(e) => setAckNotes(e.target.value)}
        />
      </Modal>
    </div>
  );
}
