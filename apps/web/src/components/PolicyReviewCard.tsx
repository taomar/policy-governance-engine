import { Button, Checkbox, Space, Tag, Tooltip, Typography } from "antd";
import { CheckOutlined, CloseOutlined, RightOutlined } from "@ant-design/icons";
import type { PolicyCard } from "../policyCards";
import { passageHeading, passagePageLabel, passageTitle, sharedRuleFacets } from "../policyCards";
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
 * WHAT IT IS CALLED
 *
 * Its own opening statement, quoted, with the heading it sits under above it
 * and the rest of the passage below. The band used to be titled "Stated
 * together in one passage", which describes why the rules were grouped rather
 * than what they are about: a reviewer scanning a queue of 155 of these learns
 * nothing from being told 155 times that a passage is a passage. See
 * `passageTitle` for why the heading alone could not do the job — 94% of
 * passages share theirs with another.
 *
 * NOTHING IS HIDDEN TO ACHIEVE THIS
 *
 * Collapsing three cards into one must not collapse three obligations into one
 * sentence. Every rule of the passage is listed with its title, condition and
 * outcome, visible without expanding anything. The title takes the passage's
 * first statement and the paragraph beneath carries the remainder, so the
 * passage is shown once, whole, in its own order — not summarised, and not
 * repeated between the title and the body.
 *
 * SAID ONCE IF SHARED, SHOWN PER RULE IF IT DIFFERS
 *
 * Every row used to carry `[Requires] [Candidate] rev 1`, which in a card of
 * three rules is three identical badge pairs stacked. What all the rules agree
 * on is now stated once, on the policy; what differs between them is shown on
 * the rule it belongs to. So a badge beside a rule always carries information.
 *
 * ROUTE IS PER RULE
 *
 * Route follows that same rule and no other: shared, it is stated once; mixed,
 * every rule shows its own and nothing is averaged. A passage holding one rule
 * the engine compares and one the source states in words is the ordinary shape
 * of a real document. Neither route is drawn as a shortfall.
 *
 * IDENTIFIERS ARE NOT ON THE FACE
 *
 * `AI-acfa998ecd` never helped anyone judge whether a contract start date is
 * right. Rule id, revision and record id live in the detail panel, one click
 * away, where somebody chasing a specific record is already looking.
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
  const title = passageTitle(rules);
  const heading = passageHeading(rules);
  const page = passagePageLabel(card.policy.page);
  const shared = sharedRuleFacets(card);
  const sharedEffect = shared.effectType
    ? card.rules[0]?.candidate.rule.effect
    : undefined;

  return (
    <article
      className={`policy-card${open ? " policy-card--open" : ""}`}
      data-testid="policy-card"
      data-passage={card.policy.key}
      data-title-from={title.source}
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
          {title.source !== "section" && (
            <div className="policy-card__section">
              {heading ? (
                <DirectionalText>{heading}</DirectionalText>
              ) : (
                <Text type="secondary">{HEADING_NOT_RECORDED}</Text>
              )}
            </div>
          )}
          <button type="button" className="policy-card__title" onClick={onOpen}>
            <DirectionalText>{title.text || card.policy.source_elements}</DirectionalText>
          </button>
          {title.source !== "statement" && (
            <Text type="secondary" className="policy-card__title-note">
              {title.source === "cell"
                ? // Said rather than papered over: a row of a table has no
                  // sentence to be named by, so it is named by a cell of
                  // itself and the whole row is left in view below.
                  "This passage is a row of a table, so it is named by its first cell. The whole row is below."
                : title.source === "section"
                  ? "This passage states no sentence of its own, so it is named by the heading it sits under. Its text is below."
                  : "Neither a statement nor a heading was recorded for this passage, so it is named by its key. Its text is below."}
            </Text>
          )}
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
            {sharedEffect && (
              <Tooltip title="Every rule of this policy has this effect.">
                <span>
                  <PolicyEffectBadge effect={sharedEffect} size="small" />
                </span>
              </Tooltip>
            )}
            {shared.ruleType && (
              <Tooltip title="Every rule of this policy is of this kind.">
                <Tag variant="filled">{ruleTypeLabel(shared.ruleType)}</Tag>
              </Tooltip>
            )}
            {shared.route && (
              <Tooltip
                title={
                  // Both routes are ordinary. A passage holding one of each is
                  // the common shape of a real document, not a half-finished
                  // version of a better one.
                  "Where the source states a test as a comparison it is evaluated directly. Where the source states it in words it is decided by reading. Every rule of this policy takes this route; where they differ, each rule below says which it takes."
                }
              >
                <Tag variant="filled" className="policy-card__route">
                  {policyRouteLabel(shared.route)}
                </Tag>
              </Tooltip>
            )}
            {shared.reviewStatus && (
              <Tag color={statusColor(shared.reviewStatus)}>{statusLabel(shared.reviewStatus)}</Tag>
            )}
          </div>
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

      {title.rest && (
        <p className="policy-card__passage">
          <DirectionalText>{title.rest}</DirectionalText>
        </p>
      )}
      {title.source === "unnamed" && !title.rest && (
        <Text type="secondary" className="policy-card__passage-absent">
          {/* Said rather than left blank: a passage whose text was not stored
              and a passage that says nothing are different facts. */}
          The source text for this passage was not stored with its rules.
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
                  {/* Only what this rule does not share with its neighbours.
                      A badge here means "unlike the others", so it is worth
                      the reviewer stopping to read. */}
                  {!shared.effectType && (
                    <PolicyEffectBadge effect={rule.candidate.rule.effect} size="small" />
                  )}
                  {!shared.ruleType && (
                    /* Named so it reads as what the rule is, not as a mark against it.
                       The type badge sits beside a route badge, and without a name a
                       reader can mistake one for the other. */
                    <Tooltip title="The kind of rule this is. It differs from the others in this policy.">
                      <Tag variant="filled">{ruleTypeLabel(rule.candidate.rule.rule_type)}</Tag>
                    </Tooltip>
                  )}
                  {!shared.route && (
                    <Tooltip title="How this rule is decided. It differs from the others in this policy, which is normal.">
                      <Tag variant="filled" className="policy-card__rule-route">
                        {policyRouteLabel(rule.evaluation_mode)}
                      </Tag>
                    </Tooltip>
                  )}
                  {!shared.reviewStatus && (
                    <Tag color={statusColor(rule.candidate.review_status)}>
                      {statusLabel(rule.candidate.review_status)}
                    </Tag>
                  )}
                  {!shared.revision && <span className="policy-card__rule-rev">rev {rule.candidate.rule.rule_revision}</span>}
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
