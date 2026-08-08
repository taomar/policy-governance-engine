import { useEffect, useState } from "react";
import { Alert, Button, Card, Select, Space, Table, Tag, Typography } from "antd";
import { SwapOutlined, ThunderboltOutlined } from "@ant-design/icons";
import { aiApi, api, PolicyPlatformApiError, type ApprovedPolicyVersion, type CompareResult, type PolicySet } from "../api";
import { RuleCard } from "./RuleCard";
import { RuleDiffRow } from "./RuleDiffRow";

const { Title, Text, Paragraph } = Typography;

/**
 * Compare view — deterministic field-level diff between any two published
 * versions of a policy set (added / removed / changed rules), plus an
 * optional AI-generated plain-English narrative summarizing the practical
 * impact. The diff itself is always computed deterministically server-side;
 * the AI only summarizes it, so the two are clearly separated in the UI.
 */
export function ComparePage({ policySetKey }: { policySetKey?: string } = {}) {
  const scoped = Boolean(policySetKey);
  const [policySets, setPolicySets] = useState<PolicySet[]>([]);
  const [selectedKey, setSelectedKey] = useState(policySetKey ?? "");
  const [versions, setVersions] = useState<ApprovedPolicyVersion[]>([]);
  const [versionA, setVersionA] = useState<number | "">("");
  const [versionB, setVersionB] = useState<number | "">("");
  const [result, setResult] = useState<CompareResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Lazy-mount set: only rules the user has explicitly expanded get a full
  // RuleCard (evidence resolution + Notes fetch). Keeps a large diff (e.g.
  // hundreds of added rules from a big candidate-batch publish) from firing
  // hundreds of effects/requests on render — see RuleDiffRow for detail.
  const [expandedDiffIds, setExpandedDiffIds] = useState<Set<string>>(new Set());

  const toggleDiffExpanded = (ruleId: string) => {
    setExpandedDiffIds((prev) => {
      const next = new Set(prev);
      if (next.has(ruleId)) next.delete(ruleId);
      else next.add(ruleId);
      return next;
    });
  };

  useEffect(() => {
    if (scoped) return; // scope is fixed by the embedding project; no picker/list needed
    api
      .listPolicySets()
      .then((sets) => {
        setPolicySets(sets);
        if (sets.length > 0) setSelectedKey(sets[0].key);
      })
      .catch((e) => setError(e instanceof PolicyPlatformApiError ? e.detail : String(e)));
  }, [scoped]);

  useEffect(() => {
    if (!selectedKey) return;
    setResult(null);
    api
      .listPolicyVersions(selectedKey)
      .then((vs) => {
        const sorted = [...vs].sort((a, b) => a.version_number - b.version_number);
        setVersions(sorted);
        if (sorted.length >= 2) {
          setVersionA(sorted[sorted.length - 2].version_number);
          setVersionB(sorted[sorted.length - 1].version_number);
        } else if (sorted.length === 1) {
          setVersionA(sorted[0].version_number);
          setVersionB(sorted[0].version_number);
        }
      })
      .catch((e) => setError(e instanceof PolicyPlatformApiError ? e.detail : String(e)));
  }, [selectedKey]);

  const runCompare = async () => {
    if (versionA === "" || versionB === "") return;
    setLoading(true);
    setError(null);
    setResult(null);
    setExpandedDiffIds(new Set());
    try {
      const r = await aiApi.compareVersions(selectedKey, versionA, versionB);
      setResult(r);
    } catch (e) {
      setError(e instanceof PolicyPlatformApiError ? e.detail : String(e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <div className="page-header-row">
        <Title level={3} style={{ margin: 0 }}>
          Compare Versions
        </Title>
        {!scoped && (
          <Select
            value={selectedKey}
            onChange={setSelectedKey}
            style={{ minWidth: 220 }}
            options={policySets.map((ps) => ({ value: ps.key, label: ps.name }))}
          />
        )}
      </div>
      <Paragraph type="secondary">
        Compares two published versions rule-by-rule. Note: AI-drafted rules get a fresh ID each time they're
        extracted, so re-extracting the same document as a new version will show its rules as "added" rather than
        "changed" against a prior AI extraction — this is a known limitation of matching AI-drafted rules across
        independent extraction runs, not a bug in the diff itself.
      </Paragraph>

      {error && <Alert type="error" showIcon message={error} />}
      {!scoped && policySets.length === 0 && <Text type="secondary">Create a policy set first.</Text>}

      {selectedKey && versions.length > 0 && (
        <Card>
          <Space size={16} wrap>
            <Space>
              <Text>From</Text>
              <Select
                value={versionA}
                onChange={(v) => setVersionA(Number(v))}
                style={{ width: 120 }}
                options={versions.map((v) => ({ value: v.version_number, label: `v${v.version_number}` }))}
              />
            </Space>
            <Space>
              <Text>To</Text>
              <Select
                value={versionB}
                onChange={(v) => setVersionB(Number(v))}
                style={{ width: 120 }}
                options={versions.map((v) => ({ value: v.version_number, label: `v${v.version_number}` }))}
              />
            </Space>
            <Button type="primary" icon={<SwapOutlined />} onClick={runCompare} loading={loading}>
              {loading ? "Comparing…" : "Compare"}
            </Button>
          </Space>
        </Card>
      )}

      {selectedKey && versions.length < 2 && (
        <Text type="secondary">This policy set needs at least 2 published versions to compare.</Text>
      )}

      {result && (
        <>
          {result.narrative && (
            <Card>
              <Space size={8} style={{ marginBottom: 8 }}>
                <ThunderboltOutlined style={{ color: "#7c3aed" }} />
                <Text strong>AI Summary</Text>
              </Space>
              <Paragraph style={{ marginBottom: 0 }}>{result.narrative}</Paragraph>
            </Card>
          )}

          <Space size={10} wrap>
            <Tag color="green">+{result.added.length} added</Tag>
            <Tag color="red">-{result.removed.length} removed</Tag>
            <Tag color="gold">{result.changed.length} changed</Tag>
            <Tag>{result.unchanged_count} unchanged</Tag>
          </Space>

          {result.added.length > 0 && (
            <Card title="Added Rules">
              <Space direction="vertical" style={{ width: "100%" }} size={8}>
                {result.added.map((r) => (
                  <div key={r.rule_id}>
                    <RuleDiffRow
                      rule={r}
                      diffKind="added"
                      expanded={expandedDiffIds.has(r.rule_id)}
                      onToggleExpand={() => toggleDiffExpanded(r.rule_id)}
                    />
                    {expandedDiffIds.has(r.rule_id) && (
                      <div className="candidate-item-detail">
                        <RuleCard rule={r} defaultExpanded />
                      </div>
                    )}
                  </div>
                ))}
              </Space>
            </Card>
          )}

          {result.removed.length > 0 && (
            <Card title="Removed Rules">
              <Space direction="vertical" style={{ width: "100%" }} size={8}>
                {result.removed.map((r) => (
                  <div key={r.rule_id}>
                    <RuleDiffRow
                      rule={r}
                      diffKind="removed"
                      expanded={expandedDiffIds.has(r.rule_id)}
                      onToggleExpand={() => toggleDiffExpanded(r.rule_id)}
                    />
                    {expandedDiffIds.has(r.rule_id) && (
                      <div className="candidate-item-detail">
                        <RuleCard rule={r} defaultExpanded />
                      </div>
                    )}
                  </div>
                ))}
              </Space>
            </Card>
          )}

          {result.changed.length > 0 && (
            <Card title="Changed Rules">
              <Space direction="vertical" style={{ width: "100%" }} size={16}>
                {result.changed.map((c) => (
                  <Card key={c.rule_id} type="inner" title={`${c.rule_id} — ${c.title}`}>
                    <Table
                      size="small"
                      pagination={false}
                      rowKey="field"
                      dataSource={Object.entries(c.changed_fields).map(([field, { before, after }]) => ({
                        field,
                        before,
                        after,
                      }))}
                      columns={[
                        { title: "Field", dataIndex: "field" },
                        { title: "Before", dataIndex: "before", render: (v) => JSON.stringify(v) },
                        { title: "After", dataIndex: "after", render: (v) => JSON.stringify(v) },
                      ]}
                    />
                  </Card>
                ))}
              </Space>
            </Card>
          )}
        </>
      )}
    </>
  );
}
