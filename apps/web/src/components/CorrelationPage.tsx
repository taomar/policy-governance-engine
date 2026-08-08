import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Alert,
  App,
  Button,
  Card,
  Col,
  Empty,
  Row,
  Segmented,
  Select,
  Space,
  Statistic,
  Tag,
  Tooltip,
  Typography,
} from "antd";
import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  CloseCircleOutlined,
  NodeIndexOutlined,
  PlayCircleOutlined,
} from "@ant-design/icons";
import {
  aiApi,
  PolicyPlatformApiError,
  type CorrelationFinding,
  type CorrelationRunSummary,
} from "../api";
import { useActor } from "../ActorContext";

const { Title, Text, Paragraph } = Typography;

const SEVERITY_COLOR: Record<string, string> = {
  critical: "red",
  high: "volcano",
  medium: "gold",
  low: "blue",
  informational: "default",
};

const SEVERITY_ORDER: Record<string, number> = {
  critical: 0,
  high: 1,
  medium: 2,
  low: 3,
  informational: 4,
};

/**
 * Status is *not* a confidence score, and the colours say so: a `confirmed`
 * finding is stated as fact, `ambiguous` means the model could not decide and
 * needs a human definition, and `potential` sits between. Rendering these as a
 * percentage would invite reviewers to threshold them, which is exactly the
 * false precision Section 53 of the specification exists to prevent.
 */
const STATUS_COLOR: Record<string, string> = {
  confirmed: "red",
  potential: "orange",
  ambiguous: "purple",
  resolved: "green",
};

const DISPOSITION_COLOR: Record<string, string> = {
  open: "default",
  accepted: "red",
  dismissed: "default",
  resolved: "green",
};

function humanize(value: string): string {
  return value
    .split("_")
    .map((w) => w.charAt(0) + w.slice(1).toLowerCase())
    .join(" ");
}

