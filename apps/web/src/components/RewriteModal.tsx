import { useState } from "react";
import { Alert, Button, Col, Input, Modal, Row, Space, Typography } from "antd";
import { ThunderboltOutlined } from "@ant-design/icons";
import { aiApi, PolicyPlatformApiError, type CandidateRule } from "../api";
import { RuleCard } from "./RuleCard";

const { Text, Paragraph } = Typography;

/**
 * "Suggest Rewrite" modal — lets a policy administrator describe, in plain
 * English, how a candidate rule should change (e.g. "make the response time
 * 15 minutes instead of 30" or "clarify which manager must approve this").
 * The AI proposes a full rewritten rule; the admin reviews a before/after
 * comparison and only the *current* candidate rule is replaced once they
 * explicitly apply it — nothing is silently overwritten.
 */
export function RewriteModal({
  candidate,
  onClose,
  onApplied,
}: {
  candidate: CandidateRule;
  onClose: () => void;
  onApplied: () => void;
}) {
  const [instruction, setInstruction] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [suggestion, setSuggestion] = useState<{ suggested: CandidateRule["rule"]; explanation: string } | null>(null);
  const [applying, setApplying] = useState(false);

  const handleSuggest = async () => {
    if (!instruction.trim()) return;
    setLoading(true);
    setError(null);
    setSuggestion(null);
    try {
      const result = await aiApi.suggestRewrite(candidate.id, instruction);
      setSuggestion({ suggested: result.suggested, explanation: result.explanation });
    } catch (err) {
      setError(err instanceof PolicyPlatformApiError ? err.detail : String(err));
    } finally {
      setLoading(false);
    }
  };

  const handleApply = async () => {
    if (!suggestion) return;
    setApplying(true);
    setError(null);
    try {
      await aiApi.applyRewrite(candidate.id, suggestion.suggested as unknown as Record<string, unknown>);
      onApplied();
      onClose();
    } catch (err) {
      setError(err instanceof PolicyPlatformApiError ? err.detail : String(err));
    } finally {
      setApplying(false);
    }
  };

  return (
    <Modal
      title={
        <Space>
          <ThunderboltOutlined style={{ color: "#7c3aed" }} />
          <span>Suggest Rewrite — {candidate.rule.rule_id}</span>
        </Space>
      }
      open
      onCancel={onClose}
      width={880}
      footer={
        suggestion
          ? [
              <Button key="discard" onClick={onClose}>
                Discard
              </Button>,
              <Button key="apply" type="primary" onClick={handleApply} loading={applying}>
                {applying ? "Applying…" : "Apply Rewrite"}
              </Button>,
            ]
          : null
      }
    >
      <Space.Compact style={{ width: "100%", marginBottom: 16 }}>
        <Input
          value={instruction}
          onChange={(e) => setInstruction(e.target.value)}
          placeholder="e.g. Change the response time to 15 minutes and clarify which team owns this"
          disabled={loading}
          onPressEnter={handleSuggest}
        />
        <Button type="primary" onClick={handleSuggest} loading={loading} disabled={!instruction.trim()}>
          {loading ? "Thinking…" : "Suggest Rewrite"}
        </Button>
      </Space.Compact>

      {error && <Alert type="error" showIcon message={error} style={{ marginBottom: 16 }} />}

      {suggestion && (
        <>
          <Alert
            type="info"
            showIcon
            message={
              <>
                <strong>What changed:</strong> {suggestion.explanation}
              </>
            }
            style={{ marginBottom: 16 }}
          />
          <Row gutter={16}>
            <Col span={12}>
              <Paragraph type="secondary" style={{ marginBottom: 6 }}>
                <Text strong>Current</Text>
              </Paragraph>
              <RuleCard rule={candidate.rule} defaultExpanded />
            </Col>
            <Col span={12}>
              <Paragraph type="secondary" style={{ marginBottom: 6 }}>
                <Text strong>Suggested</Text>
              </Paragraph>
              <RuleCard rule={suggestion.suggested} defaultExpanded />
            </Col>
          </Row>
        </>
      )}
    </Modal>
  );
}
