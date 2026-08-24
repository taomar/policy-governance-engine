import { aiApi, type EvaluationResponse, type ProjectCaseAnswer, type QualityFinding } from "./api";

export interface LinkedQualityFinding extends QualityFinding {
  matched_rule_ids: string[];
}

export async function loadLatestPublishedQualityFindings(policySetKey: string): Promise<QualityFinding[]> {
  const history = await aiApi.getQualityHistory(policySetKey, "published", 1);
  const latest = history.runs[0];
  if (!latest) return [];
  const run = await aiApi.getQualityRun(policySetKey, latest.id);
  return run.findings ?? [];
}

export function evaluationRuleIds(response: EvaluationResponse): string[] {
  return uniqueIds([
    ...response.applicable_rules,
    ...response.satisfied_rules,
    ...response.failed_rules,
    ...response.rule_results.map((result) => result.rule_id),
  ]);
}

export function projectCaseRuleIds(answer: ProjectCaseAnswer): string[] {
  const evaluation = answer.evaluation;
  if (!evaluation) return [];
  return uniqueIds([
    ...(evaluation.citations ?? []).map((citation) => citation.rule_id),
    ...(evaluation.judgement?.citations ?? []).map((citation) => citation.rule_id),
    ...(evaluation.decision?.citations ?? []).map((citation) => citation.rule_id),
    ...(evaluation.informational?.citations ?? []).map((citation) => citation.rule_id),
  ]);
}

export function findingsForRuleIds(
  findings: readonly QualityFinding[],
  ruleIds: readonly string[],
): LinkedQualityFinding[] {
  const named = new Set(ruleIds.filter(Boolean));
  if (named.size === 0) return [];
  return findings.flatMap((finding) => {
    const matched = finding.affected_rule_ids.filter((id) => named.has(id));
    return matched.length > 0 ? [{ ...finding, matched_rule_ids: matched }] : [];
  });
}

function uniqueIds(ids: readonly (string | null | undefined)[]): string[] {
  return [...new Set(ids.filter((id): id is string => Boolean(id)))];
}
