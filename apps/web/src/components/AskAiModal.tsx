import { useState } from "react";
import { Alert, Button, Collapse, Input, Modal, Space, Tag, Typography } from "antd";
import { BulbOutlined, FileTextOutlined, RobotOutlined, SendOutlined, ThunderboltOutlined } from "@ant-design/icons";
import { type ChatTurn } from "../api";
import {
  ASK_ANSWER_LANGUAGES,
  DEFAULT_ASK_ANSWER_LANGUAGE,
  fillCounts,
  type AskAnswerLanguage,
  type AskScopeKind,
} from "../askAnswerLanguage";
import { type AskInLanguageResponse } from "../askInLanguage";
import { describeApiFailure } from "../loadState";
import { AnswerLanguageToggle } from "./AnswerLanguageToggle";
import { DirectionalText } from "./DirectionalText";

const { Text, Paragraph } = Typography;

/** What one exchange in this dialog turned into.
 *
 * `empty` and `failed` are separate on purpose: one is an answer that held
 * nothing, the other is a request that never produced one. A reader can act on
 * the second by sending it again and cannot act on the first that way, so
 * collapsing them would have people pressing a button that will decline again
 * for the same reason. */
type Turn =
  | { role: "user"; content: string }
  | {
      role: "assistant";
      kind: "answer";
      content: string;
      result: AskInLanguageResponse;
      language: AskAnswerLanguage;
    }
  | { role: "assistant"; kind: "empty"; content: string; language: AskAnswerLanguage }
  | {
      role: "assistant";
      kind: "failed";
      content: string;
      detail: string;
      question: string;
      language: AskAnswerLanguage;
    };

/** Everything the dialog needs that is not the same for every subject. */
export interface AskAiModalProps {
  /** Whether this was opened about one rule or one whole policy. Selects the
   *  copy; never branched on anywhere else in this file. */
  scope: AskScopeKind;
  /** The subject's own identifier, appended to the heading unchanged. Data, not
   *  language — a rule id or a policy heading is not this app's to reword. */
  subjectLabel: string;
  /** Whether the grounding reaches past the one thing in the title: a rule's
   *  variation group, a policy stated across more than one passage. */
  wider: boolean;
  /** Sends the question. Given rather than built here, so this dialog holds no
   *  knowledge of which endpoint, which ids or which scope it is serving. */
  ask: (args: {
    question: string;
    history: ChatTurn[];
    answerLanguage: string;
  }) => Promise<AskInLanguageResponse>;
  onClose: () => void;
}

/**
 * The Ask-AI dialog, for one rule or one whole policy.
 *
 * TWO KINDS OF CONTENT, AND ONLY ONE OF THEM IS OURS
 *
 * An answer arrives in two halves and they are not interchangeable. The quoted
 * facts are the document's own words, copied character-for-character. The
 * reflection, and the topic headings over the groups, are this app's writing.
 * The language control moves the second and never the first: a reviewer
 * approves a rule against the source, so a translated quotation would let them
 * approve a paraphrase while believing they had read the document. The two are
 * therefore rendered under separate headings that say which is which, in the
 * `✦ … by this app` treatment the generated subject label established, and the
 * dialog states in words that quoted text stays in the language it was written
 * in. That boundary matters more at policy scope, not less: a policy-wide answer
 * quotes more of the document, so there is more of it to get wrong.
 *
 * WHY THE CHOICE IS NOT REMEMBERED BETWEEN OPENINGS
 *
 * It lives in this component and dies with it. The request was for a choice in
 * this window; a stored preference is a different thing — it outlives the
 * window, follows the reviewer onto other rules and other projects, and would
 * have someone open a rule they never chose a language for and find the chrome
 * around the document's words in it. The transcript already resets on close for
 * that reason, so the language resetting with it is one rule applied twice
 * rather than two behaviours.
 *
 * DIRECTION IS NEVER SET ON THIS DIALOG
 *
 * Not once, and no `dir` appears below. An answer in one language routinely
 * carries a rule id, a Latin identifier or a quoted clause from another, and a
 * dialog-level direction lays those runs out backwards. Every passage goes
 * through `DirectionalText`, which decides direction per run from the
 * characters themselves and alters none of them.
 *
 * WHY THE CLASS AND TEST-ID PREFIX STILL SAYS `ask-rule`
 *
 * It names this dialog, not the scope, and it predates the second scope. The
 * rename is cosmetic and would touch a stylesheet three other changes are
 * sitting in this week. `data-ask-scope` on the dialog says which scope is open,
 * which is the thing a test actually needs to tell them apart.
 */
