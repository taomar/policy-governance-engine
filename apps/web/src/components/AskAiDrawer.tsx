import { useEffect, useRef, useState } from "react";
import { Avatar, Button, Collapse, Drawer, Input, Select, Space, Tag, Typography } from "antd";
import {
  BulbOutlined,
  ExpandOutlined,
  FileTextOutlined,
  RobotOutlined,
  SendOutlined,
  ShrinkOutlined,
  ThunderboltOutlined,
  UserOutlined,
} from "@ant-design/icons";
import {
  aiApi,
  PolicyPlatformApiError,
  type AskGroup,
  type AskResponse,
  type AskSource,
  type ChatTurn,
  type PolicySet,
} from "../api";

const { Text, Paragraph } = Typography;

interface DisplayTurn extends ChatTurn {
  groups?: AskGroup[];
  reflection?: string;
  sources?: AskSource[];
  error?: boolean;
}

/** Flatten a structured Ask-AI answer into plain text for conversation-history
 * continuity (the backend only needs prior turns as plain strings — the
 * grouped/reflection structure is a display concern, not a chat-context one). */
function flattenAskResult(result: AskResponse): string {
  const parts: string[] = [];
  for (const g of result.groups) {
    parts.push(`${g.heading}:`);
    for (const f of g.facts) {
      parts.push(`- ${f.text}${f.source_label ? ` (Source: ${f.source_label})` : ""}`);
    }
  }
  if (result.reflection) parts.push(result.reflection);
  return parts.join("\n") || "(no relevant policy text found)";
}

/**
 * Global "Ask AI" side drawer — grounded chat over the user's own uploaded
 * documents + approved rules for a chosen policy set. This is the "ask in
 * chat on the side for a specific thing" tool the policy administrator
 * needs while working anywhere in the app, not just on one page.
 *
 * Answers are structured deterministically: verbatim source facts grouped by
 * topic (never reworded — copied exactly from the original document/rule),
 * kept separate from a distinct "AI reflection" section where the model may
 * synthesize, compare, or directly address what was asked.
 */
