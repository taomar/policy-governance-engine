import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Descriptions,
  Drawer,
  Empty,
  Input,
  Segmented,
  Space,
  Table,
  Tag,
  Tooltip,
  Typography,
} from "antd";
import { ReloadOutlined } from "@ant-design/icons";
import {
  evaluationLogApi,
  PolicyPlatformApiError,
  type EvaluationLogDetail,
  type EvaluationLogSummary,
  type EvaluationStatus,
} from "../api";
import { EvaluationResultView, EVALUATION_STATUS_COLOR } from "./EvaluationResultView";
import { JsonView } from "./JsonView";

const { Title, Text, Paragraph } = Typography;

type StatusFilter = "all" | EvaluationStatus;

const STATUS_OPTIONS: { label: string; value: StatusFilter }[] = [
  { label: "All", value: "all" },
  { label: "Satisfied", value: "SATISFIED" },
  { label: "Not satisfied", value: "NOT_SATISFIED" },
  { label: "Not applicable", value: "NOT_APPLICABLE" },
  { label: "Indeterminate", value: "INDETERMINATE" },
  { label: "Error", value: "ERROR" },
];

/**
 * The decision log: a queryable, read-only view over every runtime
 * `POST /api/evaluations` call ever made against this policy set (ADR-0009's
 * "Decision/audit logging depth (OPA Decision Logs)... Adopt, incremental").
 *
 * Distinct from the "Recent governance activity" panel (`ActivityPanel`):
 * that records who *authored/approved* the policy (a candidate reviewed, a
 * version published). This records how the *deterministic engine actually
 * decided* for a calling system at runtime — the facts it was given, the
 * verdict it returned, and a hash proving the result was not altered after
 * the fact. Deliberately read-only: an evaluation record that could be
 * edited would not be usable as evidence.
 */
