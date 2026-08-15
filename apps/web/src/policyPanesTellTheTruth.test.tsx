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
import type { PolicySightingView } from "./components/policyTabPanes";
import {
  PolicyHistoryPane,
  PolicyOverviewPane,
  PolicyPartiesAndRoutesPane,
  PolicyScopePane,
  PolicyTestsPane,
  policyTestRows,
  candidatePolicyRecord,
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
  /** `informational` is the one effect that makes a rule supply a meaning rather than settle an outcome. */
  effectType?: string;
  /** The record carries no effect at all — a third state, neither deciding nor defining. */
  statesNoEffect?: boolean;
}

function canonical(shape: RuleShape): CanonicalRule {
  const rule = {
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
    effect: {
      action: "record",
      parameters: {},
      // A shape that names no effect kind still carries one: every record the
      // extractor produces states its effect, and a fixture whose `type` is
      // `undefined` exercises the absent-effect state by accident rather than on
      // purpose. Tests that mean to reach that state say so, and the one below
      // that does asserts on it by name.
      type: shape.effectType ?? "require_action",
    },
    evidence: [],
    provenance: { document_id: "doc", page: 1 },
    tags: [],
    category: null,
    group_label: null,
    evaluation_mode: shape.mode ?? "ai_ready",
    required_facts: (shape.facts ?? []).map((name) => ({ name, data_type: "string" })),
    decision_readiness: null,
  } as unknown as CanonicalRule;
  if (shape.statesNoEffect) delete (rule as { effect?: unknown }).effect;
  return rule;
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
    const rows = policyTestRows(candidatePolicyRecord(card), [testItem("r-1", "pass")]);
    // Control: the covered rule really did come back passing.
    expect(rows.find((r) => r.ruleId === "r-1")?.state).toBe("passing");
    expect(rows.find((r) => r.ruleId === "r-2")?.state).toBe("untested");
  });

  it("does not print a passing word anywhere for a policy with no tests", () => {
    const card = cardOf([{ id: "r-1" }]);
    render(<PolicyTestsPane record={candidatePolicyRecord(card)} tests={[]} />);
    // Control: the pane rendered the rule at all.
    expect(screen.getByText(/Statement of r-1/)).toBeTruthy();
    expect(screen.queryByText(/Passing/)).toBeNull();
    expect(screen.getAllByText(/No test/).length).toBeGreaterThan(0);
  });

  it("treats a run that errored as unverified rather than failing", () => {
    const card = cardOf([{ id: "r-1" }]);
    const rows = policyTestRows(candidatePolicyRecord(card), [testItem("r-1", "error")]);
    expect(rows[0].state).toBe("unverified");
  });

  it("reports failing when a covering test failed", () => {
    const card = cardOf([{ id: "r-1" }]);
    expect(policyTestRows(candidatePolicyRecord(card), [testItem("r-1", "fail")])[0].state).toBe("failing");
  });

  it("ignores a test that targets no rule, because it belongs to no policy", () => {
    const card = cardOf([{ id: "r-1" }]);
    const rows = policyTestRows(candidatePolicyRecord(card), [testItem(null, "pass")]);
    expect(rows[0].state).toBe("untested");
  });
});

