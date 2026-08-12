import { Tree, Typography } from "antd";
import type { CanonicalRule, PolicyAttribute } from "../api";
import { effectMeta } from "../ruleDisplay";

const { Text } = Typography;

/**
 * The rule's attributes, rendered from the table the record already carries.
 *
 * Nothing is computed here. `rule.attributes` is derived once on the server,
 * from the canonical record, and served in the JSON; this draws it. That split
 * is the point — what a reader sees on screen and what they get in the file
 * are the same table, not two readings of one record that can drift apart. An
 * earlier version rebuilt the table in the browser, so a correction to how
 * attributes pair with facts had to be made in two places.
 *
 * Each row is three parts and nothing else: the attribute the formulator
 * assigned, the phrase the document wrote, and the identifier a case supplies
 * a value for. A reader checking this panel is checking exactly two things —
 * that the text is the document's, unaltered, and that it sits under the
 * attribute it was extracted into — so anything that makes the panel read more
 * smoothly at the cost of either is a defect.
 *
 * Three earlier versions each broke that differently. One translated
 * everything into XACML, which forced clauses into identifier slots so "for
 * specific cases that the university deems necessary" became the *name* of a
 * resource. One reached for friendlier labels — "who", "worked out as", "how
 * often" — and picked prepositions that collided with the source's own, so a
 * trigger reading "after the trial period has expired" was presented as "on
 * after the trial period has expired". One glued `modality` and `predicate`
 * into "shall not exceed" and hid any phrase already shown under another
 * attribute: the first displays a string no attribute contains, and the second
 * conceals that one phrase was assigned to three slots, which is precisely
 * what this panel exists to let a reader catch.
 */

interface TreeDatum {
  key: string;
  title: React.ReactNode;
  children?: TreeDatum[];
}

/** One row: attribute, original text, identifier — in that order, every time. */
function attributeRow(row: PolicyAttribute, index: number): TreeDatum {
  return {
    key: `attr-${row.attribute}-${index}`,
    title: (
      <span className="policy-attr">
        <Text code className="policy-attr-name">
          {row.attribute}
        </Text>
        <span className="policy-attr-value">{row.text}</span>
        <span className="policy-attr-fact">
          {row.fact ? (
            <Text code className="policy-attr-fact-name">
              {row.fact}
              {row.data_type ? `: ${row.data_type}` : ""}
            </Text>
          ) : null}
        </span>
      </span>
    ),
  };
}

function groupNode(key: string, label: string, rows: PolicyAttribute[]): TreeDatum {
  return {
    key,
    title: (
      <Text strong className="cond-group-label">
        {label}
      </Text>
    ),
    children:
      rows.length > 0
        ? rows.map(attributeRow)
        : [{ key: `${key}-none`, title: <Text type="secondary">none extracted</Text> }],
  };
}

export function SemanticProjectionView({ rule }: { rule: CanonicalRule }) {
  const attributes = rule.attributes;
  if (!attributes) return null;

  const effect = effectMeta(rule.effect?.type ?? "");

  return (
    <div className="semantic-projection">
      <Tree
        treeData={[groupNode("attrs-applies", "APPLIES", attributes.applies ?? [])]}
        defaultExpandAll
        selectable={false}
        showLine={{ showLeafIcon: false }}
        className="cond-tree"
      />

      <div className="semantic-projection-effect">
        <Text type="secondary" className="semantic-projection-label">
          Outcome
        </Text>
        <Tree
          treeData={[
            groupNode("attrs-outcome", effect.label.toUpperCase(), attributes.outcome ?? []),
          ]}
          defaultExpandAll
          selectable={false}
          showLine={{ showLeafIcon: false }}
          className="cond-tree"
        />
      </div>
    </div>
  );
}

/** Whether the record carries an attribute table worth showing. */
export function hasSemanticProjection(rule: CanonicalRule): boolean {
  const attributes = rule.attributes;
  if (!attributes) return false;
  return (attributes.applies?.length ?? 0) > 0 || (attributes.outcome?.length ?? 0) > 0;
}