function formatTimestamp(value: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

/**
 * Correlation view — relationships *between* rules.
 *
 * The Quality tab asks "is this rule well-formed?" one rule at a time, and that
 * question structurally cannot find a contradiction: both rules in a
 * contradictory pair usually read perfectly well on their own, and the defect
 * exists only in the relationship between them. This tab is that missing view.
 */
export function CorrelationPage({ policySetKey }: { policySetKey: string }) {
  const { message } = App.useApp();
  const { actor } = useActor();

  const [runs, setRuns] = useState<CorrelationRunSummary[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | undefined>();
  const [findings, setFindings] = useState<CorrelationFinding[]>([]);
  const [loading, setLoading] = useState(false);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [severityFilter, setSeverityFilter] = useState("all");
  const [dispositionFilter, setDispositionFilter] = useState("open");
  const [busyFindingId, setBusyFindingId] = useState<string | null>(null);

  const loadRuns = useCallback(async () => {
    try {
      const list = await aiApi.listCorrelationRuns(policySetKey);
      setRuns(list);
      return list;
    } catch (e) {
      setError(e instanceof PolicyPlatformApiError ? e.detail : String(e));
      return [];
    }
  }, [policySetKey]);

  const loadFindings = useCallback(
    async (runId?: string) => {
      setLoading(true);
      setError(null);
      try {
        const result = await aiApi.getCorrelationFindings(policySetKey, runId);
        setFindings(result.findings);
        if (result.run_id) setSelectedRunId(result.run_id);
      } catch (e) {
        setError(e instanceof PolicyPlatformApiError ? e.detail : String(e));
      } finally {
        setLoading(false);
      }
    },
    [policySetKey]
  );

  useEffect(() => {
    void loadRuns();
    void loadFindings();
  }, [loadRuns, loadFindings]);

  const runAnalysis = async () => {
    setRunning(true);
    setError(null);
    try {
      const result = await aiApi.runCorrelation(policySetKey, { actionable_only: true });
      // A run that stores nothing is a normal, good outcome, not a failure — say
      // what was examined so an empty findings list is not read as a broken run.
      message.success(
        result.findings_stored > 0
          ? `Analysed ${result.rules_analyzed} rules in ${result.groups_analyzed} groups — ${result.findings_stored} findings need a decision`
          : `Analysed ${result.rules_analyzed} rules in ${result.groups_analyzed} groups — examined ${result.findings_examined} relationships, none need a decision`
      );
      // A truncated run reporting "none need a decision" is the one case where a
      // reassuring result is actively misleading, so it gets its own warning
      // rather than being buried in the success line.
      if (result.rules_budget_skipped > 0) {
        message.warning(
          `${result.rules_budget_skipped} comparable rules fell outside the group budget and were not examined — this run covered ${result.groups_analyzed} of ${result.groups_available} comparison groups`,
          6
        );
      }
      await loadRuns();
      await loadFindings(result.correlation_run_id);
    } catch (e) {
      const detail = e instanceof PolicyPlatformApiError ? e.detail : String(e);
      setError(detail);
      message.error(detail);
    } finally {
      setRunning(false);
    }
  };

  const setDisposition = async (finding: CorrelationFinding, disposition: string) => {
    setBusyFindingId(finding.id);
    try {
      const updated = await aiApi.setFindingDisposition(finding.id, disposition, actor.name || "reviewer");
      setFindings((prev) => prev.map((f) => (f.id === updated.id ? updated : f)));
      message.success(`Finding marked ${disposition}`);
    } catch (e) {
      message.error(e instanceof PolicyPlatformApiError ? e.detail : String(e));
    } finally {
      setBusyFindingId(null);
    }
  };

  const visible = useMemo(
    () =>
      findings
        .filter((f) => severityFilter === "all" || f.severity === severityFilter)
        .filter((f) => dispositionFilter === "all" || f.disposition === dispositionFilter)
        .slice()
        .sort(
          (a, b) =>
            (SEVERITY_ORDER[a.severity] ?? 9) - (SEVERITY_ORDER[b.severity] ?? 9) ||
            a.classification.localeCompare(b.classification)
        ),
    [findings, severityFilter, dispositionFilter]
  );

  const counts = useMemo(
    () =>
      findings.reduce(
        (acc, f) => {
          acc[f.severity] = (acc[f.severity] ?? 0) + 1;
          return acc;
        },
        {} as Record<string, number>
      ),
    [findings]
  );

  const openCount = findings.filter((f) => f.disposition === "open").length;
  const selectedRun = runs.find((r) => r.id === selectedRunId);

  // "Not compared" has two causes that call for opposite responses, so the
  // explanation has to name the one that actually applies. A rule that shares
  // no signal with any other was never comparable and is nothing to act on; a
  // rule dropped by the group budget means this run is partial and a larger
  // budget would cover more. Presenting the total under the first explanation —
  // which is what this did — lets a truncated run read as a clean one.
  const budgetSkipped = selectedRun?.rules_budget_skipped ?? null;
  const truncated = budgetSkipped !== null && budgetSkipped > 0;
  const comparedCount = selectedRun
    ? Math.max(selectedRun.rules_analyzed - selectedRun.rules_uncompared, 0)
    : 0;
  const standAlone =
    selectedRun && budgetSkipped !== null
      ? Math.max(selectedRun.rules_uncompared - budgetSkipped, 0)
      : null;

  // A truncated run should say how much it left behind, not only that it left
  // something — otherwise the only remedy on offer is to guess a bigger number
  // and re-run blind.
  const groupsAvailable = selectedRun?.groups_available ?? null;
  const coverageSuffix =
    groupsAvailable !== null && selectedRun
      ? ` This run covered ${selectedRun.groups_analyzed} of the ${groupsAvailable} comparison groups the rules yield.`
      : "";

  const uncomparedExplanation = !selectedRun
    ? ""
    : budgetSkipped === null
      ? "Rules this run never compared. This run predates the breakdown, so how much of it was the group budget rather than rules genuinely standing alone is not recorded — re-run to find out."
      : truncated
        ? `Rules this run never compared. ${budgetSkipped} of them could have been compared but fell outside the group budget, so this analysis is partial — re-run with a larger budget to cover them. The other ${standAlone} shared no signal with any rule and were never comparable.${coverageSuffix}`
        : `Rules this run never compared. All of them shared no comparison signal with any other rule, so there was nothing to compare them against — the group budget did not cut anything short.${coverageSuffix}`;

  return (
    <>
      <div className="page-header-row">
        <Title level={3} style={{ margin: 0 }}>
          Correlation
        </Title>
        <Space>
          {runs.length > 0 && (
            <Select
              value={selectedRunId}
              onChange={(v) => {
                setSelectedRunId(v);
                void loadFindings(v);
              }}
              style={{ minWidth: 260 }}
              options={runs.map((r) => ({
                value: r.id,
                label: `${formatTimestamp(r.created_at)} · ${r.rules_analyzed} rules`,
              }))}
            />
          )}
          <Button type="primary" icon={<PlayCircleOutlined />} onClick={runAnalysis} loading={running}>
            {running ? "Analysing…" : "Run Correlation Analysis"}
          </Button>
        </Space>
      </div>

      <Paragraph type="secondary">
        Compares rules against each other to find contradictions, overlaps that need a precedence decision,
        duplicates and coverage gaps. Quality review examines one rule at a time and cannot see these — both rules
        in a contradictory pair are usually well-formed on their own. Findings carry a status rather than a
        confidence score: <Text code>confirmed</Text> is a statement of fact, <Text code>ambiguous</Text> means a
        human has to supply a missing definition before it can be settled.
      </Paragraph>

      {error && <Alert type="error" showIcon message={error} style={{ marginBottom: 16 }} />}

      {selectedRun && (
        <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
          <Col xs={12} lg={6}>
            <Card>
              {/* Titled "Rules analysed" over the corpus size, this asserted the
                  run examined every rule while the card two along said 79 of them
                  were never compared. Show what was actually compared, with the
                  corpus as context, so the two cards agree. */}
              <Tooltip
                title={`This run compared ${comparedCount} of the ${selectedRun.rules_analyzed} rules in scope. The rest are accounted for under "Not compared".`}
              >
                <Statistic
                  title="Rules compared"
                  value={comparedCount}
                  suffix={
                    <Text type="secondary" style={{ fontSize: 13 }}>
                      of {selectedRun.rules_analyzed}
                    </Text>
                  }
                />
              </Tooltip>
            </Card>
          </Col>
          <Col xs={12} lg={6}>
            <Card>
              <Statistic
                title="Critical + high"
                value={(counts.critical ?? 0) + (counts.high ?? 0)}
                valueStyle={{ color: "#cf222e" }}
              />
            </Card>
          </Col>
          <Col xs={12} lg={6}>
            <Card>
              <Statistic title="Awaiting decision" value={openCount} valueStyle={{ color: "#9a6700" }} />
            </Card>
          </Col>
          <Col xs={12} lg={6}>
            <Card>
              <Tooltip title={uncomparedExplanation}>
                <Statistic
                  title="Not compared"
                  value={selectedRun.rules_uncompared}
                  valueStyle={{ color: truncated ? "#9a6700" : "#57606a" }}
                  suffix={
                    truncated ? (
                      <Text type="warning" style={{ fontSize: 12, fontWeight: 500 }}>
                        run truncated
                      </Text>
                    ) : undefined
                  }
                />
              </Tooltip>
            </Card>
          </Col>
        </Row>
      )}

      <div className="page-header-row">
        <Title level={5} style={{ margin: 0 }}>
          Findings ({visible.length})
        </Title>
        <Space>
          <Segmented
            value={dispositionFilter}
            onChange={(v) => setDispositionFilter(v as string)}
            options={[
              { value: "open", label: "Open" },
              { value: "accepted", label: "Accepted" },
              { value: "dismissed", label: "Dismissed" },
              { value: "all", label: "All" },
            ]}
          />
          <Select
            value={severityFilter}
            onChange={setSeverityFilter}
            style={{ width: 160 }}
            options={[
              { value: "all", label: "All severities" },
              { value: "critical", label: "Critical" },
              { value: "high", label: "High" },
              { value: "medium", label: "Medium" },
              { value: "low", label: "Low" },
              { value: "informational", label: "Informational" },
            ]}
          />
        </Space>
      </div>

      {!loading && visible.length === 0 && (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description={
            runs.length === 0
              ? "No correlation analysis has been run for this policy set yet."
              : findings.length === 0
                ? `The last analysis examined ${comparedCount} of ${
                    selectedRun?.rules_analyzed ?? 0
                  } rules in ${
                    selectedRun?.groups_analyzed ?? 0
                  } groups and found nothing that needs a decision. Benign relationships — rules that are simply compatible, or that overlap without conflicting — are examined but not listed here.${
                    truncated
                      ? ` Note that ${budgetSkipped} comparable rules fell outside the group budget and were never examined, so this is not a clean bill of health for the whole set — re-run with a larger budget to cover them.`
                      : ""
                  }`
                : "No findings match the current filters."
          }
        />
      )}

      <Space direction="vertical" size={12} style={{ width: "100%" }}>
        {visible.map((finding) => (
          <Card
            key={finding.id}
            size="small"
            className="correlation-finding-card"
            title={
              <Space wrap size={8}>
                <NodeIndexOutlined />
                <Text strong>{humanize(finding.classification)}</Text>
                <Tag color={SEVERITY_COLOR[finding.severity] ?? "default"}>{finding.severity}</Tag>
                <Tag color={STATUS_COLOR[finding.analysis_status] ?? "default"}>{finding.analysis_status}</Tag>
                {finding.disposition !== "open" && (
                  <Tag color={DISPOSITION_COLOR[finding.disposition] ?? "default"}>{finding.disposition}</Tag>
                )}
              </Space>
            }
            extra={
              finding.disposition === "open" ? (
                <Space size={4}>
                  <Button
                    size="small"
                    icon={<CheckCircleOutlined />}
                    loading={busyFindingId === finding.id}
                    onClick={() => void setDisposition(finding, "accepted")}
                  >
                    Accept
                  </Button>
                  <Button
                    size="small"
                    icon={<CloseCircleOutlined />}
                    loading={busyFindingId === finding.id}
                    onClick={() => void setDisposition(finding, "dismissed")}
                  >
                    Dismiss
                  </Button>
                </Space>
              ) : (
                <Space size={4}>
                  <ClockCircleOutlined />
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    {finding.disposition_by ?? "—"} · {formatTimestamp(finding.disposition_at)}
                  </Text>
                  <Button size="small" type="link" onClick={() => void setDisposition(finding, "open")}>
                    Reopen
                  </Button>
                </Space>
              )
            }
          >
            <Paragraph style={{ marginBottom: 8 }}>{finding.reason}</Paragraph>

            <Space wrap size={4} style={{ marginBottom: 8 }}>
              <Text type="secondary" style={{ fontSize: 12 }}>
                Rules:
              </Text>
              {finding.rule_ids.map((id) => (
                <Tag key={id} style={{ fontFamily: "var(--font-mono, monospace)", fontSize: 11 }}>
                  {id}
                </Tag>
              ))}
            </Space>

            {finding.evidence.length > 0 && (
              <div className="correlation-evidence">
                {finding.evidence.map((ev, i) => (
                  <div key={`${finding.id}-ev-${i}`} className="correlation-evidence-item">
                    <Text type="secondary" style={{ fontSize: 11 }}>
                      {ev.rule_id || `rule #${ev.policy_index}`}
                    </Text>
                    {ev.source_text && <Paragraph style={{ margin: 0 }}>“{ev.source_text}”</Paragraph>}
                  </div>
                ))}
              </div>
            )}

            {finding.requirements.length > 0 && (
              <Alert
                type="info"
                showIcon
                style={{ marginTop: 8 }}
                message="Needed to settle this"
                description={
                  <ul style={{ margin: 0, paddingLeft: 18 }}>
                    {finding.requirements.map((r, i) => (
                      <li key={`${finding.id}-req-${i}`}>{r}</li>
                    ))}
                  </ul>
                }
              />
            )}
          </Card>
        ))}
      </Space>
    </>
  );
}
