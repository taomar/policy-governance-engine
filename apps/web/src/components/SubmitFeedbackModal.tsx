/**
 * Modal for a viewer to submit feedback on a published policy.
 *
 * The modal's primary job — besides collecting the comment — is to reassure
 * the reader that submitting will not take the policy out of service. The
 * backend guarantees this structurally (the feedback record shares no column
 * with the policy), but a viewer who does not know that needs the promise
 * stated in words, before and after.
 */

import { useState } from "react";
import { Alert, Input, message, Modal, Select } from "antd";
import { api, FEEDBACK_CATEGORIES, type PolicyReviewRequest } from "../api";

const { TextArea } = Input;

export interface SubmitFeedbackModalProps {
  open: boolean;
  policySetKey: string;
  approvedPolicyVersionId: string;
  submittedBy: string;
  onClose: () => void;
  onSubmitted: (record: PolicyReviewRequest) => void;
}

export function SubmitFeedbackModal({
  open,
  policySetKey,
  approvedPolicyVersionId,
  submittedBy,
  onClose,
  onSubmitted,
}: SubmitFeedbackModalProps) {
  const [comment, setComment] = useState("");
  const [categories, setCategories] = useState<string[]>([]);
  const [submitting, setSubmitting] = useState(false);

  const canSubmit = comment.trim().length > 0;

  async function handleSubmit() {
    if (!canSubmit) return;
    setSubmitting(true);
    try {
      const record = await api.createReviewRequest({
        policy_set_key: policySetKey,
        approved_policy_version_id: approvedPolicyVersionId,
        comment: comment.trim(),
        categories: categories.length > 0 ? categories : undefined,
        submitted_by: submittedBy,
      });
      message.success("Feedback submitted. The policy is unchanged and remains in force.");
      setComment("");
      setCategories([]);
      onSubmitted(record);
    } catch {
      message.error("Could not submit feedback. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  function handleCancel() {
    setComment("");
    setCategories([]);
    onClose();
  }

  return (
    <Modal
      open={open}
      title="Submit Feedback for Review"
      okText="Submit"
      cancelText="Cancel"
      onOk={handleSubmit}
      onCancel={handleCancel}
      okButtonProps={{ disabled: !canSubmit, loading: submitting }}
      destroyOnClose
    >
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        message="This policy remains current and in force."
        description="Your feedback will be sent to a reviewer — it does not change the policy's status or take it out of service."
      />

      <TextArea
        rows={4}
        value={comment}
        onChange={(e) => setComment(e.target.value)}
        placeholder="Describe what should change and why."
        style={{ marginBottom: 12 }}
        data-testid="feedback-comment"
      />

      <Select
        mode="tags"
        style={{ width: "100%" }}
        placeholder="Categories (optional)"
        value={categories}
        onChange={setCategories}
        options={FEEDBACK_CATEGORIES.map((c) => ({ value: c, label: c }))}
        data-testid="feedback-categories"
      />
    </Modal>
  );
}
