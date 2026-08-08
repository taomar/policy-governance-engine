import { useState } from "react";
import { Alert, Button, Card, Collapse, Space, Tag, Typography } from "antd";
import { ReloadOutlined, ThunderboltOutlined } from "@ant-design/icons";
import { aiApi, PolicyPlatformApiError, type PolicySetSummary } from "../api";

const { Text, Paragraph } = Typography;

function formatLabel(raw: string): string {
  return raw
    .split("_")
    .map((w) => (w ? w[0].toUpperCase() + w.slice(1) : w))
    .join(" ");
}

const SCOPE_DIMENSIONS = ["jurisdictions", "organizational_units", "personas", "processes"] as const;

/** Lightweight proportional bar list — avoids pulling in a charting library for
 * what is just "rank these counts against the total". */
function BreakdownBars({ counts, total }: { counts: Record<string, number>; total: number }) {
  const entries = Object.entries(counts).sort((a, b) => b[1] - a[1]);
  if (entries.length === 0) return <Text type="secondary">No data.</Text>;
  return (
    <div className="summary-bars">
      {entries.map(([label, count]) => (
        <div className="summary-bar-row" key={label}>
          <span className="summary-bar-label">{formatLabel(label)}</span>
          <div className="summary-bar-track">
            <div className="summary-bar-fill" style={{ width: `${total ? (count / total) * 100 : 0}%` }} />
          </div>
          <span className="summary-bar-count">{count}</span>
        </div>
      ))}
    </div>
  );
}

/** Renders the AI narrative's paragraphs/bullet-lists as real HTML elements
 * instead of one flattened blob of text, without pulling in a markdown
 * renderer for what is a very constrained, predictable shape (see
 * ai_summary.py's system prompt: short paragraphs + a bullet list). */

/** Splits on `**bold**` runs and renders them as real <strong> — defense in
 * depth in case the model doesn't perfectly follow the "no markdown" system
 * prompt instruction every time. Also tolerates a stray leading "- " getting
 * folded into a bold label (e.g. "**Label:**") by stripping bare "**". */
function InlineFormatted({ text }: { text: string }) {
  const parts = text.split(/\*\*(.+?)\*\*/g);
  return (
    <>
      {parts.map((part, i) =>
        i % 2 === 1 ? <strong key={i}>{part}</strong> : <span key={i}>{part}</span>
      )}
    </>
  );
}

function NarrativeBlocks({ text }: { text: string }) {
  const blocks = text.split(/\n{2,}/).filter((b) => b.trim().length > 0);
  return (
    <>
      {blocks.map((block, i) => {
        const lines = block.split("\n").filter((l) => l.trim().length > 0);
        const isBulletBlock = lines.length > 0 && lines.every((l) => /^[-*]\s+/.test(l.trim()));
        if (isBulletBlock) {
          return (
            <ul className="summary-narrative-list" key={i}>
              {lines.map((l, j) => (
                <li key={j}>
                  <InlineFormatted text={l.trim().replace(/^[-*]\s+/, "")} />
                </li>
              ))}
            </ul>
          );
        }
        return (
          <Paragraph key={i}>
            <InlineFormatted text={block} />
          </Paragraph>
        );
      })}
    </>
  );
}

/**
 * Whole-policy-set rollup shown on the project Overview tab: a deterministic
 * rule-count/scope/override breakdown (always available, always exact — see
 * ai_summary.py) plus an optional AI-generated plain-English narrative of
 * what the policy set as a whole governs. Manually triggered (mirrors the
 * Test-scenario tab's UX) rather than auto-firing an AI call every time a
 * reviewer opens the Overview tab.
 */
