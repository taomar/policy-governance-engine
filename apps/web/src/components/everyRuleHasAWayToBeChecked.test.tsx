/**
 * Every rule of a policy has a way to be checked, on whichever route it takes.
 *
 * WHY THESE TESTS
 *
 * The Tests tab could ask for a scenario, and then ran it through the engine
 * that computes comparisons. That serves the rules stating a comparison. Every
 * other rule — the ordinary case, and on the live data the overwhelming
 * majority — reached a cell reading "Checked by reading" with nothing behind
 * it. The tab named how the rule is decided and then offered no way to decide
 * anything, which is the same dead end the tab was built to remove, moved one
 * column to the right.
 *
 * A rule whose test is stated in words is checked by putting a case to the
 * judge, and the judge is already built. These pin that every row offers a way
 * in, that the way in matches the rule's route, and the several ways this could
 * quietly go wrong:
 *
 *  - a judged check being folded into the saved-test states, which would report
 *    a coverage figure that no stored test supports;
 *  - the two routes being ranked against each other in the copy, so the
 *    ordinary route reads as the compromise;
 *  - a model call firing because a reviewer opened a tab.
 */
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { AssembledPolicy, CanonicalRule } from "../api";
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
 * Both fields are set on every fixture. Which decider answers a case is derived
 * from the pair, so a fixture that sets only one is a fixture whose route the
 * test did not actually choose.
 */
function rule(
  id: string,
  title: string,
  mode: "deterministic" | "ai_ready",
  machineExecutable: boolean,
): CanonicalRule {
  return {
    rule_id: id,
    title,
    effect: "allow",
    evaluation_mode: mode,
    machine_executable: machineExecutable,
    condition: { type: "all", all: [] },
    obligations: [],
    exceptions: [],
    scope: {},
    source: { document_id: "d", quotes: [] },
    lineage: { extraction_run_id: "r" },
  } as unknown as CanonicalRule;
}

const readRule = (id = "R-read") => rule(id, "A rule stating its test in words", "ai_ready", false);
const computedRule = (id = "R-engine") =>
  rule(id, "A rule stating a comparison", "deterministic", true);

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

function verbs(overrides: Partial<PolicyTestingVerbs> = {}): PolicyTestingVerbs {
  return {
    generate: vi.fn().mockResolvedValue(undefined),
    run: vi.fn().mockResolvedValue(undefined),
    busy: new Set<string>(),
    working: false,
    error: null,
    dismissError: vi.fn(),
    ...overrides,
  } as PolicyTestingVerbs;
}

/**
 * Wordings that would put one route below the other. Ranking is the failure
 * this project keeps producing under pressure, so it is checked as vocabulary
 * rather than left to a reviewer noticing.
 */
const RANKING = [
  /not testable/i,
  /untestable/i,
  /cannot be tested/i,
  /can't be tested/i,
  /no way to test/i,
  /real engine/i,
  /guesswork/i,
  /advisory only/i,
  /less reliable/i,
  /weaker/i,
  /best guess/i,
  /just an opinion/i,
];

describe("a rule of either route can be checked from the policy", () => {
  it("offers a way in for a rule whose test is stated in words", () => {
    render(
      <PolicyTestsPane
        record={record([readRule()])}
        tests={[]}
        testing={verbs()}
        policySetKey="a-key"
      />,
    );

    expect(screen.getByTestId("put-case-R-read")).toBeTruthy();
  });

  it("leaves no rule of the policy without an action", () => {
    render(
      <PolicyTestsPane
        record={record([readRule(), computedRule()])}
        tests={[]}
        testing={verbs()}
        policySetKey="a-key"
      />,
    );

    expect(screen.getByTestId("put-case-R-read")).toBeTruthy();
    expect(screen.getByTestId("generate-rule-test-R-engine")).toBeTruthy();
  });

  it("names a different action for each route, so a reader knows what they are asking", () => {
    render(
      <PolicyTestsPane
        record={record([readRule(), computedRule()])}
        tests={[]}
        testing={verbs()}
        policySetKey="a-key"
      />,
    );

    const judged = screen.getByTestId("put-case-R-read").textContent ?? "";
    const computed = screen.getByTestId("generate-rule-test-R-engine").textContent ?? "";
    expect(judged.trim()).not.toBe("");
    expect(computed.trim()).not.toBe("");
    expect(judged).not.toBe(computed);
  });

  it("sends a rule whose route and condition disagree to the judge, not the engine", () => {
    // The engine short-circuits a rule it cannot execute before it reads the
    // case, so offering to write an engine scenario here would be offering a
    // refusal. The decider is derived from both fields for exactly this row.
    render(
      <PolicyTestsPane
        record={record([rule("R-mixed", "A rule the engine would refuse", "deterministic", false)])}
        tests={[]}
        testing={verbs()}
        policySetKey="a-key"
      />,
    );

    expect(screen.getByTestId("put-case-R-mixed")).toBeTruthy();
    expect(screen.queryByTestId("generate-rule-test-R-mixed")).toBeNull();
  });

  it("opens the case box only when asked, and puts nothing to any decider on open", () => {
    const v = verbs();
    render(
      <PolicyTestsPane
        record={record([readRule()])}
        tests={[]}
        testing={v}
        policySetKey="a-key"
      />,
    );

    expect(v.generate).not.toHaveBeenCalled();
    expect(v.run).not.toHaveBeenCalled();
    expect(screen.queryByTestId("policy-case-box")).toBeNull();

    fireEvent.click(screen.getByTestId("put-case-R-read"));
    expect(screen.getByTestId("policy-case-box")).toBeTruthy();
  });
});

