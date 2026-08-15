import { Button, Checkbox, Space, Tag, Tooltip, Typography } from "antd";
import { CheckOutlined, CloseOutlined, FileTextOutlined, RightOutlined } from "@ant-design/icons";
import type { PolicyCard } from "../policyCards";
import { passageHeading, passagePageLabel, passageStatement } from "../policyCards";
import { policyRouteLabel, policyRuleCountLabel } from "../policyGrouping";
import { ruleDecisionSummary } from "../ruleDisplay";
import { ruleTypeLabel } from "../ruleTypes";
import { HEADING_NOT_RECORDED } from "../headingContext";
import { DirectionalText } from "./DirectionalText";
import { PolicyEffectBadge } from "./PolicyEffectBadge";

const { Text } = Typography;

/**
 * One passage of the source, as one thing to decide.
 *
 * WHAT THIS REPLACES
 *
 * A band above three rows, each row carrying its own checkbox, its own approve,
 * its own reject and its own record id. The band said the three rules belonged
 * together and the interface then asked for three decisions about them. The
 * card is the policy; the rules are its logic, rendered inside it.
 *
 * NOTHING IS HIDDEN TO ACHIEVE THIS
 *
 * Collapsing three cards into one must not collapse three obligations into one
 * sentence. Every rule of the passage is listed with its own title, type,
 * effect, condition and outcome, visible without expanding anything. What
 * disappears is the repetition — the source passage is quoted once above the
 * rules instead of restated inside each of them — and the three separate asks.
 *
 * ROUTE IS PER RULE
 *
 * The head carries a summary of how the passage's rules are decided, and every
 * rule carries its own. A passage holding one rule the engine compares and one
 * the source states in words is the ordinary shape of a real document; both
 * routes are named plainly and neither is drawn as a shortfall.
 *
 * A PASSAGE OF ONE RULE IS AN ORDINARY CARD
 *
 * 83 of the 155 passages in the live corpus state exactly one rule. This
 * component has no branch for that: it lists one rule where another card lists
 * seven, and the head reads "1 rule". Nothing wraps it, nothing apologises for
 * it.
 */
