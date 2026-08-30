import { useEffect, useMemo, useState } from "react";
import { Alert, Button, Input, Modal, Radio, Select, Space, Table, Tag, Typography } from "antd";
import { ReadOutlined } from "@ant-design/icons";
import {
  api,
  INDEX_PROJECTION_UNAVAILABLE,
  PolicyPlatformApiError,
  RESPONSE_TRANSLATION_UNAVAILABLE,
  SCENARIO_TRANSLATION_EMPTY,
  SCENARIO_TRANSLATION_UNAVAILABLE,
  type AssembledPolicy,
  type ProjectCaseAnswer,
  type ProjectCaseCitation,
  type ProjectCaseGrounding,
  type ProjectCasePolicyCandidate,
  type ProjectCaseRetrievalStatus,
  type ProjectCaseRuleSelection,
  type QualityFinding,
} from "../api";
import { formatElapsed } from "../uploadFeedback";
import { retrievalStatusIsIndexRepairable } from "../policyIndexHealth";
import { DirectionalText } from "./DirectionalText";
import { findingsForRuleIds, loadLatestPublishedQualityFindings } from "../qualityFindingLinks";
import {
  NOT_EVALUATED,
  NOT_REQUESTED,
  NO_SECTION,
  missingInformationItems,
  readCaseTracks,
  readDiscovery,
  readLanguage,
  readRuleIndex,
  readRuleSlicing,
  representedRuleIds,
  ruleSelectionMethodFamily,
  trackProse,
  type CaseTrackReading,
  type CaseTracksReading,
  type MergedCaseCitation,
} from "./projectCaseTracks";
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

interface OutcomeCopy {
  label: string;
  color: string;
  title: string;
  description: string;
}

/**
 * How each verdict outcome reads. The set is the contract's, and it is written
 * out rather than derived because the difference between "the rules do not
 * settle this" and "the rules need a fact you did not give" is the whole of
 * what a reviewer acts on, and neither is a refusal.
 */
const VERDICT_OUTCOME_COPY: Record<string, OutcomeCopy> = {
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
  failed: {
    label: "Did not complete",
    color: "red",
    title: "The verdict was not produced",
    description:
      "This track did not complete after retrieval. Nothing here is a verdict, and any information answer above is unaffected — one track failing never removes the other's answer.",
  },
  [NOT_REQUESTED]: {
    label: "Not asked for",
    color: "default",
    title: "This case did not ask for a verdict",
    description:
      "The question was read as asking what the policies state, not for the case to be decided, so no verdict was gathered. This is your own question's shape, not a refusal by the policies.",
  },
  [NOT_EVALUATED]: {
    label: "Nothing evaluated",
    color: "default",
    title: "Nothing was evaluated, so no verdict was reached",
    description:
      "Retrieval produced no published policy record to decide from. Neither track ran, and this is not the policies saying nothing bears.",
  },
  [NO_SECTION]: {
    label: "Nothing returned",
    color: "orange",
    title: "A verdict was asked for, but no verdict section was returned",
    description:
      "No verdict is shown. The server returned no decision section for this path, so the space is left explicit rather than filled with an answer nobody produced.",
  },
};

/**
 * How each information outcome reads. Four gather states rather than the
 * verdict's six: only a determination can be blocked on facts or left unsettled
 * by rules that do bear on the case.
 */
const INFORMATION_OUTCOME_COPY: Record<string, OutcomeCopy> = {
  answered: {
    label: "Answered",
    color: "green",
    title: "The evaluated policies state an answer",
    description: "The answer below is what the retained published policies state on the subject asked about.",
  },
  no_rule_bears: {
    label: "No evaluated rule bears",
    color: "default",
    title: "The evaluated policies did not state an answer",
    description: "The policies listed below were read, but none answered the question.",
  },
  declined: {
    label: "No answer composed",
    color: "orange",
    title: "No project answer was composed",
    description: "The retrieval result is shown below so you can see what was and was not read.",
  },
  failed: {
    label: "Did not complete",
    color: "red",
    title: "The information answer was not produced",
    description:
      "This track did not complete after retrieval. Any verdict below is unaffected — one track failing never removes the other's answer.",
  },
  [NOT_REQUESTED]: {
    label: "Not asked for",
    color: "default",
    title: "This case did not ask what the policies state",
    description:
      "The question was read as asking for the case to be decided, not for what the policies say, so no informational answer was gathered.",
  },
  [NOT_EVALUATED]: {
    label: "Nothing evaluated",
    color: "default",
    title: "Nothing was evaluated, so nothing was stated",
    description:
      "Retrieval produced no published policy record to read from. Neither track ran, and this is not the policies saying nothing bears.",
  },
  [NO_SECTION]: {
    label: "Nothing returned",
    color: "orange",
    title: "An informational answer was asked for, but no section was returned",
    description: "The server returned no informational section for this path, so nothing is shown in its place.",
  },
};

function outcomeCopy(reading: CaseTrackReading): OutcomeCopy {
  const map = reading.track === "verdict" ? VERDICT_OUTCOME_COPY : INFORMATION_OUTCOME_COPY;
  return (
    map[reading.outcome] ?? {
      label: discardLabel(reading.outcome),
      color: "default",
      title: `${reading.track === "verdict" ? "Verdict" : "Information"} status: ${discardLabel(reading.outcome)}`,
      description: "This status is not known by this client. The raw response is available below.",
    }
  );
}

