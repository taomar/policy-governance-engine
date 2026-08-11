import { Alert, Typography } from "antd";
import type { CanonicalRule } from "../api";
import { deterministicLabel, deterministicReason } from "../ruleExecutability";

const { Text, Paragraph } = Typography;

/**
 * Why this rule's condition is what it is, stated once and plainly.
 *
 * The reason has always been derived; it just could not be read. It was
 * appended to `description` alongside two other machine annotations, so a
 * reviewer met it as the tail of an unpunctuated block and the interface could
 * not act on it at all — every non-executable rule showed the same tooltip
 * regardless of which of four quite different things had happened.
 *
 * The distinction that matters is what it asks of the reader:
 *
 * * `conditions_not_projected` — supply a fact mapping. Actionable now.
 * * `no_scope_derived` — decide whether the rule really is unconditional.
 *   A reading of the document, not a configuration task.
 * * `conditions_not_representable` — nothing to supply. The configuration is
 *   already complete and the platform cannot yet express the comparison.
 * * `derived` — nothing to say, so nothing is rendered.
 *
 * Tone follows that split rather than severity: an `info` panel for a decision
 * the reviewer must make, a `warning` only where the stored tree actively
 * understates the source.
 */
export function ConditionProvenanceNotice({
  rule,
}: {
  rule: Pick<CanonicalRule, "machine_executable" | "condition_provenance">;
}) {
  const provenance = rule.condition_provenance;
  if (!provenance || provenance.code === "derived") return null;

  // Only this case means the tree says "always applies" while the document
  // says otherwise. The other two are honest states, not defects.
  const understatesSource =
    provenance.code === "conditions_not_projected" ||
    provenance.code === "conditions_not_representable";

  return (
    <Alert
      type={understatesSource ? "warning" : "info"}
      showIcon
      className="condition-provenance-notice"
      message={
        <Text strong>{deterministicLabel(rule.machine_executable, provenance)}</Text>
      }
      description={
        <>
          <Paragraph className="condition-provenance-reason">
            {deterministicReason(provenance)}
          </Paragraph>
          {provenance.unsupported_expression && (
            <Paragraph className="condition-provenance-expression">
              <Text type="secondary">The logic that could not be compiled: </Text>
              <Text code>{provenance.unsupported_expression}</Text>
            </Paragraph>
          )}
        </>
      }
    />
  );
}
