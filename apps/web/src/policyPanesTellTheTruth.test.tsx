/**
 * What the policy's panes are not allowed to say.
 *
 * Each of these asserts a claim the pane must never make, chosen because a
 * plausible implementation makes it by accident and it reads as correct:
 *
 *  1. An untested rule must never render as passing. The four states exist
 *     because "no test" and "tested and fine" look identical once either is
 *     rounded to a tick, and only one of them is an assurance.
 *  2. A rule that could not be run must not read as failing. A run that errored
 *     has claimed nothing about the policy; reporting it as a failure puts the
 *     defect on the record instead of on the run.
 *  3. A policy whose rules are all decided by reading must never be given a
 *     count of the other route. There is no target to fall short of, and "0"
 *     beside a populated figure is read as a shortfall whatever the caption.
 *  4. A rule that states no comparison must not appear in the facts table at
 *     all. An empty cell in a column headed "facts" is read as an omission by
 *     the rule, when it is a property of how the rule is decided.
 *  5. A dimension its rules disagree on must be marked as such. The union alone
 *     would render two differently-scoped rules as one settled answer.
 *
 * Every assertion is paired with a control that fails when nothing rendered, so
 * that a blank pane cannot pass by saying nothing.
 */

import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import type {
  AssembledPolicy,
  CandidateRule,
  CanonicalRule,
  PolicyTestListItem,
} from "./api";
import { buildPolicyCards } from "./policyCards";
import {
  PolicyPartiesAndRoutesPane,
  PolicyScopePane,
  PolicyTestsPane,
  policyTestRows,
} from "./components/policyTabPanes";

beforeAll(() => {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }));
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  );
});

afterEach(() => {
  cleanup();
});

interface RuleShape {
  id: string;
  mode?: string;
  facts?: string[];
  personas?: string[];
}

function canonical(shape: RuleShape): CanonicalRule {
  return {
    schema_version: "1.0",
    policy_set_id: "set",
    policy_version_id: "draft",
    rule_id: shape.id,
    rule_revision: 1,
    title: `Statement of ${shape.id}`,
    description: `Description of ${shape.id}`,
    rule_type: "obligation",
    authority: { level: "ai_drafted", owner: "formulator", rank: 0 },
    scope: {
      jurisdictions: [],
      organizational_units: [],
      personas: shape.personas ?? [],
      processes: [],
    },
    condition: { type: "all", all: [] },
    attributes: { applies: [], produces: [] },
    effect: { action: "record", parameters: {} },
    evidence: [],
    provenance: { document_id: "doc", page: 1 },
    tags: [],
    category: null,
    group_label: null,
    evaluation_mode: shape.mode ?? "ai_ready",
    required_facts: (shape.facts ?? []).map((name) => ({ name, data_type: "string" })),
    decision_readiness: null,
  } as unknown as CanonicalRule;
}

function candidate(shape: RuleShape): CandidateRule {
  return {
    id: `cand-${shape.id}`,
    rule_type: "obligation",
    review_status: "pending",
    rule: canonical(shape),
    superseded_by_candidate_id: null,
    baseline_candidate_id: null,
  } as unknown as CandidateRule;
}

function policy(shapes: readonly RuleShape[]): AssembledPolicy {
  return {
    key: "policy-under-test",
    heading: "A heading the document supplies",
    heading_path: ["A heading the document supplies"],
    page: 1,
    rule_count: shapes.length,
    passages: [
      {
        passage_id: "passage-1",
        text: "The sentence the policy is stated in.",
        title: null,
        rules: shapes.map((s) => ({ rule_id: s.id, evaluation_mode: s.mode ?? "ai_ready" })),
      },
    ],
  } as unknown as AssembledPolicy;
}

function cardOf(shapes: readonly RuleShape[]) {
  const cards = buildPolicyCards([policy(shapes)], shapes.map(candidate));
  expect(cards).toHaveLength(1);
  return cards[0];
}

function testItem(ruleId: string | null, status: "pass" | "fail" | "error" | null): PolicyTestListItem {
  return {
    test: { id: `t-${ruleId}-${status}`, expected_rule_id: ruleId },
    latest_run: status ? { id: "run", status } : null,
    runs: [],
  } as unknown as PolicyTestListItem;
}

