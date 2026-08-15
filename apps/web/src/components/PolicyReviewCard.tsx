import { Fragment } from "react";
import { Button, Checkbox, Space, Tag, Tooltip, Typography } from "antd";
import { CheckOutlined, CloseOutlined, RightOutlined } from "@ant-design/icons";
import type { PolicyCard } from "../policyCards";
import {
  passagePageLabel,
  passageQuotations,
  policyTitle,
  policyTopicLabel,
  sharedRuleFacets,
} from "../policyCards";
import { policyRouteLabel, policyRuleCountLabel } from "../policyGrouping";
import { readPassage } from "../policyReading";
import { policyComposition, policyCompositionLabel } from "../policyRecordFacts";
import {
  STANCE_GROUPING_NOTE,
  STANCE_ORDER,
  groupByStance,
  recordStance,
  stanceHeading,
} from "../recordStance";
import { ruleTypeLabel } from "../ruleTypes";
import { DirectionalText } from "./DirectionalText";
import { MarkedQuotation } from "./MarkedQuotation";
import { PolicyEffectBadge } from "./PolicyEffectBadge";
import { PolicyExplainButton } from "./PolicyExplainButton";
import { RuleName } from "./RuleName";

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
 * `[Requires]` beside `[Obligation]` went further than that: measured over 692
 * rules, the effect is a function of the rule type in eight of the nine
 * combinations that occur, so it was the same fact twice at lower resolution.
 * It is shown only where the type is not.
 *
 * THE DOCUMENT'S WORDS ONCE, OURS ONCE
 *
 * A single-rule card printed one sentence three times — quoted, restated as the
 * rule's title, and split again across `WHEN … → THEN …`. Now the passage is
 * quoted once with the run each rule was drawn from marked in it, and the rule
 * says only what the quotation does not: its statement, what narrows it, and
 * its outcome where the statement does not already contain it (which, measured,
 * it does for 86% of AIS rules and 91% of GMU's). Where a rule's statement is
 * the marked sentence word for word, the row says so instead of setting the
 * same words a second time. Nothing is elided and nothing moves behind a
 * control: every word withheld from a row is on screen, marked, directly above
 * it.
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
 * right, and neither did `p9-E000074` or `rev 1`. Element id, rule id, revision
 * and record id live in the detail panel, one click away, where somebody
 * chasing a specific record is already looking.
 *
 * THE PASSAGE BOUNDARY WITHOUT A PASSAGE TITLE
 *
 * Each passage of the section is still its own block, quoting its own text
 * once, with its rules beneath it. It no longer gets a title of its own: the
 * card is named by the heading, and a passage's opening sentence promoted to a
 * label was a third piece of prose competing with the two that matter. A table
 * row lost a duplicate that way — its first cell was the block's name *and* was
 * quoted again in the row below it, fifty times over on one AIS card.
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
  const topicLabel = policyTopicLabel(card.policy);
  const page = passagePageLabel(card.policy.page);
  const shared = sharedRuleFacets(card);
  // Shown only when the rule-type badge is not. Measured across both documents,
  // the effect is a function of the type in eight of the nine combinations
  // present — `Requires` beside `Obligation` is the same fact twice, at lower
  // resolution. Where the types differ and the effect does not, it is the only
  // thing all the rules agree on and it stays.
  const sharedEffect =
    shared.effectType && !shared.ruleType ? card.rules[0]?.candidate.rule.effect : undefined;
  // What the card is made of, on the one axis that divides its rules without
  // counting any of them twice — taken from the shared module rather than read
  // off the rules here, because the published card states this same fact and two
  // readings of it would be two answers to one question.
  //
  // Counted over the rules on the card, which is what the reviewer can see and
  // what Approve decides. What the card is not showing is stated separately,
  // below, rather than folded into a total nobody can check.
  //
  // Read from the shared module, which now counts one tally per stance the
  // records actually take, so the parts sum to the rules on the card and a
  // reviewer can check that against the head count.
  const composition = policyCompositionLabel(
    policyComposition(card.rules.map((rule) => rule.candidate.rule)),
  );
  // The headings above this one. The innermost is the card's own title, so it
  // is not repeated in the trail.
  const trail = card.policy.heading_path.slice(0, -1);
  // Numbered across the whole card, so "rule 9 of 14" means the same thing in
  // the list, in the detail panel and in conversation — the passage blocks
  // group the rules, they do not restart them.
  let ordinal = 0;

  // Read in the document's order, always, and numbered here. The display order
  // below may differ; the numbers may not, because they are the only record on
  // the card of where the source states each rule.
  const readBlocks = card.passages.map((block) => {
    const passageRules = block.rules.map((rule) => rule.candidate.rule);
    const reading = readPassage(passageQuotations(passageRules), passageRules, ordinal + 1);
    ordinal += passageRules.length;
    const rows = block.rules.map((rule, index) => ({
      rule,
      read: reading.rules[index],
      stance: recordStance(rule.candidate.rule),
    }));
    // Grouped inside the passage, never across it. A rule and the quotation it
    // was drawn from are the two halves of the evidence a reviewer is checking,
    // and no ordering convenience is worth separating them.
    return { block, reading, groups: groupByStance(rows, (row) => row.stance) };
  });

  // Passages that state a rule someone is bound by come before passages that
  // only supply meaning. `groupByStance` returns its groups in stance order, so
  // a passage's first group is already its strongest claim on the reviewer's
  // attention and no second ranking is needed. Sorting is stable, so the
  // document's order survives among passages that rank together.
  const displayBlocks = [...readBlocks].sort(
    (a, b) =>
      STANCE_ORDER.indexOf(a.groups[0]?.stance ?? "unstated") -
      STANCE_ORDER.indexOf(b.groups[0]?.stance ?? "unstated"),
  );
  // Said only when something actually moved. A note explaining an ordering that
  // matches the document would be a line of text answering a question nobody on
  // this card can be asking.
  const regrouped =
    displayBlocks.some((entry, index) => entry !== readBlocks[index]) ||
    readBlocks.some((entry) => entry.groups.length > 1);

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
          {/* Ours, and first, so that it is read before the document's words
              rather than in among them — and so the document's heading and its
              trail stay contiguous and unbroken below.

              Drawn only when there is a name and the name adds something the
              heading does not. This line is the most prominent on the card, and
              what it costs is attention, so it has to be carrying something.

              Two ways it can carry nothing, and both now draw nothing:

              The name only repeats the heading. The reader already has that
              answer, in the document's own words, on the next line.

              There is no name — none generated yet, or generation attempted and
              refused. This is a deliberate reversal of how this line first
              behaved. It used to announce the absence, on the reasoning that an
              absent answer must never be mistaken for an empty one. That reason
              holds wherever something is lost by silence, and here nothing is:
              the document's own heading sits immediately below, fully legible,
              and the reader loses no fact by our not mentioning that we have
              nothing to add. Spending the card's lead line to say so is worse
              than spending it on nothing at all.

              The distinction is kept where it is worth reading rather than
              discarded — the state and its reason stay on the payload and in the
              JSON view, for a reviewer who wants to know why a policy has no
              name. See `policyJsonDocument`. */}
          {topicLabel.state === "named" && (
            <p className="policy-card__topic" data-generated="true" data-testid="policy-topic-label">
              <span className="policy-card__topic-mark" aria-hidden>
                ✦
              </span>
              <span className="policy-card__topic-what">Subject, named by this app:</span>{" "}
              <span className="policy-card__topic-text" title={topicLabel.provenance}>
                {/* Unquoted, deliberately. Quotation marks around these words
                    would present them as somebody's exact words, and they are
                    nobody's — the document's exact words are below. */}
                <DirectionalText>{topicLabel.text}</DirectionalText>
              </span>
            </p>
          )}
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
            <span>
              {policyRuleCountLabel(card.rules.length, card.policy.rule_count)}
            </span>
            {composition && (
              <>
                <span className="policy-card__dot">·</span>
                <Tooltip title="What this policy is made of: rules that settle a case, and rules that supply a meaning the others use.">
                  <span data-testid="policy-composition">{composition}</span>
                </Tooltip>
              </>
            )}
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
          {/* Offered only where there is a persisted grouping to explain. A
              policy assembled without one has no stable identity for the server
              to read a record back from, and a button that could only report
              that is a button that should not be drawn. The card is unchanged
              and complete either way — this adds a reading, never a fact. */}
          {card.policy.provision_id && (
            <PolicyExplainButton
              provisionId={card.policy.provision_id}
              policyKey={card.policy.key}
            />
          )}
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

      {card.passages.length > 0 && regrouped && (
        <Text type="secondary" className="policy-card__grouping-note" data-testid="rule-grouping-note">
          {STANCE_GROUPING_NOTE}
        </Text>
      )}

      {displayBlocks.map(({ block, reading, groups }) => {
        return (
          <section
            key={block.passage.key}
            className="policy-card__passage-block"
            data-testid="policy-passage"
            data-passage={block.passage.key}
          >
            {reading.quotations.length > 0 ? (
              reading.quotations.map((quotation, index) => (
                <MarkedQuotation
                  key={`${index}-${quotation.text.slice(0, 32)}`}
                  text={quotation.text}
                  marks={quotation.marks}
                  className="policy-card__passage"
                  testId="policy-passage-quotation"
                />
              ))
            ) : (
              <Text type="secondary" className="policy-card__passage-absent">
                {/* Said rather than left blank: a passage whose text was not
                    stored and a passage that says nothing are different. */}
                The source text for this passage was not stored with its rules.
              </Text>
            )}

            <ol className="policy-card__rules">
              {groups.map((group) => (
                <Fragment key={group.stance}>
                  {/* Headed only where the passage holds more than one kind.
                      A heading over every rule of a passage that holds one kind
                      names a distinction the reviewer cannot use. */}
                  {groups.length > 1 && (
                    <li
                      className="policy-card__rule-group"
                      data-testid="rule-group"
                      data-stance={group.stance}
                    >
                      {stanceHeading(group.stance, group.items.length)}
                    </li>
                  )}
                  {group.items.map(({ rule, read }) => {
                    const findings = findingsFor(rule.rule_id);
                    return (
                  <li
                    // Keyed by the row's own identity, not by `rule_id`. That is
                    // a hash of the rule's content, so two rules a passage
                    // states in identical words would share one — and React
                    // omits children that collide on a key. A card that drops a
                    // rule is the one failure this queue cannot have.
                    key={rule.candidate.id}
                    className="policy-card__rule"
                    data-testid="policy-card-rule"
                    value={read.ordinal}
                  >
                    <span className="policy-card__rule-ordinal" aria-hidden>
                      {read.ordinal}
                    </span>
                    <div className="policy-card__rule-body">
                      {/* This app's handle for the rule, above the rule's own
                          words. Renders nothing at all until one has been
                          generated, so a card with none is the card that was
                          here before. Marked as ours by the same ✦ the
                          generated subject label uses at the top of this card. */}
                      <RuleName candidateId={rule.candidate.id} variant="block" />
                      <div className="policy-card__rule-line">
                        {read.statementIsMarkedWhole ? (
                          // The words are on screen, marked, immediately above.
                          // Printing them again is the third reading of one
                          // sentence that this card was rebuilt to stop.
                          <Text type="secondary" className="policy-card__rule-restated">
                            This rule is the highlighted sentence above, word for word.
                          </Text>
                        ) : (
                          <span className="policy-card__rule-title">
                            <DirectionalText>{read.statement}</DirectionalText>
                          </span>
                        )}
                        {/* Only what this rule does not share with its
                            neighbours. A badge here means "unlike the others",
                            so it is worth the reviewer stopping to read. */}
                        {!shared.effectType && shared.ruleType !== null && (
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
                        {findings > 0 && (
                          <Tooltip title={`${findings} quality finding(s) from the last check`}>
                            <Tag color="volcano">{findings}</Tag>
                          </Tooltip>
                        )}
                      </div>
                      <p className="policy-card__rule-reading">
                        {/*
                          `when` is our word before the document's clause, and on
                          17 of the 434 rules that state a test it reads badly --
                          "when who are qualified for and interested in a posted
                          position", because the source narrowed the rule with a
                          relative clause rather than a temporal one. Measured on
                          both documents: 3 on AIS, 14 on GMU, 3.9%.

                          It is left as it reads. Every alternative either writes
                          a word the document did not (a key chosen to fit the
                          clause) or splits the surface in two, so a reviewer
                          scanning a queue would meet the test under one shape on
                          one row and another shape on the next. Awkward and the
                          document's own beats fluent and ours -- and the reading
                          stays true either way, which is the only thing a
                          reviewer is checking.
                        */}
                        {read.condition === null ? (
                          <span
                            className="policy-card__reading-always"
                            title="Nothing in this rule narrows when or to whom it applies. If the document does narrow it, that is missing and this is where to say so."
                          >
                            in every case
                          </span>
                        ) : (
                          <>
                            <span className="policy-card__reading-key">when</span>{" "}
                            <span className="policy-card__reading-value">
                              <DirectionalText>{read.condition}</DirectionalText>
                            </span>
                          </>
                        )}
                        {read.outcome && (
                          <>
                            {" "}
                            <span className="policy-card__reading-key">then</span>{" "}
                            <span className="policy-card__reading-value">
                              <DirectionalText>{read.outcome}</DirectionalText>
                            </span>
                          </>
                        )}
                      </p>
                    </div>
                  </li>
                    );
                  })}
                </Fragment>
              ))}
            </ol>
          </section>
        );
      })}

      {card.hiddenByFilter > 0 && (
        <Text type="secondary" className="policy-card__partial">
          {/* The content-kind split that used to make cards partial is gone, and
              with it every word about lanes, kinds and where a record went. What
              is left says two things and names no control, because the cause is
              no longer something the reviewer chose: a card can still be short
              when the queue is narrowed to one review status, since the policies
              it is assembled against are not narrowed the same way.

              Both facts are load-bearing. The first stops a fragment being read
              as a whole policy; the second stops one Approve being read as a
              judgement on rules that are not on screen. */}
          This card holds {card.rules.length} of the {card.policy.rule_count} rules this policy
          states.{" "}
          Approving here decides the {card.reviewableIds.length === 1 ? "rule" : "rules"} shown above.
        </Text>
      )}
    </article>
  );
}
