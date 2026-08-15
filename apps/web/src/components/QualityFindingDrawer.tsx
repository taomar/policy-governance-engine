import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Alert, Button, Drawer, Empty, Spin, Tag, Typography } from "antd";
import {
  ArrowLeftOutlined,
  BranchesOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  ExclamationCircleOutlined,
  FileSearchOutlined,
  InfoCircleOutlined,
  QuestionCircleOutlined,
  ReadOutlined,
  RightOutlined,
  SafetyCertificateOutlined,
  ToolOutlined,
  WarningOutlined,
} from "@ant-design/icons";
import type {
  ApprovedPolicyVersion,
  CanonicalRule,
  ConditionNode,
  QualityFinding,
} from "../api";
import { ruleDecisionSummary } from "../ruleDisplay";
import { PolicyEffectBadge } from "./PolicyEffectBadge";
import { PolicyInspector } from "./PolicyInspector";
import { DETERMINISTIC_LABEL } from "../ruleExecutability";

const { Text, Title } = Typography;

interface QualityFindingDrawerProps {
  finding: QualityFinding | null;
  onClose: () => void;
  policySetKey: string;
  reportScope: "published" | "candidates";
  runAt: string | null;
  version: ApprovedPolicyVersion | null;
  versions: ApprovedPolicyVersion[];
  allRules: CanonicalRule[];
  ruleLookup: Map<string, QualityRuleRecord[]>;
  loading: boolean;
  error: string | null;
}

export interface QualityRuleRecord {
  key: string;
  rule: CanonicalRule;
}

interface FindingInterpretation {
  headline: string;
  meaning: string;
}

interface FindingStandard {
  impact: string;
  acceptable: string;
  unacceptable: string;
  questions: string[];
}

const CATEGORY_INTERPRETATION: Record<string, FindingInterpretation> = {
  decision_gap: {
    headline: "A boundary case has no declared policy outcome",
    meaning:
      "The affected policies define neighboring conditions but leave at least one input between them. The evaluator can reach that input without finding a rule that decides it.",
  },
  coverage_gap: {
    headline: "A real-world scenario falls outside the written coverage",
    meaning:
      "The policies cover part of the workflow but leave a related state or continuation path undecided.",
  },
  rule_conflict: {
    headline: "These policies can prescribe competing outcomes",
    meaning:
      "More than one affected policy can govern the same decision, but the package does not state which policy takes precedence when their outcomes differ.",
  },
  conflicting_effect: {
    headline: "Equivalent decisions carry opposing effects",
    meaning:
      "The affected policies target the same action but do not agree on whether it is allowed or denied.",
  },
  scope_and_precedence: {
    headline: "Scope and precedence do not identify the controlling policy",
    meaning:
      "The policies can overlap for the same subject, but their scope or override order does not identify which result controls.",
  },
  redundancy: {
    headline: "The same obligation is represented more than once",
    meaning:
      "Duplicate or overlapping policies can create repeated actions, inflated audit counts, and inconsistent amendments later.",
  },
  rule_logic_error: {
    headline: "The formal effect may invert the written policy meaning",
    meaning:
      "The effect and action wording combine in a way that a literal evaluator may interpret differently from the source intent.",
  },
  ambiguity: {
    headline: "The wording still requires a human policy decision",
    meaning:
      "The source can be read in more than one defensible way, so automated enforcement would encode an assumption that has not been approved.",
  },
  not_machine_executable: {
    headline: "The evaluator cannot enforce these policies yet",
    meaning:
      "The policies remain readable evidence, but their fact, output, temporal, or decision mappings are incomplete for deterministic execution.",
  },
  governance_risk: {
    headline: "The governance process lacks necessary control boundaries",
    meaning:
      "The policy permits or requires a process without defining safeguards, ownership, timing, or non-waivable controls needed to operate it safely.",
  },
};

