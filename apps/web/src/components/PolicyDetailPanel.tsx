import { Button, Space, Tag, Tooltip, Typography } from "antd";
import { CheckOutlined, CloseOutlined, CodeOutlined, RightOutlined } from "@ant-design/icons";
import type { PolicyCard } from "../policyCards";
import { passageHeading, passagePageLabel, passageStatement, passageTitle, policyJsonDocument } from "../policyCards";
import { policyRouteLabel, policyRuleCountLabel } from "../policyGrouping";
import { effectActionText, isEmptyCondition, ruleDecisionSummary } from "../ruleDisplay";
import { ruleTypeLabel } from "../ruleTypes";
import { HEADING_NOT_RECORDED } from "../headingContext";
import { ConditionView } from "./ConditionView";
import { DirectionalText } from "./DirectionalText";
import { JsonView } from "./JsonView";
import { PolicyEffectBadge } from "./PolicyEffectBadge";

const { Text, Title } = Typography;

/**
 * The detail of one passage: its text once, its rules in full, and one JSON.
 *
 * WHY ONE DOCUMENT AND NOT N
 *
 * The reviewer's question is "is this how contract start dates work". Three
 * JSON documents cannot answer it, because the answer is the relationship
 * between them — a default and the cases that depart from it. So the panel
 * serialises the policy, with its rules nested inside it, and downloads as
 * `{passage key}.json`.
 *
 * The per-rule canonical JSON has not gone anywhere: opening a rule from here
 * swaps this panel for the rule inspector, which still offers evaluator,
 * canonical and DMN forms of that one rule. It is a drill-down, in the same
 * panel — never a second panel — so the reviewer is never handed three
 * documents where the source stated one policy.
 */
