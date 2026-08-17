/**
 * THE TESTS ARE READABLE FROM THE TABLE.
 *
 * The Tests tab told a reviewer a rule had "2 · Passing" and stopped there. The
 * count and the green tag were the whole of it: nothing rendered what either
 * test actually said — what situation it puts, what outcome it expects, or what
 * the last run returned. A green "Passing" is an assertion the reviewer is asked
 * to trust, and trust needs the scenario. The information was already in hand
 * (`row.testIds`, and the test items behind them) and was simply never drawn.
 *
 * So this pins the content, not a mechanism. It does not check that an expander
 * exists; it checks that the scenario, the expected outcome and the last run's
 * own account are on the page, reachable from the table itself and not from a
 * modal a reviewer would have to open to discover what they are trusting.
 *
 * The second half pins constraint 5 through the new surface: absent, never-run,
 * passed and failed are four different states, and the one this pane exists to
 * make impossible is a never-run test reading as a passed one. That must hold at
 * the rule level and inside the per-test detail the expansion now draws.
 */
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import type {
  AssembledPolicy,
  CanonicalRule,
  PolicyTest,
  PolicyTestListItem,
  PolicyTestRun,
} from "../api";
import { PolicyTestsPane, type PolicyRecordView, type PolicyTestingVerbs } from "./policyTabPanes";

beforeAll(() => {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }),
  });
  globalThis.ResizeObserver ??= class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
});

beforeEach(() => cleanup());

function rule(id: string, title: string): CanonicalRule {
  return {
    rule_id: id,
    title,
    effect: "allow",
    evaluation_mode: "deterministic",
    machine_executable: true,
    condition: { type: "all", all: [] },
    obligations: [],
    exceptions: [],
    scope: {},
    source: { document_id: "d", quotes: [] },
    lineage: { extraction_run_id: "r" },
  } as unknown as CanonicalRule;
}

function record(rules: CanonicalRule[]): PolicyRecordView {
  return {
    policy: {
      key: "k",
      heading: "A heading",
      heading_path: [],
      rules,
      passages: [],
    } as unknown as AssembledPolicy,
    passageCount: 0,
    rules: rules.map((r) => ({ rule_id: r.rule_id, rule: r })),
  } as unknown as PolicyRecordView;
}

/**
 * A test item carrying everything a reviewer needs to judge the row: what it is
 * called, the situation it puts (scenario plus supplied facts), the outcome it
 * expects, and — through `latest` — what the last run returned. Every value is
 * one this test supplies and reads back, never a claim about any corpus, and the
 * strings are domain-neutral so the assertions do not smuggle in a document.
 */
function testItem(
  id: string,
  ruleId: string,
  overrides: Partial<PolicyTest> = {},
  latest: PolicyTestRun | null = null,
): PolicyTestListItem {
  return {
    test: {
      id,
      expected_rule_id: ruleId,
      review_status: "active",
      proposed_by: "human",
      is_active: true,
      name: `Case ${id}`,
      description: "",
      scenario_text: "",
      input_facts: {},
      expected_overall_status: null,
      ...overrides,
    } as unknown as PolicyTest,
    latest_run: latest,
    runs: latest ? [latest] : [],
  };
}

function run(status: "pass" | "fail" | "error", overrides: Partial<PolicyTestRun> = {}): PolicyTestRun {
  return {
    id: `run-${status}`,
    policy_test_id: "t",
    policy_version_id: "v",
    status,
    explanation: "",
    actual_response_json: null,
    expected_assertions_json: null,
    expectation_hash: null,
    run_trigger: "manual",
    triggered_by: "a-reviewer",
    run_at: "2024-05-01T09:00:00Z",
    ...overrides,
  } as unknown as PolicyTestRun;
}

function verbs(overrides: Partial<PolicyTestingVerbs> = {}): PolicyTestingVerbs {
  return {
    generate: vi.fn().mockResolvedValue(undefined),
    run: vi.fn().mockResolvedValue(undefined),
    target: { kind: "published_version", policyVersionId: "a-version", versionNumber: 1 },
    busy: new Set<string>(),
    working: false,
    error: null,
    dismissError: vi.fn(),
    ...overrides,
  };
}

