import { useEffect, useState } from "react";
import { Alert, Empty, Space, Table, Tag, Tooltip, Typography } from "antd";
import { aiApi, type ExtractionRunSummary } from "../api";

const { Text } = Typography;

interface Props {
  documentVersionId: string;
  /** Bumped by the parent after an extraction finishes, to force a refetch. */
  refreshKey?: number;
}

function formatWhen(iso: string | null) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString();
}

function formatDuration(started: string | null, completed: string | null) {
  if (!started || !completed) return "—";
  const ms = new Date(completed).getTime() - new Date(started).getTime();
  if (!Number.isFinite(ms) || ms < 0) return "—";
  const s = Math.round(ms / 1000);
  if (s < 60) return `${s}s`;
  return `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, "0")}s`;
}

const STATUS_COLOR: Record<string, string> = {
  completed: "green",
  running: "processing",
  failed: "red",
  pending: "default",
};

/** History of extraction attempts for one document version.
 *
 * Exists because a reviewer facing hundreds of candidates has no way to answer
 * "where did these come from" or "what happens if I run it again". Each run
 * carries a short reference so it can be quoted, and the current run — the one
 * whose rules are actually in the queue — is marked, because re-running
 * replaces the unreviewed output of the run before it.
 */
export default function ExtractionRunHistory({ documentVersionId, refreshKey = 0 }: Props) {
  const [runs, setRuns] = useState<ExtractionRunSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    aiApi
      .listExtractionRuns(documentVersionId)
      .then((rs) => {
        if (!cancelled) setRuns(rs);
      })
      .catch((e) => {
        if (!cancelled) setError(String(e));
      });
    return () => {
      cancelled = true;
    };
  }, [documentVersionId, refreshKey]);

  if (error) return <Alert type="warning" showIcon message={`Could not load run history: ${error}`} />;
  if (runs === null) return <Text type="secondary">Loading run history…</Text>;
  if (runs.length === 0) {
    return (
      <Empty
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        description={
          <Text type="secondary">
            No extraction has been run against this version yet. Each run gets its own reference, and re-running
            replaces the previous run&rsquo;s <em>unreviewed</em> rules — anything you already approved or rejected is
            kept.
          </Text>
        }
      />
    );
  }

  return (
    <Space direction="vertical" size={8} style={{ width: "100%" }}>
      <Text type="secondary">
        Every extraction of this version. Re-running replaces the current run&rsquo;s <strong>unreviewed</strong>{" "}
        candidates so the queue never contains two runs at once; rules you have already approved or rejected are never
        touched by a re-run.
      </Text>
      <Table<ExtractionRunSummary>
        size="small"
        rowKey="id"
        dataSource={runs}
        pagination={runs.length > 8 ? { pageSize: 8, showSizeChanger: false } : false}
        columns={[
          {
            title: "Run",
            dataIndex: "reference",
            render: (ref: string, row) => (
              <Space size={6}>
                <Tooltip title={`Full run id: ${row.id}`}>
                  <Text code>{ref}</Text>
                </Tooltip>
                {row.is_current && (
                  <Tooltip title="The rules from this run are the ones currently in the review queue.">
                    <Tag color="blue">current</Tag>
                  </Tooltip>
                )}
              </Space>
            ),
          },
          {
            title: "Status",
            dataIndex: "status",
            render: (s: string, row) =>
              row.error_message ? (
                <Tooltip title={row.error_message}>
                  <Tag color={STATUS_COLOR[s] ?? "default"}>{s}</Tag>
                </Tooltip>
              ) : (
                <Tag color={STATUS_COLOR[s] ?? "default"}>{s}</Tag>
              ),
          },
          {
            title: "Rules",
            dataIndex: "rules_total",
            align: "right",
            render: (total: number, row) => (
              <Tooltip
                title={
                  total === 0
                    ? "This run's unreviewed rules were replaced by a later run, or it produced none."
                    : `${row.rules_reviewed} reviewed, ${total - row.rules_reviewed} still awaiting review`
                }
              >
                <span>
                  {total}
                  {row.rules_reviewed > 0 && (
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      {" "}
                      ({row.rules_reviewed} reviewed)
                    </Text>
                  )}
                </span>
              </Tooltip>
            ),
          },
          { title: "Started", dataIndex: "started_at", render: formatWhen },
          {
            title: "Duration",
            key: "duration",
            render: (_: unknown, row) => formatDuration(row.started_at, row.completed_at),
          },
          {
            title: "Prompt",
            dataIndex: "prompt_version",
            render: (v: string | null) => (
              <Tooltip title="The prompt version the agents ran with. A run with an older prompt may be worth re-running.">
                <Text type="secondary">{v ?? "—"}</Text>
              </Tooltip>
            ),
          },
        ]}
      />
    </Space>
  );
}
