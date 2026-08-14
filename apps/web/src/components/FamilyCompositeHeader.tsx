import { useState } from "react";
import { Button, Tag, Tooltip, Typography } from "antd";
import { ApartmentOutlined, EyeOutlined } from "@ant-design/icons";
import type { CanonicalRule } from "../api";
import { familyComposite } from "../familyComposite";
import { clusterLabel, type RuleVariationGroup } from "../ruleDisplay";
import { EffectivePolicyModal } from "./EffectivePolicyModal";

const { Text } = Typography;

/**
 * Header shown once at the top of a family band: the single policy its rules
 * collectively state.
 *
 * Eight rows of a severity matrix are one policy with eight variants, but the
 * list showed eight peers and left the reviewer to reconstruct that. Worse,
 * nothing said the visible rows were all of it — approving six of eight left a
 * half-decided policy with no signal.
 *
 * Only states what the members agree on. A subject or predicate appears here
 * only when every member states it identically; where they differ, the
 * variation is listed instead. Nothing is summarised or paraphrased.
 */
export function FamilyCompositeHeader({
  cluster,
  members,
  accent,
  memberCountInView,
}: {
  cluster: RuleVariationGroup;
  members: CanonicalRule[];
  accent?: string;
  /** How many members the current filter actually shows, when fewer than all. */
  memberCountInView?: number;
}) {
  const composite = familyComposite(members);
  const [showEffective, setShowEffective] = useState(false);
  const hidden =
    memberCountInView !== undefined && memberCountInView < composite.memberCount
      ? composite.memberCount - memberCountInView
      : 0;

  return (
    <div
      className="family-composite"
      style={accent ? ({ "--cluster-accent": accent } as React.CSSProperties) : undefined}
    >
      <div className="family-composite-head">
        <ApartmentOutlined className="family-composite-icon" />
        <Text strong className="family-composite-title">
          {clusterLabel(cluster)}
        </Text>
        <Tooltip title="These rules state one policy. They were extracted separately because the source states each variant on its own row or clause.">
          <Tag variant="filled" className="family-composite-count">
            {composite.memberCount} rules · 1 policy
          </Tag>
        </Tooltip>
        {composite.memberCount > 1 && (
          <Button
            size="small"
            icon={<EyeOutlined />}
            className="family-composite-action"
            onClick={() => setShowEffective(true)}
          >
            Effective policy
          </Button>
        )}
      </div>

      {(composite.subject || composite.predicate) && (
        <div className="family-composite-statement">
          {composite.subject && <Text className="family-composite-subject">{composite.subject}</Text>}
          {composite.predicate && (
            <Text type="secondary" className="family-composite-predicate">
              {composite.predicate}
            </Text>
          )}
          {composite.variants.length > 0 && (
            <Text type="secondary" className="family-composite-varies">
              varying by {composite.variants.length} case
              {composite.variants.length === 1 ? "" : "s"}
            </Text>
          )}
        </div>
      )}

      <div className="family-composite-flags">
        {composite.statuses.length > 1 && (
          <Tooltip title="Members of this policy are in different review states, so approving what is visible would leave the policy partly decided.">
            <Tag variant="filled" color="orange">
              {composite.statuses.length} review states
            </Tag>
          </Tooltip>
        )}
        {hidden > 0 && (
          <Tooltip title="The current filter hides part of this policy. What you see is not all of it.">
            <Tag variant="filled" color="warning">
              {hidden} hidden by filter
            </Tag>
          </Tooltip>
        )}
      </div>

      {showEffective && (
        <EffectivePolicyModal
          open={showEffective}
          onClose={() => setShowEffective(false)}
          cluster={cluster}
          members={members}
        />
      )}
    </div>
  );
}
