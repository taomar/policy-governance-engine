import { Button, Space, Tabs, Tag, Tooltip, Typography } from "antd";
import { useState } from "react";
import {
  CheckOutlined,
  CloseOutlined,
  CodeOutlined,
  DownOutlined,
  RightOutlined,
} from "@ant-design/icons";
import type { PolicyCard } from "../policyCards";
import {
  passagePageLabel,
  passageQuotations,
  passageTitle,
  policyJsonDocument,
  policyTitle,
} from "../policyCards";
import { policyRouteLabel, policyRuleCountLabel } from "../policyGrouping";
import {
  effectActionText,
  isEmptyCondition,
  ruleDecisionSummary,
} from "../ruleDisplay";
import { ruleTypeLabel } from "../ruleTypes";
import { ConditionView } from "./ConditionView";
import { DirectionalText } from "./DirectionalText";
import { JsonView } from "./JsonView";
import { PolicyEffectBadge } from "./PolicyEffectBadge";
import { PolicyLogicTable } from "./PolicyLogicTable";

const { Text, Title } = Typography;

/**
 * The detail of one policy: its passages once each, its rules in full, one JSON.
 *
 * WHY ONE DOCUMENT AND NOT N
 *
 * The reviewer's question is "is this how contract start dates work". Three
 * JSON documents cannot answer it, because the answer is the relationship
 * between them — a default and the cases that depart from it. So the panel
 * serialises the policy, with its passages and their rules nested inside it,
 * and downloads as one file.
 *
 * The per-rule canonical JSON has not gone anywhere: opening a rule from here
 * swaps this panel for the rule inspector, which still offers evaluator,
 * canonical and DMN forms of that one rule. It is a drill-down, in the same
 * panel — never a second panel — so the reviewer is never handed three
 * documents where the source stated one policy.
 *
 * WHAT THE SOURCE SAYS IS PER PASSAGE
 *
 * A section is stated across several sentences, and running them together as
 * one block of prose would put words next to each other that the document never
 * did. Each passage is quoted under its own element, in document order, and
 * within a passage each distinct statement is its own block for the same
 * reason.
 *
 * WHY THE HEADING TRAIL IS A LIST OF ELEMENTS
 *
 * The chain of headings above a section is drawn as separate spans with the
 * separator in the markup, not in a string. A joined path would be text this
 * app wrote between two of the document's headings, and every such join is how
 * a system that must never compose starts composing.
 *
 * WHY THE ELEMENT IDS ARE GONE
 *
 * `p29-E000188; p29-E000193; p29-E000197` under the title, and
 * `AI-7426cb71ed · rev 1 · record 87f4ffe4-…` under every rule, were sixteen
 * identifiers on a panel where a reviewer needs none of them to judge anything.
 * They are ours, not the document's, and they sat in the position that reads as
 * provenance. They now live one keystroke away, under each rule's own details,
 * where someone chasing a specific record will look for them and nobody else
 * has to read past them.
 *
 * WHY EXPANDING HAPPENS HERE AND NOT ELSEWHERE
 *
 * Leaving the panel to inspect one rule of twenty and coming back loses the
 * reviewer's place. So a rule opens where it stands. What that reveals is
 * strictly additional: the statement, the condition, the outcome and the route
 * of every rule are on screen before anything is clicked, and expanding adds
 * identifiers and citations to them. A collapsed rule would be a rule the
 * reviewer cannot know is there, which is the failure `nothingIsBehindAClick`
 * exists to prevent.
 *
 * WHY THE LOGIC TAB IS A SECOND ARRANGEMENT AND NOT A SECOND PLACE
 *
 * Reading holds everything needed to answer "is this faithful". Logic answers
 * the other half — "is this complete" — and it does so with the same rules,
 * all of them, rearranged so they can be compared. No rule is reachable only
 * from one tab, so nothing is hidden behind the switch; what changes is whether
 * the rules are read down the page or across it.
 */