export function PolicyDetailPanel({
  card,
  statusColor,
  statusLabel,
  onOpenRule,
  onApprove,
  onReject,
  actions,
}: {
  card: PolicyCard;
  statusColor: (status: string) => string;
  statusLabel: (status: string) => string;
  /** Drill into one rule, replacing this panel's content with the inspector. */
  onOpenRule: (ruleId: string) => void;
  onApprove?: () => void;
  onReject?: () => void;
  /** Panel chrome supplied by the host (hide, fullscreen, close). */
  actions?: React.ReactNode;
}) {
  const rules = card.rules.map((rule) => rule.candidate.rule);
  const heading = passageHeading(rules);
  const title = passageTitle(rules);
  const passage = passageStatement(rules);
  const page = passagePageLabel(card.policy.page);

  return (
    <div className="policy-detail-panel" data-testid="policy-detail-panel" data-passage={card.policy.key}>
      <div className="policy-detail-panel__head">
        <div className="policy-detail-panel__identity">
          {title.source !== "section" && (
            <div className="policy-card__section">
              {heading ? (
                <DirectionalText>{heading}</DirectionalText>
              ) : (
                <Text type="secondary">{HEADING_NOT_RECORDED}</Text>
              )}
            </div>
          )}
          <Title level={5} className="policy-detail-panel__title">
            <DirectionalText>{title.text || card.policy.source_elements}</DirectionalText>
          </Title>
          {title.source !== "statement" && (
            <Text type="secondary" className="policy-card__title-note">
              {title.source === "cell"
                ? "This passage is a row of a table, so it is named by its first cell."
                : title.source === "section"
                  ? "This passage states no sentence of its own, so it is named by the heading it sits under."
                  : "Neither a statement nor a heading was recorded for this passage, so it is named by its key."}
            </Text>
          )}
          <div className="policy-detail-panel__meta">
            <span>{policyRuleCountLabel(card.policy.rule_count)}</span>
            {page && (
              <>
                <span className="policy-card__dot">·</span>
                <span>{page}</span>
              </>
            )}
            <span className="policy-card__dot">·</span>
            <span className="policy-card__source">{card.policy.source_elements}</span>
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
              <Button size="small" type="primary" icon={<CheckOutlined />} onClick={onApprove}>
                Approve policy
              </Button>
              <Button size="small" danger icon={<CloseOutlined />} onClick={onReject}>
                Reject policy
              </Button>
            </>
          )}
          {actions}
        </Space>
      </div>

      <section className="policy-detail-panel__section">
        <Text type="secondary" className="policy-detail-panel__section-label">
          What the source says
        </Text>
        {passage ? (
          <p className="policy-card__passage">
            <DirectionalText>{passage}</DirectionalText>
          </p>
        ) : (
          <Text type="secondary">The source text for this passage was not stored with its rules.</Text>
        )}
      </section>

      <section className="policy-detail-panel__section">
        <Text type="secondary" className="policy-detail-panel__section-label">
          {card.rules.length === 1 ? "The rule it states" : `The ${card.rules.length} rules it states`}
        </Text>
        <ol className="policy-detail-panel__rules">
          {card.rules.map((rule, index) => {
            const canonical = rule.candidate.rule;
            const decision = ruleDecisionSummary(canonical);
            return (
              <li key={rule.rule_id} className="policy-detail-rule">
                <div className="policy-detail-rule__head">
                  <span className="policy-card__rule-ordinal" aria-hidden>
                    {index + 1}
                  </span>
                  <span className="policy-card__rule-title">
                    <DirectionalText>{canonical.title}</DirectionalText>
                  </span>
                  <PolicyEffectBadge effect={canonical.effect} size="small" />
                  <Tag variant="filled">{ruleTypeLabel(canonical.rule_type)}</Tag>
                  <Tooltip
                    title={
                      rule.evaluation_mode === "deterministic"
                        ? "The source states this test as a comparison between named quantities, so the engine settles a case by evaluating it."
                        : "The source states this test in words, so a person settles a case by reading it. This is how the document was written, and is a normal way for a rule to arrive."
                    }
                  >
                    <Tag variant="filled" className="policy-card__rule-route">
                      {policyRouteLabel(rule.evaluation_mode)}
                    </Tag>
                  </Tooltip>
                  <Tag color={statusColor(rule.candidate.review_status)}>
                    {statusLabel(rule.candidate.review_status)}
                  </Tag>
                  <Button
                    size="small"
                    type="text"
                    icon={<RightOutlined />}
                    onClick={() => onOpenRule(rule.rule_id)}
                  >
                    Open rule
                  </Button>
                </div>
                <div className="policy-decision-line" title={decision.text}>
                  <span className="policy-decision-key">When</span>
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
                  <span className="policy-decision-key">Then</span>
                  <span className="policy-decision-result">{effectActionText(canonical.effect)}</span>
                </div>
                {!isEmptyCondition(canonical.condition) && (
                  <div className="policy-detail-rule__conditions">
                    <ConditionView node={canonical.condition} />
                  </div>
                )}
                <div className="policy-card__rule-meta">
                  <span className="policy-row-mono">{rule.rule_id}</span>
                  <span className="policy-card__dot">·</span>
                  <span>rev {canonical.rule_revision}</span>
                  <span className="policy-card__dot">·</span>
                  <span className="policy-row-mono">record {rule.candidate.id}</span>
                </div>
              </li>
            );
          })}
        </ol>
        {card.hiddenByFilter > 0 && (
          <Text type="secondary">
            {card.hiddenByFilter === 1
              ? "1 more rule of this passage is outside the current filter and is not shown here or included in the JSON below."
              : `${card.hiddenByFilter} more rules of this passage are outside the current filter and are not shown here or included in the JSON below.`}
          </Text>
        )}
      </section>

      <section className="policy-detail-panel__section">
        <Text type="secondary" className="policy-detail-panel__section-label">
          <CodeOutlined /> This policy as one document — its rules nested inside it
        </Text>
        <JsonView
          value={policyJsonDocument(card)}
          downloadName={`${card.policy.key}.json`}
          maxHeight={420}
        />
      </section>
    </div>
  );
}
