import { Tooltip, Typography } from "antd";
import { InfoCircleOutlined } from "@ant-design/icons";
import {
  HEADING_CONTEXT_LABEL,
  headingContext,
} from "../headingContext";

const { Text } = Typography;

/**
 * The heading a citation sits under, shown against every citation.
 *
 * Rendered whether or not there is a heading to show. Hiding the row when
 * `section` is null is the behaviour this replaces, and it left a reviewer
 * unable to tell an unrecorded heading from a passage that needs no heading —
 * two states that call for opposite amounts of caution.
 *
 * One of these per citation rather than one per record. A quarter of the
 * records measured carry citations that disagree about their heading, and one
 * carried a numbered heading, a null and six copies of a lead-in line at once.
 * Choosing among those would mean the interface asserting something the
 * evidence does not say, so each citation states its own.
 */
export function EvidenceHeadingContext({ section }: { section?: string | null }) {
  const context = headingContext(section);

  return (
    <div className="evidence-heading-context">
      <span className="evidence-heading-context-label">
        {HEADING_CONTEXT_LABEL}{" "}
        <Tooltip
          title="Taken from the document as it was read, one heading per citation. Where the document did not supply one, this says so rather than leaving the row out."
        >
          <InfoCircleOutlined className="evidence-heading-context-hint" />
        </Tooltip>
      </span>
      {context.known ? (
        // Quoted, not paraphrased. This is source text like the excerpt below.
        <Text className="evidence-heading-context-value">“{context.heading}”</Text>
      ) : (
        <Text type="secondary" className="evidence-heading-context-absent">
          {context.absence}
        </Text>
      )}
    </div>
  );
}