export function PolicySetSummaryPanel({ policySetKey }: { policySetKey: string }) {
  const [summary, setSummary] = useState<PolicySetSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const generate = async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await aiApi.getPolicySetSummary(policySetKey, true);
      setSummary(result);
    } catch (e) {
      setError(e instanceof PolicyPlatformApiError ? e.detail : String(e));
    } finally {
      setLoading(false);
    }
  };

  const stats = summary?.stats;
  const flaggedAmbiguous = stats
    ? (stats.by_ambiguity_status.blocking ?? 0) +
      (stats.by_ambiguity_status.non_blocking ?? 0) +
      (stats.by_ambiguity_status.human_judgment_required ?? 0)
    : 0;

  return (
    <Card
      className="policy-summary-card"
      title={
        <Space size={8}>
          <ThunderboltOutlined style={{ color: "#7c3aed" }} />
          <span>Policy Set Summary</span>
        </Space>
      }
      extra={
        <Button size="small" icon={summary ? <ReloadOutlined /> : <ThunderboltOutlined />} onClick={generate} loading={loading}>
          {summary ? "Regenerate" : "Generate summary"}
        </Button>
      }
      style={{ marginTop: 16 }}
    >
      {error && <Alert type="error" showIcon message={error} style={{ marginBottom: 12 }} />}

      {!summary && !loading && !error && (
        <Text type="secondary">
          Get a plain-English rollup of what this whole policy set governs — who it applies to, key thresholds and
          approval chains, explicit overrides — plus a deterministic breakdown of rule types, effects, and coverage
          for the active published version.
        </Text>
      )}

      {summary && stats && (
        <>
          <div className="summary-stat-strip">
            <div className="summary-stat">
              <div className="summary-stat-value">{stats.total_rules}</div>
              <div className="summary-stat-label">Rules (v{summary.version_number})</div>
            </div>
            <div className="summary-stat">
              <div className="summary-stat-value" style={{ color: "#cf222e" }}>
                {stats.by_effect.deny ?? 0}
              </div>
              <div className="summary-stat-label">Deny</div>
            </div>
            <div className="summary-stat">
              <div className="summary-stat-value" style={{ color: "#059669" }}>
                {stats.by_effect.allow ?? 0}
              </div>
              <div className="summary-stat-label">Allow</div>
            </div>
            <div className="summary-stat">
              <div className="summary-stat-value" style={{ color: "#2563eb" }}>
                {stats.by_effect.require_action ?? 0}
              </div>
              <div className="summary-stat-label">Require action</div>
            </div>
            <div className="summary-stat">
              <div className="summary-stat-value" style={{ color: flaggedAmbiguous > 0 ? "#d97706" : "#94a3b8" }}>
                {flaggedAmbiguous}
              </div>
              <div className="summary-stat-label">Flagged ambiguous</div>
            </div>
            <div className="summary-stat">
              <div className="summary-stat-value" style={{ color: stats.explicit_overrides_count > 0 ? "#7c3aed" : "#94a3b8" }}>
                {stats.explicit_overrides_count}
              </div>
              <div className="summary-stat-label">Explicit overrides</div>
            </div>
          </div>

          {summary.narrative ? (
            <div className="summary-narrative">
              <NarrativeBlocks text={summary.narrative} />
            </div>
          ) : (
            <Alert
              type="warning"
              showIcon
              message="AI narrative unavailable"
              description="The deterministic breakdown below is still exact; the plain-English narrative could not be generated (AI may be disabled or the call failed)."
              style={{ margin: "12px 0" }}
            />
          )}

          <Collapse
            ghost
            className="summary-detail-collapse"
            style={{ marginTop: 4 }}
            items={[
              {
                key: "breakdown",
                label: "Detailed breakdown (rule type & category)",
                children: (
                  <div className="summary-breakdown-grid">
                    <div>
                      <Text strong>By rule type</Text>
                      <BreakdownBars counts={stats.by_rule_type} total={stats.total_rules} />
                    </div>
                    <div>
                      <Text strong>By category</Text>
                      <BreakdownBars counts={stats.by_category} total={stats.total_rules} />
                    </div>
                  </div>
                ),
              },
              {
                key: "coverage",
                label: "Scope coverage (who / where this policy set applies to)",
                children: (
                  <Space direction="vertical" size={10} style={{ width: "100%" }}>
                    {SCOPE_DIMENSIONS.map((dim) => (
                      <div key={dim}>
                        <Text type="secondary" style={{ display: "block", marginBottom: 4 }}>
                          {formatLabel(dim)}
                        </Text>
                        <Space size={4} wrap>
                          {stats.scope_coverage[dim].length > 0 ? (
                            stats.scope_coverage[dim].map((v) => (
                              <Tag key={v} className="fact-tag">
                                {v}
                              </Tag>
                            ))
                          ) : (
                            <Text type="secondary">—</Text>
                          )}
                        </Space>
                      </div>
                    ))}
                  </Space>
                ),
              },
              ...(stats.explicit_overrides_count > 0
                ? [
                    {
                      key: "overrides",
                      label: `Explicit overrides (${stats.explicit_overrides_count})`,
                      children: (
                        <Space direction="vertical" size={6}>
                          {stats.explicit_overrides.map((o) => (
                            <div key={o.rule_id}>
                              <Text>{o.title}</Text>{" "}
                              <Text type="secondary" style={{ fontSize: 12 }}>
                                ({o.rule_id})
                              </Text>
                            </div>
                          ))}
                        </Space>
                      ),
                    },
                  ]
                : []),
            ]}
          />
        </>
      )}
    </Card>
  );
}
