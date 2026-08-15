import { Typography } from "antd";

import { UNKNOWN_COUNT } from "../loadState";
import type { PolicyCard } from "../policyCards";
import type { LogicMark, LogicRuleReading } from "../policyLogicShape";
import { policyLogicShape } from "../policyLogicShape";
import { policyRouteLabel } from "../policyGrouping";
import { ruleTypeLabel } from "../ruleTypes";
import { DirectionalText } from "./DirectionalText";

const { Text } = Typography;

/**
 * The policy's rules compared — one rule at a time, whole.
 *
 * WHAT THIS TAB IS FOR
 *
 * The card reads a policy one rule at a time, which answers "is this rule
 * faithful" and cannot answer "is this set complete". Twenty rules read as
 * twenty paragraphs hide the fact that one of them states a time and nineteen
 * do not. That is what this tab exists to show, and it is still what it shows.
 *
 * WHY IT IS NO LONGER A GRID
 *
 * It was a grid — rules down, attributes across — and on the corpus it is asked
 * to work on, a grid cannot be read. Measured in the running app: the largest
 * policy fills fifteen attributes across eighty-four rules and laid out two and
 * a half times wider than the panel it sits in, so the reviewer discovered the
 * later attributes only by finding a horizontal scrollbar and could not see one
 * whole rule at any scroll position. That same view printed "not stated" eight
 * hundred and seventy-one times, which was the loudest thing on the screen and
 * the least informative. One long value set the height of a whole row, so rows
 * were ragged and mostly empty.
 *
 * None of that is a fault of the comparison. It is a fault of the shape. So the
 * comparison is unchanged and the shape is different: each rule is a block, and
 * each attribute of it is one row of the three parts an attribute has — its own
 * name, the document's words, and the identifier a case supplies a value for.
 * That is the same row the rule inspector draws, so a reviewer who has read one
 * rule there can read seven here without learning a second arrangement. A block
 * wraps, so nothing scrolls sideways, and the widest value in the policy costs
 * height only in the rule that states it.
 *
 * WHAT REPLACED THE COLUMN HEADS
 *
 * The counts, kept: `condition 39 of 84` is a fact about the document and the
 * one thing the grid did that reading rules one at a time cannot. They are now a
 * list above the rules instead of a header row, so they stay visible without
 * setting the width of anything.
 *
 * WHAT REPLACED THE REPEATED "NOT STATED"
 *
 * One line per rule naming the attributes that rule does not state. The fact is
 * unchanged and still per attribute — a reviewer can still see that a rule names
 * no actor — but it is said once per rule rather than once per empty cell, and
 * it is said quietly, because absence is information and not an alarm. Absence
 * stays distinct from the em dash this app reserves for "we do not know".
 *
 * WHAT IS NEW: THE SHAPE OF THE POLICY
 *
 * Two rules that filled the same set of attributes are the same shape, and at
 * scale that is what a reviewer wants first: on the largest policy two shapes
 * account for two thirds of the rules, so the rules alone in theirs are worth a
 * look. Each rule also carries a signature — one mark per attribute, in the
 * fixed order of the counts above, filled where the rule states it. The marks
 * sit at the same offset in every block, so scanning down shows which rules are
 * alike without reading a word. It is a second rendering of what the block
 * already says in full, never the only one, so it is hidden from assistive
 * technology rather than made to say everything twice.
 *
 * WHAT IT STILL DOES NOT DO
 *
 * It adds no summary, composes no sentence, and detects nothing. Every string
 * here is a run of the document, a canonical field name, or a count of rules.
 * Rules stay in document order under the passage that states them: ordering by
 * how many attributes a rule filled would rank rules by completeness, and a rule
 * the document states in words would sit at the bottom of every policy in the
 * system. Route is not a score and is not sorted on. Grouping by shape is
 * reported above and never applied to the rules themselves.
 *
 * Nothing is behind a click. There is no control here to expand, because a
 * reviewer checking whether we dropped something cannot be asked to open
 * fourteen things to find out.
 */
