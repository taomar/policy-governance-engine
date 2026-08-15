/**
 * The Tests tab can ask for a test, and says what it is asking for.
 *
 * WHY THESE TESTS
 *
 * The tab reported, correctly, that nothing covered any rule — and then gave
 * the reviewer no way to change that. A tab that names an absence it cannot
 * fill turns a missing feature into what reads like a permanent fact about the
 * document. These pin the way out, and the several ways it could go wrong
 * quietly:
 *
 *  - firing a paid model call on tab open, which is money spent by navigation;
 *  - a freshly written test rendering as passing, which is the false assurance
 *    the four states exist to prevent;
 *  - a refusal collapsing into "something went wrong", which leaves a reviewer
 *    unable to tell whether to retry, reword, or call someone;
 *  - the fact that a scenario was written by this app being lost, which would
 *    let a proposal read as an established check.
 */
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { AssembledPolicy, CanonicalRule, PolicyTest, PolicyTestListItem, PolicyTestRun } from "../api";
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

/**
 * `evaluation_mode` is explicit on every fixture rather than defaulted, because
 * it is what decides whether this pane offers to write a scenario at all. A
 * fixture that leaves it out is a fixture whose route this test did not choose,
 * and the pane would then be exercised on a route by accident.
 */
function rule(id: string, title: string, mode: "deterministic" | "ai_ready" = "deterministic"): CanonicalRule {
  return {
    rule_id: id,
    title,
    effect: "allow",
    evaluation_mode: mode,
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
      name: "n",
      ...overrides,
    } as unknown as PolicyTest,
    latest_run: latest,
    runs: latest ? [latest] : [],
  };
}

function verbs(overrides: Partial<PolicyTestingVerbs> = {}): PolicyTestingVerbs {
  return {
    generate: vi.fn().mockResolvedValue(undefined),
    run: vi.fn().mockResolvedValue(undefined),
    busy: new Set<string>(),
    working: false,
    error: null,
    dismissError: vi.fn(),
    ...overrides,
  };
}

/** Click through antd's Popconfirm, which puts the real confirmation in a popup. */
async function confirm(trigger: HTMLElement) {
  fireEvent.click(trigger);
  const ok = await screen.findByRole("button", { name: /Write them|Run them/ });
  fireEvent.click(ok);
}

describe("the Tests tab offers a way to be tested", () => {
  it("does not spend model time merely by being opened", () => {
    const t = verbs();
    render(<PolicyTestsPane record={record([rule("a", "One")])} tests={[]} testing={t} />);
    // Rendering is navigation. Nothing paid-for may happen because a reviewer
    // looked at a tab.
    expect(t.generate).not.toHaveBeenCalled();
    expect(t.run).not.toHaveBeenCalled();
  });

  it("asks for scenarios for exactly the rules that have none", async () => {
    const t = verbs();
    render(
      <PolicyTestsPane
        record={record([rule("covered", "Has one"), rule("bare", "Has none")])}
        tests={[testItem("t1", "covered")]}
        testing={t}
      />,
    );
    await confirm(screen.getByTestId("policy-generate-tests"));
    await waitFor(() => expect(t.generate).toHaveBeenCalled());
    // The rule that already has a test is not paid for again.
    expect((t.generate as ReturnType<typeof vi.fn>).mock.calls[0][0]).toEqual(["bare"]);
  });

  it("warns that writing scenarios costs model time before it does it", async () => {
    const t = verbs();
    render(<PolicyTestsPane record={record([rule("a", "One")])} tests={[]} testing={t} />);
    fireEvent.click(screen.getByTestId("policy-generate-tests"));
    const warning = await screen.findByText(/costs model usage/);
    expect(warning).toBeTruthy();
    // Still not called: the reviewer has been told, and has not yet agreed.
    expect(t.generate).not.toHaveBeenCalled();
  });

  it("runs only the tests covering the rule whose Run was clicked", async () => {
    const t = verbs();
    render(
      <PolicyTestsPane
        record={record([rule("a", "One"), rule("b", "Two")])}
        tests={[testItem("t-a", "a"), testItem("t-b1", "b"), testItem("t-b2", "b")]}
        testing={t}
      />,
    );
    fireEvent.click(screen.getByTestId("run-rule-tests-b"));
    await waitFor(() => expect(t.run).toHaveBeenCalledWith(["t-b1", "t-b2"]));
  });

  it("offers nothing to click when it has no verbs, rather than a control that does nothing", () => {
    render(<PolicyTestsPane record={record([rule("a", "One")])} tests={[]} />);
    expect(screen.queryByTestId("policy-test-actions")).toBeNull();
    expect(screen.queryByTestId("policy-generate-tests")).toBeNull();
  });
});

describe("a written scenario does not pass by being written", () => {
  it("reads as not yet run, never as passing or failing", () => {
    render(
      <PolicyTestsPane
        record={record([rule("a", "One")])}
        tests={[testItem("t", "a", { review_status: "pending_review", proposed_by: "ai", is_active: false })]}
        testing={verbs()}
      />,
    );
    expect(screen.getByText("Not yet run")).toBeTruthy();
    expect(screen.queryByText("Passing")).toBeNull();
    expect(screen.queryByText("Failing")).toBeNull();
  });

  it("says on the row that this app wrote it and nobody has accepted it", () => {
    render(
      <PolicyTestsPane
        record={record([rule("a", "One")])}
        tests={[testItem("t", "a", { review_status: "pending_review", proposed_by: "ai", is_active: false })]}
        testing={verbs()}
      />,
    );
    expect(screen.getByText(/Written by this app/)).toBeTruthy();
    expect(screen.getByTestId("policy-tests-awaiting-review")).toBeTruthy();
  });

  it("does not claim authorship of a test a person wrote", () => {
    render(
      <PolicyTestsPane
        record={record([rule("a", "One")])}
        tests={[testItem("t", "a")]}
        testing={verbs()}
      />,
    );
    expect(screen.queryByText(/Written by this app/)).toBeNull();
    expect(screen.queryByTestId("policy-tests-awaiting-review")).toBeNull();
  });
});