describe("an absent test is never an assurance", () => {
  it("calls a rule with no test untested, not passing", () => {
    const card = cardOf([{ id: "r-1" }, { id: "r-2" }]);
    const rows = policyTestRows(card, [testItem("r-1", "pass")]);
    // Control: the covered rule really did come back passing.
    expect(rows.find((r) => r.ruleId === "r-1")?.state).toBe("passing");
    expect(rows.find((r) => r.ruleId === "r-2")?.state).toBe("untested");
  });

  it("does not print a passing word anywhere for a policy with no tests", () => {
    const card = cardOf([{ id: "r-1" }]);
    render(<PolicyTestsPane card={card} tests={[]} />);
    // Control: the pane rendered the rule at all.
    expect(screen.getByText(/Statement of r-1/)).toBeTruthy();
    expect(screen.queryByText(/Passing/)).toBeNull();
    expect(screen.getAllByText(/No test/).length).toBeGreaterThan(0);
  });

  it("treats a run that errored as unverified rather than failing", () => {
    const card = cardOf([{ id: "r-1" }]);
    const rows = policyTestRows(card, [testItem("r-1", "error")]);
    expect(rows[0].state).toBe("unverified");
  });

  it("reports failing when a covering test failed", () => {
    const card = cardOf([{ id: "r-1" }]);
    expect(policyTestRows(card, [testItem("r-1", "fail")])[0].state).toBe("failing");
  });

  it("ignores a test that targets no rule, because it belongs to no policy", () => {
    const card = cardOf([{ id: "r-1" }]);
    const rows = policyTestRows(card, [testItem(null, "pass")]);
    expect(rows[0].state).toBe("untested");
  });
});

describe("a route is never rendered as a shortfall", () => {
  it("lists only the routes the policy's rules take", () => {
    const card = cardOf([{ id: "r-1" }, { id: "r-2" }]);
    const { container } = render(<PolicyPartiesAndRoutesPane card={card} />);
    // Control: the route section rendered something.
    expect(screen.getByText(/How its rules are decided/)).toBeTruthy();
    // No count of a route no rule took can appear, in any wording.
    expect(container.textContent).not.toMatch(/\b0\s+(of|rules?)/);
    expect(container.textContent).not.toMatch(/0 of \d+ rules/);
  });

  it("omits rules that state no comparison from the facts table", () => {
    const card = cardOf([
      { id: "r-1", mode: "deterministic", facts: ["a_named_value"] },
      { id: "r-2" },
    ]);
    const { container } = render(<PolicyPartiesAndRoutesPane card={card} />);
    // Control: the fact from the comparing rule is there.
    expect(screen.getByText("a_named_value")).toBeTruthy();
    // The rule that names none is not listed beside it with an empty entry.
    expect(container.textContent).not.toContain("Statement of r-2");
  });

  it("says plainly that a policy decided by reading waits on nothing", () => {
    const card = cardOf([{ id: "r-1" }]);
    render(<PolicyPartiesAndRoutesPane card={card} />);
    expect(screen.getByText(/none of them waits on a supplied value/)).toBeTruthy();
  });
});

describe("scope disagreements survive being read together", () => {
  it("marks a dimension the policy's rules do not agree on", () => {
    const card = cardOf([
      { id: "r-1", personas: ["one_named_group"] },
      { id: "r-2", personas: ["another_named_group"] },
    ]);
    render(<PolicyScopePane card={card} />);
    // Control: both values survived the union.
    expect(screen.getByText("one_named_group")).toBeTruthy();
    expect(screen.getByText("another_named_group")).toBeTruthy();
    expect(screen.getByText(/Its rules differ here/)).toBeTruthy();
  });

  it("does not mark a dimension every rule states identically", () => {
    const card = cardOf([
      { id: "r-1", personas: ["one_named_group"] },
      { id: "r-2", personas: ["one_named_group"] },
    ]);
    render(<PolicyScopePane card={card} />);
    expect(screen.getByText("one_named_group")).toBeTruthy();
    expect(screen.queryByText(/Its rules differ here/)).toBeNull();
  });

  it("does not let a narrow rule speak for a rule bound to everyone", () => {
    const card = cardOf([{ id: "r-1", personas: ["one_named_group"] }, { id: "r-2" }]);
    render(<PolicyScopePane card={card} />);
    expect(screen.getByText("one_named_group")).toBeTruthy();
    expect(screen.getByText(/apply to everyone/)).toBeTruthy();
  });
});