// Domain-neutral, deliberately distinctive strings so each getByText resolves to
// exactly one node and cannot be satisfied by boilerplate elsewhere on the page.
const SCENARIO = "A described situation the reviewer supplied to this rule";
const FACT_KEY = "a_named_fact";
const FACT_VALUE = "a_supplied_value";
const ACCOUNT = "The engine reached the expected verdict on this scenario.";

describe("a rule's tests can be read from the table, not merely counted", () => {
  function renderOneCoveredRule() {
    render(
      <PolicyTestsPane
        record={record([rule("r-1", "A rule that is covered")])}
        tests={[
          testItem(
            "t-1",
            "r-1",
            {
              name: "The worked case",
              scenario_text: SCENARIO,
              input_facts: { [FACT_KEY]: FACT_VALUE },
              expected_overall_status: "SATISFIED",
            },
            run("pass", {
              explanation: ACCOUNT,
              actual_response_json: { overall_status: "SATISFIED" } as unknown as PolicyTestRun["actual_response_json"],
            }),
          ),
        ]}
        testing={verbs()}
      />,
    );
  }

  it("shows the situation the test puts — its scenario and its supplied facts", () => {
    renderOneCoveredRule();
    expect(
      screen.getByText(new RegExp(SCENARIO)),
      "the scenario the test asserts was nowhere on the page",
    ).toBeTruthy();
    // The facts a case supplies are part of the situation, not decoration.
    expect(document.body.textContent).toContain(FACT_KEY);
    expect(document.body.textContent).toContain(FACT_VALUE);
  });

  it("shows the outcome the test expects", () => {
    renderOneCoveredRule();
    // The expected verdict, drawn readably (underscores spaced) rather than left
    // as an enum the reviewer must decode. It can appear more than once — the
    // detail shows expected and actual side by side, as the validation lab does —
    // so this asserts it is present, not that it is unique.
    expect(screen.getAllByText(/SATISFIED/).length).toBeGreaterThan(0);
  });

  it("shows what the last run actually returned, in the run's own account", () => {
    renderOneCoveredRule();
    expect(
      screen.getByText(new RegExp(ACCOUNT.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))),
      "the last run's explanation — the thing a green tag stands in for — was not shown",
    ).toBeTruthy();
  });

  it("does not put the reading behind a modal a reviewer must open", () => {
    renderOneCoveredRule();
    // Nothing needed to judge the record is behind a click to a separate surface:
    // no dialog is opened merely to render what the tests say.
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});

describe("the four coverage states stay distinct through the expansion", () => {
  function renderFourStates() {
    render(
      <PolicyTestsPane
        record={record([
          rule("untested", "No test targets this"),
          rule("neverrun", "A test, never run"),
          rule("passed", "A test that passed"),
          rule("failed", "A test that failed"),
        ])}
        tests={[
          testItem("t-never", "neverrun", { name: "Never run case" }, null),
          testItem("t-pass", "passed", { name: "Passing case" }, run("pass", { explanation: "It matched." })),
          testItem("t-fail", "failed", { name: "Failing case" }, run("fail", { explanation: "It did not match." })),
        ]}
        testing={verbs()}
      />,
    );
  }

  it("keeps the rule-level tags apart: No test, Not yet run, Passing, Failing", () => {
    renderFourStates();
    expect(screen.getByText("No test")).toBeTruthy();
    expect(screen.getByText("Not yet run")).toBeTruthy();
    expect(screen.getByText("Passing")).toBeTruthy();
    expect(screen.getByText("Failing")).toBeTruthy();
  });

  it("never draws a never-run test as one that passed", () => {
    renderFourStates();
    const neverRun = screen.getByTestId("rule-test-t-never");
    // Its outcome is stated as unknown, never as a pass. Both the tag and the
    // sentence say so, which is two honest matches, not one.
    expect(within(neverRun).getAllByText(/not run|nothing is known/i).length).toBeGreaterThan(0);
    expect(
      within(neverRun).queryByText(/passed/i),
      "a test that has never run was drawn as one that passed",
    ).toBeNull();
  });

  it("draws a passed test as passed and a failed test as failed", () => {
    renderFourStates();
    expect(within(screen.getByTestId("rule-test-t-pass")).getByText(/passed/i)).toBeTruthy();
    expect(within(screen.getByTestId("rule-test-t-fail")).getByText(/failed/i)).toBeTruthy();
  });
});