/** How a large policy's rules were chosen, in words rather than a method id.
 *
 *  Matched by family, never by the exact identifier: the version suffix moves
 *  when the selection algorithm changes, and a label pinned to one version
 *  would silently start printing a raw identifier at a reviewer the day it
 *  does. An algorithm this client has never heard of is shown as its own name
 *  rather than described in words nobody can check. */
function selectionMethodLabel(method: string | null | undefined): string {
  if (!method) return "";
  switch (ruleSelectionMethodFamily(method)) {
    case "whole_policy":
      return "read whole";
    case "hybrid_rule":
      return "placed by the rule index, relevance and quantity together";
    case "scenario_relevance":
      return "selected by relevance to this case, without the rule index";
    case "document_order":
      return "selected in document order, because no rule matched the question's terms";
    default:
      return discardLabel(method).toLowerCase();
  }
}

/** What the rule index did for one policy, in words rather than an enum.
 *
 *  `matched` with zero hits is stated as the real answer it is — the index was
 *  asked about this policy and placed none of its rules — because showing it as
 *  a bare "0" beside `unavailable`'s absence would report a question that was
 *  never put as one that came back empty. */
function ruleIndexStateLabel(state: string | null): string {
  if (state === "matched") return "The rule index was queried and its ranking was used";
  if (state === "degraded") return "Rule documents exist, but the query against them failed; the index's ranking was not used";
  if (state === "unavailable") return "The rule index was not consulted for this policy";
  return state ? `Rule index: ${discardLabel(state)}` : "";
}

/** Which gather composed a section, said in words rather than left to inference. */
function routeLabel(route: string | null | undefined, track: CaseTrackReading["track"]): string {
  const named = (route ?? "").trim() || (track === "verdict" ? "decision" : "informational");
  if (named === "decision") return "Composed by the decision gather";
  if (named === "informational") return "Composed by the informational gather";
  return `Composed by the ${discardLabel(named).toLowerCase()} gather`;
}

function RawResponse({ value }: { value: unknown }) {
  return (
    <details className="project-case-raw">
      <summary>Show raw response</summary>
      <pre className="project-case-json">{JSON.stringify(value, null, 2)}</pre>
    </details>
  );
}

const SERVES_LABEL: Record<string, string> = {
  information: "Information",
  verdict: "Verdict",
};

