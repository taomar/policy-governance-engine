import { Tag, Tooltip, Typography } from "antd";
import { FileTextOutlined } from "@ant-design/icons";
import { policyHeaderSummary, policyRouteLabel, type PolicyBand } from "../policyGrouping";

const { Text } = Typography;

/**
 * The passage a run of rules came from.
 *
 * A sentence can impose several obligations -- "staff must read, understand and
 * comply with the policies" states three. Without this the queue shows them as
 * three unrelated cards and a reviewer has no way to see that approving one
 * without the others splits a single provision.
 *
 * Deliberately a band above the rules rather than a container around them. Each
 * rule stays individually reviewable, editable and individually routed; folding
 * them into one card would hide the very rules the reviewer has to decide on,
 * and a policy of one rule -- which most are -- would become a container with a
 * single thing in it.
 */
export function PolicyPassageHeader({ band }: { band: PolicyBand }) {
  const { policy } = band;
  const partial = band.inView < band.total;

  return (
    <div className="policy-passage-header" data-testid="policy-passage-header">
      <div className="policy-passage-header__title">
        <FileTextOutlined aria-hidden />
        <Text strong>
          {band.total === 1 ? "Stated in one passage" : "Stated together in one passage"}
        </Text>
        <Tooltip
          title={
            // The route summarises how this passage's rules are decided. Both
            // routes are ordinary; a passage holding one of each is the common
            // shape of a real document, not a half-finished version of a better
            // one.
            "Where the source states a test as a comparison it is evaluated directly. Where the source states it in words it is decided by reading. A passage can hold both."
          }
        >
          <Tag bordered={false}>{policyRouteLabel(policy.route)}</Tag>
        </Tooltip>
      </div>
      <Text type="secondary" className="policy-passage-header__summary">
        {policyHeaderSummary(band)}
      </Text>
      {partial && (
        <Text type="secondary" className="policy-passage-header__partial">
          {/* A fragment presented as a whole passage is worse than no grouping
              at all, so the gap is stated rather than left to be inferred from
              the counts. */}
          {band.continuesAbove && band.continuesBelow
            ? "Rules from this passage appear before and after this page."
            : band.continuesAbove
              ? "Earlier rules from this passage are on the previous page."
              : band.continuesBelow
                ? "More rules from this passage continue below."
                : "Some rules from this passage are hidden by the current filter."}
        </Text>
      )}
      <Text type="secondary" className="policy-passage-header__source">
        {policy.source_elements}
      </Text>
    </div>
  );
}
