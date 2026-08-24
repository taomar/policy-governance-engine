import { useEffect, useMemo, useState } from "react";
import { Alert, Button, Input, Modal, Radio, Select, Space, Table, Tag, Typography } from "antd";
import { ReadOutlined } from "@ant-design/icons";
import {
  api,
  PolicyPlatformApiError,
  type AssembledPolicy,
  type ProjectCaseAnswer,
  type ProjectCaseCitation,
  type ProjectCaseGrounding,
  type ProjectCaseJudgement,
  type ProjectCasePolicyCandidate,
  type ProjectCaseRetrievalStatus,
  type QualityFinding,
} from "../api";
import { formatElapsed } from "../uploadFeedback";
import { retrievalStatusIsIndexRepairable } from "../policyIndexHealth";
import { DirectionalText } from "./DirectionalText";
import { findingsForRuleIds, loadLatestPublishedQualityFindings, projectCaseRuleIds } from "../qualityFindingLinks";
import "./policyCaseRunner.css";

const { Paragraph, Text } = Typography;
const { TextArea } = Input;

type ReasoningEffort = "low" | "medium" | "high";
type CaseScope = "project" | "single";

const RETRIEVAL_COPY: Record<ProjectCaseRetrievalStatus, { type: "success" | "info" | "warning" | "error"; message: string; description: string }> = {
  narrowed: {
    type: "success",
    message: "Search narrowed the published policies before evaluation",
    description:
      "The project was not evaluated as one undifferentiated set. Search kept the highest matching published policies and discarded the rest before the answer was composed.",
  },
  not_narrowed: {
    type: "info",
    message: "All published policies were evaluated",
    description:
      "This project has few enough published policies that search did not need to select between them. Every published policy went to evaluation, and none was discarded.",
  },
  bypassed: {
    type: "info",
    message: "Retrieval was bypassed for the policy you chose",
    description:
      "You selected one published policy, so the case was put to that policy directly instead of searching across the project.",
  },
  no_published_version: {
    type: "info",
    message: "This project has no published policies yet",
    description: "There is no published project scope to test. Publish policies first, or choose a project that already has a published version.",
  },
  no_match: {
    type: "info",
    message: "Published policies were searched; none matched this case",
    description: "The project has published policies, but retrieval found none that bear on this question. Nothing was evaluated.",
  },
  index_not_built: {
    type: "warning",
    message: "The policy search index has not been built for this project",
    description: "The app will not fall back to evaluating every published policy. Build or refresh the index, or choose one policy directly.",
  },
  index_stale: {
    type: "warning",
    message: "The policy search index is stale for the active published version",
    description: "The app will not trust an index for another version. Refresh the index, or choose one policy directly.",
  },
  index_empty: {
    type: "warning",
    message: "The published policies are not searchable in the index",
    description: "Retrieval cannot be relied on for this project, so the app did not evaluate every policy as a fallback.",
  },
  unavailable: {
    type: "warning",
    message: "Policy search is not available on this server",
    description: "Project-wide testing depends on search to narrow the scope. Choose one policy directly, or run this where search is configured.",
  },
  failed: {
    type: "error",
    message: "Policy search failed before evaluation",
    description: "The app did not evaluate every published policy after the search failure. Try again, or choose one policy directly.",
  },
  empty: {
    type: "info",
    message: "The active published version has no policy rules to test",
    description: "A version exists, but it contains no live rules that can answer a case.",
  },
};

function policyLabel(policy: AssembledPolicy | ProjectCasePolicyCandidate): string {
  const path = policy.heading_path?.filter(Boolean) ?? [];
  if (path.length > 0) return path.join(" › ");
  return "heading" in policy ? policy.heading : policy.provision_key;
}

