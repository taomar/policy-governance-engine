/**
 * THE UNIT IS THE POLICY — in the count, in the selection, and in the file.
 *
 * This page listed policies while counting rules, offering "select all 412
 * shown" above thirty-eight cards, and writing a download with one line per
 * rule. A reviewer who selected two policies received thirteen lines, and
 * nothing in the file recorded which two they had chosen.
 *
 * The three faults were three separate strings in three separate places, which
 * is why they drifted separately and were reported as one complaint. What is
 * pinned here is that they now come from one module, that a line of the file is
 * a policy with its rules inside it, and that the count on every control names
 * what it counts.
 *
 * No number here is a measurement of any document. Each fixture states its own
 * size and every assertion is computed from the fixture, so growing one cannot
 * turn a count into a literal somebody later "corrects".
 */
import { describe, expect, it } from "vitest";
import type { AssembledPolicy, CanonicalRule } from "./api";
import { buildPolicyCards, type PolicyCard } from "./policyCards";
import {
  exportAllContentsLabel,
  exportContentsLabel,
  exportedSummary,
  policiesAsJsonl,
  policyUnit,
  ruleUnit,
} from "./policyExport";

function rule(ruleId: string): CanonicalRule {
  return {
    schema_version: "1.0",
    policy_set_id: "set",
    policy_version_id: "version",
    rule_id: ruleId,
    rule_revision: 1,
    title: `title ${ruleId}`,
    description: `description ${ruleId}`,
    rule_type: "obligation",
    authority: { level: "ai_drafted", owner: "formulator", rank: 0 },
    scope: { jurisdictions: [], organizational_units: [], personas: [], processes: [] },
    condition: { type: "all", all: [] },
    effect: { type: "require_action", action: "act" },
    required_facts: [],
    exceptions: [],
    priority: 0,
    effective_from: "2026-01-01",
    effective_to: null,
    machine_executable: false,
    review_status: "published",
    evidence: [],
    lineage: {
      extraction_run_id: "run",
      deployment_name: "model",
      prompt_version: "v1",
      parser_version: "v1",
      schema_version: "1.0",
      source_elements: "p1-E000001",
    },
    tags: [],
    related_rule_ids: [],
    is_explicit_override: false,
    supersedes_rule_ids: [],
  } as unknown as CanonicalRule;
}

/** One policy under one heading, stating the rules named. */
function policy(key: string, ruleIds: string[]): AssembledPolicy {
  const rules = ruleIds.map((rule_id) => ({
    rule_id,
    title: `title ${rule_id}`,
    evaluation_mode: "ai_ready",
  }));
  return {
    key,
    heading: key,
    heading_path: [key],
    persisted: true,
    document_version_id: "dv1",
    source_elements: key,
    page: 3,
    rule_count: rules.length,
    passage_count: 1,
    route: "ai_ready",
    passages: [
      { key, source_elements: key, page: 3, rule_count: rules.length, rules },
    ],
    rules,
  } as AssembledPolicy;
}

/** Cards for the shape a caller describes: `[policy key, how many rules]`. */
function cardsOf(shape: [string, number][]): PolicyCard[] {
  const ruleIds = shape.flatMap(([key, count]) =>
    Array.from({ length: count }, (_unused, index) => `${key}-r${index}`),
  );
  const policies = shape.map(([key, count]) =>
    policy(
      key,
      Array.from({ length: count }, (_unused, index) => `${key}-r${index}`),
    ),
  );
  return buildPolicyCards(
    policies,
    ruleIds.map((ruleId) => ({ rule: rule(ruleId) })),
  );
}

function parsed(text: string): Record<string, unknown>[] {
  return text
    .split("\n")
    .filter((line) => line.length > 0)
    .map((line) => JSON.parse(line) as Record<string, unknown>);
}

