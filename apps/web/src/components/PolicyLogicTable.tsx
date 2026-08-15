import { Typography } from "antd";

import { UNKNOWN_COUNT } from "../loadState";
import type { PolicyCard } from "../policyCards";
import { policyLogic } from "../policyLogic";
import { policyRouteLabel } from "../policyGrouping";
import { ruleTypeLabel } from "../ruleTypes";
import { DirectionalText } from "./DirectionalText";

const { Text } = Typography;

/**
 * The policy's rules side by side, on the attributes the document filled.
 *
 * The card reads a policy one rule at a time, which answers "is this rule
 * faithful" and cannot answer "is this set complete". Twenty rules read as
 * twenty paragraphs hide the fact that one of them states a time and nineteen do
 * not. The same twenty in a column make that visible without anyone being told
 * to look for it.
 *
 * WHY A TABLE AND NOT A SUMMARY
 *
 * Because a summary would be ours. Every cell here is a run of the document,
 * placed under the name the formulator recorded it as; the only things this view
 * adds are the arrangement and a count of how many rules filled each slot. There
 * is no policy-level modality, no merged condition, no combined scope — each
 * would be a claim about the section that no sentence of it makes.
 *
 * It also detects nothing. Two rules that contradict each other are a finding,
 * with its own detection and its own severity, and a second opinion formed in a
 * tab would be the same judgement made twice by two mechanisms that will drift.
 *
 * WHY THE COLUMNS DO NOT MOVE
 *
 * They are in a fixed order and never sorted by coverage. A reviewer working a
 * queue learns where a column is; a table that reorders itself per policy has to
 * be re-read from scratch every time. What makes a rare attribute stand out is
 * the count in its header — `Time · 1 of 20` — not its position.
 *
 * Rows are in document order for the same reason, and for a stronger one:
 * ordering by how many slots a rule filled would rank the rules by completeness,
 * and a rule the document states in words would sit at the bottom of every
 * policy in the system. Route is not a score and is not sorted on.
 */
export function PolicyLogicTable({ card }: { card: PolicyCard }) {
  const logic = policyLogic(card);

  return (
    <div className="policy-logic" data-testid="policy-logic">
      <Text type="secondary" className="policy-detail-panel__section-label">
        What each rule states, side by side —{" "}
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
              className="policy-logic__shared-item"
            >
              <dt>{fact.label}</dt>
              <dd>
                <DirectionalText>{fact.value}</DirectionalText>
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
        <div className="policy-logic__scroll">
          <table
            className="policy-logic__table"
            data-testid="policy-logic-table"
          >
            <thead>
              <tr>
                <th scope="col" className="policy-logic__rule-head">
                  Rule
                </th>
                {logic.columns.map((column) => (
                  <th key={column.attribute} scope="col">
                    <span className="policy-logic__col-label">
                      {column.label}
                    </span>
                    {/* A count, not a proportion and not a bar. "1 of 20" is
                        what the document did; "5%" invites reading it as a
                        shortfall in the rule that is the odd one out. */}
                    <span className="policy-logic__col-count">
                      {column.filled} of {logic.total}
                    </span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {logic.rows.map((row) => (
                <tr
                  key={row.ruleId}
                  data-testid="policy-logic-row"
                  data-rule={row.ruleId}
                >
                  <th scope="row" className="policy-logic__rule-cell">
                    <span className="policy-card__rule-ordinal" aria-hidden>
                      {row.ordinal}
                    </span>
                    {/* Which sentence this rule came from. A reviewer reading
                        across fourteen rules still needs the passage boundary;
                        merging a section onto one card must not merge its
                        sentences into one. */}
                    <span className="policy-logic__passage">
                      {row.passageKey}
                    </span>
                    <span className="policy-logic__facets">
                      {row.ruleType && (
                        <span>{ruleTypeLabel(row.ruleType)}</span>
                      )}
                      {row.route && <span>{policyRouteLabel(row.route)}</span>}
                    </span>
                  </th>
                  {row.cells.map((cell, index) => (
                    <td key={logic.columns[index].attribute}>
                      {cell.state === "stated" ? (
                        <span className="policy-logic__stated">
                          <DirectionalText>{cell.text}</DirectionalText>
                        </span>
                      ) : cell.state === "absent" ? (
                        // A true statement about the rule: the decomposition is
                        // there and names no such component.
                        <span className="policy-logic__absent">not stated</span>
                      ) : (
                        // Nothing is known either way, which is a different fact
                        // and wears the mark this app reserves for it.
                        <span
                          className="policy-logic__unknown"
                          title="No decomposition was recorded for this rule, so whether it states this is unknown."
                        >
                          {UNKNOWN_COUNT}
                        </span>
                      )}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {logic.unrecorded > 0 && (
        <Text type="secondary" className="policy-logic__note">
          {logic.unrecorded === 1
            ? "1 rule carries no recorded decomposition, so its cells say only that we do not know."
            : `${logic.unrecorded} rules carry no recorded decomposition, so their cells say only that we do not know.`}
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