function discardLabel(reason: string | null | undefined): string {
  if (!reason) return "—";
  return reason
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function policiesDiscarded(answer: ProjectCaseAnswer): number | null {
  return answer.retrieval.policies_discarded ?? answer.considered?.filter((p) => p.retained === false).length ?? null;
}

function allPublishedPoliciesWereEvaluated(answer: ProjectCaseAnswer): boolean {
  const discarded = policiesDiscarded(answer);
  return answer.retrieval.status === "not_narrowed" || (answer.retrieval.status === "narrowed" && discarded === 0);
}

const DECISION_STATUS_COPY: Record<string, { label: string; color: string; title: string; description: string }> = {
  answered: {
    label: "Answered",
    color: "green",
    title: "The evaluated rules settle this case",
    description: "The verdict below is the decision returned from the evaluated published policies.",
  },
  missing_required_facts: {
    label: "Needs facts",
    color: "gold",
    title: "The evaluated rules need more facts",
    description: "The policy can answer this only if the case supplies the missing facts listed below.",
  },
  not_settled_by_rules: {
    label: "Not settled by rules",
    color: "blue",
    title: "The evaluated rules bear on the case but do not settle it",
    description: "This is not a verdict. The answer explains what the evaluated rules say and what they do not decide.",
  },
  no_rule_bears: {
    label: "No evaluated rule bears",
    color: "default",
    title: "No evaluated rule bears on this case",
    description: "The policies listed below were read, but none contains a rule that speaks to this scenario.",
  },
  declined: {
    label: "No answer composed",
    color: "orange",
    title: "No decision answer was composed",
    description: "The request reached the evaluated rules, but no usable decision answer was returned.",
  },
};

function RawResponse({ value }: { value: unknown }) {
  return (
    <details className="project-case-raw">
      <summary>Show raw response</summary>
      <pre className="project-case-json">{JSON.stringify(value, null, 2)}</pre>
    </details>
  );
}

function CitationList({ citations }: { citations: readonly ProjectCaseCitation[] }) {
  if (citations.length === 0) return null;
  return (
    <div className="project-case-citations" data-testid="project-case-citations">
      <Paragraph style={{ marginBottom: 4 }}>
        <Text strong>
          {citations.length === 1
            ? "The answer rests on this cited rule:"
            : `The answer rests on these ${citations.length} cited rules:`}
        </Text>
      </Paragraph>
      {citations.map((citation, index) => {
        const policy = citation.policy?.heading_path?.filter(Boolean).join(" › ") || citation.policy?.provision_key || "Retained policy";
        const source = citation.source;
        return (
          <div key={`${citation.policy?.provision_key ?? "policy"}-${citation.rule_id}-${index}`} className="policy-case-citation">
            <Text strong>{policy}</Text>
            <div className="project-case-citation__meta">
              <Text code>{citation.rule_id}</Text>
              {source?.section ? <Text type="secondary">Section {source.section}</Text> : null}
              {typeof source?.page === "number" ? <Text type="secondary">Page {source.page}</Text> : null}
            </div>
            {source?.text ? (
              <p className="policy-case-citation__quote">
                “<DirectionalText>{source.text}</DirectionalText>”
              </p>
            ) : (
              <Text type="secondary">
                {source?.state
                  ? `The citation source is ${discardLabel(source.state)}; no verbatim quote was returned.`
                  : "The cited source text was not returned with this citation."}
              </Text>
            )}
          </div>
        );
      })}
    </div>
  );
}

function GroundingLine({ grounding }: { grounding: ProjectCaseGrounding | undefined }) {
  if (!grounding) return null;
  const fabricated = grounding.fabricated_citations ?? [];
  return (
    <div data-testid="project-case-grounding">
      {fabricated.length > 0 ? (
        <Alert
          type="warning"
          showIcon
          className="project-case-grounding-warning"
          title={
            fabricated.length === 1
              ? "A fabricated citation was refused"
              : `${fabricated.length} fabricated citations were refused`
          }
          description={`The answer tried to cite ${fabricated.join(", ")}, which ${
            fabricated.length === 1 ? "is not a rule" : "are not rules"
          } in the evaluated policies. ${
            fabricated.length === 1 ? "It was" : "They were"
          } dropped and reported here rather than shown as evidence.`}
        />
      ) : (
        <Paragraph type="secondary" style={{ fontSize: 12, marginBottom: 0 }}>
          Grounded on {grounding.rules_available ?? "—"} evaluated rules
          {typeof grounding.policies_grounded === "number" ? ` across ${grounding.policies_grounded} policies` : ""};
          cited {grounding.rules_cited ?? "—"} rule{grounding.rules_cited === 1 ? "" : "s"}. No refused citations were reported.
        </Paragraph>
      )}
      {grounding.oversize ? (
        <Alert
          type="warning"
          showIcon
          style={{ marginTop: 8 }}
          title="The evaluated policy payload was too large to read in one grounded pass"
          description="No partial answer should be treated as complete."
        />
      ) : null}
    </div>
  );
}

function RetrievalSummary({ answer, onOpenPolicyIndex }: { answer: ProjectCaseAnswer; onOpenPolicyIndex?: (status: string) => void }) {
  const status = answer.retrieval.status;
  const discarded = policiesDiscarded(answer);
  const allEvaluated = allPublishedPoliciesWereEvaluated(answer);
  const copy = allEvaluated
    ? RETRIEVAL_COPY.not_narrowed
    : RETRIEVAL_COPY[status] ?? {
        type: "warning" as const,
        message: `Retrieval returned ${status}`,
        description: "This status is not known by this client. The raw narrowing details below are still shown.",
      };
  const canRepairIndex = retrievalStatusIsIndexRepairable(status);
  const retained = answer.retrieval.policies_retained ?? answer.considered?.filter((p) => p.retained).length ?? null;
  const considered = answer.retrieval.policies_considered ?? answer.considered?.length ?? null;
  return (
    <Alert
      showIcon
      type={copy.type}
      data-testid={`project-case-status-${status}`}
      title={copy.message}
      action={
        canRepairIndex && onOpenPolicyIndex ? (
          <Button size="small" onClick={() => onOpenPolicyIndex(status)}>
            Open index repair
          </Button>
        ) : undefined
      }
      description={
        <Space orientation="vertical" size={4}>
          <Text>{copy.description}</Text>
          {canRepairIndex && onOpenPolicyIndex ? (
            <Text type="secondary">Open the Overview readiness panel to rebuild the recorded project-wide case index.</Text>
          ) : null}
          {answer.retrieval.reason ? <Text type="secondary">{answer.retrieval.reason}</Text> : null}
          {considered !== null || retained !== null || discarded !== null ? (
            <Text type="secondary">
              {allEvaluated
                ? `${considered ?? "—"} published policies · all evaluated · ${discarded ?? 0} discarded`
                : `${considered ?? "—"} considered · ${retained ?? "—"} retained · ${discarded ?? "—"} discarded`}
            </Text>
          ) : null}
        </Space>
      }
    />
  );
}

function QualityFindingNotice({
  findings,
  ruleIds,
}: {
  findings: readonly QualityFinding[];
  ruleIds: readonly string[];
}) {
  const linked = findingsForRuleIds(findings, ruleIds);
  if (linked.length === 0) return null;
  return (
    <Alert
      type="warning"
      showIcon
      style={{ marginBottom: 12 }}
      title="Known quality finding covers rules in this result"
      description={
        <Space orientation="vertical" size={4}>
          {linked.map((finding, index) => (
            <span key={`${finding.category}-${finding.matched_rule_ids.join("-")}-${index}`}>
              <Tag color={finding.severity === "high" ? "red" : finding.severity === "medium" ? "gold" : "default"}>
                {finding.severity}
              </Tag>{" "}
              <strong>{finding.category.replace(/_/g, " ")}</strong> on {finding.matched_rule_ids.join(", ")}
              {finding.summary ? ` — ${finding.summary}` : ""}
            </span>
          ))}
        </Space>
      }
    />
  );
}

function EvaluationPanel({
  answer,
  qualityFindings,
}: {
  answer: ProjectCaseAnswer;
  qualityFindings: readonly QualityFinding[];
}) {
  const evaluation = answer.evaluation;
  if (!evaluation) return null;
  const linkedRuleIds = projectCaseRuleIds(answer);

  if (evaluation.intent === "decision") {
    const judgement =
      evaluation.decision ??
      evaluation.judgement ??
      (evaluation.status
        ? ({
            status: evaluation.status,
            verdict: evaluation.verdict,
            answer: evaluation.answer,
            missing_required_facts: evaluation.missing_required_facts,
            citations: evaluation.citations,
            note: evaluation.note,
            grounding: evaluation.grounding,
          } satisfies ProjectCaseJudgement)
        : null);
    const status = judgement?.status ?? "declined";
    const copy = DECISION_STATUS_COPY[status] ?? {
      label: discardLabel(status),
      color: "default",
      title: `Decision status: ${discardLabel(status)}`,
      description: "This status is not known by this client. The raw response is available below.",
    };
    const verdict = judgement?.verdict?.trim() ?? "";
    const missing = judgement?.missing_required_facts?.filter(Boolean) ?? [];
    const citations = judgement?.citations ?? [];
    return (
      <div className="policy-case-reading" data-testid="project-case-decision">
        <QualityFindingNotice findings={qualityFindings} ruleIds={linkedRuleIds} />
        <Paragraph style={{ marginBottom: 8 }}>
          <Tag color={copy.color}>{copy.label}</Tag>{" "}
          <Tag color="blue">AI Ready judge</Tag>{" "}
          <Text strong>{copy.title}</Text>
        </Paragraph>
        {judgement ? (
          <>
            {status === "answered" ? (
              verdict ? (
                <div className="project-case-verdict" data-testid="project-case-verdict">
                  <Text type="secondary">Verdict</Text>
                  <Text strong>{verdict}</Text>
                </div>
              ) : (
                <Alert
                  type="warning"
                  showIcon
                  title="The answer status is answered, but no verdict was returned"
                  description="No verdict chip is shown because an empty verdict string is not a decision."
                />
              )
            ) : null}
            <Paragraph type="secondary" style={{ marginBottom: 8 }}>
              {copy.description}
            </Paragraph>
            {judgement.answer ? (
              <div className="app-synthesis" data-generated="true" data-testid="project-case-decision-answer">
                <div>
                  <span className="app-synthesis__mark" aria-hidden>
                    ✦
                  </span>{" "}
                  {/* The informational path says "answer composed by this app", which is
                      exactly right there — the app really did compose the answer. On a
                      decision it would be false in the way that matters: the verdict shown
                      above came from the deterministic evaluator, and only the words
                      explaining it were composed. Saying the app composed "the answer"
                      invites a reader to think the model reached the outcome, which is the
                      one claim this product cannot afford to blur. */}
                  <span className="app-synthesis__caption">
                    Explanation composed by this app. The decision above came from the evaluator.
                  </span>
                </div>
                <Paragraph className="app-synthesis__body" style={{ marginBottom: 0 }}>
                  <DirectionalText align>{judgement.answer}</DirectionalText>
                </Paragraph>
              </div>
            ) : (
              <Alert
                type="info"
                showIcon
                title="No answer prose was returned"
                description="The status above is shown, and the raw response is available below."
              />
            )}
            {missing.length > 0 ? (
              <Alert
                type="warning"
                showIcon
                data-testid="project-case-missing-facts"
                title="Facts needed to answer this case"
                description={
                  <Space wrap size={4}>
                    {missing.map((fact) => (
                      <Tag key={fact} color="gold">
                        {fact}
                      </Tag>
                    ))}
                  </Space>
                }
              />
            ) : null}
            {judgement.note ? (
              <Paragraph type="secondary">
                <DirectionalText>{judgement.note}</DirectionalText>
              </Paragraph>
            ) : null}
            <CitationList citations={citations} />
            <GroundingLine grounding={judgement.grounding} />
            <RawResponse value={judgement} />
          </>
        ) : (
          <Alert
            type="info"
            showIcon
            title="This was classified as a decision, but no judgement was returned"
            description="No verdict is shown. The backend currently returns no decision judgement for this path, so the UI leaves the decision space explicit rather than inventing an answer."
          />
        )}
      </div>
    );
  }

  const informational = evaluation.informational;
  if (!informational) return null;
  if (informational.status !== "answered") {
    return (
      <Alert
        type={informational.status === "no_rule_bears" ? "info" : "warning"}
        showIcon
        data-testid="project-case-informational-empty"
        title={
          informational.status === "no_rule_bears"
            ? "The evaluated policies did not state an answer"
            : "No project answer was composed"
        }
        description={
          <Space orientation="vertical" size={8}>
            <Text>
              {informational.status === "no_rule_bears"
                ? "The policies listed below were read, but none answered the question."
                : "The retrieval result is shown below so you can see what was and was not read."}
            </Text>
            {informational.note ? (
              <Text type="secondary">
                <DirectionalText>{informational.note}</DirectionalText>
              </Text>
            ) : null}
            <RawResponse value={informational} />
          </Space>
        }
      />
    );
  }

  return (
    <div data-testid="project-case-answer">
      <QualityFindingNotice findings={qualityFindings} ruleIds={linkedRuleIds} />
      <div className="app-synthesis" data-generated="true">
        <div>
          <span className="app-synthesis__mark" aria-hidden>
            ✦
          </span>{" "}
          <span className="app-synthesis__caption">AI Ready judge read the evaluated policies below</span>
        </div>
        <Paragraph className="app-synthesis__body" style={{ marginBottom: 0 }}>
          <DirectionalText align>{informational.answer ?? ""}</DirectionalText>
        </Paragraph>
      </div>
      {informational.note ? (
        <Paragraph type="secondary">
          <DirectionalText>{informational.note}</DirectionalText>
        </Paragraph>
      ) : null}
      <CitationList citations={informational.citations ?? []} />
      <GroundingLine grounding={informational.grounding} />
      <RawResponse value={informational} />
    </div>
  );
}

function ConsideredPolicies({ answer }: { answer: ProjectCaseAnswer }) {
  const considered = answer.scope === "single" && answer.provision ? [answer.provision] : (answer.considered ?? []);
  const excluded = answer.excluded ?? [];
  const notNarrowed = allPublishedPoliciesWereEvaluated(answer);
  return (
    <Space orientation="vertical" size={12} style={{ width: "100%" }}>
      <div>
        <Paragraph style={{ marginBottom: 6 }}>
          <Text strong>{notNarrowed ? "Published policies evaluated" : "Policies considered by narrowing"}</Text>
        </Paragraph>
        <Table<ProjectCasePolicyCandidate>
          size="small"
          rowKey={(row) => row.provision_id || row.provision_key}
          dataSource={considered}
          pagination={false}
          data-testid="project-case-considered"
          locale={{ emptyText: "No candidate policies were considered for this status." }}
          columns={[
            {
              title: "Policy",
              render: (_: unknown, row) => (
                <Space orientation="vertical" size={0}>
                  <Text>{policyLabel(row)}</Text>
                  <Text type="secondary" code>
                    {row.provision_key}
                  </Text>
                </Space>
              ),
            },
            { title: "Rules", dataIndex: "rules", width: 80 },
            {
              title: "Evaluation role",
              dataIndex: "retained",
              width: 110,
              render: (retained: boolean | undefined) =>
                notNarrowed ? (
                  <Tag color="blue">Evaluated</Tag>
                ) : answer.scope === "single" ? (
                  <Tag color="blue">Chosen</Tag>
                ) : retained ? (
                  <Tag color="green">Retained</Tag>
                ) : (
                  <Tag>Discarded</Tag>
                ),
            },
            { title: "Best rank", dataIndex: "best_rank", width: 100, render: (v: number | null | undefined) => v ?? "—" },
            {
              title: "Best score",
              dataIndex: "best_score",
              width: 110,
              render: (v: number | null | undefined) => (typeof v === "number" ? v.toFixed(3) : "—"),
            },
            { title: "Matched clauses", dataIndex: "matched_clauses", width: 130, render: (v: number | null | undefined) => v ?? "—" },
            {
              title: notNarrowed ? "Retrieval note" : "Why discarded",
              dataIndex: "discard_reason",
              render: (reason: string | null | undefined) => (
                <Text type="secondary">{notNarrowed ? "Search did not discard any published policy." : discardLabel(reason)}</Text>
              ),
            },
          ]}
        />
      </div>
      {excluded.length > 0 ? (
        <div>
          <Paragraph style={{ marginBottom: 6 }}>
            <Text strong>Policies excluded before testing</Text>
          </Paragraph>
          <Table<ProjectCasePolicyCandidate>
            size="small"
            rowKey={(row) => row.provision_id || row.provision_key}
            dataSource={excluded}
            pagination={false}
            columns={[
              { title: "Policy", render: (_: unknown, row) => policyLabel(row) },
              { title: "Reason", render: (_: unknown, row) => discardLabel(row.reason ?? row.discard_reason) },
            ]}
          />
        </div>
      ) : null}
    </Space>
  );
}

export function ProjectCaseRunner({
  policySetKey,
  open,
  onClose,
  onOpenPolicyIndex,
}: {
  policySetKey: string;
  open: boolean;
  onClose: () => void;
  onOpenPolicyIndex?: (status: string) => void;
}) {
  const [scope, setScope] = useState<CaseScope>("project");
  const [scenario, setScenario] = useState("");
  const [reasoningEffort, setReasoningEffort] = useState<ReasoningEffort>("medium");
  const [policies, setPolicies] = useState<AssembledPolicy[]>([]);
  const [policyLoadError, setPolicyLoadError] = useState<string | null>(null);
  const [selectedProvisionId, setSelectedProvisionId] = useState<string | undefined>();
  const [running, setRunning] = useState(false);
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [elapsedMs, setElapsedMs] = useState(0);
  const [answer, setAnswer] = useState<ProjectCaseAnswer | null>(null);
  const [publishedQualityFindings, setPublishedQualityFindings] = useState<QualityFinding[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setPolicies([]);
    setSelectedProvisionId(undefined);
    setPolicyLoadError(null);
    setAnswer(null);
    setError(null);
  }, [policySetKey]);

  useEffect(() => {
    if (!open || scope !== "single") return;
    setPolicyLoadError(null);
    api
      .getActiveVersion(policySetKey)
      .then((version) => (version ? api.listVersionPolicies(policySetKey, version.id) : []))
      .then((loaded) => {
        const persisted = loaded.filter((policy) => policy.provision_id);
        setPolicies(persisted);
        setSelectedProvisionId((current) => current ?? persisted[0]?.provision_id ?? undefined);
      })
      .catch((caught) => {
        setPolicies([]);
        setSelectedProvisionId(undefined);
        setPolicyLoadError(caught instanceof PolicyPlatformApiError ? caught.detail : String(caught));
      });
  }, [open, policySetKey, scope]);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    loadLatestPublishedQualityFindings(policySetKey)
      .then((findings) => {
        if (!cancelled) setPublishedQualityFindings(findings);
      })
      .catch(() => {
        if (!cancelled) setPublishedQualityFindings([]);
      });
    return () => {
      cancelled = true;
    };
  }, [open, policySetKey]);

  useEffect(() => {
    if (startedAt === null) return;
    const timer = window.setInterval(() => setElapsedMs(Date.now() - startedAt), 1000);
    return () => window.clearInterval(timer);
  }, [startedAt]);

  const policyOptions = useMemo(
    () =>
      policies.map((policy) => ({
        value: policy.provision_id as string,
        label: policyLabel(policy),
      })),
    [policies],
  );

  const run = async () => {
    setRunning(true);
    setStartedAt(Date.now());
    setElapsedMs(0);
    setAnswer(null);
    setError(null);
    try {
      const result = await api.answerProjectCase(policySetKey, {
        scenario: scenario.trim(),
        reasoning_effort: reasoningEffort,
        ...(scope === "single" && selectedProvisionId ? { provision_id: selectedProvisionId } : {}),
      });
      setAnswer(result);
    } catch (caught) {
      setError(caught instanceof PolicyPlatformApiError ? caught.detail : String(caught));
    } finally {
      setRunning(false);
      setStartedAt(null);
    }
  };

  return (
    <Modal
      title="Put a case to this project's published policies"
      open={open}
      onCancel={onClose}
      footer={null}
      width={980}
      destroyOnHidden
    >
      <Space orientation="vertical" size={16} style={{ width: "100%" }} className="policy-case-runner">
        <Paragraph type="secondary" style={{ marginBottom: 0 }}>
          Ask across the project&apos;s published policies. Search narrows the set when there are more published
          policies than the retention budget; otherwise every published policy is evaluated and reported below.
        </Paragraph>
        <Radio.Group
          value={scope}
          onChange={(event) => setScope(event.target.value)}
          optionType="button"
          buttonStyle="solid"
          options={[
            { value: "project", label: "Project published policies" },
            { value: "single", label: "One published policy" },
          ]}
        />
        {scope === "single" ? (
          <Space orientation="vertical" size={6} style={{ width: "100%" }}>
            <Select
              showSearch
              value={selectedProvisionId}
              onChange={setSelectedProvisionId}
              style={{ width: "100%" }}
              options={policyOptions}
              placeholder={policyOptions.length === 0 ? "No published policy to choose" : "Choose a published policy"}
              optionFilterProp="label"
              disabled={policyOptions.length === 0}
            />
            {policyLoadError ? (
              <Alert
                type="info"
                showIcon
                title="This project has not published any policies yet"
                description="Single-policy testing runs against the published version, so there is nothing to choose from until a version is published. Review and publish candidate rules first."
              />
            ) : policyOptions.length === 0 ? (
              <Alert
                type="info"
                showIcon
                title="The published version contains no policies to choose"
                description="A version is published but holds no policy this dialog can test."
              />
            ) : (
              <Text type="secondary">
                {policyOptions.length} published {policyOptions.length === 1 ? "policy" : "policies"} in the active
                version. Rules still under review are not listed — only what has been published is testable here.
              </Text>
            )}
          </Space>
        ) : null}
        <div>
          <Paragraph style={{ marginBottom: 8 }}>
            <Text strong>Describe a case in plain English</Text>
          </Paragraph>
          <TextArea
            rows={4}
            value={scenario}
            onChange={(event) => setScenario(event.target.value)}
            placeholder="e.g. Someone in the situation these policies govern asks whether they may proceed"
            data-testid="project-case-scenario"
          />
        </div>
        <Space wrap>
          <Button
            type="primary"
            icon={<ReadOutlined />}
            onClick={() => {
              void run();
            }}
            loading={running}
            disabled={!scenario.trim() || (scope === "single" && !selectedProvisionId)}
            data-testid="project-case-run"
          >
            {running ? "Searching and reading policies…" : "Put this case to published policies"}
          </Button>
          <Text type="secondary" style={{ fontSize: 12 }}>
            Reasoning effort
          </Text>
          <Select<ReasoningEffort>
            size="small"
            value={reasoningEffort}
            onChange={setReasoningEffort}
            style={{ width: 112 }}
            options={[
              { value: "low", label: "Low" },
              { value: "medium", label: "Medium" },
              { value: "high", label: "High" },
            ]}
          />
        </Space>
        {running ? (
          <div className="project-case-wait" role="status" aria-live="polite">
            <Space orientation="vertical" size={4}>
              <Text strong>Searching published policies and reading evaluated policies · {formatElapsed(elapsedMs)} elapsed</Text>
              <Text type="secondary">
                The server is using the project&apos;s policy index to find the policies that best match your case, then
                evaluates the policies the retrieval step returns.
              </Text>
              <Text type="secondary">
                This can take 30–120 seconds. There is one reply at the end, so the live signal here is the running
                clock rather than a guessed percentage.
              </Text>
            </Space>
          </div>
        ) : null}
        {error ? <Alert type="error" showIcon title={error} /> : null}
        {answer ? (
          <Space orientation="vertical" size={16} style={{ width: "100%" }}>
            <RetrievalSummary answer={answer} onOpenPolicyIndex={onOpenPolicyIndex} />
            <EvaluationPanel answer={answer} qualityFindings={publishedQualityFindings} />
            <ConsideredPolicies answer={answer} />
            <Paragraph type="secondary" style={{ fontSize: 12, marginBottom: 0 }} data-testid="project-case-size">
              Evaluated payload size: {answer.size.combined_chars.toLocaleString()} of{" "}
              {answer.size.budget_chars.toLocaleString()} characters
              {answer.size.oversize ? "; over budget, so no partial answer was composed." : "."}
            </Paragraph>
          </Space>
        ) : null}
      </Space>
    </Modal>
  );
}
