import { Tag, Tooltip, Tree, Typography } from "antd";
import { InfoCircleOutlined } from "@ant-design/icons";
import type { CanonicalRule, DmnSemanticProjection } from "../api";
import {
  ACTION_ATTRIBUTE,
  RESOURCE_ATTRIBUTE,
  XACML_NOTE,
  categoryForSubject,
  effectLabel,
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
    "The conditions below are what the source states. No fact model has been configured for this policy set, so none of them has been bound to an attribute yet — that is a setup step on our side, not a gap in the document, and no request has been evaluated.",
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

/** A named slot carrying the source's own wording, not a XACML attribute.
 *
 * Distinct from `attributeLeaf` on purpose: an attribute is matched against a
 * request and belongs in `name = "value"` form, while these are parts of the
 * sentence the document wrote. Rendering the second as the first is what put a
 * whole clause where an action identifier belongs.
 */
function slotLeaf(key: string, slot: string, value: string): TreeDatum {
  return {
    key,
    title: (
      <span className="cond-leaf">
        <Text type="secondary" className="semantic-projection-slot">
          {slot}
        </Text>
        <Text>{value}</Text>
      </span>
    ),
  };
}

export function SemanticProjectionView({ rule }: { rule: CanonicalRule }) {
  const projection = projectionOf(rule);
  if (!projection) return null;

  const decision = rule.formulation?.dmn_decisions?.[0];
  const note = STATUS_NOTE[decision?.dmn_mapping_status ?? ""];
  const canonicalType = rule.formulation?.canonical?.rule?.rule_type ?? projection.rule_type ?? "";
  const effect = xacmlEffect(rule.effect?.type);

  // TARGET. The categorised entity, if the evidence establishes a category.
  //
  // This used to emit `subject.subject-id = <canonical subject>` for every
  // rule, which asserted that "the allowance" and "A work nature allowance at
  // the rate of (200) two hundred SR per month" were XACML subjects. XACML's
  // subject is the requesting entity; a benefit requests nothing, and a
  // request matched against `subject-id = "the allowance"` matches nothing.
  // The category now comes from party evidence, not the grammatical slot.
  const whenChildren: TreeDatum[] = [];
  const partyNames = (rule.decision_readiness?.parties ?? []).map((party) => party.name);
  const subject = projection.subject || rule.formulation?.canonical?.rule?.subject || "";
  if (subject) {
    const category = categoryForSubject(subject, canonicalType, partyNames);
    if (category) {
      whenChildren.push(
        attributeLeaf("proj-subj", category.attribute, "=", `"${subject}"`)
      );
    }
  }

  // CONDITIONS. Shown as what the source states, and nothing more.
  //
  // These used to be badged `Indeterminate · missing-attribute`, which was
  // three errors at once: Indeterminate is a PDP result and no PDP has run;
  // missing-attribute is raised when a PDP cannot *obtain* an attribute during
  // evaluation; and both blamed the document for a gap in our fact model.
  //
  // Replacing it with a per-condition "Fact mapping: missing" was still wrong,
  // for two reasons. No fact model is configured for these policy sets at all,
  // so nothing is pending — every condition would carry the same badge for one
  // shared reason, which reads as N problems instead of one piece of context.
  // And "depending on the recommendation of the director of the concerned
  // Department" *is* the condition: it is completely identified, and stamping a
  // deficiency beside it misreads a clear sentence as an unclear one.
  //
  // The banner above already states the fact-model position once. A condition
  // the source stated is shown as stated.
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
        </span>
      ),
    });
  }

  // THEN. The XACML decision, and beneath it the Obligation or Advice the
  // source attaches to it.
  //
  // Every slot is read from the field that owns it. Falling back across slots
  // is what produced the defect this guards against: an earlier version let
  // `resource` accept `outcome` when `object` was absent, so one phrase
  // appeared as two different attributes.
  //
  // `action` is the decomposed predicate, never the effect's action string.
  // `Effect.action` is `predicate + object` glued back together — a whole
  // clause — so reading it here rendered
  // `action.action-id = "exceed 10% of the …"`, which is a sentence sitting in
  // a slot that holds an identifier. The canonical record already separates
  // them, and `xacml_view` already carries the normalised identifier that a
  // request would actually be matched against.
  const canonicalRule = rule.formulation?.canonical?.rule;
  const semantics = rule.xacml_view?.source_semantics;
  const directiveChildren: TreeDatum[] = [];
  const action = semantics?.action?.phrase || projection.predicate || canonicalRule?.predicate || "";
  const actionId = semantics?.action?.normalized_id || "";
  const resource = projection.object || canonicalRule?.object || "";
  const threshold = canonicalRule?.threshold || "";
  const outcome = projection.outcome || projection.outcome_source || "";
  if (action) {
    directiveChildren.push(
      attributeLeaf("proj-act", ACTION_ATTRIBUTE, "=", `"${actionId || action}"`)
    );
  }
  // The verb as the document wrote it, when the normalised identifier differs.
  // The identifier is what a request matches; the phrase is what the sentence
  // said, and a reader checking the record against the document needs both.
  if (actionId && action && actionId !== action) {
    directiveChildren.push(slotLeaf("proj-act-phrase", "stated as", action));
  }
  // Guarded even so: a projection that repeats one phrase in both slots would
  // otherwise state it twice under two different attributes, which reads as a
  // finding about the policy rather than a duplication in the extraction.
  if (resource && resource !== action) {
    directiveChildren.push(attributeLeaf("proj-res", RESOURCE_ATTRIBUTE, "=", `"${resource}"`));
  }
  // The bound the sentence states, in its own slot. It is the operative part
  // of a limiting rule — "not exceed X" means nothing without X — and showing
  // it only inside a glued action string left it unreadable as a limit.
  if (threshold && threshold !== resource) {
    directiveChildren.push(slotLeaf("proj-threshold", "limit", threshold));
  }
  if (outcome && outcome !== action && outcome !== resource && outcome !== threshold) {
    directiveChildren.push(slotLeaf("proj-outcome", "outcome", outcome));
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
      effectLabel(effect.effect),
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
