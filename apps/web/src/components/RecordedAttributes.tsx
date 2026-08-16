import { Typography } from "antd";
import type { PolicyAttribute, PolicyAttributes } from "../api";
import { UNKNOWN_COUNT } from "../loadState";
import { DirectionalText } from "./DirectionalText";

const { Text } = Typography;

/**
 * Every attribute a record carries, as it carries it.
 *
 * WHY THIS IS ITS OWN FILE
 *
 * This is the display the reviewer agreed to: "every attribute is one row of
 * three parts — the attribute's own name, the document's words verbatim, and
 * the identifier a case supplies a value for. Nothing renamed, nothing merged,
 * nothing hidden."
 *
 * It lived inside the queue's own inline detail, which was a second reading of
 * a record beside the inspector's. Collapsing the two would have deleted this,
 * because the inspector never had it — so the agreed display would have been
 * lost to a change made in the name of consistency, which is the worst way to
 * lose something. It moves out here instead, unchanged, and the inspector draws
 * it. One reading of a record everywhere, and it is the reading that was agreed.
 *
 * The class names still say `rule-detail-inline`. They are the styles this
 * markup was written against and they are unchanged by the move; renaming them
 * would be a redesign wearing an extraction's clothes.
 */

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
          not known.
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

/**
 * Both halves of what a record assigns, under the heading that names them.
 *
 * Two tables rather than one because what a rule reaches and what follows from
 * it are different questions, and a reviewer checking whether a rule bites on
 * their case reads only the first. They are not merged, and neither is dropped
 * when it is empty: a missing half is a fact about the record and is said.
 */
export function RecordedAttributes({ attributes }: { attributes?: PolicyAttributes }) {
  return (
    <section className="rule-detail-inline__block">
      <h4 className="rule-detail-inline__heading">Every attribute, as recorded</h4>
      <AttributeTable caption="What it applies to" rows={attributes?.applies} absent={attributes === undefined} />
      <AttributeTable caption="What follows" rows={attributes?.outcome} absent={attributes === undefined} />
    </section>
  );
}
