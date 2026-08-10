import { Tag, Tooltip, Tree, Typography } from "antd";
import { InfoCircleOutlined } from "@ant-design/icons";
import type { CanonicalRule, DmnSemanticProjection } from "../api";
import {
  ACTION_ATTRIBUTE,
  RESOURCE_ATTRIBUTE,
  XACML_NOTE,
  subjectAttribute,
  xacmlEffect,
} from "../xacml";

const { Text } = Typography;

/**
 * Renders the logic a rule states when no executable condition exists.
 *
 * A rule whose DMN projection is `not_directly_mappable`, `ambiguous` or
 * `enrichment_required` has an empty condition tree, and the tree view then
 * showed a bare "ALL of" with nothing under it — literally nothing about the
 * policy, on the one panel meant to explain when it fires.
 *
 * The formulator did record the meaning: `semantic_projection` carries the
 * subject, predicate and object it read from the source, or the conditions it
 * found but could not bind. That is shown here in the same
 * attribute-and-operator form the executable view uses, and in the same XACML
 * vocabulary the rest of the platform already follows, so a reviewer reads one
 * notation across both.
 *
 * What this deliberately does NOT do is write the projection into
 * `rule.condition`. Those nodes name fact paths a fact model is expected to
 * supply, and "The ED/CEO" is not such a path — putting it there would make
 * the evaluator, exports and DMN compilation all read an invented binding as
 * real. Shown, labelled, and kept out of the executable contract.
 */

interface TreeDatum {
  key: string;
  title: React.ReactNode;
  children?: TreeDatum[];
}

function projectionOf(rule: CanonicalRule): DmnSemanticProjection | null {
  for (const decision of rule.formulation?.dmn_decisions ?? []) {
    const projection = decision.semantic_projection;
    if (!projection) continue;
    const hasContent =
      projection.subject ||
      projection.predicate ||
      projection.object ||
      projection.outcome ||
      projection.condition_source ||
      (projection.conditions?.length ?? 0) > 0;
    if (hasContent) return projection;
  }
  return null;
}

const STATUS_NOTE: Record<string, string> = {
  not_directly_mappable:
    "The source states this as a responsibility rather than a decision, so there is no decision table to compile.",
  ambiguous:
    "The source wording admits more than one reading, so it was not compiled into a decision table.",
  enrichment_required:
    "Conditions were found in the source but could not be bound to facts, because the policy set has no fact model covering them.",
};

/** One `attribute op "value"` leaf, matching the executable condition view. */
function attributeLeaf(key: string, attribute: string, operator: string, value: string): TreeDatum {
  return {
    key,
    title: (
      <span className="cond-leaf">
        <Text code className="cond-fact">
          {attribute}
        </Text>
        <Text strong className="cond-op">
          {operator}
        </Text>
        <Text keyboard className="cond-value">
          {value}
        </Text>
      </span>
    ),
  };
}

function groupNode(key: string, label: string, children: TreeDatum[]): TreeDatum {
  return {
    key,
    title: (
      <Text strong className="cond-group-label">
        {label}
      </Text>
    ),
    children,
  };
}

export function SemanticProjectionView({ rule }: { rule: CanonicalRule }) {
  const projection = projectionOf(rule);
  if (!projection) return null;

  const decision = rule.formulation?.dmn_decisions?.[0];
  const note = STATUS_NOTE[decision?.dmn_mapping_status ?? ""];
  const canonicalType = rule.formulation?.canonical?.rule?.rule_type ?? projection.rule_type ?? "";
  const effect = xacmlEffect(rule.effect?.type);

  // WHEN. A stated subject is the one thing the source pins down, so it is
  // shown as an equality against the XACML attribute it constrains. Unbound
  // condition phrases are listed beneath it as the prose they still are —
  // giving them an operator would imply a binding nobody has made.
  const whenChildren: TreeDatum[] = [];
  if (projection.subject) {
    whenChildren.push(
      attributeLeaf("proj-subj", subjectAttribute(canonicalType), "=", `"${projection.subject}"`)
    );
  }
  const statedConditions = [
    ...(projection.conditions ?? []),
    ...(projection.condition_source ? [projection.condition_source] : []),
  ];
  for (const [index, condition] of statedConditions.entries()) {
    whenChildren.push({
      key: `proj-cond-${index}`,
      title: (
        <span className="cond-leaf">
          <Text>{condition}</Text>
          <Tag bordered={false} color="orange" className="semantic-projection-inline-tag">
            unbound
          </Tag>
        </span>
      ),
    });
  }

  // THEN. The XACML decision, and beneath it the Obligation or Advice the
  // source attaches to it, described by action and resource attributes.
  const directiveChildren: TreeDatum[] = [];
  const action = projection.predicate || rule.effect?.action || "";
  if (action) {
    directiveChildren.push(attributeLeaf("proj-act", ACTION_ATTRIBUTE, "=", `"${action}"`));
  }
  const resource = projection.object || projection.outcome || projection.outcome_source || "";
  if (resource) {
    directiveChildren.push(attributeLeaf("proj-res", RESOURCE_ATTRIBUTE, "=", `"${resource}"`));
  }

  const thenChildren: TreeDatum[] =
    effect.directive && directiveChildren.length > 0
      ? [groupNode("proj-directive", effect.directive, directiveChildren)]
      : directiveChildren;

  const whenTree: TreeDatum[] =
    whenChildren.length > 0
      ? [groupNode("proj-when", "ALL OF", whenChildren)]
      : [
          {
            key: "proj-when-empty",
            title: (
              <Text type="secondary">
                No condition stated — a reviewer must decide whether it is unconditional
              </Text>
            ),
          },
        ];

  const thenTree: TreeDatum[] = [
    groupNode(
      "proj-then",
      effect.decision,
      thenChildren.length > 0
        ? thenChildren
        : [{ key: "proj-then-empty", title: <Text type="secondary">no action stated</Text> }]
    ),
  ];

  return (
    <div className="semantic-projection">
      <div className="semantic-projection-banner">
        <Tooltip title="Read from the formulator's semantic projection — the meaning it recorded when it could not generate executable FEEL. Shown in XACML terms, but not evaluated at runtime.">
          <Tag bordered={false} color="orange" className="semantic-projection-tag">
            <InfoCircleOutlined /> Stated in the source · not executable
          </Tag>
        </Tooltip>
        {note && (
          <Text type="secondary" className="semantic-projection-note">
            {note}
          </Text>
        )}
      </div>

      <Tree
        treeData={whenTree}
        defaultExpandAll
        selectable={false}
        showLine={{ showLeafIcon: false }}
        className="cond-tree"
      />

      <div className="semantic-projection-effect">
        <Text type="secondary" className="semantic-projection-label">
          Effect
        </Text>
        <Tooltip title={effect.gloss}>
          <div>
            <Tree
              treeData={thenTree}
              defaultExpandAll
              selectable={false}
              showLine={{ showLeafIcon: false }}
              className="cond-tree"
            />
          </div>
        </Tooltip>
      </div>

      <Text type="secondary" className="semantic-projection-standard">
        {XACML_NOTE}
      </Text>
    </div>
  );
}

/** Whether a rule has a projection worth showing in place of an empty tree. */
export function hasSemanticProjection(rule: CanonicalRule): boolean {
  return projectionOf(rule) !== null;
}
