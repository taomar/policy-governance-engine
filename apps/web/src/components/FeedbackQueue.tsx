/**
 * Inbound feedback queue for policy authors and admins.
 *
 * Rendered inside ReviewQueue.tsx as a segment of its Segmented control —
 * "Candidates | Submitted feedback". Not a separate tab or nav entry,
 * because the Review tab already means "someone needs me to look at this
 * and decide"; a separate destination would fragment that.
 *
 * F7: uses the same hairline-divided register idiom as the candidate queue
 * rather than an Ant Table, so the two segments of one surface read as one
 * product. Each item carries a link to the rule it concerns so an author
 * who reads a comment does not have to go hunting.
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
  Tag,
  Tooltip,
  Typography,
  message,
} from "antd";
import {
  CheckOutlined,
  EditOutlined,
  CloseOutlined,
  RightOutlined,
} from "@ant-design/icons";
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
  /** Navigate to a specific rule from a feedback item. */
  onNavigateToRule?: (ruleId: string) => void;
}

export function FeedbackQueue({ policySetKey, actorName, epoch, onCountChange, onNavigateToRule }: FeedbackQueueProps) {
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

  if (!loading && items.length === 0) {
    return (
      <Empty
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        description="No feedback waiting. Viewers can submit comments on published policies."
      />
    );
  }

  const actionable = (r: PolicyReviewRequest) =>
    r.status === "open" || r.status === "acknowledged";

  return (
    <>
      <div className="feedback-register" data-testid="feedback-queue-register">
        {items.map((record, i) => (
          <div
            key={record.id}
            className={`feedback-row${i < items.length - 1 ? " feedback-row--ruled" : ""}`}
          >
            <div className="feedback-row__main">
              <div className="feedback-row__line1">
                <span className="feedback-row__author">{record.submitted_by}</span>
                <span className="feedback-row__date">
                  {new Date(record.submitted_at).toLocaleString()}
                </span>
                <Tag color={STATUS_COLOR[record.status]}>{record.status}</Tag>
              </div>
              <div className="feedback-row__comment">{record.comment}</div>
              <div className="feedback-row__meta">
                {record.categories && record.categories.length > 0 && (
                  <Space size={4} wrap>
                    {record.categories.map((c) => (
                      <Tag key={c}>{c}</Tag>
                    ))}
                  </Space>
                )}
                {record.approved_policy_version_id && onNavigateToRule && (
                  <Tooltip title="Open the rule this feedback concerns">
                    <Button
                      size="small"
                      type="link"
                      icon={<RightOutlined />}
                      onClick={() => onNavigateToRule(record.approved_policy_version_id)}
                    >
                      View rule
                    </Button>
                  </Tooltip>
                )}
              </div>
            </div>
            <div className="feedback-row__actions" onClick={(e) => e.stopPropagation()}>
              {actionable(record) ? (
                <Space size={4}>
                  {record.status === "open" && (
                    <Tooltip title="Mark as seen — the submitter will know you read it">
                      <Button size="small" icon={<CheckOutlined />} onClick={() => handleAcknowledge(record)}>
                        Acknowledge
                      </Button>
                    </Tooltip>
                  )}
                  <Tooltip title="Open the policy for revision based on this feedback">
                    <Button size="small" type="primary" icon={<EditOutlined />} onClick={() => handleAction(record)}>
                      Open for revision
                    </Button>
                  </Tooltip>
                  <Button
                    size="small"
                    icon={<CloseOutlined />}
                    onClick={() => { setDismissTarget(record); setDismissNote(""); }}
                  >
                    Dismiss
                  </Button>
                </Space>
              ) : (
                record.resolution_note && (
                  <Text type="secondary" italic>
                    {record.resolution_note}
                  </Text>
                )
              )}
            </div>
          </div>
        ))}
      </div>
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