describe("a route is never rendered as a shortfall", () => {
  it("lists only the routes the policy's rules take", () => {
    const card = cardOf([{ id: "r-1" }, { id: "r-2" }]);
    const { container } = render(<PolicyPartiesAndRoutesPane record={candidatePolicyRecord(card)} />);
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
    const { container } = render(<PolicyPartiesAndRoutesPane record={candidatePolicyRecord(card)} />);
    // Control: the fact from the comparing rule is there.
    expect(screen.getByText("a_named_value")).toBeTruthy();
    // The rule that names none is not listed beside it with an empty entry.
    expect(container.textContent).not.toContain("Statement of r-2");
  });

  it("says how a policy decided by reading works, rather than what it holds none of", () => {
    const card = cardOf([{ id: "r-1" }]);
    render(<PolicyPartiesAndRoutesPane record={candidatePolicyRecord(card)} />);
    expect(screen.getByText(/the words\s+are the test/)).toBeTruthy();
  });

  /**
   * A denial is not a defence.
   *
   * Two earlier drafts of these captions tried to be reassuring — "it names no
   * facts, and is not missing any", "none of them waits on a supplied value" —
   * and both put the reader in front of a shortage in order to wave it away.
   * The noun survives the skim; the negation does not. So the assertion below
   * is not that the copy is polite about the reading route, it is that the copy
   * never raises the subject: there is no shortage here to be generous about.
   *
   * The phrases are matched, not the sentences that once held them, because the
   * failure mode is a later tidy-up reaching for the same shape in new words.
   */
  const REASSURANCE_SHAPED_AS_A_DENIAL = [
    /\bis not missing\b/i,
    /\bnot missing any\b/i,
    /\bnothing (is )?missing\b/i,
    /\bwaits on nothing\b/i,
    /\bnames no facts\b/i,
    /\bno rule .* states a comparison\b/i,
    /\bdoes not lack\b/i,
    /\bis not incomplete\b/i,
  ];

  it.each([
    ["a policy every rule of which is decided by reading", [{ id: "r-1" }, { id: "r-2" }]],
    [
      "a policy with both routes in it",
      [{ id: "r-1", mode: "deterministic" as const, facts: ["a_named_value"] }, { id: "r-2" }],
    ],
  ])("never reassures %s out of a shortage it would have introduced", (_name, spec) => {
    const { container } = render(
      <PolicyPartiesAndRoutesPane record={candidatePolicyRecord(cardOf(spec))} />,
    );
    const rendered = container.textContent ?? "";
    // Control: the pane rendered its captions, so an empty match proves nothing.
    expect(rendered).toMatch(/the words\s+are the test/);
    for (const denial of REASSURANCE_SHAPED_AS_A_DENIAL) {
      expect(rendered).not.toMatch(denial);
    }
  });
});

describe("scope disagreements survive being read together", () => {
  it("marks a dimension the policy's rules do not agree on", () => {
    const card = cardOf([
      { id: "r-1", personas: ["one_named_group"] },
      { id: "r-2", personas: ["another_named_group"] },
    ]);
    render(<PolicyScopePane record={candidatePolicyRecord(card)} />);
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
    render(<PolicyScopePane record={candidatePolicyRecord(card)} />);
    expect(screen.getByText("one_named_group")).toBeTruthy();
    expect(screen.queryByText(/Its rules differ here/)).toBeNull();
  });

  it("does not let a narrow rule speak for a rule bound to everyone", () => {
    const card = cardOf([{ id: "r-1", personas: ["one_named_group"] }, { id: "r-2" }]);
    render(<PolicyScopePane record={candidatePolicyRecord(card)} />);
    expect(screen.getByText("one_named_group")).toBeTruthy();
    expect(screen.getByText(/apply to everyone/)).toBeTruthy();
  });
});

/**
 * Both of these were found in the running app, not in review, and both are the
 * same class of fault: a pane rendering one sentence for two different absences.
 */
describe("a policy holding rules is never described as holding none", () => {
  it("says what its single rule does rather than calling the policy empty", () => {
    const card = cardOf([{ id: "r-1" }]);
    render(<PolicyOverviewPane record={candidatePolicyRecord(card)} />);
    expect(screen.getByText("1 rule")).toBeTruthy();
    expect(screen.queryByText(/no rules/i)).toBeNull();
    expect(screen.getByText(/Its one rule decides a case\./)).toBeTruthy();
  });

  it("describes a policy whose rules all supply meanings without printing a zero", () => {
    const card = cardOf([
      { id: "r-1", effectType: "informational" },
      { id: "r-2", effectType: "informational" },
    ]);
    render(<PolicyOverviewPane record={candidatePolicyRecord(card)} />);
    expect(screen.getByText(/Every rule of this policy supplies a meaning\./)).toBeTruthy();
    expect(screen.queryByText(/\b0\b/)).toBeNull();
  });

  it("still contrasts the two sides when the policy holds both", () => {
    const card = cardOf([{ id: "r-1" }, { id: "r-2", effectType: "informational" }]);
    render(<PolicyOverviewPane record={candidatePolicyRecord(card)} />);
    expect(screen.getByText(/1 decides a case · 1 supplies a meaning/)).toBeTruthy();
  });

  it("counts a rule stating no effect apart rather than as one that decides", () => {
    // A record carrying no effect kind is one this app knows nothing about, and
    // there is no honest way to put it on either side. It used to be counted as
    // deciding, which left the total right and the split wrong — the version of
    // the fault a reader has no way to notice.
    const card = cardOf([
      { id: "r-1" },
      { id: "r-2", effectType: "informational" },
      { id: "r-3", effectType: undefined, statesNoEffect: true },
    ]);
    render(<PolicyOverviewPane record={candidatePolicyRecord(card)} />);
    const said = screen.getByText(/decides a case/).textContent ?? "";
    const counts = [...said.matchAll(/(\d+)/g)].map((match) => Number(match[1]));

    expect(counts.reduce((total, one) => total + one, 0)).toBe(3);
    expect(said).toMatch(/does not state/i);
  });
});

