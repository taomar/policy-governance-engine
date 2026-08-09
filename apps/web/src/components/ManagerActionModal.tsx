import { useState } from "react";
import { Alert, Button, Input, Modal, Radio, Space, Typography } from "antd";
import { SendOutlined, SafetyCertificateOutlined } from "@ant-design/icons";
import { api, PolicyPlatformApiError, type CandidateRule } from "../api";
import { useActor } from "../ActorContext";

const { TextArea } = Input;
const { Text, Paragraph } = Typography;

const REASON_CHIPS = [
  "Wording is unclear",
  "Threshold/amount looks wrong",
  "Missing an exception",
  "Conflicts with another rule",
  "Needs stronger source evidence",
  "Scope too broad/narrow",
];

/**
 * Manager-only actions on an approved-but-unpublished candidate: send it back
 * to the composer/reviewer for rework, or directly override the review
 * decision. Both require a mandatory reason (governance audit trail) and are
 * rejected server-side (403) unless the current actor's role is
 * "policy_manager" — see `_require_manager` in candidate_rules.py.
 */
export function ManagerActionModal({
  policySetKey,
  candidate,
  mode,
  onClose,
  onApplied,
}: {
  policySetKey: string;
  candidate: CandidateRule;
  mode: "request-changes" | "override-approve" | "override-reject";
  onClose: () => void;
  onApplied: () => void;
}) {
  const { actor } = useActor();
  const [reason, setReason] = useState("");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isOverride = mode !== "request-changes";
  const title = mode === "request-changes" ? "Send Back for Changes" : mode === "override-approve" ? "Override → Approve" : "Override → Reject";
  const icon = mode === "request-changes" ? <SendOutlined style={{ color: "#d97706" }} /> : <SafetyCertificateOutlined style={{ color: "#dc2626" }} />;

  const handleSubmit = async () => {
    setError(null);
    if (actor.role !== "policy_manager") {
      setError("Only the Policy Manager role can do this. Switch actor role first.");
      return;
    }
    if (!actor.name.trim()) {
      setError("Set your name in the actor switcher first.");
      return;
    }
    if (!reason.trim()) {
      setError("A reason is required — this is recorded on the audit trail.");
      return;
    }
    setBusy(true);
    try {
      if (mode === "request-changes") {
        await api.requestChanges(policySetKey, candidate.id, {
          manager: actor.name,
          actor_role: actor.role,
          reason,
          notes: notes.trim() || null,
        });
      } else {
        await api.overrideReview(policySetKey, candidate.id, {
          manager: actor.name,
          actor_role: actor.role,
          decision: mode === "override-approve" ? "approve" : "reject",
          reason,
          notes: notes.trim() || null,
        });
      }
      onApplied();
      onClose();
    } catch (err) {
      setError(err instanceof PolicyPlatformApiError ? err.detail : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      title={
        <Space>
          {icon}
          <span>
            {title} — {candidate.rule.rule_id}
          </span>
        </Space>
      }
      open
      onCancel={onClose}
      width={560}
      footer={[
        <Button key="cancel" onClick={onClose}>
          Cancel
        </Button>,
        <Button key="submit" type="primary" danger={isOverride} onClick={handleSubmit} loading={busy}>
          {busy ? "Submitting…" : title}
        </Button>,
      ]}
    >
      {error && <Alert type="error" showIcon message={error} style={{ marginBottom: 16 }} />}

      <Paragraph type="secondary">
        {mode === "request-changes"
          ? "This candidate is approved but not yet published. Sending it back reopens it for editing and re-review — nothing published is affected."
          : "This directly forces the review decision, bypassing the normal composer/reviewer step. Use for a documented correction, not routine review."}
      </Paragraph>

      <Text strong>Reason (required)</Text>
      <Space size={[6, 6]} wrap style={{ margin: "8px 0" }}>
        {REASON_CHIPS.map((chip) => (
          <Radio.Button key={chip} checked={reason === chip} onClick={() => setReason(chip)} className="manager-reason-choice">
            {chip}
          </Radio.Button>
        ))}
      </Space>
      <Input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Or type a specific reason…" style={{ marginBottom: 16 }} />

      <Text strong>Additional notes (optional)</Text>
      <TextArea rows={3} value={notes} onChange={(e) => setNotes(e.target.value)} style={{ marginTop: 8 }} />
    </Modal>
  );
}
