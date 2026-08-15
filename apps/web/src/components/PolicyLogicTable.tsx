import { Typography } from "antd";
import { Fragment } from "react";

import { UNKNOWN_COUNT } from "../loadState";
import type { PolicyCard } from "../policyCards";
import type {
  LogicAttributeReading,
  LogicBranch,
  LogicMark,
  LogicRuleReading,
  LogicShapeMember,
} from "../policyLogicShape";
import { policyLogicShape } from "../policyLogicShape";
import { policyRouteLabel } from "../policyGrouping";
import { ruleTypeLabel } from "../ruleTypes";
import { DirectionalText } from "./DirectionalText";

const { Text } = Typography;

/**
 * The policy's rules compared — one rule at a time, whole, each drawn the way
 * the rule inspector draws it.
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
 * None of that is a fault of the comparison. It is a fault of the shape.
 *
 * THE SHAPE IT HAS INSTEAD, AND WHY IT IS NOT A NEW ONE
 *
 * Two other surfaces already draw a rule's logic — the inspector's own tab and
 * the live preview beside the revise form — and both draw it the same way: what
 * scopes the rule under `APPLIES`, what follows from it under the effect the
 * record declares, each attribute one row of its own name, the document's words
 * and the identifier a case supplies a value for. A reviewer moving between
 * those and this one should not have to learn a second arrangement of the same
 * record, so this draws the same tree, from the same rows, with the same class
 * names — the rows here and the rows there are laid out by one rule in one
 * stylesheet, not by two that happen to agree today.
 *
 * The overview above the rules is what this view adds, because it is the part
 * only a policy has: how many of its rules state each attribute, which rules
 * state the same set as each other, and what they all state alike. That
 * composes with the tree instead of competing with it — the counts say where to
 * look and the trees say what is there.
 *
 * A sentence with its constituents marked up was the other candidate and was
 * rejected for the same reason: it reads well, and it would have been a third
 * way of showing one record, on the screen a reviewer arrives at from the other
 * two.
 *
 * WHY THE GROUPS DO NOT COLLAPSE
 *
 * The inspector's tree has a switcher on each group because it draws one rule.
 * This draws eighty-four, and eighty-four rules is a hundred and sixty-eight
 * switchers — a hundred and sixty-eight tab stops between a reviewer and the
 * bottom of the policy, and a hundred and sixty-eight chances for the view to
 * be showing less than it holds. A reviewer checking whether we dropped
 * something cannot be asked to open things to find out. So the groups keep the
 * heading and the indent guide and drop the control, and nothing here is behind
 * a click.
 *
 * WHAT REPLACED THE REPEATED "NOT STATED"
 *
 * One line per half of a rule, naming the attributes that half does not state.
 * The fact is unchanged and still per attribute — a reviewer can still see that
 * a rule names no actor — but it is said once rather than once per empty cell,
 * and quietly, because absence is information and not an alarm. It stays
 * distinct from the em dash this app reserves for "we do not know".
 *
 * WHAT IS NOT HERE, AND WHY
 *
 * The live preview also carries who set the rule, what it applies to and its
 * priority. Measured over the live corpus, every rule of both stored documents
 * carries the same authority, an empty scope and priority zero, so at policy
 * scale those are three identical lines per rule and nothing a reviewer could
 * compare. They are worth showing where one rule is the subject; here they
 * would be four hundred cells that look like evidence and are not.
 *
 * WHAT IT STILL DOES NOT DO
 *
 * It adds no summary, composes no sentence, and detects nothing. Every string
 * here is a run of the document, a canonical field name, an effect the record
 * declares, or a count of rules. Rules stay in document order under the passage
 * that states them: ordering by how many attributes a rule filled would rank
 * rules by completeness, and a rule whose test the source states in words would
 * sit at the bottom of every policy in the system.
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
          ` · ${logic.columns.length === 1 ? "1 attribute" : `${logic.columns.length} attributes`} across them`}
      </Text>

      {logic.columns.length === 0 ? (
        <Text type="secondary">
          No decomposition was recorded for the rules of this policy, so there is
          nothing to compare here. Each rule's own statement is above.
        </Text>
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
              <li
                key={`${column.side}-${column.attribute}`}
                className="policy-logic__coverage-item"
                data-side={column.side}
              >
                <span className="policy-logic__col-label">
                  <Wrappable text={column.attribute} />
                </span>
                <span className="policy-logic__col-count">
                  {column.filled} of {logic.total}
                </span>
              </li>
            ))}
          </ul>

          {logic.shared.length > 0 && (
            <Text type="secondary" className="policy-logic__note">
              {logic.total === 1
                ? `This rule states ${listNames(logic.shared.map((fact) => fact.attribute))}.`
                : `All ${logic.total} rules state ${listNames(logic.shared.map((fact) => fact.attribute))} with the same words.`}
            </Text>
          )}

          {shapesCollapse ? (
            <ul className="policy-logic__shapes" data-testid="policy-logic-shapes">
              {logic.shapes.map((shape, index) => (
                <li key={index} className="policy-logic__shape">
                  <span className="policy-logic__shape-count">
                    {shape.rules.length === 1
                      ? "1 rule"
                      : `${shape.rules.length} rules`}
                  </span>
                  <span className="policy-logic__shape-rules">
                    {shape.rules.map((member) => (
                      <JumpToRule key={member.ruleId} member={member} />
                    ))}
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
                          <Wrappable text={attribute} />
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

/** Canonical names run together, so a sentence about them stays a sentence. */
function listNames(names: string[]): string {
  if (names.length <= 1) return names.join("");
  return `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
}

/** Where one part of a name ends and the next begins, in any naming style. */
const SEAM = /[_\-./\s]/;

/**
 * A canonical name, whole, wherever the room for it runs out.
 *
 * A name can be longer than the space beside a value. It may not be shortened
 * and it may not push its row sideways, which leaves wrapping — so this says
 * where a wrap may land: at the seams the name already has, between its parts
 * rather than inside one. A name with no seam still wraps, because a name that
 * ran off the row would be a name the reviewer could not read. Nothing is added
 * to the text: the marks are break opportunities, and the name a reader copies
 * is the name the record holds.
 */
function Wrappable({ text }: { text: string }) {
  const parts: string[] = [];
  let start = 0;
  for (let index = 0; index < text.length; index += 1) {
    if (SEAM.test(text[index])) {
      parts.push(text.slice(start, index + 1));
      start = index + 1;
    }
  }
  if (start < text.length || parts.length === 0) parts.push(text.slice(start));

  return (
    <>
      {parts.map((part, index) => (
        <Fragment key={index}>
          {index > 0 && <wbr />}
          {part}
        </Fragment>
      ))}
    </>
  );
}

/** The identifier a case supplies a value for, and the kind of value it is. */
function FactChip({ fact, dataType }: { fact: string; dataType: string | null }) {
  return (
    <code className="policy-attr-fact-name policy-logic__fact-name">
      {fact}
      {dataType ? `: ${dataType}` : ""}
    </code>
  );
}

/**
 * One attribute, in three parts and nothing else.
 *
 * Wears the classes the rule inspector's rows wear, so the two surfaces are
 * laid out by the same stylesheet rule rather than by two that were written to
 * look alike. It also wears this view's own names, which its guards address and
 * which keep the value's freedom to wrap checkable from here.
 */
function AttributeRow({ row }: { row: LogicAttributeReading }) {
  return (
    <div className="policy-attr policy-logic__attr">
      <dt className="policy-attr-name policy-logic__col-label">
        <Wrappable text={row.attribute} />
      </dt>
      {/* The document's words, whole. Marked so a guard can tell what this app
          wrote from what the document did. */}
      <dd
        className="policy-attr-value policy-logic__stated"
        data-verbatim="true"
      >
        <DirectionalText align>{row.text}</DirectionalText>
      </dd>
      <dd className="policy-attr-fact policy-logic__fact">
        {row.fact && <FactChip fact={row.fact} dataType={row.dataType} />}
      </dd>
    </div>
  );
}

/** What scopes a rule, or what follows from it — the inspector's two groups. */
function Branch({ branch }: { branch: LogicBranch }) {
  return (
    <div
      className="policy-logic__branch"
      data-testid="policy-logic-branch"
      data-side={branch.side}
    >
      <span className="cond-group-label policy-logic__branch-label">
        {branch.heading}
      </span>

      {branch.rows.length > 0 && (
        <dl className="policy-logic__branch-rows">
          {branch.rows.map((row) => (
            <AttributeRow key={`${row.side}-${row.attribute}`} row={row} />
          ))}
        </dl>
      )}

      {branch.absent.length > 0 && (
        // A true statement about the rule: the decomposition is there and names
        // no such component. Said once, not once per empty cell.
        <p className="policy-logic__absent" data-testid="policy-logic-absent">
          <span className="policy-logic__absent-label">states no</span>
          {branch.absent.map((attribute) => (
            <span key={attribute} className="policy-logic__absent-name">
              <Wrappable text={attribute} />
            </span>
          ))}
        </p>
      )}
    </div>
  );
}

/** Where a rule's own block sits in the document, addressable from elsewhere. */
function blockId(ruleId: string): string {
  return `policy-logic-rule-${ruleId}`;
}

/**
 * The number of a rule in a group, and a way to get to it.
 *
 * The groups above answer "which of these rules are alike"; the reader's next
 * move is to go and read the one that is not. On a policy of sixty rules that
 * meant scrolling and counting block heads. This carries them there instead.
 *
 * It hides nothing: every rule is already drawn, and this only moves the view
 * to one of them. Focus goes with the scroll, so a reader who does not see the
 * page arrives where a reader who does sees.
 */
function JumpToRule({ member }: { member: LogicShapeMember }) {
  return (
    <button
      type="button"
      className="policy-logic__shape-rule"
      // The number alone is the whole label on screen, where the group around
      // it says what it counts. Read aloud, out of that group, it would be a
      // bare digit, so the spoken name says what the number is.
      aria-label={`Rule ${member.ordinal}`}
      onClick={() => {
        const block = document.getElementById(blockId(member.ruleId));
        if (!block) return;
        // Not every environment that runs this component lays anything out.
        if (typeof block.scrollIntoView === "function") {
          block.scrollIntoView({ block: "start", behavior: "auto" });
        }
        block.focus({ preventScroll: true });
      }}
    >
      {member.ordinal}
    </button>
  );
}

/** One rule, whole: what scopes it, then what follows from it. */
function RuleBlock({ rule }: { rule: LogicRuleReading }) {
  const [applies, outcome] = rule.branches;
  return (
    <article
      className="policy-logic__rule"
      data-testid="policy-logic-rule"
      data-rule={rule.ruleId}
      id={blockId(rule.ruleId)}
      // Reachable when something sends a reader here, and skipped by the tab
      // order when nothing has, so the reading order is unchanged.
      tabIndex={-1}
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

      {rule.unrecorded ? (
        // Nothing is known either way, which is a different fact from absence
        // and wears the mark this app reserves for it.
        <p className="policy-logic__unknown" data-testid="policy-logic-unrecorded">
          <span aria-hidden>{UNKNOWN_COUNT}</span> No decomposition was recorded
          for this rule, so whether it states any of these attributes is unknown.
        </p>
      ) : (
        <div className="policy-logic__tree">
          <span className="semantic-projection-label policy-logic__half">
            Condition
          </span>
          <Branch branch={applies} />
          <span className="semantic-projection-label policy-logic__half">
            Outcome
          </span>
          <Branch branch={outcome} />
        </div>
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