export function AskAiModal({ scope, subjectLabel, wider, ask, onClose }: AskAiModalProps) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [question, setQuestion] = useState("");
  const [asking, setAsking] = useState(false);
  const [language, setLanguage] = useState<AskAnswerLanguage>(DEFAULT_ASK_ANSWER_LANGUAGE);
  const copy = language.copy;
  const scopeCopy = copy.scopes[scope];

  const handleAsk = async (q?: string) => {
    const text = (q ?? question).trim();
    if (!text || asking) return;
    if (!q) setQuestion("");
    // The language each answer was asked in travels with it, chrome and all. A
    // later toggle moves what is asked next; it never relabels — or rewrites —
    // an answer already on screen.
    const askedIn = language;
    const history: ChatTurn[] = turns.map(({ role, content }) => ({ role, content }));
    setTurns((prev) => [...prev, { role: "user", content: text }]);
    setAsking(true);
    try {
      const result = await ask({ question: text, history, answerLanguage: askedIn.tag });
      const flat = result.groups.flatMap((g) => g.facts.map((f) => f.text)).join(" ") || result.reflection;
      setTurns((prev) => [
        ...prev,
        flat
          ? { role: "assistant", kind: "answer", content: flat, result, language: askedIn }
          : { role: "assistant", kind: "empty", content: "", language: askedIn },
      ]);
    } catch (err) {
      const detail = describeApiFailure(err);
      setTurns((prev) => [
        ...prev,
        { role: "assistant", kind: "failed", content: detail, detail, question: text, language: askedIn },
      ]);
    } finally {
      setAsking(false);
    }
  };

  return (
    <Modal
      title={
        <div className="ask-rule-header">
          <Space>
            <ThunderboltOutlined style={{ color: "#5b4db1" }} />
            {/* The subject's own identifier is data, not language: it is
                appended to the heading unchanged and laid out as its own run. */}
            <DirectionalText>{`${scopeCopy.titlePrefix} ${subjectLabel}`}</DirectionalText>
          </Space>
          <AnswerLanguageToggle
            languages={ASK_ANSWER_LANGUAGES}
            value={language}
            onChange={setLanguage}
            label={copy.languageChoiceLabel}
            scopeNote={copy.languageScopeNote}
          />
        </div>
      }
      open
      onCancel={onClose}
      width={680}
      footer={null}
      rootClassName="ask-rule-modal"
      data-ask-scope={scope}
    >
      <Paragraph type="secondary" className="modal-intro" lang={language.tag}>
        <DirectionalText align>
          {wider ? scopeCopy.groundingNoteWider : scopeCopy.groundingNote}
        </DirectionalText>
      </Paragraph>

      {turns.length === 0 && (
        <Space size={[8, 8]} wrap style={{ marginBottom: 16 }} data-testid="ask-rule-suggestions">
          {scopeCopy.suggestions.map((q) => (
            <Tag
              key={q}
              className="ask-rule-suggestion"
              onClick={() => handleAsk(q)}
              style={{ cursor: "pointer" }}
              lang={language.tag}
            >
              <DirectionalText>{q}</DirectionalText>
            </Tag>
          ))}
        </Space>
      )}

      <div className="ask-rule-messages">
        {turns.map((t, i) => (
          <div
            key={i}
            className={`ask-ai-msg ask-ai-msg-${t.role} ${
              t.role === "assistant" && t.kind === "failed" ? "ask-ai-msg-error" : ""
            }`}
            style={{ marginBottom: 12 }}
          >
            {t.role === "user" ? (
              <Text strong>
                <DirectionalText>{t.content}</DirectionalText>
              </Text>
            ) : t.kind === "failed" ? (
              <Alert
                type="warning"
                showIcon
                data-testid="ask-rule-failed"
                message={<span lang={t.language.tag}>{t.language.copy.failedHeading}</span>}
                description={
                  <>
                    <p>
                      <DirectionalText>{t.detail}</DirectionalText>
                    </p>
                    <Button size="small" onClick={() => void handleAsk(t.question)} lang={t.language.tag}>
                      {t.language.copy.retryLabel}
                    </Button>
                  </>
                }
              />
            ) : t.kind === "empty" ? (
              <Alert
                type="info"
                showIcon
                data-testid="ask-rule-empty"
                message={
                  <span lang={t.language.tag}>
                    <DirectionalText>{t.language.copy.emptyAnswerNote}</DirectionalText>
                  </span>
                }
              />
            ) : (
              <div className="ask-ai-structured">
                {/* Said before the answer, not after it. A reader who learns
                    halfway down that they were reading a partial grounding has
                    already read it as a whole one. */}
                {t.result.grounding && !t.result.grounding.covers_every_rule && (
                  <Alert
                    type="info"
                    showIcon
                    className="ask-rule-coverage"
                    data-testid="ask-rule-coverage"
                    message={
                      <span lang={t.language.tag}>
                        <DirectionalText align>
                          {fillCounts(t.language.copy.coverageNote, {
                            covered: t.result.grounding.covered_rule_count,
                            total: t.result.grounding.rule_count,
                          })}
                        </DirectionalText>
                      </span>
                    }
                  />
                )}
                {t.result.groups.length > 0 && (
                  <section className="ask-rule-quoted" data-testid="ask-rule-quoted">
                    <p className="ask-rule-quoted__heading" lang={t.language.tag}>
                      <DirectionalText>{t.language.copy.quotedHeading}</DirectionalText>
                    </p>
                    <p className="ask-rule-quoted__note" lang={t.language.tag}>
                      <Text type="secondary">
                        <DirectionalText>{t.language.copy.quotedStaysNote}</DirectionalText>
                      </Text>
                    </p>
                    <Collapse
                      ghost
                      size="small"
                      defaultActiveKey={t.result.groups.map((_, gi) => `g${gi}`)}
                      items={t.result.groups.map((g, gi) => ({
                        key: `g${gi}`,
                        label: (
                          <Text strong lang={t.language.tag}>
                            <DirectionalText>{g.heading}</DirectionalText>
                          </Text>
                        ),
                        children: (
                          <ul className="ask-ai-fact-list">
                            {g.facts.map((f, fi) => (
                              <li key={fi} className="ask-ai-fact-item">
                                {/* No `lang` here, and there never can be one:
                                    this is the document's language, which this
                                    app does not know and must not assert. */}
                                <div className="ask-ai-fact-text" data-testid="ask-rule-fact">
                                  <DirectionalText align>{f.text}</DirectionalText>
                                </div>
                                {f.source_label && (
                                  <div className="ask-ai-fact-source" data-testid="ask-rule-fact-source">
                                    <DirectionalText>{f.source_label}</DirectionalText>
                                  </div>
                                )}
                              </li>
                            ))}
                          </ul>
                        ),
                      }))}
                    />
                  </section>
                )}
                {t.result.reflection && (
                  <section
                    className="ask-ai-reflection"
                    data-generated="true"
                    data-testid="ask-rule-reflection"
                    lang={t.language.tag}
                  >
                    <div className="ask-ai-reflection-label">
                      <span className="ask-rule-reflection__mark" aria-hidden>
                        ✦
                      </span>{" "}
                      <BulbOutlined /> <DirectionalText>{t.language.copy.writtenByAppLabel}</DirectionalText>
                    </div>
                    <Paragraph className="ask-ai-reflection-text">
                      <DirectionalText align>{t.result.reflection}</DirectionalText>
                    </Paragraph>
                  </section>
                )}
                {t.result.sources.length > 0 && (
                  <div className="ask-rule-sources">
                    <Text type="secondary" lang={t.language.tag}>
                      <DirectionalText>{t.language.copy.retrievedFromLabel}</DirectionalText>
                    </Text>{" "}
                    <Space size={[4, 4]} wrap style={{ marginTop: 8 }}>
                      {t.result.sources.map((s, si) => (
                        <Tag key={si} icon={<FileTextOutlined />}>
                          <DirectionalText>
                            {`${s.heading ?? ""}${s.section ? ` · ${s.section}` : ""}`.trim()}
                          </DirectionalText>
                        </Tag>
                      ))}
                    </Space>
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
        {asking && (
          <Space data-testid="ask-rule-thinking">
            <RobotOutlined />
            <Text type="secondary" lang={language.tag}>
              <DirectionalText>{copy.thinkingLabel}</DirectionalText>
            </Text>
          </Space>
        )}
      </div>

      <Space.Compact style={{ width: "100%", marginTop: 12 }}>
        <Input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onPressEnter={() => handleAsk()}
          placeholder={scopeCopy.followUpPlaceholder}
          lang={language.tag}
          disabled={asking}
        />
        <Button
          type="primary"
          icon={<SendOutlined />}
          onClick={() => handleAsk()}
          disabled={asking || !question.trim()}
          lang={language.tag}
        >
          {copy.askLabel}
        </Button>
      </Space.Compact>
    </Modal>
  );
}
