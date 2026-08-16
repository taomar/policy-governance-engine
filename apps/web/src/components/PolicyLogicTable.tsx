import { Typography } from "antd";
import { Fragment } from "react";

import { UNKNOWN_COUNT } from "../loadState";
import type { PolicyCard } from "../policyCards";
import type {
  LogicAttributeReading,
  LogicBranch,
  LogicMark,
  LogicPassageBlock,
  LogicRuleReading,
} from "../policyLogicShape";
import { policyLogicShape } from "../policyLogicShape";
import { policyRouteLabel } from "../policyGrouping";
import { ruleTypeLabel } from "../ruleTypes";
import { DirectionalText } from "./DirectionalText";
import { RuleName } from "./RuleName";
import "./policyLogic.css";

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
 * The overview above the rules was what this view added, and it is gone. It
 * counted how many of the policy's rules stated each attribute and grouped the
 * rules that stated the same set, and both were true. Neither was read. A
 * reviewer's verdict on it was that it showed no value, and looking at it
 * again they were right: a reader arriving at a policy wants to know what its
 * rules say, and a strip of `subject 9 of 9` chips over a list of attribute
 * names is a census of the schema rather than a reading of the document. The
 * counts are still computed — each rule's own block names what that rule
 * leaves out, and that line is derived from them — so nothing a reader could
 * see was lost with the panel that reported them in aggregate.
 *
 * WHAT REPLACED IT AT THE TOP OF EACH PASSAGE
 *
 * The passage heading was the source element run and nothing else, which is the
 * pipeline's address for a passage and means nothing to the compliance officer
 * this screen is for. The document's own heading leads now, the page follows,
 * and the run stays as the reference it always was rather than as the name it
 * was mistaken for. Each rule then carries the name generated for it and its
 * own stated words, so the trees below can be told apart by what they say.
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
 * WHAT THE COUNTS COUNT
 *
 * Every number this view still prints counts the whole policy. A policy arrives
 * whole, so the rules on the card are the policy's rules and there is no second
 * population to confuse them with. If something above this view ever lets a
 * reviewer narrow which rules they are looking at, these numbers must keep
 * counting the policy and not the narrowing: a count that quietly meant "of the
 * ones showing" would make two different readings of one policy look alike, and
 * a reviewer comparing them could not tell which they had. There is a test on
 * `card.policy.rule_count` that says so.
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
 * declares, or a name generated for a rule and marked as generated. Rules stay
 * in document order under the passage that states them: ordering by how many
 * attributes a rule filled would rank rules by completeness, and a rule whose
 * test the source states in words would sit at the bottom of every policy in
 * the system.
 */
export function PolicyLogicTable({ card }: { card: PolicyCard }) {
  const logic = policyLogicShape(card);

  return (
    <div className="policy-logic" data-testid="policy-logic">
      {logic.columns.length === 0 ? (
        <Text type="secondary">
          No decomposition was recorded for the rules of this policy, so there is
          nothing to compare here. Each rule's own statement is above.
        </Text>
      ) : (
        <>
          {logic.blocks.map((block, index) => (
            <section
              key={`${block.passageKey}-${index}`}
              className="policy-logic__block"
              data-testid="policy-logic-block"
            >
              {/* Which sentence these rules came from. A reviewer reading across
                  fourteen rules still needs the passage boundary; merging a
                  section onto one card must not merge its sentences into one. */}
              <PassageHead block={block} />
              {block.rules.map((rule) => (
                <RuleBlock key={rule.ruleId} rule={rule} policySetKey={card.policy_set_key} />
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

    </div>
  );
}

/**
 * Which passage of the document these rules were read from.
 *
 * It used to be the source element run — `p4-E000007` — and nothing else. That
 * is the address the pipeline uses and it is the right thing to quote back when
 * asking where something came from, but as the only thing on the line it named
 * the passage in a language the reader of this screen does not speak, and a
 * reviewer said so.
 *
 * So the document's own heading leads where its rules cite one, the page
 * follows where one was recorded, and the element run stays as the reference it
 * always was. Nothing was removed to make room: a passage whose rules cite no
 * heading still shows its run, because a reader who has only the run still has
 * a way to find the passage.
 */
function PassageHead({ block }: { block: LogicPassageBlock }) {
  return (
    <div className="policy-logic__passage-head">
      {block.headings.length > 0 && (
        <h4 className="policy-logic__passage-heading">
          {block.headings.map((heading, index) => (
            <Fragment key={heading}>
              {index > 0 && <span aria-hidden> · </span>}
              <DirectionalText>{heading}</DirectionalText>
            </Fragment>
          ))}
        </h4>
      )}
      <p className="policy-logic__passage">
        {block.page !== null && (
          <span className="policy-logic__passage-page">Page {block.page}</span>
        )}
        <span className="policy-logic__passage-key">{block.passageKey}</span>
      </p>
    </div>
  );
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

/** One rule, whole: what it is called, then what scopes it, then what follows. */
function RuleBlock({
  rule,
  policySetKey,
}: {
  rule: LogicRuleReading;
  /** The set this rule's card was built from, or `null` where the build was not
   *  told. A generated name is looked up by (set, rule id) — the one handle that
   *  resolves on the review queue and inside a sealed version alike — so with no
   *  set nothing is asked, which is a fact about this card and never a fault of
   *  the rule. Never the draft-row id: this view holds no draft row, and the
   *  shape both surfaces share must never carry one. */
  policySetKey: string | null;
}) {
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
      {/* What this rule is called: the short handle this app generated for it,
          so a reader can tell it from its siblings without reading all of them
          first. It is ours and says so, it is a finding aid and never a reading,
          and it is a different kind of thing from the rule's own title below —
          which is the document's verbatim words. It is looked up by the set the
          card carries and renders nothing at all where no set was given or no
          name was generated: the rule then reads exactly as it did before. */}
      {policySetKey && (
        <RuleName policySetKey={policySetKey} ruleId={rule.ruleId} variant="block" />
      )}
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

      {rule.title && (
        <p className="policy-logic__rule-title" data-verbatim="true">
          <DirectionalText align>{rule.title}</DirectionalText>
        </p>
      )}

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

      {/* The one thing on this surface that is behind a control, and the reason
          is that it is the one thing this surface never showed: the sentence
          the rule was read out of. Every attribute the rule states is drawn
          above it, open, so a reviewer checking whether anything was dropped
          still never has to press anything to find out. */}
      {rule.statedText && (
        <details className="policy-logic__source" data-testid="policy-logic-source">
          <summary>What the document says here</summary>
          <blockquote className="policy-logic__source-text" data-verbatim="true">
            <DirectionalText align>{rule.statedText}</DirectionalText>
          </blockquote>
        </details>
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