export function PolicyLogicTable({ card }: { card: PolicyCard }) {
  const logic = policyLogicShape(card);

  const known = logic.blocks
    .flatMap((block) => block.rules)
    .filter((rule) => !rule.unrecorded).length;
  /* Worth printing only when it says something a reader cannot get from the
     blocks themselves: that some rules are alike. One group per rule is a list
     of every rule again, so that case is said in a sentence instead. */
  const shapesCollapse = logic.shapes.length > 0 && logic.shapes.length < known;

  return (
    <div className="policy-logic" data-testid="policy-logic">
      <Text type="secondary" className="policy-detail-panel__section-label">
        What each rule states —{" "}
        {logic.total === 1 ? "1 rule" : `${logic.total} rules`}
        {logic.columns.length > 0 &&
          ` · ${logic.columns.length === 1 ? "1 attribute" : `${logic.columns.length} attributes`} where they differ`}
      </Text>

      {logic.shared.length > 0 && (
        <dl className="policy-logic__shared" data-testid="policy-logic-shared">
          {/* Said once because every rule says it the same way. Twenty cells
              carrying one value is a column a reviewer scans and learns nothing
              from, and the value itself is not dropped — it moves here. */}
          {logic.shared.map((fact) => (
            <div
              key={fact.attribute ?? fact.label}
              className="policy-logic__shared-item policy-logic__attr"
            >
              <dt className="policy-logic__col-label">
                {fact.attribute ?? fact.label}
              </dt>
              <dd className="policy-logic__stated" data-verbatim="true">
                <DirectionalText align>{fact.text}</DirectionalText>
              </dd>
              <dd className="policy-logic__fact">
                {fact.fact && (
                  <FactChip fact={fact.fact} dataType={fact.dataType} />
                )}
              </dd>
            </div>
          ))}
        </dl>
      )}
      {logic.shared.length > 0 && logic.columns.length > 0 && (
        <Text type="secondary" className="policy-logic__note">
          {logic.total === 1
            ? "Stated by this rule."
            : `Stated the same way by all ${logic.total} rules.`}
        </Text>
      )}

      {logic.columns.length === 0 ? (
        logic.shared.length === 0 && (
          <Text type="secondary">
            No decomposition was recorded for the rules of this policy, so there
            is nothing to compare here. Each rule's own statement is above.
          </Text>
        )
      ) : (
        <>
          {/* What the header row of the grid carried, kept, and no longer
              setting the width of anything. A count, not a proportion and not a
              bar: "1 of 20" is what the document did; "5%" invites reading it
              as a shortfall in the rule that is the odd one out. */}
          <ul
            className="policy-logic__coverage"
            data-testid="policy-logic-coverage"
          >
            {logic.columns.map((column) => (
              <li key={column.attribute} className="policy-logic__coverage-item">
                <span className="policy-logic__col-label">
                  {column.attribute}
                </span>
                <span className="policy-logic__col-count">
                  {column.filled} of {logic.total}
                </span>
              </li>
            ))}
          </ul>

          {shapesCollapse ? (
            <ul className="policy-logic__shapes" data-testid="policy-logic-shapes">
              {logic.shapes.map((shape, index) => (
                <li key={index} className="policy-logic__shape">
                  <span className="policy-logic__shape-count">
                    {shape.ruleOrdinals.length === 1
                      ? "1 rule"
                      : `${shape.ruleOrdinals.length} rules`}
                  </span>
                  <span className="policy-logic__shape-rules">
                    {shape.ruleOrdinals.join(", ")}
                  </span>
                  <span className="policy-logic__shape-attrs">
                    {shape.attributes.length === 0 ? (
                      <span className="policy-logic__absent-name">
                        none of these attributes
                      </span>
                    ) : (
                      shape.attributes.map((attribute) => (
                        <span
                          key={attribute}
                          className="policy-logic__col-label"
                        >
                          {attribute}
                        </span>
                      ))
                    )}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            known > 1 && (
              <Text type="secondary" className="policy-logic__note">
                No two of these {known} rules state the same set of attributes.
              </Text>
            )
          )}

          {logic.blocks.map((block, index) => (
            <section
              key={`${block.passageKey}-${index}`}
              className="policy-logic__block"
              data-testid="policy-logic-block"
            >
              {/* Which sentence these rules came from. A reviewer reading across
                  fourteen rules still needs the passage boundary; merging a
                  section onto one card must not merge its sentences into one. */}
              <h4 className="policy-logic__passage">{block.passageKey}</h4>
              {block.rules.map((rule) => (
                <RuleBlock key={rule.ruleId} rule={rule} />
              ))}
            </section>
          ))}
        </>
      )}

      {logic.unrecorded > 0 && (
        <Text type="secondary" className="policy-logic__note">
          {logic.unrecorded === 1
            ? "1 rule carries no recorded decomposition, so this view can say only that we do not know."
            : `${logic.unrecorded} rules carry no recorded decomposition, so this view can say only that we do not know.`}
        </Text>
      )}

      {card.hiddenByFilter > 0 && (
        // The head of the panel counts every rule of the policy; this compares
        // the ones the current filter admits. Without this line the tab reads as
        // a policy that lost rules between one tab and the next.
        <Text type="secondary" className="policy-logic__note">
          {card.hiddenByFilter === 1
            ? "1 more rule of this policy is outside the current filter and is not compared here."
            : `${card.hiddenByFilter} more rules of this policy are outside the current filter and are not compared here.`}
        </Text>
      )}
    </div>
  );
}

/** The identifier a case supplies a value for, and the kind of value it is. */
function FactChip({ fact, dataType }: { fact: string; dataType: string | null }) {
  return (
    <>
      <code className="policy-logic__fact-name">{fact}</code>
      {dataType && <span className="policy-logic__fact-type">{dataType}</span>}
    </>
  );
}

/** One rule, whole: what it states, then what it does not. */
function RuleBlock({ rule }: { rule: LogicRuleReading }) {
  return (
    <article
      className="policy-logic__rule"
      data-testid="policy-logic-rule"
      data-rule={rule.ruleId}
    >
      <div className="policy-logic__rule-line">
        <span className="policy-card__rule-ordinal" aria-hidden>
          {rule.ordinal}
        </span>
        <Signature marks={rule.marks} />
        <span className="policy-logic__facets">
          {rule.ruleType && <span>{ruleTypeLabel(rule.ruleType)}</span>}
          {rule.route && <span>{policyRouteLabel(rule.route)}</span>}
        </span>
      </div>

      {rule.stated.length > 0 && (
        <dl className="policy-logic__attrs">
          {rule.stated.map((attribute) => (
            <div key={attribute.attribute} className="policy-logic__attr">
              <dt className="policy-logic__col-label">{attribute.attribute}</dt>
              {/* The document's words, whole. Marked so a guard can tell what
                  this app wrote from what the document did. */}
              <dd className="policy-logic__stated" data-verbatim="true">
                <DirectionalText align>{attribute.text}</DirectionalText>
              </dd>
              <dd className="policy-logic__fact">
                {attribute.fact && (
                  <FactChip
                    fact={attribute.fact}
                    dataType={attribute.dataType}
                  />
                )}
              </dd>
            </div>
          ))}
        </dl>
      )}

      {rule.unrecorded ? (
        // Nothing is known either way, which is a different fact from absence
        // and wears the mark this app reserves for it.
        <p
          className="policy-logic__unknown"
          data-testid="policy-logic-unrecorded"
        >
          <span aria-hidden>{UNKNOWN_COUNT}</span> No decomposition was recorded
          for this rule, so whether it states any of these attributes is unknown.
        </p>
      ) : (
        rule.absent.length > 0 && (
          // A true statement about the rule: the decomposition is there and
          // names no such component. Said once, not once per empty cell.
          <p className="policy-logic__absent" data-testid="policy-logic-absent">
            <span className="policy-logic__absent-label">This rule states no</span>
            {rule.absent.map((attribute) => (
              <span key={attribute} className="policy-logic__absent-name">
                {attribute}
              </span>
            ))}
          </p>
        )
      )}
    </article>
  );
}

const MARK_CLASS: Record<LogicMark, string> = {
  stated: "policy-logic__mark--stated",
  absent: "policy-logic__mark--absent",
  unrecorded: "policy-logic__mark--unrecorded",
};

/** One mark per attribute, in the order of the counts above. A second rendering
 *  of what the block says in full, so it is spoken by neither. */
function Signature({ marks }: { marks: LogicMark[] }) {
  return (
    <span
      className="policy-logic__signature"
      aria-hidden
      data-testid="policy-logic-signature"
    >
      {marks.map((mark, index) => (
        <span
          key={index}
          className={`policy-logic__mark ${MARK_CLASS[mark]}`}
          data-mark={mark}
        />
      ))}
    </span>
  );
}
