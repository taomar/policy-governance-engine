/**
 * A viewer's own feedback submissions on a policy, shown as a timeline.
 *
 * Only the current user's records are shown (`submitted_by` filter). The
 * timeline is placed below the policy content, so a viewer sees their own
 * history without it competing with the policy they are reading.
 *
 * Withdraw is offered only while the request is `open`. There is no amend
 * action — a second submission is simpler than comment edit history.
 */

import { useCallback, useEffect, useState } from "react";
import { Button, message, Modal, Space, Tag, Timeline, Typography } from "antd";
import { api, PolicyPlatformApiError, type PolicyReviewRequest, type ReviewRequestStatus } from "../api";
import "./policies.css";

const { Text, Title } = Typography;

const STATUS_COLOR: Record<ReviewRequestStatus, string> = {
  open: "blue",
  acknowledged: "cyan",
  actioned: "purple",
  dismissed: "default",
  withdrawn: "default",
};

export interface FeedbackTimelineProps {
  policySetKey: string;
  submittedBy: string;
  /** Bumped externally after a new submission, so the timeline re-fetches. */
  epoch?: number;
}

export function FeedbackTimeline({ policySetKey, submittedBy, epoch }: FeedbackTimelineProps) {
  const [items, setItems] = useState<PolicyReviewRequest[]>([]);
  const [loaded, setLoaded] = useState(false);

  const load = useCallback(() => {
    if (!policySetKey || !submittedBy) return;
    api
      .listReviewRequests({ policy_set_key: policySetKey, submitted_by: submittedBy })
      .then((records) => {
        setItems(records);
        setLoaded(true);
      })
      .catch(() => {
        setLoaded(true);
      });
  }, [policySetKey, submittedBy]);

  useEffect(() => {
    load();
  }, [load, epoch]);

  function handleWithdraw(id: string) {
    Modal.confirm({
      title: "Withdraw this feedback?",
      content: "The feedback will be removed and reviewers will no longer see it.",
      okText: "Withdraw",
      okType: "danger",
      onOk: async () => {
        try {
          await api.withdrawReviewRequest(id);
          message.success("Feedback withdrawn.");
          load();
        } catch (err) {
          if (err instanceof PolicyPlatformApiError && err.status === 409) {
            message.warning("This feedback can no longer be withdrawn — it may have been acknowledged.");
          } else if (err instanceof PolicyPlatformApiError && err.status === 404) {
            message.info("This feedback has already been removed.");
          } else {
            message.error("Could not withdraw feedback. Please try again.");
          }
          load();
        }
      },
    });
  }

  // Nothing to show and nothing loaded, or empty — stay quiet.
  if (!loaded || items.length === 0) return null;

  return (
    <div className="feedback-timeline" data-testid="feedback-timeline">
      <Title level={5}>Your feedback</Title>
      <Timeline
        items={items.map((item) => ({
          key: item.id,
          children: (
            <Space direction="vertical" size={2}>
              <Space size={8} wrap>
                <Tag color={STATUS_COLOR[item.status]}>{item.status}</Tag>
                <Text type="secondary">{new Date(item.submitted_at).toLocaleString()}</Text>
                {item.status === "open" && (
                  <Button type="link" size="small" onClick={() => handleWithdraw(item.id)} data-testid={`withdraw-${item.id}`}>
                    Withdraw
                  </Button>
                )}
              </Space>
              <Text>{item.comment}</Text>
              {item.categories && item.categories.length > 0 && (
                <Space size={4} wrap>
                  {item.categories.map((c) => (
                    <Tag key={c}>{c}</Tag>
                  ))}
                </Space>
              )}
              {item.resolution_note && (
                <Text type="secondary" italic>
                  Reviewer note: {item.resolution_note}
                </Text>
              )}
            </Space>
          ),
        }))}
      />
    </div>
  );
}