describe("a refusal reaches the reviewer in the server's own words", () => {
  it("shows the specific reason rather than that something went wrong", () => {
    const reason = "Expected 1 scenario for rule 'x' but the model returned 0.";
    render(
      <PolicyTestsPane
        record={record([rule("a", "One")])}
        tests={[]}
        testing={verbs({ error: reason })}
      />,
    );
    expect(screen.getByTestId("policy-test-error").textContent).toContain(reason);
  });

  it("says nothing at all when nothing was refused", () => {
    render(<PolicyTestsPane record={record([rule("a", "One")])} tests={[]} testing={verbs()} />);
    expect(screen.queryByTestId("policy-test-error")).toBeNull();
  });
});

/**
 * FOUND BY RUNNING IT, NOT BY READING IT.
 *
 * The generate control was offered on every rule, and the server refused for a
 * rule decided by reading with: "blind validation runs against the deterministic
 * engine; these selected rules are decided by reading, so the engine does not
 * run them". The refusal is accurate and well worded. The interaction that
 * provoked it was not.
 *
 * Offering an action on every rule and letting it fail on one of the two routes
 * teaches a reviewer that that route is the lesser one — the exact claim the
 * copy guards keep out of the words, arriving instead through what the buttons
 * do. So the offer is derived from the rule's own route, and what is true of a
 * rule decided by reading is stated positively: it is checked the way it is
 * decided.
 */
describe("the offer follows the route the rule takes", () => {
  it("offers to write a scenario for a rule the engine evaluates", () => {
    render(
      <PolicyTestsPane
        record={record([rule("a", "One", "deterministic")])}
        tests={[]}
        testing={verbs()}
      />,
    );
    expect(screen.getByTestId("generate-rule-test-a")).toBeTruthy();
    expect(screen.queryByTestId("read-decided-a")).toBeNull();
  });

  it("says how a rule decided by reading is checked, instead of offering it an engine scenario", () => {
    render(
      <PolicyTestsPane
        record={record([rule("a", "One", "ai_ready")])}
        tests={[]}
        testing={verbs()}
      />,
    );
    expect(screen.queryByTestId("generate-rule-test-a")).toBeNull();
    expect(screen.getByTestId("read-decided-a").textContent).toBe("Checked by reading");
  });

  it("writes only for the rules the engine evaluates when the policy holds both routes", async () => {
    const generate = vi.fn().mockResolvedValue(undefined);
    render(
      <PolicyTestsPane
        record={record([rule("a", "One", "deterministic"), rule("b", "Two", "ai_ready")])}
        tests={[]}
        testing={verbs({ generate })}
      />,
    );
    fireEvent.click(screen.getByTestId("policy-generate-tests"));
    fireEvent.click(await screen.findByRole("button", { name: /Write them/ }));
    await waitFor(() => expect(generate).toHaveBeenCalled());
    // Sending the read-decided rule too is what earned the refusal.
    expect(generate.mock.calls[0][0]).toEqual(["a"]);
  });

  it("offers no scenario control at all when the engine evaluates none of them", () => {
    render(
      <PolicyTestsPane
        record={record([rule("a", "One", "ai_ready"), rule("b", "Two", "ai_ready")])}
        tests={[]}
        testing={verbs()}
      />,
    );
    expect(screen.queryByTestId("policy-generate-tests")).toBeNull();
  });

  it("explains which instrument runs what, without naming a shortfall", () => {
    render(
      <PolicyTestsPane
        record={record([rule("a", "One", "deterministic"), rule("b", "Two", "ai_ready")])}
        tests={[]}
        testing={verbs()}
      />,
    );
    const said = screen.getByTestId("policy-tests-instrument").textContent ?? "";
    expect(said).toMatch(/run by the engine that computes comparisons/);
    expect(said).toMatch(/states its test in words/);
    // A denial still names the thing it denies, so there is nothing to negate.
    expect(said).not.toMatch(/\b(not|no|cannot|can't|without|missing|lacks?|unsupported)\b/i);
  });

  it("says the same sentence whatever the mix, so no count of the day is written into it", () => {
    // This began as a sentence carrying a share, which read "every rule of this
    // policy state their test in words" the first time a real policy took one
    // route — ungrammatical, and a number in a sentence whose job is to explain
    // an instrument rather than to count. The split is in the table, row by row.
    const said = (rules: CanonicalRule[]) => {
      cleanup();
      render(<PolicyTestsPane record={record(rules)} tests={[]} testing={verbs()} />);
      return screen.getByTestId("policy-tests-instrument").textContent ?? "";
    };
    const allReading = said([rule("a", "One", "ai_ready"), rule("b", "Two", "ai_ready")]);
    const mixed = said([rule("a", "One", "deterministic"), rule("b", "Two", "ai_ready")]);
    expect(allReading).toBe(mixed);
    expect(allReading).not.toMatch(/\d/);
  });

  it("says nothing about instruments when every rule takes the one route", () => {
    render(
      <PolicyTestsPane
        record={record([rule("a", "One", "deterministic")])}
        tests={[]}
        testing={verbs()}
      />,
    );
    expect(screen.queryByTestId("policy-tests-instrument")).toBeNull();
  });
});
