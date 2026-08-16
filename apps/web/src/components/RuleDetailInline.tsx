import { useMemo } from "react";
import { Button, Descriptions, Typography } from "antd";
import { ExportOutlined } from "@ant-design/icons";
import type { AggregateLimit, CandidateRule, CanonicalRule } from "../api";
import { UNKNOWN_COUNT } from "../loadState";
import { DirectionalText } from "./DirectionalText";
import { RecordedAttributes } from "./RecordedAttributes";
import { ConditionView } from "./ConditionView";
import { ConditionRouteNote } from "./ConditionRouteNote";
import { DecisionReadinessView } from "./DecisionReadinessView";
import { NotesPanel } from "./NotesPanel";
import { RuleName } from "./RuleName";
import { InlineTabs, type InlineTabItem } from "./InlineTabs";
import { RuleJsonPane, RuleLogicPane, RuleScopePane, RuleTechnicalMetadata } from "./ruleTabPanes";
import { effectActionText, isEmptyCondition } from "../ruleDisplay";

const { Text } = Typography;

/**
 * One rule, in full, rendered where the rule stands.
 *
 * The queue used to answer "what does this rule actually say?" by replacing the
 * surface the reviewer was reading. They left the policy to read the rule and
 * clicked back to return, and the passage, the sibling rules and the scroll
 * position all went away while they were gone — so the one comparison a
 * reviewer makes constantly, this rule against the rest of its policy, was the
 * one thing the interface took away at the moment they needed it.
 *
 * It then answered it twice: a short inline detail beside a second control that
 * still sent the reviewer away for everything the short version left out. Two
 * controls on every row, one of which was the old cost wearing a new label.
 *
 * There is now one control. It opens here, and everything that used to be on
 * the other surface opens with it, arranged as the tabs it was already
 * arranged into — the same components, not a second rendering of the same
 * record, so the two cannot come to disagree.
 *
 * WHY TABS, GIVEN THAT NOTHING A REVIEWER NEEDS MAY BE BEHIND A CLICK
 *
 * Because the first tab is not behind one. It opens with the row and holds the
 * whole of what a reviewer judges: the document's words, every attribute as
 * recorded, the test, what follows, and the exceptions the same passage states.
 * A reviewer who reads that tab and never touches another has been given the
 * decision. The rest answer questions that only arise after it — how the same
 * rule reads as logic, who it names, what it reaches, where it came from and
 * what has happened to it since, and its stored forms. Those are references,
 * and a reference that is one key away is not hidden.
 *
 * The alternative — seven sections stacked — was measured against a real
 * policy, not imagined: it puts a JSON viewer and a version table between the
 * reviewer and the next rule on every row they open.
 *
 * WHAT THIS COSTS TO OPEN
 *
 * One tab's body. `InlineTabs` takes each body as a function and calls only the
 * open one, so a row that is expanded builds one pane and a row that is closed
 * builds nothing at all — the detail is not rendered-and-hidden, it does not
 * exist. That is what makes this safe on a policy holding dozens of rules.
 *
 * Nothing here fetches except the two tabs that must: notes, which are written
 * by people after the fact and cannot be in the record, and the generated name,
 * which resolves to nothing and renders nothing when it has nothing to say.
 * Notes are behind their own tab, so no row pays for them until asked. Every
 * other pane reads the record already in hand — there is no state in which any
 * of them can sit on "Loading…", which is what the two panels in this app that
 * did are a standing warning about. Where a field can be genuinely absent from
 * the payload rather than merely empty, the two are said differently:
 * `attributes` missing means the record did not carry the table, which is not
 * the same claim as the table being here and naming nothing.
 *
 * What is deliberately still NOT here: the source document body, with the
 * clause highlighted in it. That one needs a request per rule and a viewer the
 * width of a page, and putting it in a queue row would mean every opened row
 * starting a fetch and then holding a spinner where a quotation should be. The
 * full record keeps it, and the link at the foot of this goes there.
 */