export function DecisionLogPage({ policySetKey }: { policySetKey: string }) {
  const [rows, setRows] = useState<EvaluationLogSummary[]>([]);
  const [count, setCount] = useState(0);
  const [truncated, setTruncated] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [correlationId, setCorrelationId] = useState("");
  const [callingSystem, setCallingSystem] = useState("");

  const [detail, setDetail] = useState<EvaluationLogDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const page = await evaluationLogApi.list(policySetKey, {
        overallStatus: statusFilter === "all" ? undefined : statusFilter,
        correlationId: correlationId.trim() || undefined,
        callingSystemIdentity: callingSystem.trim() || undefined,
        limit: 200,
      });
      setRows(page.evaluations);
      setCount(page.count);
      setTruncated(page.truncated);
    } catch (e) {
      setError(e instanceof PolicyPlatformApiError ? e.detail : String(e));
    } finally {
      setLoading(false);
    }
  }, [policySetKey, statusFilter, correlationId, callingSystem]);

  useEffect(() => {
    void load();
  }, [load]);

  const openDetail = async (id: string) => {
    setOpenId(id);
    setDetail(null);
    setDetailError(null);
    setDetailLoading(true);
    try {
      const d = await evaluationLogApi.getDetail(id);
      setDetail(d);
    } catch (e) {
      setDetailError(e instanceof PolicyPlatformApiError ? e.detail : String(e));
    } finally {
      setDetailLoading(false);
    }
  };

  const columns = useMemo(
    () => [
      {
        title: "When",
        dataIndex: "evaluation_timestamp",
        width: 190,
        render: (v: string) => new Date(v).toLocaleString(),
      },
      {
        title: "Status",
        dataIndex: "overall_status",
        width: 140,
        render: (v: EvaluationStatus) => <Tag color={EVALUATION_STATUS_COLOR[v] ?? "default"}>{v}</Tag>,
      },
      {
        title: "Correlation id",
        dataIndex: "correlation_id",
        render: (v: string | null) => (v ? <Text code>{v}</Text> : <Text type="secondary">—</Text>),
      },
      {
        title: "Calling system",
        dataIndex: "calling_system_identity",
        render: (v: string | null) => v ?? <Text type="secondary">—</Text>,
      },
      {
        title: "Result hash",
        dataIndex: "result_hash",
        render: (v: string) => (
          <Tooltip title={v}>
            <Text code copyable={{ text: v }} style={{ fontSize: 12 }}>
              {v.slice(0, 12)}…
            </Text>
          </Tooltip>
        ),
      },
      {
        title: "",
        key: "actions",
        width: 90,
        render: (_: unknown, row: EvaluationLogSummary) => (
          <Button size="small" onClick={() => openDetail(row.id)}>
            View
          </Button>
        ),
      },
    ],
    []
  );

  return (
    <div className="decision-log-page">
      <div className="page-header-row">
        <div>
          <Title level={4} style={{ marginBottom: 4 }}>
            Decision Log
          </Title>
          <Paragraph type="secondary" style={{ marginBottom: 0, maxWidth: 720 }}>
            Every runtime evaluation call against this policy set, recorded as immutable evidence — who called, what
            facts were given, what the engine decided, and a hash proving the result wasn't altered afterward. Mirrors
            OPA's Decision Logs.
          </Paragraph>
        </div>
        <Button icon={<ReloadOutlined />} onClick={() => void load()} loading={loading}>
          Refresh
        </Button>
      </div>

      {error && <Alert type="error" message={error} showIcon style={{ marginTop: 16 }} />}

      <Card size="small" style={{ marginTop: 16, marginBottom: 16 }}>
        <Space direction="vertical" size={12} style={{ width: "100%" }}>
          <Segmented value={statusFilter} onChange={(v) => setStatusFilter(v as StatusFilter)} options={STATUS_OPTIONS} />
          <Space wrap>
            <Input.Search
              placeholder="Filter by correlation id"
              allowClear
              style={{ width: 260 }}
              value={correlationId}
              onChange={(e) => setCorrelationId(e.target.value)}
              onSearch={() => void load()}
            />
            <Input.Search
              placeholder="Filter by calling system"
              allowClear
              style={{ width: 260 }}
              value={callingSystem}
              onChange={(e) => setCallingSystem(e.target.value)}
              onSearch={() => void load()}
            />
          </Space>
        </Space>
      </Card>

      {!loading && rows.length === 0 ? (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description="No evaluation calls recorded for this policy set yet. Calls to POST /api/evaluations (including from the Evaluate page) will appear here."
          style={{ marginTop: 48 }}
        />
      ) : (
        <>
          <Table
            size="small"
            rowKey="id"
            loading={loading}
            dataSource={rows}
            columns={columns}
            pagination={{ pageSize: 20, showSizeChanger: false }}
          />
          <Text type="secondary" style={{ fontSize: 12 }}>
            Showing {count} record{count === 1 ? "" : "s"}
            {truncated && " (most recent 200 — narrow the filters above to see more specific results)"}.
          </Text>
        </>
      )}

      <Drawer
        title="Decision detail"
        open={openId !== null}
        onClose={() => setOpenId(null)}
        size={720}
        destroyOnHidden
      >
        {detailLoading && <Text type="secondary">Loading…</Text>}
        {detailError && <Alert type="error" message={detailError} showIcon />}
        {detail && (
          <>
            <Descriptions size="small" column={1} bordered style={{ marginBottom: 20 }}>
              <Descriptions.Item label="Evaluation id">
                <Text code copyable={{ text: detail.id }}>
                  {detail.id}
                </Text>
              </Descriptions.Item>
              <Descriptions.Item label="Policy version id">
                <Text code copyable={{ text: detail.policy_version_id }}>
                  {detail.policy_version_id}
                </Text>
              </Descriptions.Item>
              <Descriptions.Item label="Correlation id">{detail.correlation_id ?? "—"}</Descriptions.Item>
              <Descriptions.Item label="Calling system">{detail.calling_system_identity ?? "—"}</Descriptions.Item>
              <Descriptions.Item label="Timestamp">
                {new Date(detail.evaluation_timestamp).toLocaleString()}
              </Descriptions.Item>
            </Descriptions>

            <Title level={5}>Request facts</Title>
            <JsonView value={detail.request_facts} downloadName={`${detail.id}-facts.json`} maxHeight={220} />

            <Title level={5} style={{ marginTop: 20 }}>
              Result
            </Title>
            <EvaluationResultView response={detail.response} />
          </>
        )}
      </Drawer>
    </div>
  );
}

export default DecisionLogPage;
