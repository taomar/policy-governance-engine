import { useState } from "react";
import { Button, Collapse, Input, Modal, Space, Tag, Typography } from "antd";
import { BulbOutlined, FileTextOutlined, RobotOutlined, SendOutlined, ThunderboltOutlined } from "@ant-design/icons";
import { aiApi, PolicyPlatformApiError, type AskResponse, type CandidateRule, type ChatTurn } from "../api";

const { Text, Paragraph } = Typography;

const SUGGESTED_QUESTIONS = [
  "Explain this rule in plain English",
  "Does this conflict with any other rule?",
  "What happens if a required fact is missing?",
  "Summarize the exceptions in one sentence",
];

/**
 * Focused "Ask AI about this rule" — pins the exact candidate rule's content
 * (plus any sibling rules sharing its variation group) as priority context,
 * so a reviewer/manager can ask "does this conflict with X?" or "explain this
 * in plain English" without leaving the review queue. Distinct from the
 * global Ask AI drawer (which is unscoped) — this is scoped to one rule by
 * design, so it's kept as a lightweight self-contained modal rather than
 * threading focus state through the global drawer.
 */
export function AskAboutRuleModal({ candidate, onClose }: { candidate: CandidateRule; onClose: () => void }) {
  const [turns, setTurns] = useState<{ role: "user" | "assistant"; content: string; result?: AskResponse; error?: boolean }[]>([]);
  const [question, setQuestion] = useState("");
  const [asking, setAsking] = useState(false);

  const handleAsk = async (q?: string) => {
    const text = (q ?? question).trim();
    if (!text || asking) return;
    setQuestion("");
    const history: ChatTurn[] = turns.map(({ role, content }) => ({ role, content }));
    setTurns((prev) => [...prev, { role: "user", content: text }]);
    setAsking(true);
    try {
      const result = await aiApi.ask(text, candidate.policy_set_id, history, candidate.id);
      const flat =
        result.groups.flatMap((g) => g.facts.map((f) => f.text)).join(" ") || result.reflection || "(no answer)";
      setTurns((prev) => [...prev, { role: "assistant", content: flat, result }]);
    } catch (err) {
      const detail = err instanceof PolicyPlatformApiError ? err.detail : String(err);
      setTurns((prev) => [...prev, { role: "assistant", content: `Error: ${detail}`, error: true }]);
    } finally {
      setAsking(false);
    }
  };

  return (
    <Modal
      title={
        <Space>
          <ThunderboltOutlined style={{ color: "#7c3aed" }} />
          <span>Ask AI about {candidate.rule.rule_id}</span>
        </Space>
      }
      open
      onCancel={onClose}
      width={680}
      footer={null}
    >
      <Paragraph type="secondary" style={{ marginTop: -8 }}>
        Grounded specifically in this rule{candidate.rule.group_label ? " and its variation group" : ""} — verbatim
        facts, plus a separate AI reflection.
      </Paragraph>

      {turns.length === 0 && (
        <Space size={[8, 8]} wrap style={{ marginBottom: 16 }}>
          {SUGGESTED_QUESTIONS.map((q) => (
            <Tag key={q} className="ask-rule-suggestion" onClick={() => handleAsk(q)} style={{ cursor: "pointer" }}>
              {q}
            </Tag>
          ))}
        </Space>
      )}

      <div className="ask-rule-messages">
        {turns.map((t, i) => (
          <div key={i} className={`ask-ai-msg ask-ai-msg-${t.role} ${t.error ? "ask-ai-msg-error" : ""}`} style={{ marginBottom: 12 }}>
            {t.role === "user" ? (
              <Text strong>{t.content}</Text>
            ) : t.result && (t.result.groups.length > 0 || t.result.reflection) ? (
              <div className="ask-ai-structured">
                {t.result.groups.length > 0 && (
                  <Collapse
                    ghost
                    size="small"
                    defaultActiveKey={t.result.groups.map((_, gi) => `g${gi}`)}
                    items={t.result.groups.map((g, gi) => ({
                      key: `g${gi}`,
                      label: <Text strong>{g.heading}</Text>,
                      children: (
                        <ul className="ask-ai-fact-list">
                          {g.facts.map((f, fi) => (
                            <li key={fi} className="ask-ai-fact-item">
                              <div className="ask-ai-fact-text">{f.text}</div>
                              {f.source_label && <div className="ask-ai-fact-source">Source: {f.source_label}</div>}
                            </li>
                          ))}
                        </ul>
                      ),
                    }))}
                  />
                )}
                {t.result.reflection && (
                  <div className="ask-ai-reflection">
                    <div className="ask-ai-reflection-label">
                      <BulbOutlined /> AI reflection
                    </div>
                    <Paragraph className="ask-ai-reflection-text">{t.result.reflection}</Paragraph>
                  </div>
                )}
                {t.result.sources.length > 0 && (
                  <Space size={[4, 4]} wrap style={{ marginTop: 8 }}>
                    {t.result.sources.map((s, si) => (
                      <Tag key={si} icon={<FileTextOutlined />}>
                        {s.heading ?? "Document"}
                        {s.section ? ` · ${s.section}` : ""}
                      </Tag>
                    ))}
                  </Space>
                )}
              </div>
            ) : (
              <Text type={t.error ? "danger" : undefined}>{t.content}</Text>
            )}
          </div>
        ))}
        {asking && (
          <Space>
            <RobotOutlined />
            <Text type="secondary">Thinking…</Text>
          </Space>
        )}
      </div>

      <Space.Compact style={{ width: "100%", marginTop: 12 }}>
        <Input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onPressEnter={() => handleAsk()}
          placeholder="Ask a follow-up about this rule…"
          disabled={asking}
        />
        <Button type="primary" icon={<SendOutlined />} onClick={() => handleAsk()} disabled={asking || !question.trim()}>
          Ask
        </Button>
      </Space.Compact>
    </Modal>
  );
}
