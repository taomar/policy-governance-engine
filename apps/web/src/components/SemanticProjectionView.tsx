import { Tag, Tooltip, Typography } from "antd";
import { InfoCircleOutlined } from "@ant-design/icons";
import type { CanonicalRule, DmnSemanticProjection } from "../api";

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
 * found but could not bind. That is read and shown here.
 *
 * What this deliberately does NOT do is convert that projection into
 * `factComparison` nodes. Those name fact paths the fact model is expected to
 * supply, and "The ED/CEO" is not such a path — writing it as
 * `subject.role = "ED/CEO"` would put an invented binding into the executable
 * contract, where the evaluator, exports and DMN compilation all read it as
 * real. Showing it as the source's own words keeps the claim exactly as strong
 * as the evidence for it.
 */

function projectionOf(rule: CanonicalRule): DmnSemanticProjection | null {
  const decisions = rule.formulation?.dmn_decisions ?? [];
  for (const decision of decisions) {
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

/** The statuses the projection covers, phrased for a reviewer. */
const STATUS_NOTE: Record<string, string> = {
  not_directly_mappable:
    "The source states this as a responsibility rather than a decision, so there is no decision table to compile.",
  ambiguous:
    "The source wording admits more than one reading, so it was not compiled into a decision table.",
  enrichment_required:
    "Conditions were found in the source but could not be bound to facts, because the policy set has no fact model covering them.",
};

export function SemanticProjectionView({ rule }: { rule: CanonicalRule }) {
  const projection = projectionOf(rule);
  if (!projection) return null;

  const status = rule.formulation?.dmn_decisions?.[0]?.dmn_mapping_status ?? "";
  const note = STATUS_NOTE[status];

  // `conditions` is the enrichment_required shape: source-grounded condition
  // phrases the agent found but could not bind. Shown as the conditions they
  // are, unbound.
  const conditions = projection.conditions ?? [];
  const conditionSource = projection.condition_source ?? "";

  return (
    <div className="semantic-projection">
      <div className="semantic-projection-banner">
        <Tooltip title="Read from the formulator's semantic projection — the meaning it recorded when it could not generate executable FEEL. Not evaluated at runtime.">
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

      {(conditions.length > 0 || conditionSource) && (
        <div className="semantic-projection-block">
          <Text type="secondary" className="semantic-projection-label">
            Conditions found in the source
          </Text>
          {conditions.map((condition) => (
            <div key={condition} className="semantic-projection-line">
              <Text>{condition}</Text>
            </div>
          ))}
          {conditionSource && (
            <div className="semantic-projection-line">
              <Text>{conditionSource}</Text>
            </div>
          )}
        </div>
      )}

      {(projection.subject || projection.predicate || projection.object) && (
        <div className="semantic-projection-block">
          <Text type="secondary" className="semantic-projection-label">
            What the source states
          </Text>
          <dl className="semantic-projection-spo">
            {projection.subject && (
              <div>
                <dt>Who</dt>
                <dd>{projection.subject}</dd>
              </div>
            )}
            {projection.predicate && (
              <div>
                <dt>Must</dt>
                <dd>{projection.predicate}</dd>
              </div>
            )}
            {projection.object && (
              <div>
                <dt>What</dt>
                <dd>{projection.object}</dd>
              </div>
            )}
          </dl>
        </div>
      )}

      {(projection.outcome || projection.outcome_source) && (
        <div className="semantic-projection-block">
          <Text type="secondary" className="semantic-projection-label">
            Outcome
          </Text>
          <div className="semantic-projection-line">
            <Text>{projection.outcome || projection.outcome_source}</Text>
          </div>
        </div>
      )}
    </div>
  );
}

/** Whether a rule has a projection worth showing in place of an empty tree. */
export function hasSemanticProjection(rule: CanonicalRule): boolean {
  return projectionOf(rule) !== null;
}
