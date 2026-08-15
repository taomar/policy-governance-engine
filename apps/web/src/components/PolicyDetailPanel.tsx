import { Button, Space, Tabs, Tag, Tooltip, Typography } from "antd";
import { useEffect, useState } from "react";
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
import { PolicyAskAiButton } from "./PolicyAskAiButton";
import { PolicyCompositionChips } from "./PolicyCompositionChips";
import { composeFocus, recordStance, type RecordStance } from "../recordStance";
import { PolicyEffectBadge } from "./PolicyEffectBadge";
import { PolicyExplainButton } from "./PolicyExplainButton";
import { PolicyLogicTable } from "./PolicyLogicTable";
import { RecordActionsMenu, type RecordActionHandlers } from "./RecordActionsMenu";
import {
  PARTIES_AND_ROUTES_TAB_LABEL,
  PolicyHistoryPane,
  PolicyNotesPane,
  PolicyOverviewPane,
  PolicyPartiesAndRoutesPane,
  PolicyScopePane,
  PolicyTestsPane,
  candidatePolicyRecord,
  type PolicySightingView,
  type PolicyTestingVerbs,
} from "./policyTabPanes";
import type { PolicyTestListItem } from "../api";
import "./policyHeaderActions.css";

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
  ruleDetail,
  onApprove,
  onReject,
  policySetKey,
  policyActions,
  ruleActions,
  actions,
  tests,
  testsLoading,
  testing,
  history,
  historyLoading,
  onRequestHistory,
  documentName,
}: {
  card: PolicyCard;
  statusColor: (status: string) => string;
  statusLabel: (status: string) => string;
  /** This rule's detail, shown in place under it when the reviewer opens it.
   *
   *  A function, so a policy of fourteen rules builds detail for the ones that
   *  are open and not for the ones that are not.
   *
   *  There used to be a second control beside the expander, which took the rule
   *  to a separate surface for everything the inline detail left out. It was
   *  the old cost wearing a new label: the reviewer still left the policy they
   *  were comparing against, and still clicked back. What that surface held is
   *  now inside what this returns, so the row has one control and the policy
   *  stays on screen. */
  ruleDetail?: (ruleId: string) => React.ReactNode;
  onApprove?: () => void;
  onReject?: () => void;
  /** The set this policy belongs to, which asking about it has to name.
   *
   *  Optional, because a panel can be drawn from a card alone; the ask control
   *  is simply absent when nothing can say which set the question is about,
   *  rather than drawn and then failing when it is pressed. */
  policySetKey?: string;
  /** What the host can do to this policy beyond deciding it. Handlers, not
   *  flags: the panel does not decide who may do what, and the host does not
   *  decide how a menu is drawn. Absent handlers simply produce fewer entries. */
  policyActions?: RecordActionHandlers;
  /** What the host can do to one of this policy's rules, given its id. */
  ruleActions?: (ruleId: string) => RecordActionHandlers;
  /** Panel chrome supplied by the host (hide, fullscreen, close). */
  actions?: React.ReactNode;
  /** Every test in this policy set, from which this policy's are picked.
   *
   *  Handed in rather than fetched here, and handed in *whole*, because the
   *  policy's tests are the ones aimed at rules it holds and that question is
   *  answered from the card. Asking a server for "this policy's tests" would
   *  make it re-derive which rules are in the policy — a second opinion on
   *  grouping, free to disagree with the first.
   *
   *  `null` means nothing has been loaded, which the Tests tab says plainly. It
   *  is not the same as an empty list, which means the set has no tests. */
  tests?: readonly PolicyTestListItem[] | null;
  testsLoading?: boolean;
  /** Lets the Tests tab ask for scenarios and run them. Absent means it reports only. */
  testing?: PolicyTestingVerbs;
  /** This policy's published sightings, newest last. Supplied by the host,
   *  which knows whether the record has ever been published; a candidate that
   *  has not simply passes nothing and the tab says so. */
  history?: readonly PolicySightingView[] | null;
  historyLoading?: boolean;
  /** Asked for when the reader opens History, not before. The same policy key
   *  serves a candidate and its published sightings, so a policy under review
   *  can show what has already been published of it. */
  onRequestHistory?: (provisionKey: string) => void;
  /** The name of the document this policy was read out of, where the surface
   *  knows it. Passed through to the JSON view for one reason: whether the card
   *  showed the generated subject label is reported there, and that answer
   *  depends on this. Asking it here with a different argument than the card
   *  used would make the file disagree with the screen. */
  documentName?: string | null;
}) {
  const record = candidatePolicyRecord(card);
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

  /**
   * Which kind of rule the reviewer has chosen to look at, within this policy.
   *
   * View state, and only that. It is never read by approve, reject, export or
   * the JSON pane, it never reaches a URL or storage, and it is dropped the
   * moment a different policy is opened — so a reviewer cannot arrive at a
   * policy already narrowed by a choice they made about another one.
   */
  const [focus, setFocus] = useState<RecordStance | null>(null);
  useEffect(() => setFocus(null), [card.policy.key]);

  /**
   * The narrowing, derived once from the same component that draws the chips.
   *
   * The ordinal each rule carries is assigned over every rule of the policy
   * before this is applied, so narrowing never renumbers anything: rule 7 is
   * the seventh rule of the document whether or not rules 1 to 6 are on screen.
   * A number that changed with a view control would be a worse lie than the
   * fragment warning we just deleted, because nothing would announce it.
   */
  const focusView = composeFocus(
    card.rules,
    (rule) => recordStance(rule.rule),
    focus,
  );
  const shownRuleIds = new Set(focusView.shown.map((rule) => rule.rule_id));

  // Both read the policy and neither writes to it, so they belong together and
  // apart from the two that decide it. Each is present only when it has what it
  // needs: the explainer needs a persisted grouping to explain, and asking needs
  // the set the question is about. Neither is drawn to be pressed and fail.
  const assistive = [
    card.policy.provision_id ? (
      <PolicyExplainButton
        key="explain"
        provisionId={card.policy.provision_id}
        policyKey={card.policy.key}
      />
    ) : null,
    policySetKey ? (
      <PolicyAskAiButton
        key="ask"
        policy={card.policy}
        policySetKey={policySetKey}
      />
    ) : null,
  ].filter(Boolean);

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
        {/* Three kinds of control, kept apart.
         *
         *  Approving and rejecting change the record. Explaining and asking
         *  change nothing and produce a reading. Expanding and hiding change
         *  neither and move furniture. Run as one row of six they read as six
         *  equal options, and the two that write are the two that cannot be
         *  taken back — so each kind is its own labelled group with a rule
         *  between, and a group that has nothing in it draws neither the group
         *  nor its rule. */}
        <div className="policy-header-actions">
          {onApprove && onReject && (
            <Space
              size={4}
              wrap
              role="group"
              aria-label="Decide this policy"
              className="policy-header-actions__group"
            >
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
            </Space>
          )}
          {assistive.length > 0 && (
            <Space
              size={4}
              wrap
              role="group"
              // Named for what both do and neither decides, so the pair reads
              // as two ways of asking rather than as two spellings of one.
              // Their own labels then carry the difference: one answers a
              // question nobody typed, the other answers the reviewer's.
              aria-label="Ask about this policy"
              className="policy-header-actions__group policy-header-actions__group--assistive"
            >
              {assistive}
            </Space>
          )}
          {/* Everything else this policy admits, in the same control and the
              same place it takes on a rule row. It is never empty — a record
              can always have its id copied — so it needs no guard. */}
          <Space
            size={4}
            wrap
            role="group"
            aria-label="More for this policy"
            className="policy-header-actions__group policy-header-actions__group--more"
          >
            <RecordActionsMenu
              scope="policy"
              recordId={card.policy.key}
              recordName={title.text}
              reviewStatuses={card.reviewStatuses}
              on={policyActions}
            />
          </Space>
          {actions && (
            <Space
              size={4}
              wrap
              role="group"
              aria-label="This panel"
              className="policy-header-actions__group policy-header-actions__group--chrome"
            >
              {actions}
            </Space>
          )}
        </div>
      </div>

      <Tabs
        className="policy-detail-panel__tabs"
        defaultActiveKey="overview"
        onChange={(next) => {
          if (next === "history" && history == null && !historyLoading) {
            onRequestHistory?.(card.policy.key);
          }
        }}
        items={[
          {
            key: "overview",
            label: "Overview",
            children: <PolicyOverviewPane record={record} />,
          },
          {
            key: "reading",
            label: "Reading",
            children: (
              <>
                <PolicyCompositionChips
                  composition={focusView}
                  onFocus={setFocus}
                />
                {card.passages.map((block) => {
                  const passageRules = block.rules.map(
                    (rule) => rule.rule,
                  );
                  const quotations = passageQuotations(passageRules);
                  const name = passageTitle(passageRules);
                  // Ordinals are spent on every rule of the passage, shown or
                  // not, so the numbering is the document's and not the view's.
                  const numbered = block.rules.map((rule) => {
                    ordinal += 1;
                    return { rule, ordinal };
                  });
                  const visible = numbered.filter((entry) =>
                    shownRuleIds.has(entry.rule.rule_id),
                  );
                  // A passage none of whose rules are in focus is dropped whole
                  // rather than left as a quotation with nothing under it. The
                  // quotation is evidence for its rules; with those rules off
                  // screen it is evidence for nothing, and it would push the
                  // rules the reviewer asked for further down the page.
                  if (visible.length === 0) return null;
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
                        {visible.map(({ rule, ordinal }) => {
                          const canonical = rule.rule;
                          const decision = ruleDecisionSummary(canonical);
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
                                    rule.reviewStatus,
                                  )}
                                >
                                  {statusLabel(rule.reviewStatus)}
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
                                <RecordActionsMenu
                                  scope="rule"
                                  recordId={rule.rule_id}
                                  recordName={canonical.title}
                                  reviewStatuses={[rule.reviewStatus]}
                                  on={ruleActions?.(rule.rule_id)}
                                />
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
                                      {rule.recordId}
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

                {/*
                  There is no short-card notice here any more, and no filter
                  that could cause one: cards are assembled from every candidate
                  and then selected whole, so narrowing the queue cannot take a
                  rule off a card. Every policy shown lists every rule it holds.

                  The count itself still exists on the card as `hiddenByFilter`
                  and still reaches the JSON pane as `rules_hidden_by_filter`,
                  so the one case that is not a filter — the policy's declared
                  rule_count exceeding the records actually loaded — is still in
                  the record a reviewer can read and export. It is not shown as
                  prose because it was measured dormant across both documents,
                  and a warning nobody can trigger competes with the evidence.
                */}
              </>
            ),
          },
          {
            key: "logic",
            label: "Logic",
            children: <PolicyLogicTable card={card} />,
          },
          {
            key: "parties",
            label: PARTIES_AND_ROUTES_TAB_LABEL,
            children: <PolicyPartiesAndRoutesPane record={record} />,
          },
          {
            key: "scope",
            label: "Scope",
            children: <PolicyScopePane record={record} />,
          },
          {
            key: "tests",
            label: "Tests",
            children: <PolicyTestsPane record={record} tests={tests ?? null} loading={testsLoading} testing={testing} />,
          },
          {
            key: "history",
            label: "History",
            children: (
              <PolicyHistoryPane sightings={history ?? null} loading={historyLoading} />
            ),
          },
          {
            key: "notes",
            label: "Notes",
            children: <PolicyNotesPane record={record} />,
          },
          {
            key: "json",
            label: "JSON",
            children: (
              <section className="policy-detail-panel__section">
                <Text type="secondary" className="policy-detail-panel__section-label">
                  <CodeOutlined /> This policy as one document — its rules nested inside it
                </Text>
                {/* The download is named by the policy, not by its key: a persisted
                    provision is keyed by a digest, and a reviewer who downloads three of
                    these wants three filenames they can tell apart. */}
                <JsonView
                  value={policyJsonDocument(card, documentName)}
                  downloadName={`${(title.text || card.policy.key).replace(/[^\w.-]+/g, "_").slice(0, 80)}.json`}
                  maxHeight={420}
                />
              </section>
            ),
          },
        ]}
      />
    </div>
  );
}
