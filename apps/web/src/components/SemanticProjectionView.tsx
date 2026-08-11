import { Tooltip, Tree, Typography } from "antd";
import type { CanonicalRule, DmnSemanticProjection, SourceCondition } from "../api";
import { effectMeta } from "../ruleDisplay";
import {
  ACTION_ATTRIBUTE,
  RESOURCE_ATTRIBUTE,
  SUBJECT_ATTRIBUTE,
  XACML_NOTE,
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

/** One `attribute op "value"` leaf, matching the executable condition view.
 *
 * `statedAs` carries the document's own wording when it differs from the
 * identifier. Both matter and neither substitutes for the other: the
 * identifier is what a request is matched against, the wording is what a
 * reviewer checks the record against.
 */
function attributeLeaf(
  key: string,
  attribute: string,
  operator: string,
  value: string,
  statedAs?: string
): TreeDatum {
  const quoted = value.replace(/^"|"$/g, "");
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
        {statedAs && statedAs !== quoted && (
          <Text type="secondary" className="semantic-projection-stated">
            stated as “{statedAs}”
          </Text>
        )}
      </span>
    ),
  };
}

/** A condition the source states, shown decomposed rather than as a sentence.
 *
 * The concept is the attribute the condition is about. The comparison appears
 * when the sentence states one; when it does not, that is said plainly instead
 * of being left blank or filled in — an unstated comparison is a fact about
 * the document, and inventing an operator here would be the fabrication this
 * whole pipeline exists to avoid.
 */
function conditionLeaf(key: string, condition: SourceCondition): TreeDatum {
  const specified = condition.operator != null && condition.value != null;
  return {
    key,
    title: (
      <span className="cond-leaf">
        <Text code className="cond-fact">
          {condition.concept}
        </Text>
        {specified ? (
          <>
            <Text strong className="cond-op">
              {condition.operator}
            </Text>
            <Text keyboard className="cond-value">
              {condition.value}
            </Text>
          </>
        ) : (
          <Text type="secondary" className="semantic-projection-slot">
            stated, no comparison given
          </Text>
        )}
        <Text type="secondary" className="semantic-projection-stated">
          “{condition.source_text}”
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

  const effect = xacmlEffect(rule.effect?.type);

  // TARGET. The categorised entity, if the evidence establishes a category.
  //
  // This used to emit `subject.subject-id = <canonical subject>` for every
  // rule, which asserted that "the allowance" and "A work nature allowance at
  // the rate of (200) two hundred SR per month" were XACML subjects. XACML's
  // subject is the requesting entity; a benefit requests nothing, and a
  // request matched against `subject-id = "the allowance"` matches nothing.
  // The category now comes from party evidence, not the grammatical slot.
  // TARGET. Every entity the projection classified, with the identifier a
  // request would be matched against.
  //
  // Read from `xacml_view`, which is where the classification and its evidence
  // live. An earlier version re-derived a category from the grammatical
  // subject, which asserted that a benefit was the requesting entity; and the
  // conditions beside it were rendered as bare sentences from the DMN
  // projection while a fully decomposed form sat unused on the same record.
  const whenChildren: TreeDatum[] = [];
  const semantics = rule.xacml_view?.source_semantics;

  for (const [index, entity] of (semantics?.subjects ?? []).entries()) {
    whenChildren.push(
      attributeLeaf(
        `proj-subj-${index}`,
        SUBJECT_ATTRIBUTE,
        "=",
        `"${entity.normalized_id || entity.phrase}"`,
        entity.phrase
      )
    );
  }
  for (const [index, entity] of (semantics?.resources ?? []).entries()) {
    whenChildren.push(
      attributeLeaf(
        `proj-res-t-${index}`,
        RESOURCE_ATTRIBUTE,
        "=",
        `"${entity.normalized_id || entity.phrase}"`,
        entity.phrase
      )
    );
  }

  // CONDITIONS, decomposed.
  //
  // Each carries the concept it is about, and the comparison when the sentence
  // states one. `predicate_status` distinguishes "the source states a test and
  // its terms" from "the source states a test but not what satisfies it" —
  // which is a fact about the document, not a deficiency in the extraction,
  // and reads very differently to someone deciding whether to trust the rule.
  const conditions = semantics?.conditions ?? [];
  for (const [index, condition] of conditions.entries()) {
    whenChildren.push(conditionLeaf(`proj-cond-${index}`, condition));
  }
  // Nothing classified: fall back to the sentences the formulator recorded, so
  // a rule is never shown as having no conditions when it stated some.
  if (conditions.length === 0) {
    const stated = [
      ...(projection.conditions ?? []),
      ...(projection.condition_source ? [projection.condition_source] : []),
    ];
    for (const [index, phrase] of stated.entries()) {
      whenChildren.push({
        key: `proj-cond-raw-${index}`,
        title: (
          <span className="cond-leaf">
            <Text>{phrase}</Text>
          </span>
        ),
      });
    }
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

  // The heading says what the *policy* does, in the same words as the badge on
  // the rule itself. The XACML Effect follows as the technical mapping.
  //
  // Leading with the Effect made the two views of one rule contradict each
  // other on screen: an obligation is badged "Requires" and maps to a XACML
  // Permit carrying an ObligationExpression, so the row said Requires while
  // the logic below it said PERMIT in a heading. Both are true and only one is
  // the answer to "what does this rule do".
  const effectHeading = effect.effect
    ? `${effectMeta(rule.effect?.type ?? "").label} · XACML ${effect.effect}`
    : effectMeta(rule.effect?.type ?? "").label;

  const thenTree: TreeDatum[] = [
    groupNode(
      "proj-then",
      effectHeading,
      thenChildren.length > 0
        ? thenChildren
        : [{ key: "proj-then-empty", title: <Text type="secondary">no action stated</Text> }]
    ),
  ];

  return (
    <div className="semantic-projection">
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
