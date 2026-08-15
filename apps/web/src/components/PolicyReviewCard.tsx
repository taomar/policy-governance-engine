import { Button, Checkbox, Space, Tag, Tooltip, Typography } from "antd";
import { CheckOutlined, CloseOutlined, RightOutlined } from "@ant-design/icons";
import type { PolicyCard } from "../policyCards";
import {
  passagePageLabel,
  passageTitle,
  policyTitle,
  sharedRuleFacets,
} from "../policyCards";
import { policyRouteLabel, policyRuleCountLabel } from "../policyGrouping";
import { ruleDecisionSummary } from "../ruleDisplay";
import { ruleTypeLabel } from "../ruleTypes";
import { DirectionalText } from "./DirectionalText";
import { PolicyEffectBadge } from "./PolicyEffectBadge";

const { Text } = Typography;

/**
 * One section of the source, as one thing to decide.
 *
 * WHAT THIS REPLACES
 *
 * First a band above three rows, each row carrying its own checkbox, approve,
 * reject and record id — the band said the three rules belonged together and
 * the interface then asked for three decisions about them. Then, once the
 * passage was the card, two consecutive sentences of one section still drew two
 * cards with the same name. The card is the section; its passages are how the
 * document says it; its rules are its logic.
 *
 * WHAT IT IS CALLED
 *
 * The heading, verbatim — `7.2. WORK PERMIT (IQAMA) & TRANSFERRING ONES
 * SPONSORSHIP`. It is the grouping key, so it names the whole card and no two
 * cards share it.
 *
 * NOTHING IS HIDDEN TO ACHIEVE THIS
 *
 * A bigger card must not mean fewer rules. Every rule of the section is listed
 * with its title, condition and outcome, visible without expanding anything —
 * fourteen rules show fourteen, and seventy-two show seventy-two.
 *
 * THE PASSAGE BOUNDARY SURVIVES
 *
 * Rules from different sentences are still from different sentences. Each
 * passage of the section is its own block, named by its own words and quoting
 * its own text once, with its rules beneath it — so a reviewer scanning a long
 * card can always see which words an obligation came from.
 *
 * SAID ONCE IF SHARED, SHOWN PER RULE IF IT DIFFERS
 *
 * Every row used to carry `[Requires] [Candidate] rev 1`, which in a card of
 * three rules is three identical badge pairs stacked. What all the rules agree
 * on is stated once, on the policy; what differs between them is shown on the
 * rule it belongs to. So a badge beside a rule always carries information.
 *
 * ROUTE IS PER RULE
 *
 * Route follows that same rule and no other: shared, it is stated once; mixed,
 * every rule shows its own and nothing is averaged. A section holding one rule
 * the engine compares and one the source states in words is the ordinary shape
 * of a real document. Neither route is drawn as a shortfall.
 *
 * IDENTIFIERS ARE NOT ON THE FACE
 *
 * `AI-acfa998ecd` never helped anyone judge whether a contract start date is
 * right. Rule id, revision and record id live in the detail panel, one click
 * away, where somebody chasing a specific record is already looking.
 *
 * A SECTION OF ONE RULE IS AN ORDINARY CARD
 *
 * Most sections state one or two. This component has no branch for that: it
 * lists one rule where another card lists seventy-two, and the head reads
 * "1 rule". Nothing wraps it, nothing apologises for it.
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
  /** Every reviewable rule of this policy is in the bulk selection. */
  selected: boolean;
  /** Some but not all are — which can only happen via another card's family. */
  indeterminate: boolean;
  /** This policy is the one in the detail panel. */
  open: boolean;
  statusColor: (status: string) => string;
  statusLabel: (status: string) => string;
  findingsFor: (ruleId: string) => number;
  onToggleSelect: () => void;
  onOpen: () => void;
  /** Records the decision against every reviewable rule of the policy at
   *  once. Absent when the policy holds nothing left to decide. */
  onApprove?: () => void;
  onReject?: () => void;
}) {
  const title = policyTitle(card.policy, card.passages);
  const page = passagePageLabel(card.policy.page);
  const shared = sharedRuleFacets(card);
  const sharedEffect = shared.effectType
    ? card.rules[0]?.candidate.rule.effect
    : undefined;
  // The headings above this one. The innermost is the card's own title, so it
  // is not repeated in the trail.
  const trail = card.policy.heading_path.slice(0, -1);
  // Numbered across the whole card, so "rule 9 of 14" means the same thing in
  // the list, in the detail panel and in conversation — the passage blocks
  // group the rules, they do not restart them.
  let ordinal = 0;

  return (
    <article
      className={`policy-card${open ? " policy-card--open" : ""}`}
      data-testid="policy-card"
      data-policy={card.policy.key}
      data-passage={card.passages[0]?.passage.key ?? card.policy.key}
      data-title-from={title.source}
      aria-label={`Policy ${title.text || card.policy.key}`}
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
          {trail.length > 0 && (
            <p className="policy-card__trail" data-testid="policy-heading-trail">
              {/* The chain of headings that governs this section, each verbatim
                  and each its own element. A joined path string would be text
                  this app wrote between two of the document's headings. */}
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
          <button type="button" className="policy-card__title" onClick={onOpen}>
            <DirectionalText>{title.text || card.policy.key}</DirectionalText>
          </button>
          {title.source !== "heading" && (
            <Text type="secondary" className="policy-card__title-note">
              {/* Said rather than papered over: the heading is what names a
                  policy, and where the document did not give one the card says
                  what it fell back to. */}
              {title.source === "statement"
                ? "No heading was recorded for this policy, so it is named by its opening statement."
                : title.source === "cell"
                  ? "No heading was recorded for this policy, and it is a row of a table, so it is named by its first cell. The whole row is below."
                  : title.source === "section"
                    ? "This policy states no sentence of its own, so it is named by the heading in its citations. Its text is below."
                    : "Neither a heading nor a statement was recorded for this policy, so it is named by its key. Its text is below."}
            </Text>
          )}
          <div className="policy-card__meta">
            <span>{policyRuleCountLabel(card.policy.rule_count)}</span>
            {card.policy.passage_count > 1 && (
              <>
                <span className="policy-card__dot">·</span>
                <Tooltip title="The rules of this policy are stated across this many passages of the source. Each is shown separately below.">
                  <span>{card.policy.passage_count} passages</span>
                </Tooltip>
              </>
            )}
            {page && (
              <>
                <span className="policy-card__dot">·</span>
                <span>{page}</span>
              </>
            )}
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
                  // Both routes are ordinary. A section holding one of each is
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
              aria-label={open ? "Viewing this policy" : `Open details for ${title.text || card.policy.key}`}
            />
          </Tooltip>
        </Space>
      </div>

      {card.passages.map((block) => {
        const passageRules = block.rules.map((rule) => rule.candidate.rule);
        const name = passageTitle(passageRules);
        // The block's own words, once: its opening statement as the label and
        // the remainder beneath. Together they are the passage, in its order,
        // with nothing reworded and nothing dropped.
        return (
          <section
            key={block.passage.key}
            className="policy-card__passage-block"
            data-testid="policy-passage"
            data-passage={block.passage.key}
            data-title-from={name.source}
          >
            <div className="policy-card__passage-head">
              {name.text ? (
                <span className="policy-card__passage-title">
                  <DirectionalText>{name.text}</DirectionalText>
                </span>
              ) : (
                <Text type="secondary" className="policy-card__passage-absent">
                  {/* Said rather than left blank: a passage whose text was not
                      stored and a passage that says nothing are different. */}
                  The source text for this passage was not stored with its rules.
                </Text>
              )}
              <Tooltip title="The element of the source this passage was read from.">
                <span className="policy-card__passage-source">{block.passage.key}</span>
              </Tooltip>
            </div>
            {name.rest.map((quotation, index) => (
              <p
                key={`${index}-${quotation.slice(0, 32)}`}
                className="policy-card__passage"
                data-testid="policy-passage-quotation"
              >
                {/* One block per statement the passage makes. They were joined
                    into a single string, which put two of the document's texts
                    next to each other in an order it never wrote. */}
                <DirectionalText>{quotation}</DirectionalText>
              </p>
            ))}

            <ol className="policy-card__rules">
              {block.rules.map((rule) => {
                const decision = ruleDecisionSummary(rule.candidate.rule);
                const findings = findingsFor(rule.rule_id);
                ordinal += 1;
                return (
                  <li
                    key={rule.rule_id}
                    className="policy-card__rule"
                    data-testid="policy-card-rule"
                    value={ordinal}
                  >
                    <span className="policy-card__rule-ordinal" aria-hidden>
                      {ordinal}
                    </span>
                    <div className="policy-card__rule-body">
                      <div className="policy-card__rule-line">
                        <span className="policy-card__rule-title">
                          <DirectionalText>{rule.candidate.rule.title}</DirectionalText>
                        </span>
                        {/* Only what this rule does not share with its
                            neighbours. A badge here means "unlike the others",
                            so it is worth the reviewer stopping to read. */}
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
                        {!shared.revision && (
                          <span className="policy-card__rule-rev">
                            rev {rule.candidate.rule.rule_revision}
                          </span>
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
                    </div>
                  </li>
                );
              })}
            </ol>
          </section>
        );
      })}

      {card.hiddenByFilter > 0 && (
        <Text type="secondary" className="policy-card__partial">
          {/* A fragment presented as a whole policy is worse than no grouping
              at all, so the gap is stated rather than left to be read off two
              numbers that do not agree. */}
          {card.hiddenByFilter === 1
            ? "1 more rule of this policy is outside the current filter."
            : `${card.hiddenByFilter} more rules of this policy are outside the current filter.`}{" "}
          Approving here decides the {card.reviewableIds.length === 1 ? "rule" : "rules"} shown above.
        </Text>
      )}
    </article>
  );
}
