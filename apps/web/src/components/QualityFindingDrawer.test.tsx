import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import type { ApprovedPolicyVersion, CanonicalRule, QualityFinding } from "../api";
import { QualityFindingDrawer, type QualityRuleRecord } from "./QualityFindingDrawer";

const version: ApprovedPolicyVersion = {
  id: "version-1",
  policy_set_id: "set-1",
  version_number: 1,
  effective_from: "2026-01-01",
  effective_to: null,
  is_active: true,
  approved_by: "Reviewer",
  approved_at: "2026-01-01T00:00:00Z",
  rule_count: 3,
};

function rule(ruleId: string, title: string): CanonicalRule {
  return {
    schema_version: "1.0",
    policy_set_id: "set-1",
    policy_version_id: version.id,
    rule_id: ruleId,
    rule_revision: 1,
    title,
    description: `${title} source text`,
    rule_type: "eligibility",
    authority: { level: "policy", owner: "Owner", rank: 1 },
    scope: { jurisdictions: [], organizational_units: [], personas: [], processes: [] },
    condition: { type: "all", all: [] },
    condition_provenance: null,
    effect: { type: "allow", action: "continue" },
    required_facts: [],
    exceptions: [],
    priority: 1,
    effective_from: "2026-01-01",
    effective_to: null,
    machine_executable: true,
    ambiguity_status: "none",
    review_status: "published",
    evidence: [],
    lineage: {
      extraction_run_id: null,
      deployment_name: null,
      prompt_version: null,
      parser_version: null,
      schema_version: "1.0",
    },
    category: "",
    tags: [],
    group_label: "",
    related_rule_ids: [],
    is_explicit_override: false,
    supersedes_rule_ids: [],
    advice: [],
  } as CanonicalRule;
}

function finding(ruleIds: string[]): QualityFinding {
  return {
    severity: "high",
    category: "rule_conflict",
    summary: "Overlapping rules disagree",
    finding: "Three rules from two policies can apply to the same case.",
    affected_rule_ids: ruleIds,
    recommendation: "Review the affected rules.",
    source: "deterministic",
  };
}

function openDrawer(rules: CanonicalRule[], ruleIds = rules.map((item) => item.rule_id)) {
  const lookup = new Map<string, QualityRuleRecord[]>(
    rules.map((item, index) => [
      item.rule_id,
      [{ key: `record-${index}`, rule: item }],
    ]),
  );

  render(
    <QualityFindingDrawer
      finding={finding(ruleIds)}
      onClose={() => {}}
      policySetKey="set-1"
      reportScope="published"
      runAt="2026-01-02T00:00:00Z"
      version={version}
      versions={[version]}
      allRules={rules}
      ruleLookup={lookup}
      loading={false}
      error={null}
    />,
  );
}

afterEach(cleanup);

describe("QualityFindingDrawer counts rules as rules", () => {
  it("does not label affected_rule_ids as policies when three rules come from two policies", () => {
    openDrawer([
      rule("AI-001", "Leave policy — eligibility"),
      rule("AI-002", "Leave policy — approval"),
      rule("AI-003", "Remote-work policy — equipment"),
    ]);

    expect(screen.getByText("3 rules referenced")).toBeTruthy();
    expect(screen.getByText("Rule records involved")).toBeTruthy();
    expect(screen.getByText("3 rules found")).toBeTruthy();
    expect(screen.queryByText("3 referenced policies")).toBeNull();
    expect(screen.queryByText("Policy records involved")).toBeNull();
    expect(screen.queryByText("3 resolved")).toBeNull();
  });

  it("uses the singular rule label for a one-rule finding", () => {
    openDrawer([rule("AI-004", "Travel policy — approval")]);

    expect(screen.getByText("1 rule referenced")).toBeTruthy();
    expect(screen.getByText("1 rule found")).toBeTruthy();
    expect(screen.queryByText("1 referenced policy")).toBeNull();
  });
});