export function PolicyReviewCard({
  card,
  selected,
  indeterminate,
  open,
  statusColor,
  statusLabel,
  findingsFor,
  onToggleSelect,
  onOpen,
  onApprove,
  onReject,
}: {
  card: PolicyCard;
  /** Every reviewable rule of this passage is in the bulk selection. */
  selected: boolean;
  /** Some but not all are — which can only happen via another card's family. */
  indeterminate: boolean;
  /** This passage is the one in the detail panel. */
  open: boolean;
  statusColor: (status: string) => string;
  statusLabel: (status: string) => string;
  findingsFor: (ruleId: string) => number;
  onToggleSelect: () => void;
  onOpen: () => void;
  /** Records the decision against every reviewable rule of the passage at
   *  once. Absent when the passage holds nothing left to decide. */
  onApprove?: () => void;
  onReject?: () => void;
}) {
  const rules = card.rules.map((rule) => rule.candidate.rule);
  const heading = passageHeading(rules);
  const passage = passageStatement(rules);
  const page = passagePageLabel(card.policy.page);
  const mixedStatus = card.reviewStatuses.length > 1;

  return (
    <article
      className={`policy-card${open ? " policy-card--open" : ""}`}
      data-testid="policy-card"
      data-passage={card.policy.key}
      aria-label={`Policy from ${card.policy.source_elements}`}
    >
      <div className="policy-card__head">
        {(onApprove || onReject) && (
          <Checkbox
            checked={selected}
            indeterminate={indeterminate}
            onChange={onToggleSelect}
            onClick={(e) => e.stopPropagation()}
            title={`Select this policy and all ${card.reviewableIds.length} of its rules still open for review`}
          />
        )}
        <div className="policy-card__headings">
          <button type="button" className="policy-card__title" onClick={onOpen}>
            <FileTextOutlined aria-hidden />
            <DirectionalText>{heading || card.policy.source_elements}</DirectionalText>
          </button>
          <div className="policy-card__meta">
            <span>{policyRuleCountLabel(card.policy.rule_count)}</span>
            {page && (
              <>
                <span className="policy-card__dot">·</span>
                <span>{page}</span>
              </>
            )}
            <span className="policy-card__dot">·</span>
            <span className="policy-card__source">{card.policy.source_elements}</span>
            <Tooltip
              title={
                // Both routes are ordinary. A passage holding one of each is
                // the common shape of a real document, not a half-finished
                // version of a better one.
                "Where the source states a test as a comparison it is evaluated directly. Where the source states it in words it is decided by reading. A passage can hold both, and each rule below says which it takes."
              }
            >
              <Tag variant="filled" className="policy-card__route">
                {policyRouteLabel(card.policy.route)}
              </Tag>
            </Tooltip>
          </div>
        </div>
        <div className="policy-card__statuses">
          {card.reviewStatuses.map((status) => (
            <Tag key={status} color={statusColor(status)}>
              {statusLabel(status)}
            </Tag>
          ))}
        </div>
        <Space size={4} className="policy-card__actions">
          {onApprove && onReject && (
            <>
              <Tooltip
                title={`Approve this policy — records the decision against ${
                  card.reviewableIds.length === 1
                    ? "its rule"
                    : `all ${card.reviewableIds.length} of its rules still open`
                }`}
              >
                <Button size="small" icon={<CheckOutlined />} onClick={onApprove}>
                  Approve
                </Button>
              </Tooltip>
              <Tooltip
                title={`Reject this policy — records the decision against ${
                  card.reviewableIds.length === 1
                    ? "its rule"
                    : `all ${card.reviewableIds.length} of its rules still open`
                }`}
              >
                <Button size="small" danger icon={<CloseOutlined />} onClick={onReject}>
                  Reject
                </Button>
              </Tooltip>
            </>
          )}
          <Tooltip title={open ? "Shown in the detail panel" : "Open this policy in the detail panel"}>
            <Button
              size="small"
              type="text"
              icon={<RightOutlined />}
              onClick={onOpen}
              aria-label={open ? "Viewing this policy" : `Open details for ${card.policy.source_elements}`}
            />
          </Tooltip>
        </Space>
      </div>

      {passage ? (
        <p className="policy-card__passage">
          <DirectionalText>{passage}</DirectionalText>
        </p>
      ) : (
        <Text type="secondary" className="policy-card__passage-absent">
          {/* Said rather than left blank: a passage whose text was not stored
              and a passage that says nothing are different facts. */}
          The source text for this passage was not stored with its rules.
        </Text>
      )}
      {!heading && (
        <Text type="secondary" className="policy-card__heading-absent">
          {HEADING_NOT_RECORDED}
        </Text>
      )}

      <ol className="policy-card__rules">
        {card.rules.map((rule, index) => {
          const decision = ruleDecisionSummary(rule.candidate.rule);
          const findings = findingsFor(rule.rule_id);
          return (
            <li key={rule.rule_id} className="policy-card__rule">
              <span className="policy-card__rule-ordinal" aria-hidden>
                {index + 1}
              </span>
              <div className="policy-card__rule-body">
                <div className="policy-card__rule-line">
                  <span className="policy-card__rule-title">
                    <DirectionalText>{rule.candidate.rule.title}</DirectionalText>
                  </span>
                  <PolicyEffectBadge effect={rule.candidate.rule.effect} size="small" />
                  <Tag variant="filled">{ruleTypeLabel(rule.candidate.rule.rule_type)}</Tag>
                  <Tag variant="filled" className="policy-card__rule-route">
                    {policyRouteLabel(rule.evaluation_mode)}
                  </Tag>
                  {mixedStatus && (
                    <Tag color={statusColor(rule.candidate.review_status)}>
                      {statusLabel(rule.candidate.review_status)}
                    </Tag>
                  )}
                  {findings > 0 && (
                    <Tooltip title={`${findings} quality finding(s) from the last check`}>
                      <Tag color="volcano">{findings}</Tag>
                    </Tooltip>
                  )}
                </div>
                <div className="policy-decision-line" title={decision.text}>
                  <span className="policy-decision-key">When</span>
                  <span
                    className={
                      decision.conditionIsStatedOnly
                        ? "policy-decision-value is-stated-only"
                        : "policy-decision-value"
                    }
                    title={
                      decision.conditionIsStatedOnly
                        ? "The source states this test in words rather than as a comparison between named quantities, so a judge settles a case by reading it."
                        : undefined
                    }
                  >
                    {decision.condition}
                  </span>
                  <span className="policy-decision-arrow">→</span>
                  <span className="policy-decision-key">Then</span>
                  <span className="policy-decision-result">{decision.action}</span>
                </div>
                <div className="policy-card__rule-meta">
                  <span className="policy-row-mono">{rule.rule_id}</span>
                  <span className="policy-card__dot">·</span>
                  <span>rev {rule.candidate.rule.rule_revision}</span>
                </div>
              </div>
            </li>
          );
        })}
      </ol>

      {card.hiddenByFilter > 0 && (
        <Text type="secondary" className="policy-card__partial">
          {/* A fragment presented as a whole passage is worse than no grouping
              at all, so the gap is stated rather than left to be read off two
              numbers that do not agree. */}
          {card.hiddenByFilter === 1
            ? "1 more rule of this passage is outside the current filter."
            : `${card.hiddenByFilter} more rules of this passage are outside the current filter.`}{" "}
          Approving here decides the {card.reviewableIds.length === 1 ? "rule" : "rules"} shown above.
        </Text>
      )}
    </article>
  );
}
