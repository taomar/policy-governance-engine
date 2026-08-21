/**
 * Inbound feedback queue for policy authors and admins.
 *
 * Rendered inside ReviewQueue.tsx as a segment of its Segmented control —
 * "Candidates | Submitted feedback". Not a separate tab or nav entry,
 * because the Review tab already means "someone needs me to look at this
 * and decide"; a separate destination would fragment that.
 *
 * Actions: Acknowledge, Open for revision (resolve as `actioned`),
 * Dismiss with reason (resolution_note required before calling).
 */

import { useCallback, useEffect, useState } from "react";
import {
  Button,
  Empty,
  Input,
  Modal,
  Space,
  Table,
  Tag,
  Tooltip,
  Typography,
  message,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import { api, PolicyPlatformApiError, type PolicyReviewRequest, type ReviewRequestStatus } from "../api";

const { Text } = Typography;
const { TextArea } = Input;

const STATUS_COLOR: Record<ReviewRequestStatus, string> = {
  open: "blue",
  acknowledged: "cyan",
  actioned: "green",
  dismissed: "default",
  withdrawn: "default",
};

export interface FeedbackQueueProps {
  policySetKey: string;
  actorName: string;
  /** Bumped externally to trigger a re-fetch, e.g. after an action. */
  epoch?: number;
  /** Reports how many open items are in the queue so the parent can badge. */
  onCountChange?: (count: number) => void;
}

export function FeedbackQueue({ policySetKey, actorName, epoch, onCountChange }: FeedbackQueueProps) {
  const [items, setItems] = useState<PolicyReviewRequest[]>([]);
  const [loading, setLoading] = useState(false);
  const [dismissTarget, setDismissTarget] = useState<PolicyReviewRequest | null>(null);
  const [dismissNote, setDismissNote] = useState("");

  const load = useCallback(() => {
    if (!policySetKey) return;
    setLoading(true);
    api
      .listReviewRequests({ policy_set_key: policySetKey })
      .then((records) => {
        setItems(records);
        onCountChange?.(records.filter((r) => r.status === "open").length);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [policySetKey, onCountChange]);

  useEffect(() => {
    load();
  }, [load, epoch]);

  async function handleAcknowledge(record: PolicyReviewRequest) {
    try {
      await api.acknowledgeReviewRequest(record.id, actorName);
      message.success("Feedback acknowledged.");
      load();
    } catch (err) {
      if (err instanceof PolicyPlatformApiError && err.status === 409) {
        message.warning("This feedback has already been acted on.");
      } else {
        message.error("Could not acknowledge feedback.");
      }
      load();
    }
  }

  async function handleAction(record: PolicyReviewRequest) {
    try {
      await api.resolveReviewRequest(record.id, {
        disposition: "actioned",
        resolved_by: actorName,
      });
      message.success("Marked as actioned — the policy will be revised.");
      load();
    } catch (err) {
      if (err instanceof PolicyPlatformApiError && err.status === 409) {
        message.warning("This feedback has already been resolved.");
      } else {
        message.error("Could not resolve feedback.");
      }
      load();
    }
  }

  async function handleDismissConfirm() {
    if (!dismissTarget || !dismissNote.trim()) return;
    try {
      await api.resolveReviewRequest(dismissTarget.id, {
        disposition: "dismissed",
        resolution_note: dismissNote.trim(),
        resolved_by: actorName,
      });
      message.success("Feedback dismissed.");
      setDismissTarget(null);
      setDismissNote("");
      load();
    } catch (err) {
      if (err instanceof PolicyPlatformApiError && err.status === 409) {
        message.warning("This feedback has already been resolved.");
      } else {
        message.error("Could not dismiss feedback.");
      }
      load();
    }
  }

  const columns: ColumnsType<PolicyReviewRequest> = [
    {
      title: "Submitted by",
      dataIndex: "submitted_by",
      key: "submitted_by",
      width: 140,
    },
    {
      title: "When",
      dataIndex: "submitted_at",
      key: "submitted_at",
      width: 160,
      render: (v: string) => new Date(v).toLocaleString(),
    },
    {
      title: "Categories",
      dataIndex: "categories",
      key: "categories",
      width: 180,
      render: (cats?: string[]) =>
        cats && cats.length > 0 ? (
          <Space size={4} wrap>
            {cats.map((c) => (
              <Tag key={c}>{c}</Tag>
            ))}
          </Space>
        ) : (
          <Text type="secondary">—</Text>
        ),
    },
    {
      title: "Comment",
      dataIndex: "comment",
      key: "comment",
      ellipsis: { showTitle: false },
      render: (text: string) => (
        <Tooltip title={text} placement="topLeft">
          <span>{text}</span>
        </Tooltip>
      ),
    },
    {
      title: "Status",
      dataIndex: "status",
      key: "status",
      width: 120,
      render: (s: ReviewRequestStatus) => <Tag color={STATUS_COLOR[s]}>{s}</Tag>,
    },
    {
      title: "Actions",
      key: "actions",
      width: 260,
      render: (_: unknown, record: PolicyReviewRequest) => {
        if (record.status !== "open" && record.status !== "acknowledged") {
          if (record.resolution_note) {
            return (
              <Text type="secondary" italic>
                {record.resolution_note}
              </Text>
            );
          }
          return null;
        }
        return (
          <Space size={4}>
            {record.status === "open" && (
              <Button size="small" onClick={() => handleAcknowledge(record)}>
                Acknowledge
              </Button>
            )}
            <Button size="small" type="primary" onClick={() => handleAction(record)}>
              Open for revision
            </Button>
            <Button size="small" danger onClick={() => { setDismissTarget(record); setDismissNote(""); }}>
              Dismiss
            </Button>
          </Space>
        );
      },
    },
  ];

  if (!loading && items.length === 0) {
    return (
      <Empty
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        description="No feedback waiting. Viewers can submit comments on published policies."
      />
    );
  }

  return (
    <>
      <Table<PolicyReviewRequest>
        dataSource={items}
        columns={columns}
        rowKey="id"
        loading={loading}
        size="small"
        pagination={{ pageSize: 20 }}
        data-testid="feedback-queue-table"
      />
      <Modal
        open={!!dismissTarget}
        title="Dismiss feedback"
        okText="Dismiss"
        okType="danger"
        onCancel={() => { setDismissTarget(null); setDismissNote(""); }}
        onOk={handleDismissConfirm}
        okButtonProps={{ disabled: !dismissNote.trim() }}
      >
        <Text>
          A reason is required so the submitter understands why their feedback was not acted on.
        </Text>
        <TextArea
          rows={3}
          value={dismissNote}
          onChange={(e) => setDismissNote(e.target.value)}
          placeholder="Why is this feedback being dismissed?"
          style={{ marginTop: 12 }}
          data-testid="dismiss-note"
        />
      </Modal>
    </>
  );
}