describe("history never claims a status it was not told", () => {
  it("says its versions were not loaded when it was never given any", () => {
    render(<PolicyHistoryPane sightings={null} />);
    expect(screen.getByText(/have not been loaded/)).toBeTruthy();
    expect(screen.queryByText(/not been published/)).toBeNull();
  });

  it("separates having asked and found nothing from never having asked", () => {
    render(<PolicyHistoryPane sightings={[]} />);
    expect(screen.getByText(/No published version of this policy was found/)).toBeTruthy();
    expect(screen.queryByText(/have not been loaded/)).toBeNull();
  });
});

/**
 * The shape below was recorded from a live response of
 * `GET /api/policy-sets/{key}/provisions/{provision_key}/history`, and is kept
 * verbatim rather than hand-built.
 *
 * Every other test in this file constructs its own input, which is what let the
 * History tab ship with a view type that had invented `rules_changed`,
 * `rule_count` and `effective_from`. Tests written against an invented shape
 * agree with it. The only thing that disagrees is the server, and the only
 * place they meet is the running page — where this crashed on the first real
 * payload.
 *
 * So this fixture is a witness: it is here to be *unlike* what a test author
 * would write. Nothing in it is a target — no count, heading or identifier is
 * asserted as a product expectation, only that each field the pane reads is
 * one the server actually sends.
 */
const RECORDED_HISTORY_RESPONSE: unknown = [
  {
    version_id: "0f2d7f1e-3a55-4f0e-9f2d-1c2b3a4d5e6f",
    version_number: 1,
    is_active: false,
    approved_by: "a-reviewer",
    approved_at: "2026-08-15T13:28:52.934338Z",
    heading_path: ["A DOCUMENT TITLE"],
    change: "first_seen",
    rules: [{ rule_id: "AI-299b7808a3", title: "It may not be disclosed", fingerprint: "272b113b" }],
    rules_added: [],
    rules_removed: [],
    rules_reworded: [],
  },
  {
    version_id: "1a3e8b2f-4c66-5a1f-8e3d-2d3c4b5e6f70",
    version_number: 2,
    is_active: true,
    approved_by: null,
    approved_at: null,
    heading_path: ["A DOCUMENT TITLE"],
    change: "unchanged",
    rules: [{ rule_id: "AI-299b7808a3", title: "It may not be disclosed", fingerprint: "272b113b" }],
    rules_added: [],
    rules_removed: [],
    rules_reworded: [],
  },
];

describe("the history pane reads the fields the server sends", () => {
  const recorded = RECORDED_HISTORY_RESPONSE as PolicySightingView[];

  it("renders a recorded response without inventing a field that is not in it", () => {
    render(<PolicyHistoryPane sightings={recorded} />);
    expect(screen.getByText(/first seen/)).toBeTruthy();
    expect(screen.getByText(/unchanged/)).toBeTruthy();
  });

  it("counts the rules the sighting carries rather than a separate total", () => {
    render(<PolicyHistoryPane sightings={recorded} />);
    const counts = screen.getAllByText(String(recorded[0].rules.length));
    expect(counts.length).toBeGreaterThan(0);
  });

  it("says a sighting was not recorded as approved rather than leaving it blank", () => {
    render(<PolicyHistoryPane sightings={recorded} />);
    expect(screen.getByText(/not recorded/)).toBeTruthy();
  });
});
