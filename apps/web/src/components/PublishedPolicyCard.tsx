import { useState } from "react";
import { Checkbox, Space, Tabs, Tag, Tooltip, Typography } from "antd";
import type { AggregateLimit, CanonicalRule, PolicyTestListItem } from "../api";
import {
  passagePageLabel,
  passageQuotations,
  policyTopicLabel,
} from "../policyCards";
import { policyRouteLabel, policyRuleCountLabel } from "../policyGrouping";
import { readPassage } from "../policyReading";
import {
  policyComposition,
  policyCompositionLabel,
  publishedPolicyJsonDocument,
  publishedPolicyTitle,
  publishedSharedFacets,
  type PublishedPolicyCard as PublishedPolicyCardModel,
} from "../publishedPolicyCards";
import { ruleTypeLabel } from "../ruleTypes";
import { DirectionalText } from "./DirectionalText";
import { MarkedQuotation } from "./MarkedQuotation";
import {
  PARTIES_AND_ROUTES_TAB_LABEL,
  PolicyHistoryPane,
  PolicyNotesPane,
  PolicyOverviewPane,
  PolicyPartiesAndRoutesPane,
  PolicyScopePane,
  PolicyTestsPane,
  publishedPolicyRecord,
  type PolicySightingView,
} from "./policyTabPanes";
import { PolicyEffectBadge } from "./PolicyEffectBadge";
import { PolicyExplainButton } from "./PolicyExplainButton";
import { PolicyAskAiButton } from "./PolicyAskAiButton";
import { PublishedRuleAskAiButton } from "./PublishedRuleAskAiButton";
import { RecordActionsMenu } from "./RecordActionsMenu";
import { RuleCard } from "./RuleCard";
import { RuleName } from "./RuleName";

const { Text } = Typography;

/**
 * One section of a published version, as one thing to read.
 *
 * WHAT THIS REPLACES
 *
 * A flat list of records grouped by the kind of rule each one is. That is a
 * taxonomy this system assigns, not a structure the document has, and grouping
 * by it took every policy the document states and dealt it out across several
 * headings — so one section of a handbook appeared as pieces under names it
 * never wrote, with nothing on screen saying the pieces belonged together. The
 * review queue was rebuilt around the document's own sections; this is the same
 * arrangement on the other side of publication, because a policy does not stop
 * being one policy when it is approved.
 *
 * WHAT IS DIFFERENT FROM THE QUEUE, AND WHY
 *
 * Nothing here decides anything. A published version is an immutable snapshot,
 * so there is no approve, no reject, no edit and no draft: those record a
 * judgement, and the judgement on these records was already made and sealed
 * into a numbered version. What remains is `Revise`, which does not change this
 * record at all — it starts a new one and leaves the published version standing.
 *
 * The selection control is likewise not a decision. On the queue it gathers
 * records for a review action; here it gathers them for an export, which is a
 * read.
 *
 * WHY THE CARD IS THE UNIT AND NOT THE ROW
 *
 * A policy is what a document states and what a person asks about. Splitting it
 * into rows and letting the reader reassemble it is how the two surfaces drifted
 * apart; the count on the head is the policy's own, so a card that is showing
 * fewer rules than the policy holds says so rather than presenting a fragment
 * as the whole.
 */