describe("a judged check is not counted as a stored test", () => {
  it("still reports a rule with no stored test as having none", () => {
    render(
      <PolicyTestsPane
        record={record([readRule()])}
        tests={[]}
        testing={verbs()}
        policySetKey="a-key"
      />,
    );

    // Opening the case box changes nothing about coverage: no test has been
    // stored, and a verdict read here is exploratory.
    fireEvent.click(screen.getByTestId("put-case-R-read"));
    const body = document.body.textContent ?? "";
    expect(body).toMatch(/No test/i);
    expect(body).not.toMatch(/\bPassing\b/);
  });

  it("says a case put here is not kept", () => {
    render(
      <PolicyTestsPane
        record={record([readRule()])}
        tests={[]}
        testing={verbs()}
        policySetKey="a-key"
      />,
    );

    fireEvent.click(screen.getByTestId("put-case-R-read"));
    expect(screen.getByTestId("policy-case-box").textContent ?? "").toMatch(/not saved/i);
  });

  it("says that before any model time is spent, not after", () => {
    render(
      <PolicyTestsPane
        record={record([readRule()])}
        tests={[]}
        testing={verbs()}
        policySetKey="a-key"
      />,
    );

    fireEvent.click(screen.getByTestId("put-case-R-read"));
    // Nothing has been put to the judge yet — no case has even been typed —
    // and the reviewer already knows what will become of the answer.
    expect(screen.queryByTestId("scenario-verdict")).toBeNull();
    expect(screen.getByTestId("policy-case-box").textContent ?? "").toMatch(/not saved/i);
  });
});

describe("neither route is offered as the lesser one", () => {
  it("carries no deficiency word beside a route name, in copy or in comment", () => {
    // The guard that scans for this is sentence-scoped and build-failing, and
    // it caught the first draft of this pane's own prop comment: "Absent, the
    // case box still opens for the rules decided by reading". Nothing was
    // wrong with the behaviour; the sentence put a lack word next to a route
    // and left a reader carrying the lack. This keeps the check inside the
    // suite that owns the pane, so a later tidy-up meets it here first.
    const SHORTFALL = /\b(absent|missing|lacks?|lacking|gap|incomplete|insufficient|unsupported|unable|cannot|can't)\b/i;
    const ROUTE = /(decided by reading|ai[-_ ]?ready|judge reads|put a case to the judge)/i;

    render(
      <PolicyTestsPane
        record={record([readRule(), computedRule()])}
        tests={[]}
        testing={verbs()}
        policySetKey="a-key"
      />,
    );
    fireEvent.click(screen.getByTestId("put-case-R-read"));

    const body = document.body.textContent ?? "";
    for (const sentence of body.split(/(?<=[.!?…])\s+/)) {
      if (ROUTE.test(sentence)) expect(sentence).not.toMatch(SHORTFALL);
    }
  });

  it("ranks nothing in the pane, whichever routes the policy's rules take", () => {
    render(
      <PolicyTestsPane
        record={record([readRule(), computedRule()])}
        tests={[]}
        testing={verbs()}
        policySetKey="a-key"
      />,
    );

    const body = document.body.textContent ?? "";
    for (const banned of RANKING) expect(body).not.toMatch(banned);
  });

  it("ranks nothing once the case box is open", () => {
    render(
      <PolicyTestsPane
        record={record([readRule()])}
        tests={[]}
        testing={verbs()}
        policySetKey="a-key"
      />,
    );

    fireEvent.click(screen.getByTestId("put-case-R-read"));
    const body = document.body.textContent ?? "";
    for (const banned of RANKING) expect(body).not.toMatch(banned);
  });

  it("does not offer the judged route only where the engine has already declined", () => {
    // A policy of one judged rule is the ordinary case, not a degenerate one.
    // The way in must be there without an engine rule beside it to explain it.
    render(
      <PolicyTestsPane
        record={record([readRule()])}
        tests={[]}
        testing={verbs()}
        policySetKey="a-key"
      />,
    );

    expect(screen.getByTestId("put-case-R-read")).toBeTruthy();
  });
});
