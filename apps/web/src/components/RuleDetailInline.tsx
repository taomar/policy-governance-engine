import { useMemo } from "react";
import { Button, Typography } from "antd";
import { ExportOutlined } from "@ant-design/icons";
import type { CandidateRule, PolicyAttribute } from "../api";
import { UNKNOWN_COUNT } from "../loadState";
import { DirectionalText } from "./DirectionalText";
import { ConditionView } from "./ConditionView";
import { ConditionRouteNote } from "./ConditionRouteNote";
import { effectActionText, isEmptyCondition } from "../ruleDisplay";

const { Text } = Typography;

/**
 * One rule's judgeable detail, rendered where the rule stands.
 *
 * The queue used to answer "what does this rule actually say?" by replacing the
 * surface the reviewer was reading. They left the policy to read the rule and
 * clicked back to return, and the passage, the sibling rules and the scroll
 * position all went away while they were gone — so the one comparison a
 * reviewer makes constantly, this rule against the rest of its policy, was the
 * one thing the interface took away at the moment they needed it.
 *
 * So this renders inside the row it belongs to and the policy stays on screen.
 *
 * Everything here comes from the record already in hand. There is no fetch, so
 * there is no state in which this can sit on "Loading…" — the two panels in
 * this app that did are what that rule is written against. Where a field can be
 * genuinely absent from the payload rather than merely empty, the two are said
 * differently: `attributes` missing means the record did not carry the table,
 * which is not the same claim as the table being here and naming nothing.
 *
 * What is deliberately NOT here: the evaluator/canonical/DMN JSON forms, the
 * scope editor, version history, notes, and the scenario runner. Those want a
 * large surface and their own scroll, and none of them is needed to judge
 * whether the rule matches the document. They stay in the full inspector, which
 * is still one click away — it is simply no longer the only way in.
 */
export function RuleDetailInline({
  candidate,
  onOpenFullRecord,
  className,
}: {
  candidate: CandidateRule;
  /** Open the larger surface for this rule. Omitted where it isn't reachable. */
  onOpenFullRecord?: () => void;
  className?: string;
}) {
  const rule = candidate.rule;
  const attributes = rule.attributes;

  const conditionEmpty = useMemo(() => isEmptyCondition(rule.condition), [rule.condition]);

  return (
    <div className={`rule-detail-inline${className ? ` ${className}` : ""}`}>
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

      <section className="rule-detail-inline__block">
        <h4 className="rule-detail-inline__heading">Every attribute, as recorded</h4>
        <AttributeTable
          caption="What it applies to"
          rows={attributes?.applies}
          absent={attributes === undefined}
        />
        <AttributeTable
          caption="What follows"
          rows={attributes?.outcome}
          absent={attributes === undefined}
        />
      </section>

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
        <dl className="rule-detail-inline__ids">
          <div className="rule-detail-inline__id-row">
            <dt>Rule</dt>
            <dd className="rule-detail-inline__mono">{rule.rule_id}</dd>
          </div>
          <div className="rule-detail-inline__id-row">
            <dt>Revision</dt>
            <dd className="rule-detail-inline__mono">{rule.rule_revision}</dd>
          </div>
          <div className="rule-detail-inline__id-row">
            <dt>Extraction record</dt>
            <dd className="rule-detail-inline__mono">{candidate.id}</dd>
          </div>
        </dl>
      </section>

      {onOpenFullRecord && (
        <div className="rule-detail-inline__footer">
          <Button size="small" type="link" icon={<ExportOutlined />} onClick={onOpenFullRecord}>
            Open the full record — source passage, JSON forms, history and notes
          </Button>
        </div>
      )}
    </div>
  );
}

/**
 * The agreed three-part row, once per attribute: the attribute's own name, the
 * document's words verbatim, and the identifier a case supplies a value for.
 *
 * A table because that is what it is — three columns with the same meaning on
 * every row — and because a screen reader then announces which column a cell
 * belongs to instead of reading three unlabelled runs of text. Nothing is
 * renamed on the way through: `attribute` is printed exactly as the record
 * declares it, because a reviewer comparing this against the JSON is comparing
 * against that string and not against a prettier one.
 *
 * `absent` is a different claim from an empty list and is worded differently.
 * The record not carrying the table at all means nobody knows what it would
 * have said; the table being here and naming none means the answer is none.
 */
function AttributeTable({
  caption,
  rows,
  absent,
}: {
  caption: string;
  rows: PolicyAttribute[] | undefined;
  absent: boolean;
}) {
  if (absent) {
    return (
      <div className="rule-detail-inline__attr-group">
        <p className="rule-detail-inline__caption">{caption}</p>
        <Text type="secondary" className="rule-detail-inline__quiet">
          {UNKNOWN_COUNT} This record did not carry an attribute table, so what it assigns here is
          not known from the queue. The full record shows the extraction as it was stored.
        </Text>
      </div>
    );
  }
  if (!rows || rows.length === 0) {
    return (
      <div className="rule-detail-inline__attr-group">
        <p className="rule-detail-inline__caption">{caption}</p>
        <Text type="secondary" className="rule-detail-inline__quiet">
          The attribute table is present and names none here.
        </Text>
      </div>
    );
  }
  return (
    <div className="rule-detail-inline__attr-group">
      <table className="rule-detail-inline__attrs">
        <caption className="rule-detail-inline__caption">{caption}</caption>
        <thead>
          <tr>
            <th scope="col">Attribute</th>
            <th scope="col">The document&rsquo;s words</th>
            <th scope="col">A case supplies</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((attr, idx) => (
            <tr key={`${attr.attribute}-${idx}`}>
              <th scope="row" className="rule-detail-inline__mono">
                {attr.attribute}
              </th>
              <td>
                <DirectionalText align>{attr.text}</DirectionalText>
              </td>
              <td className="rule-detail-inline__mono">
                {attr.fact ? (
                  <>
                    {attr.fact}
                    {attr.data_type && (
                      <span className="rule-detail-inline__datatype"> ({attr.data_type})</span>
                    )}
                  </>
                ) : (
                  <Text type="secondary">stated by the document</Text>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
