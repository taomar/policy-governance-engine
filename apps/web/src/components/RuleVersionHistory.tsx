/**
 * "Version history" panel for a single rule — answers the user's explicit
 * request: "if there are multi version of the same policy should know the
 * previous one." Reuses the existing deterministic version-compare engine
 * (`ai_compare.compare_versions`, the same one that powers the standalone
 * Compare tab) scoped down to just this rule's own `changed_fields`, rather
 * than building a second diffing implementation. Calls it with
 * `narrative=false` so opening a rule's History tab never triggers an AI
 * narrative generation for the *whole* version diff — this only needs the
 * deterministic added/changed arrays for one rule_id.
 */
import { useEffect, useState } from "react";
import { Alert, Descriptions, Skeleton, Space, Tag, Typography } from "antd";
import { HistoryOutlined } from "@ant-design/icons";
import { aiApi, PolicyPlatformApiError, type ApprovedPolicyVersion, type CanonicalRule } from "../api";

const { Text, Paragraph } = Typography;

interface RuleVersionHistoryProps {
  policySetKey: string;
  rule: CanonicalRule;
  /** All published versions of this policy set (any order — sorted internally). */
  versions: ApprovedPolicyVersion[];
  /** The version number currently being viewed in the Policies tab. */
  currentVersionNumber: number | null;
}

const FIELD_LABELS: Record<string, string> = {
  title: "Title",
  description: "Description",
  rule_type: "Rule type",
  effect: "Effect",
  condition: "Condition (logic)",
  priority: "Priority",
  effective_from: "Effective from",
  effective_to: "Effective to",
};

function formatValue(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "object") return JSON.stringify(v, null, 2);
  return String(v);
}

type Lineage =
  | { kind: "no-prior" }
  | { kind: "new"; prevVersionNumber: number }
  | { kind: "unchanged"; prevVersionNumber: number }
  | { kind: "changed"; prevVersionNumber: number; changedFields: Record<string, { before: unknown; after: unknown }> };

export function RuleVersionHistory({ policySetKey, rule, versions, currentVersionNumber }: RuleVersionHistoryProps) {
  const [lineage, setLineage] = useState<Lineage | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setError(null);
    setLineage(null);
    if (currentVersionNumber === null) return;

    const prevVersion = [...versions]
      .filter((v) => v.version_number < currentVersionNumber)
      .sort((a, b) => b.version_number - a.version_number)[0];

    if (!prevVersion) {
      setLineage({ kind: "no-prior" });
      return;
    }

    setLoading(true);
    aiApi
      .compareVersions(policySetKey, prevVersion.version_number, currentVersionNumber, false)
      .then((result) => {
        const added = result.added.find((r) => r.rule_id === rule.rule_id);
        const changed = result.changed.find((c) => c.rule_id === rule.rule_id);
        if (added) {
          setLineage({ kind: "new", prevVersionNumber: prevVersion.version_number });
        } else if (changed) {
          setLineage({ kind: "changed", prevVersionNumber: prevVersion.version_number, changedFields: changed.changed_fields });
        } else {
          setLineage({ kind: "unchanged", prevVersionNumber: prevVersion.version_number });
        }
      })
      .catch((e) => setError(e instanceof PolicyPlatformApiError ? e.detail : String(e)))
      .finally(() => setLoading(false));
  }, [policySetKey, rule.rule_id, currentVersionNumber, versions]);

  if (loading) {
    return <Skeleton active paragraph={{ rows: 2 }} />;
  }

  if (error) {
    return <Alert type="error" showIcon message={error} />;
  }

  if (!lineage || lineage.kind === "no-prior") {
    return (
      <Paragraph type="secondary">
        <HistoryOutlined /> This is the first published version of this policy set — no prior version exists to
        compare against.
      </Paragraph>
    );
  }

  if (lineage.kind === "new") {
    return (
      <Space direction="vertical" size={4} style={{ width: "100%" }}>
        <Tag color="green">NEW IN v{currentVersionNumber}</Tag>
        <Text type="secondary">This rule did not exist in v{lineage.prevVersionNumber} — it was introduced here.</Text>
      </Space>
    );
  }

  if (lineage.kind === "unchanged") {
    return (
      <Space direction="vertical" size={4} style={{ width: "100%" }}>
        <Tag color="default">UNCHANGED SINCE v{lineage.prevVersionNumber}</Tag>
        <Text type="secondary">
          None of this rule's tracked fields (title, description, type, effect, condition, priority, effective
          dates) differ from v{lineage.prevVersionNumber}.
        </Text>
      </Space>
    );
  }

  const fieldEntries = Object.entries(lineage.changedFields);

  return (
    <Space direction="vertical" size={10} style={{ width: "100%" }}>
      <Tag color="purple">CHANGED SINCE v{lineage.prevVersionNumber}</Tag>
      <Text type="secondary">
        What changed between v{lineage.prevVersionNumber} and v{currentVersionNumber} for this specific rule:
      </Text>
      <Descriptions size="small" column={1} bordered className="version-history-descriptions">
        {fieldEntries.map(([field, { before, after }]) => (
          <Descriptions.Item key={field} label={FIELD_LABELS[field] ?? field}>
            <div className="version-history-diff-cell">
              <Text delete type="secondary" className="version-history-before">
                {formatValue(before)}
              </Text>
              <Text className="version-history-after">{formatValue(after)}</Text>
            </div>
          </Descriptions.Item>
        ))}
      </Descriptions>
    </Space>
  );
}