function readableCategory(category: string): string {
  return category
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

function interpretationFor(finding: QualityFinding): FindingInterpretation {
  const direct = CATEGORY_INTERPRETATION[finding.category];
  if (direct) return direct;
  if (finding.category.includes("conflict") || finding.category.includes("precedence")) {
    return CATEGORY_INTERPRETATION.rule_conflict;
  }
  if (finding.category.includes("gap") || finding.category.includes("missing")) {
    return CATEGORY_INTERPRETATION.coverage_gap;
  }
  if (finding.category.includes("risk")) {
    return CATEGORY_INTERPRETATION.governance_risk;
  }
  return {
    headline: `${readableCategory(finding.category)} requires review`,
    meaning:
      "The evaluation found a condition that may make the policy package incomplete, inconsistent, or unsafe to rely on without a reviewer decision.",
  };
}

function standardFor(finding: QualityFinding): FindingStandard {
  const category = finding.category;
  if (category.includes("conflict") || category.includes("precedence")) {
    return {
      impact:
        "The same case can be governed by more than one policy outcome. Without explicit precedence, behavior can depend on implementation order or an unstated assumption rather than approved policy intent.",
      acceptable:
        "The policies cannot apply to the same subject and time, or an explicit priority, override, or supersession rule identifies the controlling outcome.",
      unacceptable:
        "A reachable case satisfies multiple affected policies, their outcomes differ, and no approved precedence rule resolves them.",
      questions: [
        "Can these policies apply to the same person, asset, request, and effective date?",
        "Which outcome must control when they overlap?",
        "Should the controlling policy explicitly override or supersede the others?",
      ],
    };
  }
  if (category.includes("gap") || category.includes("missing")) {
    return {
      impact:
        "A reachable input or workflow state can produce no declared policy outcome, forcing manual interpretation or inconsistent caller behavior.",
      acceptable:
        "The uncovered state is impossible under validated input constraints, or another explicit policy outside this comparison already decides it.",
      unacceptable:
        "The state can occur in production and the published package has no rule that assigns an outcome.",
      questions: [
        "Can the uncovered boundary or workflow state occur with real inputs?",
        "Which policy outcome should own that state?",
        "Are rounding, inclusivity, timing, and exception boundaries explicit?",
      ],
    };
  }
  if (category === "not_machine_executable") {
    return {
      impact:
        "The affected policies cannot participate in deterministic evaluation, so automated coverage is materially lower than the published rule count suggests.",
      acceptable:
        "Manual handling is intentional, documented, and the policy is not represented or consumed as machine-enforceable.",
      unacceptable:
        "A caller relies on these policies for automated decisions or coverage reporting before their fact and output mappings are complete.",
      questions: [
        "Which affected policies are intended to be automated?",
        "Which trusted fact, output, temporal, or decision mappings are missing?",
        "Who owns enrichment and re-publication?",
      ],
    };
  }
  if (category === "ambiguity") {
    return {
      impact:
        "Different reviewers or systems can encode different meanings from the same wording, producing inconsistent decisions and difficult-to-defend audit outcomes.",
      acceptable:
        "Human judgment is an explicit part of the process, with named criteria, owner, and recorded rationale.",
      unacceptable:
        "The policy is used for deterministic evaluation while a material interpretation remains undecided.",
      questions: [
        "What exact interpretation should be authoritative?",
        "Can the condition, threshold, exception, or outcome be stated deterministically?",
        "Who approves that interpretation?",
      ],
    };
  }
  if (category === "redundancy") {
    return {
      impact:
        "Duplicate policies can trigger repeated actions, inflate audit counts, and diverge when one copy is amended without the other.",
      acceptable:
        "The duplication is intentional, produces no duplicate side effect, and both records point to one authoritative source and amendment path.",
      unacceptable:
        "Both policies can execute independently or can be maintained separately without an explicit canonical record.",
      questions: [
        "Which policy is authoritative?",
        "Can references be redirected to one canonical record?",
        "Would both policies trigger the same action or notification?",
      ],
    };
  }
  return {
    impact:
      "If confirmed, the policy package may be incomplete, misleading, or operationally unsafe in the affected scenario.",
    acceptable:
      "The reviewer can demonstrate that the scenario is impossible, intentionally manual, or already controlled by an explicit policy not represented in this finding.",
    unacceptable:
      "The scenario is reachable and the published package leaves behavior unclear, uncontrolled, or dependent on an unstated assumption.",
    questions: [
      "Is the finding supported by the canonical policies and source evidence below?",
      "What concrete scenario triggers the issue?",
      "What is the smallest policy change or documented disposition that closes it?",
    ],
  };
}

function conditionFacts(node: ConditionNode): string[] {
  if (node.type === "factComparison") return [node.fact];
  // Both operands, matching the evaluator: a relative comparison depends on
  // the fact it compares against just as much as the one it compares, so
  // omitting it would understate what two rules actually share.
  if (node.type === "factRelativeComparison") return [node.fact, node.reference.fact];
  if (node.type === "not") return conditionFacts(node.not);
  return (node.type === "all" ? node.all : node.any).flatMap(conditionFacts);
}

function sharedFacts(rules: CanonicalRule[]): string[] {
  if (rules.length === 0) return [];
  const [first, ...rest] = rules.map((rule) => new Set(conditionFacts(rule.condition)));
  return [...first].filter((fact) => rest.every((facts) => facts.has(fact))).sort();
}

function effectiveWindowsOverlap(rules: CanonicalRule[]): boolean | null {
  if (rules.length < 2) return null;
  const latestStart = rules
    .map((rule) => rule.effective_from)
    .sort()
    .at(-1);
  const ends = rules
    .map((rule) => rule.effective_to)
    .filter((value): value is string => Boolean(value))
    .sort();
  const earliestEnd = ends[0];
  return !earliestEnd || !latestStart || latestStart <= earliestEnd;
}

function sourceText(rule: CanonicalRule): string {
  return (
    rule.formulation?.canonical?.source_text ||
    rule.description ||
    "No source excerpt is stored on this policy record."
  );
}

function findingLeadIcon(finding: QualityFinding): ReactNode {
  if (finding.category === "not_machine_executable") return <ToolOutlined />;
  if (finding.category.includes("ambiguity")) return <QuestionCircleOutlined />;
  if (
    finding.category.includes("conflict") ||
    finding.category.includes("gap") ||
    finding.category.includes("precedence") ||
    finding.category.includes("overlap")
  ) {
    return <BranchesOutlined />;
  }
  if (finding.category.includes("risk") || finding.severity === "high") {
    return <ExclamationCircleOutlined />;
  }
  return <SafetyCertificateOutlined />;
}

export function QualityFindingDrawer({
  finding,
  onClose,
  policySetKey,
  reportScope,
  runAt,
  version,
  versions,
  allRules,
  ruleLookup,
  loading,
  error,
}: QualityFindingDrawerProps) {
  const [policyPreview, setPolicyPreview] = useState<CanonicalRule | null>(null);
  const [policyPreviewTab, setPolicyPreviewTab] = useState("overview");
  const [showAllAffected, setShowAllAffected] = useState(false);

  useEffect(() => {
    setPolicyPreview(null);
    setPolicyPreviewTab("overview");
    setShowAllAffected(false);
  }, [finding]);

  const resolvedRecords = useMemo(() => {
    if (!finding) return [];
    const seen = new Set<string>();
    return finding.affected_rule_ids.flatMap((reference) => {
      const matches = ruleLookup.get(reference) ?? [];
      return matches.filter((record) => {
        if (seen.has(record.key)) return false;
        seen.add(record.key);
        return true;
      });
    });
  }, [finding, ruleLookup]);
  const resolvedRules = useMemo(
    () => resolvedRecords.map((record) => record.rule),
    [resolvedRecords],
  );

  const unresolvedReferences = useMemo(
    () =>
      finding?.affected_rule_ids.filter((reference) => !ruleLookup.has(reference)) ?? [],
    [finding, ruleLookup],
  );

  const commonFacts = sharedFacts(resolvedRules);
  const outcomeCount = new Set(
    resolvedRules.map((rule) => `${rule.effect.type}:${rule.effect.action}`),
  ).size;
  const priorityCount = new Set(resolvedRules.map((rule) => rule.priority)).size;
  const windowsOverlap = effectiveWindowsOverlap(resolvedRules);
  const detailedComparison = resolvedRules.length <= 8;
  const visibleRules = showAllAffected ? resolvedRules : resolvedRules.slice(0, 12);
  const interpretation = finding ? interpretationFor(finding) : null;
  const standard = finding ? standardFor(finding) : null;
  const analysisStatus =
    finding?.analysis_status ??
    (finding?.source === "ai_review" ? "requires_human_confirmation" : "confirmed");

  return (
    <Drawer
      open={finding !== null}
      onClose={onClose}
      size="min(1040px, 100vw)"
      title={
        policyPreview ? (
          <div className="quality-finding-drawer-title">
            <Button
              type="text"
              size="small"
              icon={<ArrowLeftOutlined />}
              onClick={() => setPolicyPreview(null)}
            >
              Back to quality finding
            </Button>
            <strong>Read-only policy record</strong>
          </div>
        ) : (
          "Quality finding evidence"
        )
      }
      className="quality-finding-drawer"
      styles={{ body: policyPreview ? { padding: 0 } : undefined }}
    >
      {policyPreview ? (
        <PolicyInspector
          rule={policyPreview}
          allRules={allRules}
          publishedVersion={version}
          versions={versions}
          policySetKey={policySetKey}
          activeTabKey={policyPreviewTab}
          onTabChange={setPolicyPreviewTab}
          onSelectRule={(rule) => {
            setPolicyPreviewTab("overview");
            setPolicyPreview(rule);
          }}
          shownAsReference
          recordKind={reportScope === "candidates" ? "candidate" : "published"}
          recordLabel={reportScope === "candidates" ? "candidate" : "policy"}
          contextMeta={<Tag color="purple">Referenced by quality finding</Tag>}
        />
      ) : finding && interpretation && standard ? (
        <div className="quality-finding-detail">
          <header className={`quality-finding-brief is-${finding.severity}`}>
            <div className="quality-finding-tags">
              <Tag color={finding.severity === "high" ? "red" : finding.severity === "medium" ? "gold" : "default"}>
                {finding.severity.toUpperCase()}
              </Tag>
              <Tag>{readableCategory(finding.category)}</Tag>
              <Tag
                icon={finding.source === "ai_review" ? <SafetyCertificateOutlined /> : undefined}
                color={finding.source === "ai_review" ? "purple" : "blue"}
              >
                {analysisStatus === "requires_human_confirmation"
                  ? "Potential issue · confirm"
                  : "Confirmed structural check"}
              </Tag>
            </div>
            <div className="quality-finding-heading">
              <span className="quality-finding-heading-icon">{findingLeadIcon(finding)}</span>
              <div>
                <Title level={4}>{finding.summary || interpretation.headline}</Title>
                <Text type="secondary">
                  {analysisStatus === "requires_human_confirmation"
                    ? "Review the evidence below before accepting this as a policy defect."
                    : "This condition was confirmed directly from the stored policy structure."}
                </Text>
              </div>
            </div>
            <div className="quality-finding-claim">
              <FileSearchOutlined />
              <div>
                <span>Evidence summary</span>
                <p>{finding.finding}</p>
              </div>
            </div>
          </header>

          <dl className="quality-finding-boundary" aria-label="Quality assessment boundary">
            <div>
              <dt>Evaluated against</dt>
              <dd>
                {reportScope === "published"
                  ? `Published version ${version?.version_number ?? "unknown"}`
                  : "Candidate rules still in review"}
              </dd>
            </div>
            <div>
              <dt>Evidence set</dt>
              <dd>
                {finding.affected_rule_ids.length > 0
                  ? `${finding.affected_rule_ids.length} referenced polic${finding.affected_rule_ids.length === 1 ? "y" : "ies"}`
                  : "Policy-set-level control"}
              </dd>
            </div>
            <div>
              <dt>Finding status</dt>
              <dd>
                {analysisStatus === "requires_human_confirmation"
                  ? "Human confirmation required"
                  : "Confirmed by deterministic check"}
              </dd>
            </div>
            <div>
              <dt>Evaluation time</dt>
              <dd>{runAt ? new Date(runAt).toLocaleString() : "Current evaluation"}</dd>
            </div>
          </dl>

          <section className="quality-finding-analysis">
            <div className="quality-finding-explanation">
              <article>
                <span><InfoCircleOutlined /> What this means</span>
                <p>{interpretation.meaning}</p>
              </article>
              <article>
                <span><WarningOutlined /> How this can cause an issue</span>
                <p>{finding.why_it_matters || standard.impact}</p>
              </article>
            </div>
            <div className="quality-finding-acceptance">
              <article className="is-acceptable">
                <span><CheckCircleOutlined /> Acceptable only when</span>
                <p>{finding.acceptable_when || standard.acceptable}</p>
              </article>
              <article className="is-unacceptable">
                <span><CloseCircleOutlined /> Not acceptable when</span>
                <p>{finding.unacceptable_when || standard.unacceptable}</p>
              </article>
            </div>
            <div className="quality-finding-resolution">
              <article>
                <span><QuestionCircleOutlined /> Reviewer questions</span>
                <ul>
                  {(finding.review_questions?.length ? finding.review_questions : standard.questions).map(
                    (question) => <li key={question}>{question}</li>,
                  )}
                </ul>
              </article>
              <article>
                <span><SafetyCertificateOutlined /> How to close this finding</span>
                <p>
                  {finding.recommendation ||
                    "Review the affected policy records and document the intended controlling behavior."}
                </p>
              </article>
            </div>
          </section>

          {loading ? (
            <div className="quality-finding-loading">
              <Spin size="small" />
              <Text type="secondary">Resolving the affected policies from the evaluated version…</Text>
            </div>
          ) : error ? (
            <Alert type="error" showIcon message="Affected policies could not be loaded" description={error} />
          ) : finding.affected_rule_ids.length === 0 ? (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description="This is a policy-set-level finding; it does not accuse one specific policy record."
            />
          ) : (
            <>
              <dl className="quality-conflict-mechanics" aria-label="Finding comparison summary">
                <div>
                  <dt>Policy records involved</dt>
                  <dd>{resolvedRules.length || finding.affected_rule_ids.length}</dd>
                </div>
                <div>
                  <dt>Shared decision facts</dt>
                  <dd>{commonFacts.length > 0 ? commonFacts.slice(0, 3).join(", ") : "None declared"}</dd>
                </div>
                <div>
                  <dt>Outcome directions</dt>
                  <dd>{outcomeCount || "—"} distinct</dd>
                </div>
                <div>
                  <dt>Priority order</dt>
                  <dd>{priorityCount <= 1 ? "Same priority" : `${priorityCount} priority levels`}</dd>
                </div>
                <div>
                  <dt>Effective windows</dt>
                  <dd>{windowsOverlap === null ? "One policy" : windowsOverlap ? "Overlap" : "Do not overlap"}</dd>
                </div>
              </dl>

              <section className="quality-policy-comparison">
                <div className="quality-policy-comparison-header">
                  <div>
                    <Text strong>
                      <BranchesOutlined /> What contradicts or leaves a gap
                    </Text>
                    <Text type="secondary">
                      Canonical decisions from {reportScope === "published" ? `published v${version?.version_number ?? "?"}` : "the evaluated candidate set"}
                    </Text>
                  </div>
                  <Tag>{resolvedRules.length} resolved</Tag>
                </div>

                <div className="quality-policy-comparison-list">
                  {visibleRules.map((rule, index) => {
                    const decision = ruleDecisionSummary(rule, detailedComparison ? 8 : 3);
                    const evidence = rule.evidence[0];
                    const recordKey =
                      resolvedRecords.find((record) => record.rule === rule)?.key ??
                      `${rule.policy_version_id}:${rule.rule_id}:${rule.rule_revision}:${index}`;
                    return (
                      <article
                        key={recordKey}
                        className={`quality-policy-evidence${detailedComparison ? "" : " is-compact"}`}
                      >
                        <span className="quality-policy-evidence-index" aria-hidden="true">
                          {String.fromCharCode(65 + (index % 26))}
                        </span>
                        <div className="quality-policy-evidence-main">
                          <div className="quality-policy-evidence-title">
                            <span>
                              <strong>{rule.title}</strong>
                              <code>{rule.rule_id}</code>
                            </span>
                            <PolicyEffectBadge effect={rule.effect} size="small" />
                          </div>
                          <div className="quality-policy-evidence-decision">
                            <span>When</span>
                            <strong>{decision.condition}</strong>
                            <RightOutlined />
                            <span>Then</span>
                            <strong>{decision.action}</strong>
                          </div>
                          <div className="quality-policy-evidence-meta">
                            <span>Priority {rule.priority}</span>
                            <span>{rule.machine_executable ? DETERMINISTIC_LABEL.yes : DETERMINISTIC_LABEL.no}</span>
                            <span>Effective {rule.effective_from} → {rule.effective_to ?? "open-ended"}</span>
                            <span>
                              {evidence
                                ? `${evidence.section ?? "Source"} · p.${evidence.page ?? "?"}`
                                : "No linked citation"}
                            </span>
                          </div>
                          {detailedComparison && (
                            <blockquote>
                              <FileSearchOutlined />
                              <p>{sourceText(rule)}</p>
                            </blockquote>
                          )}
                        </div>
                        <Button
                          size="small"
                          type="link"
                          className="quality-policy-open"
                          onClick={() => {
                            setPolicyPreviewTab("overview");
                            setPolicyPreview(rule);
                          }}
                        >
                          <ReadOutlined />
                          View policy record
                          <RightOutlined />
                        </Button>
                      </article>
                    );
                  })}
                </div>

                {!showAllAffected && resolvedRules.length > visibleRules.length && (
                  <Button
                    type="text"
                    className="quality-show-all-policies"
                    onClick={() => setShowAllAffected(true)}
                  >
                    Show all {resolvedRules.length} affected policies
                  </Button>
                )}

                {unresolvedReferences.length > 0 && (
                  <Alert
                    type="warning"
                    showIcon
                    message={`${unresolvedReferences.length} referenced policy record${unresolvedReferences.length === 1 ? "" : "s"} could not be resolved`}
                    description={
                      reportScope === "candidates"
                        ? "Candidate evaluations are stored, but candidate records can later be superseded or rejected. The original finding remains immutable."
                        : `Missing references: ${unresolvedReferences.join(", ")}`
                    }
                  />
                )}
              </section>
            </>
          )}

          <footer className="quality-finding-provenance">
            <span>{reportScope === "published" ? `Published version ${version?.version_number ?? "unknown"}` : "Candidate review scope"}</span>
            <span>{runAt ? `Evaluated ${new Date(runAt).toLocaleString()}` : "Current evaluation"}</span>
            <span>{finding.source === "ai_review" ? "Interpretation generated by AI; policy evidence is canonical" : "Finding computed deterministically"}</span>
          </footer>
        </div>
      ) : null}
    </Drawer>
  );
}