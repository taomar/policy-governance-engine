/**
 * THE TESTS THAT RUN READ APART FROM THE DRAFTS THAT DO NOT.
 *
 * WHY THIS TEST
 *
 * A reviewer asked to see "the tests that run". In this product that phrase is
 * exact: `is_active = true` makes a test a GUARD — the server re-runs it on
 * every publish. A `pending_review` AI draft has no teeth: nothing runs it and
 * it protects nothing until a human accepts it. Two populations, different in
 * kind.
 *
 * The Tests table drew neither the distinction nor its consequence:
 *   1. `is_active` was on every row's items and never rendered — a reviewer
 *      could not tell which test would run on the next publish. Same shape as
 *      the count that stood in for its own content: the fact was in hand and
 *      simply never drawn.
 *   2. The rule-level "Last run" tag pooled every covering test's run and then
 *      dropped the ones that had not run — so a rule whose only run evidence was
 *      two toothless drafts that passed read "Passing" in green, while the
 *      active guard, the thing that actually runs on publish, had never run. A
 *      draft's pass standing in for a guard's unrun state is a constraint-5
 *      collapse: "ran and passed" and "never run" flattened into one word.
 *
 * The fixture mirrors the real policy set `e2e-trace-leave`: one rule, one
 * active human guard that has never run, two `pending_review` AI drafts that
 * passed. Domain-neutral strings throughout; nothing here names a document.
 *
 * The teeth wording is reused verbatim from the validation lab
 * (`PolicyValidationLab.tsx`, the "Regression suite" field) so the two surfaces
 * cannot drift into two accounts of the same fact.
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
import {
  PolicyTestsPane,
  policyTestRows,
  type PolicyRecordView,
  type PolicyTestingVerbs,
} from "./policyTabPanes";

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
    id: `run-${status}-${Math.random()}`,
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

// The real policy set `e2e-trace-leave`, in the shape the row is built from:
// one rule, one active human guard never run, two pending_review AI drafts that
// passed. GUARD is is_active; the DRAFTS are not.
const GUARD_ID = "t-guard";
const DRAFT_A_ID = "t-draft-a";
const DRAFT_B_ID = "t-draft-b";

function mixedRecord() {
  return record([rule("covered", "A rule with a guard and two drafts")]);
}

function mixedTests(): PolicyTestListItem[] {
  return [
    testItem(
      GUARD_ID,
      "covered",
      {
        name: "The active guard",
        review_status: "active",
        proposed_by: "human",
        is_active: true,
        scenario_text: "A described boundary the guard holds the rule to",
        expected_overall_status: "NOT_SATISFIED",
      },
      null, // never run — this is the protection, and it is unverified
    ),
    testItem(
      DRAFT_A_ID,
      "covered",
      {
        name: "A drafted case A",
        review_status: "pending_review",
        proposed_by: "ai",
        is_active: false,
        scenario_text: "A described situation this app proposed",
        expected_overall_status: "SATISFIED",
      },
      run("pass", { explanation: "It matched." }),
    ),
    testItem(
      DRAFT_B_ID,
      "covered",
      {
        name: "A drafted case B",
        review_status: "pending_review",
        proposed_by: "ai",
        is_active: false,
        scenario_text: "Another described situation this app proposed",
        expected_overall_status: "SATISFIED",
      },
      run("pass", { explanation: "It matched too." }),
    ),
  ];
}

describe("a draft's pass does not stand in for an unrun guard", () => {
  it("does not read the rule as passing when its active guard has never run, though drafts passed", () => {
    const rows = policyTestRows(mixedRecord(), mixedTests());
    const covered = rows.find((r) => r.ruleId === "covered");
    // The two drafts passed, but they run nothing on publish. The one test that
    // does — the active guard — has never run, so the rule is not verified.
    expect(covered?.state).not.toBe("passing");
    expect(covered?.state).toBe("unverified");
  });

  it("still reads passing on the strength of an active guard that ran, not a draft", () => {
    // Control that the fix does not simply refuse to pass: an active guard that
    // ran and passed carries the rule, even beside an unrun draft.
    const rows = policyTestRows(mixedRecord(), [
      testItem(
        GUARD_ID,
        "covered",
        { is_active: true, review_status: "active" },
        run("pass"),
      ),
      testItem(
        DRAFT_A_ID,
        "covered",
        { is_active: false, review_status: "pending_review", proposed_by: "ai" },
        null,
      ),
    ]);
    expect(rows.find((r) => r.ruleId === "covered")?.state).toBe("passing");
  });
});

describe("which tests run on the next publish is legible from the table", () => {
  function renderMixed() {
    render(<PolicyTestsPane record={mixedRecord()} tests={mixedTests()} testing={verbs()} />);
  }

  it("names the active guard as the test that re-runs on every publish", () => {
    renderMixed();
    const guard = screen.getByTestId(`rule-test-${GUARD_ID}`);
    // The teeth axis, drawn from is_active, in the lab's own words.
    expect(within(guard).getByText(/re-runs on every future publish/i)).toBeTruthy();
  });

  it("names a draft as one that runs only when requested, not on publish", () => {
    renderMixed();
    const draft = screen.getByTestId(`rule-test-${DRAFT_A_ID}`);
    expect(within(draft).getByText(/only runs when requested/i)).toBeTruthy();
    // And a draft is never labelled as a guard that runs on publish.
    expect(within(draft).queryByText(/re-runs on every future publish/i)).toBeNull();
  });

  it("puts the distinction on the page itself, not behind a modal", () => {
    renderMixed();
    // The teeth axis is readable in the default-open detail, with no dialog to
    // open to discover what would run — constraint 6.
    expect(screen.getByText(/re-runs on every future publish/i)).toBeTruthy();
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("does not let the rule-level tag read Passing while the guard is unrun", () => {
    renderMixed();
    // The green a reviewer would trust is not printed: the protection is unrun.
    expect(screen.queryByText("Passing")).toBeNull();
    expect(screen.getByText("Not yet run")).toBeTruthy();
  });
});

describe("the guard's never-run state is not flattened into the drafts' passes", () => {
  function renderMixed() {
    render(<PolicyTestsPane record={mixedRecord()} tests={mixedTests()} testing={verbs()} />);
  }

  it("draws the guard as not run and the drafts as passed, each in its own detail", () => {
    renderMixed();
    const guard = screen.getByTestId(`rule-test-${GUARD_ID}`);
    // The guard: never run, and never drawn as a pass.
    expect(within(guard).getAllByText(/not run|nothing is known/i).length).toBeGreaterThan(0);
    expect(
      within(guard).queryByText(/passed/i),
      "the active guard has never run and must not be drawn as one that passed",
    ).toBeNull();
    // The drafts: their runs are real and shown, but as drafts, not as the
    // rule's verification.
    expect(within(screen.getByTestId(`rule-test-${DRAFT_A_ID}`)).getByText(/passed/i)).toBeTruthy();
    expect(within(screen.getByTestId(`rule-test-${DRAFT_B_ID}`)).getByText(/passed/i)).toBeTruthy();
  });
});