export function AskAiDrawer({
  open,
  onClose,
  policySets,
  initialPolicySetKey,
}: {
  open: boolean;
  onClose: () => void;
  policySets: PolicySet[];
  /** When the user opens Ask AI while inside a specific project, pre-scope the conversation
   * to that project as soon as the drawer opens. The user can still broaden/narrow scope
   * afterward via the picker below — this only seeds the starting point. */
  initialPolicySetKey?: string;
}) {
  const [policySetKey, setPolicySetKey] = useState<string>("");
  const [turns, setTurns] = useState<DisplayTurn[]>([]);
  const [question, setQuestion] = useState("");
  const [asking, setAsking] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Contextual scoping: every time the drawer opens (or the embedding project context
  // changes while it's open), re-seed the scope to the current project. After that the
  // user is free to change it via the picker without being overridden.
  useEffect(() => {
    if (open && initialPolicySetKey) setPolicySetKey(initialPolicySetKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, initialPolicySetKey]);

  // Global fallback: with no project context, default to the first available policy set
  // once the list has loaded (unchanged from prior behavior).
  useEffect(() => {
    if (!initialPolicySetKey && policySets.length > 0 && !policySetKey) setPolicySetKey(policySets[0].key);
  }, [policySets, policySetKey, initialPolicySetKey]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [turns, open]);

  const handleAsk = async () => {
    const q = question.trim();
    if (!q || asking) return;
    setQuestion("");
    const history = turns.map(({ role, content }) => ({ role, content }));
    setTurns((prev) => [...prev, { role: "user", content: q }]);
    setAsking(true);
    try {
      const result = await aiApi.ask(q, policySetKey || undefined, history);
      setTurns((prev) => [
        ...prev,
        {
          role: "assistant",
          content: flattenAskResult(result),
          groups: result.groups,
          reflection: result.reflection,
          sources: result.sources,
        },
      ]);
    } catch (err) {
      const detail = err instanceof PolicyPlatformApiError ? err.detail : String(err);
      setTurns((prev) => [...prev, { role: "assistant", content: `Error: ${detail}`, error: true }]);
    } finally {
      setAsking(false);
    }
  };

  return (
    <Drawer
      title={
        <Space>
          <ThunderboltOutlined style={{ color: "#5b4db1" }} />
          <span>Ask AI</span>
        </Space>
      }
      placement="right"
      size={expanded ? 720 : 440}
      open={open}
      onClose={onClose}
      className="ask-ai-drawer"
      extra={
        <Space size={8}>
          <Select
            size="small"
            value={policySetKey}
            onChange={setPolicySetKey}
            style={{ width: 170 }}
            placeholder="All policy sets"
            allowClear
            options={policySets.map((ps) => ({ value: ps.key, label: ps.name }))}
          />
          <Button
            size="small"
            icon={expanded ? <ShrinkOutlined /> : <ExpandOutlined />}
            onClick={() => setExpanded((v) => !v)}
            title={expanded ? "Collapse panel" : "Expand panel"}
            aria-label={expanded ? "Collapse Ask AI panel" : "Expand Ask AI panel"}
          />
        </Space>
      }
      styles={{ body: { display: "flex", flexDirection: "column", padding: 0 } }}
    >
      <Paragraph type="secondary" className="ask-ai-subtitle">
        Grounded in your uploaded documents &amp; approved rules — quoted facts are always verbatim from source
      </Paragraph>

      <div className="ask-ai-messages" ref={scrollRef}>
        {turns.length === 0 && (
          <div className="ask-ai-empty">
            <Text type="secondary">
              Ask about anything in your policies — e.g. "What does the handbook say about annual leave?" or "What
              confidentiality duties apply to employees?" Answers group verbatim source facts by topic, plus a separate
              AI reflection for direct synthesis and analysis.
            </Text>
          </div>
        )}
        {turns.map((t, i) => (
          <div key={i} className={`ask-ai-msg ask-ai-msg-${t.role} ${t.error ? "ask-ai-msg-error" : ""}`}>
            <Avatar
              size={26}
              icon={t.role === "user" ? <UserOutlined /> : <RobotOutlined />}
              className={t.role === "user" ? "ask-ai-avatar-user" : "ask-ai-avatar-ai"}
            />
            <div className="ask-ai-msg-content">
              {t.role === "assistant" && !t.error && ((t.groups && t.groups.length > 0) || t.reflection) ? (
                <div className="ask-ai-structured">
                  {t.groups && t.groups.length > 0 && (
                    <Collapse
                      ghost
                      className="ask-ai-fact-groups"
                      defaultActiveKey={t.groups.map((_, gi) => `g${gi}`)}
                      items={t.groups.map((g, gi) => ({
                        key: `g${gi}`,
                        label: (
                          <Text strong className="ask-ai-group-heading">
                            {g.heading}
                          </Text>
                        ),
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
                  {t.reflection && (
                    <div className="ask-ai-reflection">
                      <div className="ask-ai-reflection-label">
                        <BulbOutlined /> AI reflection
                      </div>
                      <Paragraph className="ask-ai-reflection-text">{t.reflection}</Paragraph>
                    </div>
                  )}
                </div>
              ) : (
                <div className="ask-ai-msg-bubble">{t.content}</div>
              )}
              {t.sources && t.sources.length > 0 && (
                <div className="ask-ai-sources">
                  <Text type="secondary" className="ask-ai-sources-label">
                    Retrieved from:
                  </Text>
                  {t.sources.map((s, si) => (
                    <Tag key={si} icon={<FileTextOutlined />} className="ask-ai-source-chip" title={s.clause_id ?? undefined}>
                      {s.heading ?? "Document"}
                      {s.section ? ` · ${s.section}` : ""}
                    </Tag>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}
        {asking && (
          <div className="ask-ai-msg ask-ai-msg-assistant">
            <Avatar size={26} icon={<RobotOutlined />} className="ask-ai-avatar-ai" />
            <div className="ask-ai-msg-content">
              <div className="ask-ai-msg-bubble ask-ai-thinking">Thinking…</div>
            </div>
          </div>
        )}
      </div>

      <div className="ask-ai-input-row">
        <Input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onPressEnter={handleAsk}
          placeholder="Ask about a policy…"
          disabled={asking}
        />
        <Button
          type="primary"
          icon={<SendOutlined />}
          onClick={handleAsk}
          disabled={asking || !question.trim()}
          aria-label="Send Ask AI question"
        />
      </div>
    </Drawer>
  );
}