export function PolicyDetailPanel({
  card,
  statusColor,
  statusLabel,
  onOpenRule,
  ruleDetail,
  onApprove,
  onReject,
  actions,
}: {
  card: PolicyCard;
  statusColor: (status: string) => string;
  statusLabel: (status: string) => string;
  /** Take one rule to the larger surface, replacing this panel's content with
   *  the inspector. Optional, and no longer the way to read a rule: the
   *  reviewer used to have to leave the policy to see any of its detail and
   *  click back to return, which cost them the passage they were comparing
   *  against. `ruleDetail` opens it here instead. */
  onOpenRule?: (ruleId: string) => void;
  /** This rule's detail, shown in place under it when the reviewer opens it.
   *  A function, so a policy of fourteen rules builds detail for the ones that
   *  are open and not for the ones that are not. */
  ruleDetail?: (ruleId: string) => React.ReactNode;
  onApprove?: () => void;
  onReject?: () => void;
  /** Panel chrome supplied by the host (hide, fullscreen, close). */
  actions?: React.ReactNode;
}) {
  const title = policyTitle(card.policy, card.passages);
  const page = passagePageLabel(card.policy.page);
  // The headings above this one. The innermost is the card's own title, so it
  // is not repeated here.
  const trail = card.policy.heading_path.slice(0, -1);
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(new Set());
  const toggle = (ruleId: string) =>
    setExpanded((current) => {
      const next = new Set(current);
      if (!next.delete(ruleId)) next.add(ruleId);
      return next;
    });
  let ordinal = 0;

  return (
    <div
      className="policy-detail-panel"
      data-testid="policy-detail-panel"
      data-policy={card.policy.key}
      data-passage={card.passages[0]?.passage.key ?? card.policy.key}
    >
      <div className="policy-detail-panel__head">
        <div className="policy-detail-panel__identity">
          {trail.length > 0 && (
            <p
              className="policy-card__trail"
              data-testid="policy-heading-trail"
            >
              {trail.map((step, index) => (
                <span key={`${index}-${step}`}>
                  {index > 0 && (
                    <span className="policy-card__dot" aria-hidden>
                      ·
                    </span>
                  )}
                  <DirectionalText>{step}</DirectionalText>
                </span>
              ))}
            </p>
          )}
          <Title level={5} className="policy-detail-panel__title">
            <DirectionalText>{title.text || card.policy.key}</DirectionalText>
          </Title>
          {title.source !== "heading" && (
            <Text type="secondary" className="policy-card__title-note">
              {title.source === "statement"
                ? "No heading was recorded for this policy, so it is named by its opening statement."
                : title.source === "cell"
                  ? "No heading was recorded for this policy, and it is a row of a table, so it is named by its first cell."
                  : title.source === "section"
                    ? "This policy states no sentence of its own, so it is named by the heading in its citations."
                    : "Neither a heading nor a statement was recorded for this policy, so it is named by its key."}
            </Text>
          )}
          <div className="policy-detail-panel__meta">
            <span>
              {policyRuleCountLabel(card.rules.length, card.policy.rule_count)}
            </span>
            <span className="policy-card__dot">·</span>
            <span>
              {card.policy.passage_count === 1
                ? "1 passage"
                : `${card.policy.passage_count} passages`}
            </span>
            {page && (
              <>
                <span className="policy-card__dot">·</span>
                <span>{page}</span>
              </>
            )}
            {card.reviewStatuses.map((status) => (
              <Tag key={status} color={statusColor(status)}>
                {statusLabel(status)}
              </Tag>
            ))}
          </div>
        </div>
        <Space size={4} wrap className="policy-detail-panel__actions">
          {onApprove && onReject && (
            <>
              <Button
                size="small"
                type="primary"
                icon={<CheckOutlined />}
                onClick={onApprove}
              >
                Approve policy
              </Button>
              <Button
                size="small"
                danger
                icon={<CloseOutlined />}
                onClick={onReject}
              >
                Reject policy
              </Button>
            </>
          )}
          {actions}
        </Space>
      </div>

      <Tabs
        className="policy-detail-panel__tabs"
        defaultActiveKey="reading"
        items={[
          {
            key: "reading",
            label: "Reading",
            children: (
              <>
                {card.passages.map((block) => {
                  const passageRules = block.rules.map(
                    (rule) => rule.candidate.rule,
                  );
                  const quotations = passageQuotations(passageRules);
                  const name = passageTitle(passageRules);
                  return (
                    <section
                      key={block.passage.key}
                      className="policy-detail-panel__section"
                      data-testid="policy-detail-passage"
                      data-passage={block.passage.key}
                    >
                      <Text
                        type="secondary"
                        className="policy-detail-panel__section-label"
                      >
                        What the source says
                        {block.passage.page === null
                          ? ""
                          : ` · page ${block.passage.page}`}
                      </Text>
                      {quotations.length > 0 ? (
                        quotations.map((quotation, index) => (
                          <p
                            key={`${index}-${quotation.slice(0, 32)}`}
                            className="policy-card__passage"
                            data-testid="policy-detail-quotation"
                          >
                            <DirectionalText>{quotation}</DirectionalText>
                          </p>
                        ))
                      ) : (
                        <Text type="secondary">
                          The source text for this passage was not stored with
                          its rules.
                        </Text>
                      )}
                      {name.source === "cell" && (
                        <Text
                          type="secondary"
                          className="policy-card__title-note"
                        >
                          This passage is a row of a table, so it is listed by
                          its first cell.
                        </Text>
                      )}

                      <ol className="policy-detail-panel__rules">
                        {block.rules.map((rule) => {
                          const canonical = rule.candidate.rule;
                          const decision = ruleDecisionSummary(canonical);
                          ordinal += 1;
                          return (
                            <li
                              key={rule.rule_id}
                              className="policy-detail-rule"
                              value={ordinal}
                            >
                              <div className="policy-detail-rule__head">
                                <span
                                  className="policy-card__rule-ordinal"
                                  aria-hidden
                                >
                                  {ordinal}
                                </span>
                                <span className="policy-card__rule-title">
                                  <DirectionalText>
                                    {canonical.title}
                                  </DirectionalText>
                                </span>
                                <PolicyEffectBadge
                                  effect={canonical.effect}
                                  size="small"
                                />
                                <Tag variant="filled">
                                  {ruleTypeLabel(canonical.rule_type)}
                                </Tag>
                                <Tooltip
                                  title={
                                    rule.evaluation_mode === "deterministic"
                                      ? "The source states this test as a comparison between named quantities, so the engine settles a case by evaluating it."
                                      : "The source states this test in words, so a person settles a case by reading it. This is how the document was written, and is a normal way for a rule to arrive."
                                  }
                                >
                                  <Tag
                                    variant="filled"
                                    className="policy-card__rule-route"
                                  >
                                    {policyRouteLabel(rule.evaluation_mode)}
                                  </Tag>
                                </Tooltip>
                                <Tag
                                  color={statusColor(
                                    rule.candidate.review_status,
                                  )}
                                >
                                  {statusLabel(rule.candidate.review_status)}
                                </Tag>
                                <Button
                                  size="small"
                                  type="text"
                                  icon={
                                    expanded.has(rule.rule_id) ? (
                                      <DownOutlined />
                                    ) : (
                                      <RightOutlined />
                                    )
                                  }
                                  aria-expanded={expanded.has(rule.rule_id)}
                                  aria-controls={
                                    expanded.has(rule.rule_id)
                                      ? `policy-rule-detail-${rule.rule_id}`
                                      : undefined
                                  }
                                  onClick={() => toggle(rule.rule_id)}
                                >
                                  Details
                                </Button>
                                {onOpenRule && (
                                  <Button
                                    size="small"
                                    type="text"
                                    onClick={() => onOpenRule(rule.rule_id)}
                                  >
                                    Open rule
                                  </Button>
                                )}
                              </div>
                              <div
                                className="policy-decision-line"
                                title={decision.text}
                              >
                                <span className="policy-decision-key">
                                  When
                                </span>
                                <span
                                  className={
                                    decision.conditionIsStatedOnly
                                      ? "policy-decision-value is-stated-only"
                                      : "policy-decision-value"
                                  }
                                >
                                  {decision.condition}
                                </span>
                                <span className="policy-decision-arrow">→</span>
                                <span className="policy-decision-key">
                                  Then
                                </span>
                                <span className="policy-decision-result">
                                  {effectActionText(canonical.effect)}
                                </span>
                              </div>
                              {!isEmptyCondition(canonical.condition) && (
                                <div className="policy-detail-rule__conditions">
                                  <ConditionView node={canonical.condition} />
                                </div>
                              )}
                              {expanded.has(rule.rule_id) && (
                                <div
                                  id={`policy-rule-detail-${rule.rule_id}`}
                                  className="policy-detail-rule__expanded"
                                  role="region"
                                  aria-label={canonical.title}
                                >
                                  {ruleDetail?.(rule.rule_id)}
                                <dl
                                  className="policy-detail-rule__ids"
                                  data-testid="policy-rule-details"
                                  data-rule={rule.rule_id}
                                >
                                  {/* Ours, not the document's. Here rather than under the
                            title, because a reviewer judging faithfulness needs
                            none of them and a reviewer chasing one record needs
                            all three. */}
                                  <div>
                                    <dt>Rule</dt>
                                    <dd className="policy-row-mono">
                                      {rule.rule_id}
                                    </dd>
                                  </div>
                                  <div>
                                    <dt>Revision</dt>
                                    <dd>{canonical.rule_revision}</dd>
                                  </div>
                                  <div>
                                    <dt>Candidate record</dt>
                                    <dd className="policy-row-mono">
                                      {rule.candidate.id}
                                    </dd>
                                  </div>
                                  <div>
                                    <dt>Cited element</dt>
                                    <dd className="policy-row-mono">
                                      {block.passage.source_elements}
                                    </dd>
                                  </div>
                                </dl>
                                </div>
                              )}
                            </li>
                          );
                        })}
                      </ol>
                    </section>
                  );
                })}

                {card.hiddenByFilter > 0 && (
                  <Text type="secondary">
                    {card.hiddenByFilter === 1
                      ? "1 more rule of this policy is outside the current filter and is not shown here or included in the JSON below."
                      : `${card.hiddenByFilter} more rules of this policy are outside the current filter and are not shown here or included in the JSON below.`}
                  </Text>
                )}
              </>
            ),
          },
          {
            key: "logic",
            label: "Logic",
            children: <PolicyLogicTable card={card} />,
          },
        ]}
      />

      <section className="policy-detail-panel__section">
        <Text type="secondary" className="policy-detail-panel__section-label">
          <CodeOutlined /> This policy as one document — its rules nested inside
          it
        </Text>
        {/* The download is named by the policy, not by its key: a persisted
            provision is keyed by a digest, and a reviewer who downloads three of
            these wants three filenames they can tell apart. */}
        <JsonView
          value={policyJsonDocument(card)}
          downloadName={`${(title.text || card.policy.key).replace(/[^\w.-]+/g, "_").slice(0, 80)}.json`}
          maxHeight={420}
        />
      </section>
    </div>
  );
}
