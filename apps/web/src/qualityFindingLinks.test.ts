import { describe, expect, it } from "vitest";
import type { EvaluationResponse, ProjectCaseAnswer, QualityFinding } from "./api";
import { evaluationRuleIds, findingsForRuleIds, projectCaseRuleIds } from "./qualityFindingLinks";

const finding: QualityFinding = {
  severity: "high",
  category: "exception_logic_mismatch",
  finding: "The rule contradicts its exception.",
  affected_rule_ids: ["AI-1421ce9ea2", "AI-5b6e00e53c"],
  recommendation: "Review the extracted rule.",
  source: "deterministic",
};

describe("quality finding links for case and evaluation results", () => {
  it("links an evaluation result to open findings by named rule ids", () => {
    const response = {
      applicable_rules: ["AI-1421ce9ea2"],
      satisfied_rules: [],
      failed_rules: [],
      rule_results: [{ rule_id: "AI-other" }],
    } as unknown as EvaluationResponse;

    const linked = findingsForRuleIds([finding], evaluationRuleIds(response));

    expect(linked).toHaveLength(1);
    expect(linked[0].category).toBe("exception_logic_mismatch");
    expect(linked[0].matched_rule_ids).toEqual(["AI-1421ce9ea2"]);
  });

  it("links an AI Ready case answer to findings by cited rule ids", () => {
    const answer = {
      evaluation: {
        intent: "decision",
        decision: {
          citations: [{ rule_id: "AI-5b6e00e53c" }],
        },
      },
    } as unknown as ProjectCaseAnswer;

    const linked = findingsForRuleIds([finding], projectCaseRuleIds(answer));

    expect(linked).toHaveLength(1);
    expect(linked[0].matched_rule_ids).toEqual(["AI-5b6e00e53c"]);
  });
});
