import { Alert, Button, List, Modal, Space, Tag, Typography } from "antd";
import { ClusterOutlined } from "@ant-design/icons";
import type { FamilyGap } from "../ruleFamilyReview";

const { Text, Paragraph } = Typography;

/**
 * Asks the reviewer to confirm splitting a banded family before it happens.
 *
 * The point is not to block the action — leaving siblings for later is a
 * legitimate choice. The point is that until now the consequence was invisible:
 * the list showed the family relationship, but approving one member said
 * nothing about the others, so a reviewer could publish a decision with most of
 * its branches missing and find out only when an evaluation returned the wrong
 * answer.
 *
 * So this states the gap plainly and makes "review the whole family" the easy
 * path, with "just this one" still available and clearly labelled.
 */
export function FamilyReviewConfirm({
  open,
  gaps,
  decision,
  busy,
  onCancel,
  onProceedPartial,
  onProceedWholeFamily,
}: {
  open: boolean;
  gaps: FamilyGap[];
  decision: "approve" | "reject";
  busy?: boolean;
  onCancel: () => void;
  /** Continue with only what the reviewer originally selected. */
  onProceedPartial: () => void;
  /** Extend the action to every open member of the affected families. */
  onProceedWholeFamily: () => void;
}) {
  const verb = decision === "approve" ? "Approve" : "Reject";
  const leftTotal = gaps.reduce((n, g) => n + g.left.length, 0);
  const coveredTotal = gaps.reduce((n, g) => n + g.covered.length, 0);
  const wholeTotal = coveredTotal + leftTotal;

  return (
    <Modal
      open={open}
      onCancel={onCancel}
      title={
        <Space>
          <ClusterOutlined />
          <span>
            {gaps.length === 1 ? "This rule belongs to a family" : `This affects ${gaps.length} rule families`}
          </span>
        </Space>
      }
      width={640}
      footer={
        <Space wrap>
          <Button onClick={onCancel} disabled={busy}>
            Cancel
          </Button>
          <Button onClick={onProceedPartial} disabled={busy}>
            {verb} only the {coveredTotal} I selected
          </Button>
          <Button type="primary" onClick={onProceedWholeFamily} loading={busy}>
            {verb} all {wholeTotal} in {gaps.length === 1 ? "this family" : "these families"}
          </Button>
        </Space>
      }
    >
      <Alert
        type="warning"
        showIcon
        style={{ marginBottom: 16 }}
        message={
          leftTotal === 1
            ? "1 related rule would be left unreviewed"
            : `${leftTotal} related rules would be left unreviewed`
        }
        description={
          <Paragraph style={{ margin: 0, fontSize: 13 }}>
            These rules are variations of the same decision. {verb}ing part of a family publishes a
            decision with some of its branches missing — at evaluation time the approved branch
            answers on its own, and the gap shows up as a wrong result rather than as an error.
          </Paragraph>
        }
      />

      {gaps.map((gap) => (
        <div key={gap.key} style={{ marginBottom: 16 }}>
          <Space size={8} style={{ marginBottom: 6 }}>
            <Text strong style={{ fontSize: 13 }}>
              {gap.label}
            </Text>
            <Tag>
              {gap.covered.length} of {gap.total} selected
            </Tag>
          </Space>
          <List
            size="small"
            bordered
            dataSource={gap.left}
            renderItem={(item) => (
              <List.Item>
                <Space direction="vertical" size={0} style={{ width: "100%" }}>
                  <Text style={{ fontSize: 13 }}>{item.rule.title}</Text>
                  <Text type="secondary" style={{ fontSize: 11 }}>
                    {item.rule.rule_id} · rev {item.rule.rule_revision} · {item.review_status}
                  </Text>
                </Space>
              </List.Item>
            )}
          />
        </div>
      ))}
    </Modal>
  );
}