describe("a line of the file is a policy", () => {
  it("writes one line per policy, however many rules each states", () => {
    // The fault this replaces: a policy of many rules became many lines, so the
    // number of lines answered "how many rules" to a reader who had chosen
    // policies.
    const shape: [string, number][] = [
      ["A", 4],
      ["B", 1],
      ["C", 2],
    ];
    const written = policiesAsJsonl(cardsOf(shape));
    expect(parsed(written.text)).toHaveLength(shape.length);
    expect(written.policyCount).toBe(shape.length);
  });

  it("keeps every rule, nested inside the policy that states it", () => {
    // Fewer lines must not mean fewer rules. The rules move inside the line
    // rather than off the page.
    const shape: [string, number][] = [
      ["A", 3],
      ["B", 2],
    ];
    const expectedRules = shape.reduce((total, [, count]) => total + count, 0);
    const written = policiesAsJsonl(cardsOf(shape));

    const nested = parsed(written.text).flatMap((document) =>
      (document.passages as { rules: CanonicalRule[] }[]).flatMap((passage) => passage.rules),
    );
    expect(nested).toHaveLength(expectedRules);
    expect(written.ruleCount).toBe(expectedRules);
  });

  it("gives every line the policy's own identity, not a rule's", () => {
    const written = policiesAsJsonl(cardsOf([["A", 2]]));
    const [document] = parsed(written.text);
    // The policy's key is the identity a reader traces across versions. A line
    // carrying a rule id at its top level would be the old shape returning.
    expect(document.key).toBe("A");
    expect(document).not.toHaveProperty("rule_id");
  });

  it("follows the order it was given, so a file reads like the page", () => {
    const written = policiesAsJsonl(
      cardsOf([
        ["C", 1],
        ["A", 1],
        ["B", 1],
      ]),
    );
    expect(parsed(written.text).map((document) => document.key)).toEqual(["C", "A", "B"]);
  });

  it("terminates every line, including the last", () => {
    const written = policiesAsJsonl(cardsOf([["A", 1]]));
    expect(written.text.endsWith("\n")).toBe(true);
  });

  it("writes nothing at all when nothing was chosen", () => {
    // Not a lone newline: an empty file is empty, and a one-byte file looks
    // like a record to anything counting lines.
    const written = policiesAsJsonl([]);
    expect(written.text).toBe("");
    expect(written.policyCount).toBe(0);
    expect(written.ruleCount).toBe(0);
  });
});

describe("every control names what it counts", () => {
  it("says policies, and says policy when there is one", () => {
    expect(policyUnit(1)).toBe("1 policy");
    expect(policyUnit(0)).toBe("0 policies");
    expect(policyUnit(7)).toBe("7 policies");
  });

  it("says rules the same way, for the count that sits beside it", () => {
    expect(ruleUnit(1)).toBe("1 rule");
    expect(ruleUnit(4)).toBe("4 rules");
  });

  it("names the unit on the button, before it is pressed", () => {
    // A reviewer who exported this page before received rules. The button has
    // to say the shape changed at the moment they choose, not afterwards.
    const count = 3;
    expect(exportContentsLabel(count)).toContain(policyUnit(count));
    expect(exportAllContentsLabel(count)).toContain(policyUnit(count));
  });

  it("never offers to export a number of rules", () => {
    // The specific regression: a button reading "Export all 13 JSONL" over a
    // list of two policies, where 13 was the rule count.
    for (const label of [exportContentsLabel(2), exportAllContentsLabel(2)]) {
      expect(label).not.toMatch(/\brules?\b/i);
    }
  });

  it("tracks the count it is given rather than any fixed number", () => {
    const labels = [1, 2, 40].map((count) => exportAllContentsLabel(count));
    expect(new Set(labels).size).toBe(labels.length);
    expect(labels[2]).toContain("40");
  });
});

describe("what was written is reported afterwards", () => {
  it("states policies first, and the rules as something they hold", () => {
    const shape: [string, number][] = [
      ["A", 2],
      ["B", 3],
    ];
    const written = policiesAsJsonl(cardsOf(shape));
    const summary = exportedSummary(written, "file.jsonl");

    expect(summary.indexOf(policyUnit(written.policyCount))).toBeLessThan(
      summary.indexOf(ruleUnit(written.ruleCount)),
    );
    // Said as contained, so the rule tally cannot be read as a second thing
    // exported beside the policies, nor as the number of lines.
    expect(summary).toContain("nested inside them");
    expect(summary).toContain("file.jsonl");
  });

  it("reports both counts, so neither has to be guessed", () => {
    const shape: [string, number][] = [["A", 5]];
    const written = policiesAsJsonl(cardsOf(shape));
    const summary = exportedSummary(written, "file.jsonl");
    expect(summary).toContain(policyUnit(1));
    expect(summary).toContain(ruleUnit(5));
  });

  it("says one policy in the singular", () => {
    const written = policiesAsJsonl(cardsOf([["A", 1]]));
    const summary = exportedSummary(written, "file.jsonl");
    expect(summary).toContain("1 policy ");
    expect(summary).toContain("1 rule ");
  });
});