export function RuleDetailInline({
  candidate,
  onOpenFullRecord,
  className,
  statementVisibleAbove = false,
  allRules,
  onSelectRule,
  aggregateLimits,
}: {
  candidate: CandidateRule;
  /** Open the larger surface for this rule. Omitted where it isn't reachable. */
  onOpenFullRecord?: () => void;
  className?: string;
  /**
   * The caller already shows this rule's statement, verbatim, above this.
   *
   * Set where the surrounding card quotes the passage: repeating it here is the
   * one thing an expansion can do that is worse than showing nothing, because
   * it charges a click for text the reviewer has already read. Left false where
   * nothing above carries the words — a queue row shows a title, and a title is
   * not the statement.
   */
  statementVisibleAbove?: boolean;
  /** The rest of this rule's set, so rule references can be jumped to. */
  allRules?: CanonicalRule[];
  onSelectRule?: (rule: CanonicalRule) => void;
  aggregateLimits?: AggregateLimit[];
}) {
  const rule = candidate.rule;
  const attributes = rule.attributes;

  const conditionEmpty = useMemo(() => isEmptyCondition(rule.condition), [rule.condition]);

  const overview = () => (
    <div className="rule-detail-inline__panes">
      {!statementVisibleAbove && (
        <section className="rule-detail-inline__block">
          <h4 className="rule-detail-inline__heading">What the document says</h4>
          {rule.description.trim() ? (
            <DirectionalText as="p" align className="rule-detail-inline__prose">
              {rule.description}
            </DirectionalText>
          ) : (
            <Text type="secondary" className="rule-detail-inline__quiet">
              The record carries no statement for this rule beyond its title.
            </Text>
          )}
        </section>
      )}

      <RecordedAttributes attributes={attributes} />

      <section className="rule-detail-inline__block">
        <h4 className="rule-detail-inline__heading">The test, as recorded</h4>
        {conditionEmpty ? (
          <Text type="secondary" className="rule-detail-inline__quiet">
            No comparison between named quantities was recorded for this one, so the words above are
            what a case is judged against.
          </Text>
        ) : (
          <div className="rule-detail-inline__condition">
            <ConditionView node={rule.condition} />
          </div>
        )}
        <ConditionRouteNote provenance={rule.condition_provenance} />
      </section>

      <section className="rule-detail-inline__block">
        <h4 className="rule-detail-inline__heading">Then</h4>
        <DirectionalText as="p" align className="rule-detail-inline__prose">
          {effectActionText(rule.effect)}
        </DirectionalText>
      </section>

      {rule.exceptions.length > 0 && (
        <section className="rule-detail-inline__block">
          <h4 className="rule-detail-inline__heading">
            Exceptions the same passage states ({rule.exceptions.length})
          </h4>
          <ul className="rule-detail-inline__list">
            {rule.exceptions.map((ex) => (
              <li key={ex.exception_id}>
                <DirectionalText align>{ex.description}</DirectionalText>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );

  const history = () => (
    <div className="rule-detail-inline__panes">
      <section className="rule-detail-inline__block">
        <h4 className="rule-detail-inline__heading">Where it came from</h4>
        {rule.evidence.length === 0 ? (
          <Text type="secondary" className="rule-detail-inline__quiet">
            No source citation is recorded on this rule.
          </Text>
        ) : (
          <ul className="rule-detail-inline__list">
            {rule.evidence.map((ev, idx) => (
              <li key={`${ev.document_version_id}-${ev.clause_id ?? idx}`}>
                <span className="rule-detail-inline__mono">{ev.section ?? "no section recorded"}</span>
                {ev.page !== null && <span> · page {ev.page}</span>}
                {ev.clause_id && <span> · clause {ev.clause_id}</span>}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="rule-detail-inline__block">
        <h4 className="rule-detail-inline__heading">What has happened to this record</h4>
        <Descriptions column={1} size="small" bordered className="inspector-descriptions">
          <Descriptions.Item label="Revision">rev {candidate.revision}</Descriptions.Item>
          <Descriptions.Item label="Review state">{candidate.review_status}</Descriptions.Item>
          <Descriptions.Item label="Drafted">
            {new Date(candidate.created_at).toLocaleString()}
          </Descriptions.Item>
          {candidate.reviewed_by !== null && (
            <Descriptions.Item label="Reviewed by">{candidate.reviewed_by}</Descriptions.Item>
          )}
          {candidate.reviewed_at !== null && (
            <Descriptions.Item label="Reviewed at">
              {new Date(candidate.reviewed_at).toLocaleString()}
            </Descriptions.Item>
          )}
          {/* Absent is its own answer: a record drafted before this was tracked
              has no comparison to show, which is not the same as having been
              compared and found unchanged. */}
          <Descriptions.Item label="Against the previous reading">
            {candidate.delta_status === null ? (
              <Text type="secondary">
                {UNKNOWN_COUNT} Not recorded for this one — it predates the comparison being kept.
              </Text>
            ) : (
              <>
                {candidate.delta_status}
                {candidate.reworded && <Text type="secondary"> · same meaning, rewritten wording</Text>}
              </>
            )}
          </Descriptions.Item>
          {candidate.superseded_by_candidate_id !== null && (
            <Descriptions.Item label="Replaced by">
              <span className="rule-detail-inline__mono">{candidate.superseded_by_candidate_id}</span>
            </Descriptions.Item>
          )}
          <Descriptions.Item label="Extraction record">
            <span className="rule-detail-inline__mono">{candidate.id}</span>
          </Descriptions.Item>
        </Descriptions>
      </section>

      <RuleTechnicalMetadata rule={rule} />
    </div>
  );

  const items: InlineTabItem[] = [
    { key: "overview", label: "Overview", render: overview },
    {
      key: "logic",
      label: "Logic",
      render: () => (
        <RuleLogicPane
          rule={rule}
          allRules={allRules}
          onSelectRule={onSelectRule}
          aggregateLimits={aggregateLimits}
        />
      ),
    },
    {
      key: "readiness",
      label: "Parties & routes",
      render: () => (
        <div className="inspector-pane">
          <DecisionReadinessView rule={rule} />
        </div>
      ),
    },
    {
      key: "scope",
      label: "Scope",
      render: () => <RuleScopePane rule={rule} allRules={allRules} onSelectRule={onSelectRule} />,
    },
    { key: "history", label: "History", render: history },
    {
      key: "notes",
      label: "Notes",
      render: () => (
        <div className="inspector-pane">
          <NotesPanel entityType="candidate_rule" entityId={candidate.id} title="Review discussion" />
        </div>
      ),
    },
    { key: "json", label: "JSON", render: () => <RuleJsonPane rule={rule} /> },
  ];

  return (
    <div className={`rule-detail-inline${className ? ` ${className}` : ""}`}>
      {/* Says what the rule is for, in a few words, above the record that says
          it at length. Renders nothing when no name has been generated, so it
          costs an empty line in exactly no case. */}
      <RuleName candidateId={candidate.id} variant="block" />

      <InlineTabs items={items} ariaLabel={`${rule.title} — detail`} className="rule-detail-inline__tabs" />

      {onOpenFullRecord && (
        <div className="rule-detail-inline__footer">
          <Button size="small" type="link" icon={<ExportOutlined />} onClick={onOpenFullRecord}>
            Open the full record — the source document, with this rule&rsquo;s passage in it
          </Button>
        </div>
      )}
    </div>
  );
}