export function PublishedPolicyCard({
  card,
  open,
  selectedForExport,
  indeterminateForExport,
  aggregateLimits,
  expandedRuleId,
  onToggleExportSelection,
  onOpen,
  onSelectRule,
  onToggleRule,
  onRevise,
  onViewHistory,
  tests,
  testsLoading,
  history,
  historyLoading,
  onRequestHistory,
  policySetKey,
  policyVersionId,
}: {
  card: PublishedPolicyCardModel;
  /** This policy is the one showing in the detail panel. */
  open: boolean;
  /** Every rule of this policy is in the export selection. */
  selectedForExport: boolean;
  /** Some but not all of them are. */
  indeterminateForExport: boolean;
  aggregateLimits?: AggregateLimit[];
  /** The rule whose detail is expanded in place, if any. */
  expandedRuleId?: string | null;
  onToggleExportSelection?: () => void;
  onOpen: () => void;
  onSelectRule: (rule: CanonicalRule) => void;
  onToggleRule: (rule: CanonicalRule) => void;
  /** Present only when this version is the one a revision may start from. */
  onRevise?: (rule: CanonicalRule) => void;
  onViewHistory?: (rule: CanonicalRule) => void;
  /** The policy set's tests, whole. Filtered to this policy's rules here, for
   *  the same reason the queue does it: a policy's tests are the ones aimed at
   *  rules it holds, and that is answered from the card rather than by asking a
   *  server to re-derive the grouping. `null` means not loaded, which is not
   *  the same as none. */
  tests?: readonly PolicyTestListItem[] | null;
  testsLoading?: boolean;
  /** This policy's sightings across published versions, newest last. */
  history?: readonly PolicySightingView[] | null;
  historyLoading?: boolean;
  /** Asked for when the reader opens History, not before. A version holds many
   *  policies and each has its own history; fetching all of them to render one
   *  card's tab spends a request per policy on a tab most readers never open. */
  onRequestHistory?: (provisionKey: string) => void;
  /** Where this record is published, which together with a rule id is what
   *  identifies it. Asking without the version reaches the draft row that
   *  produced the rule — the same id, possibly revised since — so a question
   *  about a sealed record could be answered from the one still under review.
   *  These are not permissions and grant nothing: a question is not a decision,
   *  so nothing here is derived from editability. */
  policySetKey: string;
  policyVersionId: string;
}) {
  const [tab, setTab] = useState<string>("reading");
  const record = publishedPolicyRecord(card);
  const title = publishedPolicyTitle(card.policy, card.passages);
  const topicLabel = policyTopicLabel(card.policy);
  const page = passagePageLabel(card.policy.page);
  const shared = publishedSharedFacets(card);
  // Shown only where the rule-type badge is not: the effect is a function of
  // the type in nearly every combination that occurs, so the two together are
  // the same fact twice at different resolutions.
  const sharedEffect = shared.effectType && !shared.ruleType ? card.rules[0]?.rule.effect : undefined;
  const composition = policyCompositionLabel(policyComposition(card.rules));
  // The headings above this one. The innermost is the card's own title, so it
  // is not repeated in the trail.
  const trail = card.policy.heading_path.slice(0, -1);
  let ordinal = 0;

  const ruleDetail = (rule: CanonicalRule) => (
    <div className="policy-card__rule-detail" data-testid="policy-card-rule-detail">
      <RuleCard
        rule={rule}
        defaultExpanded
        hideNotes
        aggregateLimits={aggregateLimits}
        onRevise={onRevise}
        headerActions={
          <RecordActionsMenu
            scope="rule"
            recordId={rule.rule_id}
            recordName={rule.rule_id}
            reviewStatuses={["published"]}
            on={{
              revise: onRevise ? () => onRevise(rule) : undefined,
              "view-history": onViewHistory ? () => onViewHistory(rule) : undefined,
            }}
          />
        }
      />
    </div>
  );

  const reading = (
    <>
      {card.passages.map((block) => {
        const passageRules = block.rules.map((entry) => entry.rule);
        const read = readPassage(passageQuotations(passageRules), passageRules, ordinal + 1);
        ordinal += passageRules.length;
        return (
          <section
            key={block.passage.key}
            className="policy-card__passage-block"
            data-testid="policy-passage"
            data-passage={block.passage.key}
          >
            {read.quotations.length > 0 ? (
              read.quotations.map((quotation, index) => (
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
                The source text for this passage was not stored with its rules.
              </Text>
            )}

            <ol className="policy-card__rules">
              {block.rules.map((entry, index) => {
                const line = read.rules[index];
                const expanded = expandedRuleId === entry.rule_id;
                return (
                  <li
                    key={entry.rule_id}
                    className="policy-card__rule"
                    data-testid="policy-card-rule"
                    data-rule={entry.rule_id}
                    value={line.ordinal}
                  >
                    <span className="policy-card__rule-ordinal" aria-hidden>
                      {line.ordinal}
                    </span>
                    <div className="policy-card__rule-body">
                      {/* This app's handle for the rule, above the rule's own
                          words — the same aid the queue draws, reached by the
                          rule's own identifier because a published version
                          holds no draft row to ask about. Renders nothing at
                          all until one has been generated. */}
                      <RuleName
                        policySetKey={policySetKey}
                        ruleId={entry.rule_id}
                        variant="block"
                      />
                      <div className="policy-card__rule-line">
                        {line.statementIsMarkedWhole ? (
                          <Text type="secondary" className="policy-card__rule-restated">
                            This rule is the highlighted sentence above, word for word.
                          </Text>
                        ) : (
                          <span className="policy-card__rule-title">
                            <DirectionalText>{line.statement}</DirectionalText>
                          </span>
                        )}
                        {/* Only what this rule does not share with its
                            neighbours, so a badge here always carries
                            something worth stopping for. */}
                        {!shared.effectType && shared.ruleType !== null && (
                          <PolicyEffectBadge effect={entry.rule.effect} size="small" />
                        )}
                        {!shared.ruleType && (
                          <Tooltip title="The kind of rule this is. It differs from the others in this policy.">
                            <Tag variant="filled">{ruleTypeLabel(entry.rule.rule_type)}</Tag>
                          </Tooltip>
                        )}
                        {!shared.route && (
                          <Tooltip title="How this rule is decided. It differs from the others in this policy, which is normal.">
                            <Tag variant="filled" className="policy-card__rule-route">
                              {policyRouteLabel(entry.evaluation_mode)}
                            </Tag>
                          </Tooltip>
                        )}
                      </div>
                      <p className="policy-card__rule-reading">
                        {line.condition === null ? (
                          <span
                            className="policy-card__reading-always"
                            title="Nothing in this rule narrows when or to whom it applies."
                          >
                            in every case
                          </span>
                        ) : (
                          <>
                            <span className="policy-card__reading-key">when</span>{" "}
                            <span className="policy-card__reading-value">
                              <DirectionalText>{line.condition}</DirectionalText>
                            </span>
                          </>
                        )}
                        {line.outcome && (
                          <>
                            {" "}
                            <span className="policy-card__reading-key">then</span>{" "}
                            <span className="policy-card__reading-value">
                              <DirectionalText>{line.outcome}</DirectionalText>
                            </span>
                          </>
                        )}
                      </p>
                      {/* The rule's own detail opens here rather than in a
                          panel elsewhere, so the words it was read from stay
                          on screen beside it. */}
                      {expanded && ruleDetail(entry.rule)}
                    </div>
                    <Space size={2} className="policy-card__rule-actions">
                      <button
                        type="button"
                        className="policy-card__rule-open"
                        aria-expanded={expanded}
                        onClick={() => {
                          onToggleRule(entry.rule);
                          onSelectRule(entry.rule);
                        }}
                      >
                        {expanded ? "Hide rule" : "Open rule"}
                      </button>
                      <PublishedRuleAskAiButton
                        rule={entry.rule}
                        policySetKey={policySetKey}
                        policyVersionId={policyVersionId}
                      />
                      <RecordActionsMenu
                        scope="rule"
                        recordId={entry.rule.rule_id}
                        recordName={entry.rule.rule_id}
                        reviewStatuses={["published"]}
                        on={{
                          revise: onRevise ? () => onRevise(entry.rule) : undefined,
                          "view-history": onViewHistory
                            ? () => onViewHistory(entry.rule)
                            : undefined,
                        }}
                      />
                    </Space>
                  </li>
                );
              })}
            </ol>
          </section>
        );
      })}
    </>
  );

  const logic = (
    <div className="policy-card__logic" data-testid="published-policy-logic">
      {card.rules.map((entry) => (
        <div key={entry.rule_id} className="policy-card__logic-rule">
          <RuleCard
            rule={entry.rule}
            defaultExpanded
            hideNotes
            aggregateLimits={aggregateLimits}
            onRevise={onRevise}
            headerActions={
              <RecordActionsMenu
                scope="rule"
                recordId={entry.rule.rule_id}
                recordName={entry.rule.rule_id}
                reviewStatuses={["published"]}
                on={{
                  revise: onRevise ? () => onRevise(entry.rule) : undefined,
                  "view-history": onViewHistory ? () => onViewHistory(entry.rule) : undefined,
                }}
              />
            }
          />
        </div>
      ))}
    </div>
  );

  return (
    <article
      className={`policy-card${open ? " policy-card--open" : ""}`}
      data-testid="published-policy-card"
      data-policy={card.policy.key}
      data-passage={card.passages[0]?.passage.key ?? card.policy.key}
      data-title-from={title.source}
      aria-label={`Policy ${title.text || card.policy.key}`}
    >
      <div className="policy-card__head">
        {onToggleExportSelection && (
          <Tooltip
            title={`Include this policy's ${
              card.rules.length === 1 ? "rule" : `${card.rules.length} rules`
            } in the export selection`}
          >
            <Checkbox
              checked={selectedForExport}
              indeterminate={indeterminateForExport}
              onChange={onToggleExportSelection}
              onClick={(e) => e.stopPropagation()}
            />
          </Tooltip>
        )}
        <div className="policy-card__headings">
          {topicLabel.state === "named" && (
            <p className="policy-card__topic" data-generated="true" data-testid="policy-topic-label">
              <span className="policy-card__topic-mark" aria-hidden>
                ✦
              </span>
              <span className="policy-card__topic-what">Subject, named by this app:</span>{" "}
              <span className="policy-card__topic-text" title={topicLabel.provenance}>
                <DirectionalText>{topicLabel.text}</DirectionalText>
              </span>
            </p>
          )}
          {trail.length > 0 && (
            <p className="policy-card__trail" data-testid="policy-heading-trail">
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
            <span>{policyRuleCountLabel(card.rules.length, card.policy.rule_count)}</span>
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
              <Tooltip title="Where the source states a test as a comparison it is evaluated directly. Where the source states it in words it is decided by reading. Every rule of this policy takes this route; where they differ, each rule below says which it takes.">
                <Tag variant="filled" className="policy-card__route">
                  {policyRouteLabel(shared.route)}
                </Tag>
              </Tooltip>
            )}
          </div>
        </div>
        <Space size={4} className="policy-card__actions">
          {card.policy.provision_id && (
            <PolicyExplainButton provisionId={card.policy.provision_id} policyKey={card.policy.key} />
          )}
          <PolicyAskAiButton
            policy={card.policy}
            policySetKey={policySetKey}
            policyVersionId={policyVersionId}
          />
        </Space>
      </div>

      <Tabs
        size="small"
        activeKey={tab}
        onChange={(next) => {
          setTab(next);
          if (next === "history" && history == null && !historyLoading) {
            onRequestHistory?.(card.policy.key);
          }
        }}
        className="policy-card__tabs"
        items={[
          { key: "overview", label: "Overview", children: <PolicyOverviewPane record={record} /> },
          { key: "reading", label: "Reading", children: reading },
          { key: "logic", label: "Logic", children: logic },
          {
            key: "parties",
            label: PARTIES_AND_ROUTES_TAB_LABEL,
            children: <PolicyPartiesAndRoutesPane record={record} />,
          },
          { key: "scope", label: "Scope", children: <PolicyScopePane record={record} /> },
          {
            key: "tests",
            label: "Tests",
            children: <PolicyTestsPane record={record} tests={tests ?? null} loading={testsLoading} />,
          },
          {
            key: "history",
            label: "History",
            children: <PolicyHistoryPane sightings={history ?? null} loading={historyLoading} />,
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
              <section className="policy-card__json" data-testid="published-policy-json">
                <Text type="secondary" className="policy-card__json-label">
                  This policy as one document — its rules nested inside it
                </Text>
                <pre className="policy-card__json-body">
                  {JSON.stringify(publishedPolicyJsonDocument(card), null, 2)}
                </pre>
              </section>
            ),
          },
        ]}
      />

      {card.hiddenByFilter > 0 && (
        <Text type="secondary" className="policy-card__partial" data-testid="policy-card-partial">
          {/* A fragment presented as a whole policy is worse than no grouping
              at all, so the gap is stated rather than left to be read off two
              numbers that do not agree. */}
          {card.hiddenByFilter === 1
            ? "1 more rule of this policy is not served by this version, so it is not on this card."
            : `${card.hiddenByFilter} more rules of this policy are not served by this version, so they are not on this card.`}
        </Text>
      )}
    </article>
  );
}