function CitationList({
  citations,
  heading,
  showServes = false,
}: {
  citations: readonly (ProjectCaseCitation | MergedCaseCitation)[];
  heading?: string;
  showServes?: boolean;
}) {
  if (citations.length === 0) return null;
  return (
    <div className="project-case-citations" data-testid="project-case-citations">
      <Paragraph style={{ marginBottom: 4 }}>
        <Text strong>
          {heading ??
            (citations.length === 1
              ? "The answer rests on this cited rule:"
              : `The answer rests on these ${citations.length} cited rules:`)}
        </Text>
      </Paragraph>
      {citations.map((citation, index) => {
        const policy = citation.policy?.heading_path?.filter(Boolean).join(" › ") || citation.policy?.provision_key || "Retained policy";
        const source = citation.source;
        const serves = citation.serves ?? [];
        return (
          <div key={`${citation.policy?.provision_key ?? "policy"}-${citation.rule_id}-${index}`} className="policy-case-citation">
            <Text strong>{policy}</Text>
            <div className="project-case-citation__meta">
              <Text code>{citation.rule_id}</Text>
              {/* Which track cited the rule, on the rule. A rule both tracks
                  cited is listed once and carries both tags, so a reader counts
                  the authorities the policies hold rather than the number of
                  times two gathers happened to reach for the same one. */}
              {showServes
                ? serves.map((serve) => (
                    <Tag key={serve} color={serve === "verdict" ? "blue" : "default"}>
                      Cited for {SERVES_LABEL[serve] ?? discardLabel(serve)}
                    </Tag>
                  ))
                : null}
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

/**
 * WHAT THE SEARCH ACTUALLY MATCHED, AND WHETHER IT COULD.
 *
 * Two content types are searched, not one: a policy's own document, and — for a
 * policy holding more rules than a single case can read — one document per
 * rule, so a row past what its policy's combined text had room for is still
 * findable on its own terms. `policies_elevated_by_rule` is the count that says
 * whether that did anything on this question.
 *
 * The projection profile is here because a question and the text it is scored
 * against must be rendered under one contract or the two are not comparable.
 * When they are not, the answer is a refusal rather than a confident "nothing
 * bears" — which is why `projection_ready` is only ever true on a served answer.
 */
function DiscoveryNote({ answer }: { answer: ProjectCaseAnswer }) {
  const discovery = readDiscovery(answer.retrieval);
  if (!discovery) return null;
  const { policyDocuments, ruleDocuments, ruleScan, elevatedByRule, ruleIndexState } = discovery;
  return (
    <div data-testid="project-case-discovery">
      {policyDocuments !== null || ruleDocuments !== null ? (
        <Text type="secondary">
          Search matched {policyDocuments ?? "—"} policy document{policyDocuments === 1 ? "" : "s"} and{" "}
          {ruleDocuments ?? "—"} rule document{ruleDocuments === 1 ? "" : "s"}
          {ruleScan !== null ? `, from ${ruleScan} rule documents examined` : ""}. A large policy is indexed one
          document per rule as well as its own, so a rule past what its policy&apos;s combined text could carry is
          still findable.
        </Text>
      ) : null}
      {elevatedByRule !== null ? (
        <Text type="secondary" data-testid="project-case-elevated">
          {elevatedByRule === 0
            ? "No policy's ranking was raised by one of its own rules surfacing, so rule-level retrieval changed nothing on this question."
            : elevatedByRule === 1
              ? "1 policy was ranked higher because one of its own rules surfaced — including, possibly, a policy the policy-level search did not return at all."
              : `${elevatedByRule} policies were ranked higher because one of their own rules surfaced — including, possibly, policies the policy-level search did not return at all.`}
        </Text>
      ) : null}
      {ruleIndexState !== null && ruleIndexState !== "matched" ? (
        <Text type="secondary" data-testid="project-case-rule-index-state">
          {ruleIndexState === "degraded"
            ? "Rule documents exist for this project, but the query against them failed. Selection ran without the rule index's ranking; the rules read were still chosen by relevance and quantity, not by document order."
            : ruleIndexState === "unavailable"
              ? "The rule index was not consulted for this question. That is not the same as it being asked and placing nothing."
              : `Rule index state: ${discardLabel(ruleIndexState)}.`}
        </Text>
      ) : null}
      {discovery.projectionProfile ? (
        <Text type="secondary" data-testid="project-case-projection">
          Matched against the {discovery.projectionProfile} corpus projection
          {discovery.projectionReady === true
            ? ", which the index reported complete. A question and the text it is scored against are rendered under one contract, or they are not compared at all."
            : "."}
        </Text>
      ) : null}
    </div>
  );
}

/**
 * THE NARROWINGS THAT HAPPEN AFTER SEARCH.
 *
 * Search discarding by relevance is reported above. These are the ones that
 * happen to policies search *kept*, and they are disclosed because a reader
 * told only "retained" would otherwise believe every rule of every retained
 * policy was read. A policy holding more rules than the threshold is read rule
 * by rule; a whole record that would overflow one grounded pass is set aside
 * entire. No rule and no policy is ever trimmed to fit, and the per-policy
 * counts sit on the candidate table beneath so this claim can be checked.
 *
 * TWO THINGS THAT LOOK ALIKE AND ARE NOT
 *
 * A *collapsed duplicate* is a policy proven to govern identically to one
 * already retrieved. Its terms were read — through the representative, which is
 * named — so it is the one discard that costs a reader nothing. A
 * *diversity-deferred* policy is not a duplicate: nothing proved it identical,
 * it kept its own rank and score, and it was offered after the budget only
 * because a policy requiring the same thing was offered first. Its terms were
 * **not** read.
 *
 * They are stated in separate sentences with separate counts, and neither is
 * ever added to the other. Told as one number, either the interface claims a
 * policy was read when it was not, or it reports the corpus as holding one
 * policy where it holds two copies of one.
 */
function RuleSlicingNote({ answer }: { answer: ProjectCaseAnswer }) {
  const slicing = readRuleSlicing(answer);
  if (!slicing) return null;
  return (
    <div data-testid="project-case-rule-slicing">
      {slicing.slicedCount > 0 ? (
        <Text type="secondary">
          {slicing.slicedCount === 1
            ? "1 retained policy was read rule by rule rather than whole"
            : `${slicing.slicedCount} retained policies were read rule by rule rather than whole`}
          {slicing.threshold !== null ? `, because it holds more than ${slicing.threshold} rules` : ""}
          {slicing.ruleBudget !== null ? `; at most ${slicing.ruleBudget} of its rules go to one case` : ""}. Each
          policy&apos;s selected and unselected rule counts are in the table below; no rule was trimmed to fit.
        </Text>
      ) : null}
      {slicing.duplicateRulesCollapsed > 0 ? (
        <Text type="secondary" data-testid="project-case-duplicate-rules">
          {slicing.duplicateRulesCollapsed === 1
            ? "1 of those unread rules is an exact copy of a rule that was read"
            : `${slicing.duplicateRulesCollapsed} of those unread rules are exact copies of rules that were read`}
          , so {slicing.duplicateRulesCollapsed === 1 ? "it says" : "they say"} nothing the answer did not see —{" "}
          {slicing.duplicateRulesCollapsed === 1 ? "it was" : "they were"} represented rather than read, and{" "}
          {slicing.duplicateRulesCollapsed === 1 ? "was" : "were"} never put in front of the model. The rule ids are on
          the policy&apos;s row below.
        </Text>
      ) : null}
      {slicing.duplicateCollapsed > 0 ? (
        <Text type="secondary" data-testid="project-case-duplicate-policies">
          {slicing.duplicateCollapsed === 1
            ? "1 policy was collapsed as an exact copy of another that was retrieved"
            : `${slicing.duplicateCollapsed} policies were collapsed as exact copies of others that were retrieved`}
          : {slicing.duplicateCollapsed === 1 ? "its terms were" : "their terms were"} read, through the policy named
          beside {slicing.duplicateCollapsed === 1 ? "it" : "each"} in the table below. This is the one discard whose
          content still reached the answer.
        </Text>
      ) : null}
      {slicing.diversityDeferred > 0 ? (
        <Text type="secondary" data-testid="project-case-diversity-deferred">
          {slicing.diversityDeferred === 1
            ? "1 policy ranked inside the retention budget and was offered after it"
            : `${slicing.diversityDeferred} policies ranked inside the retention budget and were offered after it`}
          , because a policy requiring the same thing was offered first.{" "}
          {slicing.diversityDeferred === 1 ? "It is not a duplicate" : "These are not duplicates"}: nothing proved{" "}
          {slicing.diversityDeferred === 1 ? "it" : "them"} identical to anything,{" "}
          {slicing.diversityDeferred === 1 ? "it keeps its" : "each keeps its"} own rank and score, and{" "}
          {slicing.diversityDeferred === 1 ? "its terms were" : "their terms were"} not read.
        </Text>
      ) : null}
      {slicing.overPayloadBudget > 0 ? (
        <Text type="secondary">
          {slicing.overPayloadBudget === 1
            ? "1 policy search kept was set aside whole because its record would not fit one grounded pass"
            : `${slicing.overPayloadBudget} policies search kept were set aside whole because their records would not fit one grounded pass`}
          {slicing.payloadBudgetChars !== null
            ? ` (${slicing.payloadBudgetChars.toLocaleString()} characters per policy)`
            : ""}
          . They are listed below as outside payload budget, which is a size decision, not a relevance one.
        </Text>
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
          <RuleSlicingNote answer={answer} />
          <DiscoveryNote answer={answer} />
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

/**
 * WHAT THIS CASE WAS READ AS ASKING FOR.
 *
 * Read first, and stated before either answer, because it is the fact that
 * explains both. The two booleans are the classifier's reading of the question
 * — there is no field a caller sets to declare them — so a track that did not
 * run says so as the shape of the question rather than as a refusal by the
 * policies.
 */
function AskedTracks({ reading }: { reading: CaseTracksReading }) {
  const { asked, evaluated } = reading;
  return (
    <div className="project-case-asked" data-testid="project-case-asked">
      <Space wrap size={6} align="center">
        <Text strong>This case was read as asking for</Text>
        <Tag color={asked.information ? "green" : "default"} data-testid="project-case-asked-information">
          {asked.information ? "What the policies state" : "Not: what the policies state"}
        </Tag>
        <Tag color={asked.verdict ? "green" : "default"} data-testid="project-case-asked-verdict">
          {asked.verdict ? "A verdict on the case" : "Not: a verdict on the case"}
        </Tag>
      </Space>
      {!evaluated ? (
        <Paragraph type="secondary" style={{ marginBottom: 0, marginTop: 4 }}>
          Nothing was evaluated, so the question was never classified. Both tracks below report that, which is not the
          same as the policies having nothing to say.
        </Paragraph>
      ) : asked.reasoning ? (
        <Paragraph type="secondary" style={{ marginBottom: 0, marginTop: 4 }}>
          <DirectionalText>{asked.reasoning}</DirectionalText>
        </Paragraph>
      ) : null}
      {evaluated && !asked.declared ? (
        <Paragraph type="secondary" style={{ marginBottom: 0, marginTop: 4 }}>
          This server answered with one branch rather than two tracks, so what was asked for is read from the branch it
          returned rather than stated by a classifier.
        </Paragraph>
      ) : null}
      {asked.information && asked.verdict ? (
        <Paragraph type="secondary" style={{ marginBottom: 0, marginTop: 4 }} data-testid="project-case-mixed-note">
          Both were asked for, and each is answered on its own below. One track answering does not settle the other, and
          one track failing does not remove the other&apos;s answer.
        </Paragraph>
      ) : null}
    </div>
  );
}

/**
 * WHAT LANGUAGE THIS WAS READ AND ANSWERED IN.
 *
 * Quiet when nothing was rendered, because then the words on screen are the
 * words that were read and there is nothing for a reviewer to reconcile. Loud —
 * a panel, carrying the adjudicated text in full — when the question *was*
 * carried into the processing language, because then what they typed is not
 * what was read, and comparing the two is the only way anyone catches a
 * rendering that changed the question.
 *
 * The evidence is untouched either way, and this says so where it matters. A
 * document's own sentence is never translated: a citation's quoted text is the
 * document's characters, in the document's language, in every state of this
 * block. So is every rule id, provision key and retrieval counter.
 */
function LanguageNote({ answer }: { answer: ProjectCaseAnswer }) {
  const language = readLanguage(answer);
  if (!language) return null;
  if (!language.questionRendered && !language.answerRendered && !language.guidanceDropped) return null;
  return (
    <div className="project-case-asked" data-testid="project-case-language">
      <Space wrap size={6} align="center">
        <Text strong>Language</Text>
        {language.questionRendered ? (
          <Tag color="blue">
            Read in {language.processingLanguage ?? "the processing language"}
          </Tag>
        ) : null}
        {language.answerRendered ? <Tag color="blue">Answered in {language.responseLanguage ?? "your language"}</Tag> : null}
      </Space>
      {language.questionRendered ? (
        <>
          <Paragraph type="secondary" style={{ marginBottom: 4, marginTop: 4 }}>
            Your question was carried into {language.processingLanguage ?? "the processing language"} before any
            policy was read. Retrieval, the classifier and both gathers all read the text below — not the words you
            typed — so this is what to compare against if an answer surprises you.
          </Paragraph>
          {language.processingScenario ? (
            <Paragraph className="project-case-processing-scenario" style={{ marginBottom: 4 }}>
              <DirectionalText align>{language.processingScenario}</DirectionalText>
            </Paragraph>
          ) : null}
        </>
      ) : null}
      {language.guidanceDropped ? (
        <Paragraph type="secondary" style={{ marginBottom: 4 }} data-testid="project-case-guidance-dropped">
          Presentation guidance could not be carried across and was dropped rather than applied un-rendered. What was
          decided is unaffected.
        </Paragraph>
      ) : null}
      <Paragraph type="secondary" style={{ marginBottom: 0, fontSize: 12 }}>
        Evidence is not translated. Every quoted sentence below is the document&apos;s own characters in the
        document&apos;s own language, and so are the rule ids, provision keys and every retrieval count.
      </Paragraph>
    </div>
  );
}
/**
 * A REFUSAL THIS SURFACE HAS WORDS FOR.
 *
 * `index_projection_unavailable` is the one that must never be softened into an
 * answer. The project's index holds documents that were never rendered into the
 * language a question is matched in — or rendered under a superseded contract,
 * or left half-written by an interrupted rebuild. Matching a rendered question
 * against an unrendered corpus scores near zero on every policy, which reads
 * exactly like "no published policy bears on your question". A reviewer told
 * that would go looking for a policy that is already published and already
 * relevant, and would conclude their corpus was wrong when their index was.
 *
 * So the words say what is true — nothing was compared — and name the one
 * repair, which is a rebuild of this project's policy index. The language
 * refusals beside it are told apart for the same reason: a question that could
 * not be read is a different problem from an answer that could not be returned.
 */
function CaseRefusal({
  code,
  message,
  onOpenPolicyIndex,
}: {
  code: string;
  message: string;
  onOpenPolicyIndex?: (status: string) => void;
}) {
  if (code === INDEX_PROJECTION_UNAVAILABLE) {
    return (
      <Alert
        type="error"
        showIcon
        data-testid="project-case-refusal-index_projection_unavailable"
        title="This project's policy index must be rebuilt before a case can be tested"
        action={
          onOpenPolicyIndex ? (
            <Button size="small" onClick={() => onOpenPolicyIndex("index_projection_unavailable")}>
              Open index repair
            </Button>
          ) : undefined
        }
        description={
          <Space orientation="vertical" size={4}>
            <Text>
              No policy was read and nothing was compared. The index holds documents that were not prepared for the
              language questions are matched in — never built, built under a superseded contract, or left incomplete
              by a rebuild that did not finish.
            </Text>
            <Text strong>This is not the same as no published policy bearing on your question.</Text>
            <Text type="secondary">
              Your published policies are unaffected: every index document is derived from the active approved
              version, so rebuilding is the whole repair and nothing has to be re-extracted or restored.
            </Text>
            {onOpenPolicyIndex ? (
              <Text type="secondary">Open the Overview readiness panel to rebuild this project&apos;s policy index.</Text>
            ) : (
              <Text type="secondary">
                Rebuild this project&apos;s policy index from the Overview readiness panel, then run the case again.
              </Text>
            )}
          </Space>
        }
      />
    );
  }
  if (
    code === SCENARIO_TRANSLATION_UNAVAILABLE ||
    code === SCENARIO_TRANSLATION_EMPTY ||
    code === RESPONSE_TRANSLATION_UNAVAILABLE
  ) {
    const inbound = code !== RESPONSE_TRANSLATION_UNAVAILABLE;
    return (
      <Alert
        type="error"
        showIcon
        data-testid={`project-case-refusal-${code}`}
        title={
          inbound
            ? "Your question could not be carried into the language this platform reads in"
            : "The answer could not be carried back into the language you asked in"
        }
        description={
          <Space orientation="vertical" size={4}>
            <Text>
              {inbound
                ? "No policy was read. The question is never read in a language these prompts were not written for, so this is a refusal rather than an answer drawn from the original text."
                : "The case was read and evaluated, but the finished prose could not be returned in your language, so it is withheld rather than shown in another."}
            </Text>
            <Text type="secondary">{message}</Text>
          </Space>
        }
      />
    );
  }
  return <Alert type="error" showIcon title={message} />;
}

/** A track that did not run, told in one line rather than an empty panel. */
function QuietTrack({ reading, name }: { reading: CaseTrackReading; name: string }) {
  const copy = outcomeCopy(reading);
  return (
    <div className="project-case-track project-case-track--quiet" data-testid={`project-case-${reading.track}-track`} data-outcome={reading.outcome}>
      <Space wrap size={6} align="center">
        <Text strong>{name}</Text>
        <Tag color={copy.color}>{copy.label}</Tag>
        <Text type="secondary">{copy.title}</Text>
      </Space>
      <Paragraph type="secondary" style={{ marginBottom: 0, marginTop: 2, fontSize: 12 }}>
        {copy.description}
      </Paragraph>
    </div>
  );
}

/**
 * THE VERDICT TRACK.
 *
 * `decision` is shown only when the track reached one. A "no", a "not
 * compliant" or a "denied" is a reached verdict and belongs here; a case that
 * could not be decided leaves this empty, and nothing on this surface may
 * present the second as the first. The facts a blocked case is waiting on are
 * the actionable part and are given their own panel rather than a sentence.
 */
function VerdictTrack({ reading }: { reading: CaseTrackReading }) {
  const copy = outcomeCopy(reading);
  const section = reading.section;
  if (!section) return <QuietTrack reading={reading} name="Verdict" />;

  const verdict = section.verdict?.trim() ?? "";
  const explanation = trackProse(section);
  const missing = missingInformationItems(section);
  return (
    <section
      className="policy-case-reading project-case-track"
      data-testid="project-case-verdict-track"
      data-outcome={reading.outcome}
      aria-label="Verdict"
    >
      <Paragraph style={{ marginBottom: 8 }}>
        <Text strong>Verdict</Text> <Tag color={copy.color}>{copy.label}</Tag> <Tag color="blue">AI Ready judge</Tag>{" "}
        <Text strong>{copy.title}</Text>
      </Paragraph>
      {reading.answered ? (
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
      {explanation ? (
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
              {reading.answered
                ? "Explanation composed by this app. The decision above came from the evaluator."
                : "Composed by this app to say what stopped a verdict being reached. It is not a verdict."}
            </span>
          </div>
          <Paragraph className="app-synthesis__body" style={{ marginBottom: 0 }}>
            <DirectionalText align>{explanation}</DirectionalText>
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
          title={
            missing.length === 1
              ? "One fact is needed before this case can be decided"
              : `${missing.length} facts are needed before this case can be decided`
          }
          description={
            <ul className="project-case-missing">
              {missing.map((item) => (
                <li key={item.fact} className="project-case-missing__item">
                  <Text strong>
                    <DirectionalText>{item.label}</DirectionalText>
                  </Text>
                  {item.whyNeeded ? (
                    <div>
                      <Text type="secondary">
                        <DirectionalText>{item.whyNeeded}</DirectionalText>
                      </Text>
                    </div>
                  ) : null}
                  {item.requiredByRuleIds.length > 0 ? (
                    <div className="project-case-missing__rules">
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        Waited on by
                      </Text>{" "}
                      {item.requiredByRuleIds.map((ruleId) => (
                        <Text key={ruleId} code>
                          {ruleId}
                        </Text>
                      ))}
                    </div>
                  ) : null}
                </li>
              ))}
            </ul>
          }
        />
      ) : null}
      {section.note ? (
        <Paragraph type="secondary">
          <DirectionalText>{section.note}</DirectionalText>
        </Paragraph>
      ) : null}
      <CitationList citations={section.citations ?? []} heading="This track cited:" />
      <GroundingLine grounding={section.grounding} />
      <Paragraph type="secondary" style={{ fontSize: 12, marginBottom: 0 }}>
        {routeLabel(section.route, "verdict")}.
      </Paragraph>
      <RawResponse value={section} />
    </section>
  );
}

/**
 * THE INFORMATION TRACK.
 *
 * What the retained published policies state on the subject asked about. A
 * track that stood back explains itself in prose and states no answer, and the
 * two are never rendered in the same place: an explanation of why nothing was
 * stated must not be able to read as a statement.
 */
function InformationTrack({ reading }: { reading: CaseTrackReading }) {
  const copy = outcomeCopy(reading);
  const section = reading.section;
  if (!section) return <QuietTrack reading={reading} name="Information" />;

  const prose = trackProse(section);
  return (
    <section
      className="policy-case-reading project-case-track"
      data-testid="project-case-information-track"
      data-outcome={reading.outcome}
      aria-label="Information"
    >
      <Paragraph style={{ marginBottom: 8 }}>
        <Text strong>Information</Text> <Tag color={copy.color}>{copy.label}</Tag>{" "}
        <Text strong>{copy.title}</Text>
      </Paragraph>
      <Paragraph type="secondary" style={{ marginBottom: 8 }}>
        {copy.description}
      </Paragraph>
      {reading.answered ? (
        <div className="app-synthesis" data-generated="true">
          <div>
            <span className="app-synthesis__mark" aria-hidden>
              ✦
            </span>{" "}
            <span className="app-synthesis__caption">AI Ready judge read the evaluated policies below</span>
          </div>
          <Paragraph className="app-synthesis__body" style={{ marginBottom: 0 }}>
            <DirectionalText align>{prose}</DirectionalText>
          </Paragraph>
        </div>
      ) : prose ? (
        <Paragraph>
          <DirectionalText align>{prose}</DirectionalText>
        </Paragraph>
      ) : null}
      {section.note ? (
        <Paragraph type="secondary">
          <DirectionalText>{section.note}</DirectionalText>
        </Paragraph>
      ) : null}
      <CitationList citations={section.citations ?? []} heading="This track cited:" />
      <GroundingLine grounding={section.grounding} />
      <Paragraph type="secondary" style={{ fontSize: 12, marginBottom: 0 }}>
        {routeLabel(section.route, "information")}.
      </Paragraph>
      <RawResponse value={section} />
    </section>
  );
}

/**
 * THE EVIDENCE, ONCE.
 *
 * Each track cites for itself above; this is the union, deduplicated by rule id
 * with the tracks that cited each rule carried on it. The rule that *states* a
 * cap is frequently the same rule that *decides* whether a case was within it,
 * and listing it twice would make a reader count two authorities where the
 * policies hold one.
 */
function EvidencePanel({ citations }: { citations: readonly MergedCaseCitation[] }) {
  if (citations.length === 0) return null;
  const both = citations.filter((citation) => citation.serves.length > 1).length;
  return (
    <div className="project-case-evidence" data-testid="project-case-evidence">
      <CitationList
        citations={citations}
        showServes
        heading={
          citations.length === 1
            ? "This answer rests on one cited rule:"
            : `This answer rests on ${citations.length} cited rules:`
        }
      />
      {both > 0 ? (
        <Paragraph type="secondary" style={{ fontSize: 12, marginBottom: 0 }}>
          {both === 1
            ? "One rule was cited by both tracks and is listed once, carrying both tags."
            : `${both} rules were cited by both tracks and are listed once, each carrying both tags.`}
        </Paragraph>
      ) : null}
    </div>
  );
}

/** How the answer was produced: the versions and settings behind it. Kept
 *  behind a disclosure because it is provenance rather than evidence, and shown
 *  only for what this surface actually carries — a reviewer's test is not a
 *  stored receipt and this dialog will not pretend it has one. */
function ProductionTrace({ answer, reading }: { answer: ProjectCaseAnswer; reading: CaseTracksReading }) {
  const evaluation = answer.evaluation;
  const rows: [string, string][] = [];
  if (reading.asked.classifierVersion) rows.push(["Classifier", reading.asked.classifierVersion]);
  if (evaluation?.reasoning_effort) rows.push(["Reasoning effort", evaluation.reasoning_effort]);
  if (answer.retrieval.method) rows.push(["Retrieval method", answer.retrieval.method]);
  // How the retained set was ordered, not merely how it was scored. A reader
  // looking at a highly-ranked policy sitting outside the budget has nothing
  // else on this surface that explains it.
  if (answer.retrieval.policy_selection_order) {
    rows.push(["Policy selection order", answer.retrieval.policy_selection_order]);
  }
  const language = readLanguage(answer);
  if (language) {
    // Which languages, and under which contracts. Two renderings of one
    // question are not interchangeable, so the contract that produced the text
    // that was adjudicated is part of how this answer was produced.
    if (language.sourceLanguage && language.processingLanguage) {
      rows.push([
        "Language",
        `${language.sourceLanguage} → ${language.processingLanguage}${
          language.responseLanguage && language.responseLanguage !== language.processingLanguage
            ? ` → ${language.responseLanguage}`
            : ""
        }`,
      ]);
    }
    if (language.inputProfile) rows.push(["Question rendering contract", language.inputProfile]);
    if (language.outputProfile) rows.push(["Answer rendering contract", language.outputProfile]);
    if (language.projectionProfile) rows.push(["Corpus projection", language.projectionProfile]);
  }
  const discovery = readDiscovery(answer.retrieval);
  if (!language?.projectionProfile && discovery?.projectionProfile) {
    rows.push(["Corpus projection", discovery.projectionProfile]);
  }
  const informationPrompt = reading.information.section?.grounding?.prompt_version;
  const verdictPrompt = reading.verdict.section?.grounding?.prompt_version;
  if (informationPrompt) rows.push(["Information prompt", informationPrompt]);
  if (verdictPrompt) rows.push(["Verdict prompt", verdictPrompt]);
  if (rows.length === 0) return null;
  return (
    <details className="project-case-raw" data-testid="project-case-trace">
      <summary>How this answer was produced</summary>
      <Space orientation="vertical" size={2} style={{ marginTop: 8 }}>
        {rows.map(([label, value]) => (
          <Text key={label} type="secondary" style={{ fontSize: 12 }}>
            {label}: <Text code>{value}</Text>
          </Text>
        ))}
        <Text type="secondary" style={{ fontSize: 12 }}>
          This is a reviewer&apos;s test, so no decision receipt was stored and none is shown.
        </Text>
      </Space>
    </details>
  );
}

function EvaluationPanel({
  answer,
  qualityFindings,
}: {
  answer: ProjectCaseAnswer;
  qualityFindings: readonly QualityFinding[];
}) {
  const reading = readCaseTracks(answer);
  return (
    <div className="project-case-tracks" data-testid="project-case-tracks">
      <QualityFindingNotice findings={qualityFindings} ruleIds={reading.ruleIds} />
      <LanguageNote answer={answer} />
      <AskedTracks reading={reading} />
      <VerdictTrack reading={reading.verdict} />
      <InformationTrack reading={reading.information} />
      <EvidencePanel citations={reading.citations} />
      <ProductionTrace answer={answer} reading={reading} />
    </div>
  );
}

/**
 * HOW ONE POLICY'S RULES WERE PLACED.
 *
 * Three rankings can place a rule and they are reported apart: the rule index's
 * own search rank, a relevance rank over the English projection, and a
 * quantity-compatibility rank — a rule stating an interval that admits a value
 * the question states. The last is a *retrieval* rank only: it decides whether
 * a rule is worth reading and never what the rule decides, and the wording here
 * says so, because a reader who took it for a finding would be reading a search
 * heuristic as policy.
 *
 * `rules_without_projection` is disclosed rather than absorbed: those rules
 * scored zero on relevance because the index held no English projection for
 * them, not because they say nothing relevant. They were never scored against
 * the document's own language — one language on both sides of a match, always.
 */
function RuleIndexCell({ selection }: { selection: ProjectCaseRuleSelection }) {
  const reading = readRuleIndex(selection);
  if (!reading) return null;
  const parts: string[] = [];
  if (reading.lexical !== null) parts.push(`${reading.lexical} by relevance`);
  if (reading.quantity !== null) parts.push(`${reading.quantity} by stated quantity`);
  if (reading.hits !== null) parts.push(`${reading.hits} by the rule index`);
  return (
    <div data-testid="project-case-rule-index">
      {reading.state ? (
        <Text type="secondary" style={{ fontSize: 12 }}>
          {ruleIndexStateLabel(reading.state)}
          {reading.state === "matched" && reading.hits === 0
            ? " — it placed none of this policy's rules, which is an answer, not an absence"
            : ""}
        </Text>
      ) : null}
      {parts.length > 0 ? (
        <div>
          <Text type="secondary" style={{ fontSize: 12 }}>
            Placed: {parts.join(" · ")}
            {reading.fused !== null ? ` · ${reading.fused} in the fused pool the budget chose from` : ""}
          </Text>
        </div>
      ) : null}
      {reading.evidenceQuota !== null ? (
        <div>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {reading.evidenceQuota} slot{reading.evidenceQuota === 1 ? "" : "s"} reserved so distinct source passages
            are covered before a passage&apos;s second rule competes
          </Text>
        </div>
      ) : null}
      {reading.withoutProjection !== null && reading.withoutProjection > 0 ? (
        <div>
          <Text type="secondary" style={{ fontSize: 12 }} data-testid="project-case-without-projection">
            {reading.withoutProjection} rule{reading.withoutProjection === 1 ? "" : "s"} could not be scored for
            relevance because the index held no English projection for{" "}
            {reading.withoutProjection === 1 ? "it" : "them"} — scored zero rather than matched against the
            document&apos;s own language, and still placeable by the rule index or by stated quantity
          </Text>
        </div>
      ) : null}
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
            {
              title: "Rules",
              dataIndex: "rules",
              width: 150,
              // A count alone would say "74 rules" about a policy of which eight
              // rules were read. The selection is stated on the same cell as the
              // total, so the two can never be read apart.
              render: (rules: number | undefined, row) => {
                const selection = row.rule_selection;
                const total = selection?.total_rules ?? rules;
                if (!selection || selection.sliced !== true) return total ?? "—";
                const represented = representedRuleIds(selection);
                const collapsed = selection.duplicate_rules_collapsed ?? 0;
                return (
                  <Space orientation="vertical" size={0}>
                    <Text>
                      {total} · {selection.selected_rules} read for this case
                    </Text>
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      {typeof selection.rules_discarded === "number"
                        ? `${selection.rules_discarded} not selected`
                        : "Read rule by rule"}
                      {selection.method ? ` · ${selectionMethodLabel(selection.method)}` : ""}
                    </Text>
                    {/* Of the rules not selected, the ones that say exactly what
                        a selected rule says. Worded as "represented by", never
                        as "read": naming them makes the unselected count less
                        alarming, and it would be a lie to let that read as the
                        model having seen them. */}
                    {collapsed > 0 ? (
                      <Text type="secondary" style={{ fontSize: 12 }} data-testid="project-case-represented-rules">
                        {collapsed === 1
                          ? "1 of those is an exact copy, represented by a rule that was read, not read itself"
                          : `${collapsed} of those are exact copies, represented by rules that were read, not read themselves`}
                        {represented.length > 0 ? `: ${represented.join(", ")}` : ""}
                      </Text>
                    ) : null}
                    <RuleIndexCell selection={selection} />
                  </Space>
                );
              },
            },
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
              // A collapsed duplicate is the one discard a reader should not
              // worry about, and the only way to say so honestly is to name the
              // record its terms were read in. Every other discard, including a
              // diversity-deferred policy carrying the ordinary
              // `outside_budget`, is left to read as exactly what it is.
              render: (reason: string | null | undefined, row) => {
                if (notNarrowed) return <Text type="secondary">Search did not discard any published policy.</Text>;
                if (row.duplicate_of_provision_key) {
                  return (
                    <Space orientation="vertical" size={0}>
                      <Text type="secondary">Exact copy of another retrieved policy</Text>
                      <Text type="secondary" style={{ fontSize: 12 }} data-testid="project-case-duplicate-of">
                        Its terms were read in <Text code>{row.duplicate_of_provision_key}</Text>; this record was not
                        read.
                      </Text>
                    </Space>
                  );
                }
                return <Text type="secondary">{discardLabel(reason)}</Text>;
              },
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
  /**
   * A refusal the server named, kept apart from an error sentence.
   *
   * `index_projection_unavailable` is the one this surface must not blur: the
   * project's index holds documents that were never rendered into the language
   * a question is matched in — or rendered under a superseded contract, or left
   * half-written by an interrupted rebuild. Matching a rendered question
   * against an unrendered corpus scores near zero on every policy, which reads
   * exactly like "no published policy bears on your question". A reviewer told
   * that would go and look for a policy that is already there.
   */
  const [refusalCode, setRefusalCode] = useState<string | null>(null);

  useEffect(() => {
    setPolicies([]);
    setSelectedProvisionId(undefined);
    setPolicyLoadError(null);
    setAnswer(null);
    setError(null);
    setRefusalCode(null);
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
    setRefusalCode(null);
    try {
      const result = await api.answerProjectCase(policySetKey, {
        scenario: scenario.trim(),
        reasoning_effort: reasoningEffort,
        ...(scope === "single" && selectedProvisionId ? { provision_id: selectedProvisionId } : {}),
      });
      setAnswer(result);
    } catch (caught) {
      // The code is what decides which words a reviewer sees, never the
      // server's sentence: a refusal reworded upstream must not change what
      // this surface offers to do about it.
      setRefusalCode(caught instanceof PolicyPlatformApiError ? (caught.code ?? null) : null);
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
        {error ? (
          refusalCode ? (
            <CaseRefusal code={refusalCode} message={error} onOpenPolicyIndex={onOpenPolicyIndex} />
          ) : (
            <Alert type="error" showIcon title={error} />
          )
        ) : null}
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
