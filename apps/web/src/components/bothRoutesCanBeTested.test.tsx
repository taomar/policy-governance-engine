/**
 * Both routes can be tested, and neither answer is the lesser one.
 *
 * WHY THESE TESTS
 *
 * A rule states its test either as a comparison between named quantities,
 * which the engine computes, or in words, which a judge reads against a case.
 * The second route exists so that a rule stated in language can still be
 * decided. It is how most policy text arrives.
 *
 * The rule-scope tester served only the first route. For every rule on the
 * other route it disabled the scenario box and captioned its own button with a
 * refusal — under a paragraph that had already promised the reader a judge.
 * The copy described the route correctly and the controls refused it, which is
 * the worst of both: a reader is told a judge decides this rule and then given
 * no way to ask one.
 *
 * WHAT THESE PIN, AND WHY EACH WOULD OTHERWISE COME BACK
 *
 *  - A rule on either route can be put to a case. The route chooses which
 *    decider is asked, never whether asking is possible.
 *  - Which decider is asked is derived from the record. A caller cannot pass
 *    in a flag that sends a rule to the wrong one.
 *  - A read verdict carries three answers, not two. The third is the honest
 *    report that the case does not settle it, and it must survive as its own
 *    answer rather than collapsing into either of the others or into an error.
 *  - No verdict carries a number. A model asked for a probability supplies
 *    one, and `0.87` reads as measurement when it is invention. This is the
 *    same rule `contracts/correlation.py` states for findings, applied where
 *    the temptation is strongest — beside a computed answer, where a number
 *    would look like the judged answer apologising for itself.
 *  - Neither route's copy ranks the other. The interface presents two ways of
 *    deciding, not a real one and a hedge.
 *
 * Nothing here is a phrase from any document, and no number in it measures one.
 */
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { CanonicalRule } from "../api";

const testRuleScenario = vi.fn();
const evaluateScenario = vi.fn();

vi.mock("../api", async () => {
  const actual = await vi.importActual<typeof import("../api")>("../api");
  return {
    ...actual,
    aiApi: {
      ...actual.aiApi,
      testRuleScenario: (...args: unknown[]) => testRuleScenario(...args),
      evaluateScenario: (...args: unknown[]) => evaluateScenario(...args),
    },
  };
});

const { RuleScenarioTester } = await import("./RuleScenarioTester");

beforeAll(() => {
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  );
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  );
});

/**
 * Words that would rank one route below the other, in any copy this component
 * renders. Each is banned for what it asserts about the judged answer: that it
 * is not a test, not real, or not to be relied on.
 */
const RANKING = [
  /not testable/i,
  /guesswork/i,
  /real engine/i,
  /advisory only/i,
  /just an opinion/i,
  /less reliable/i,
  /weaker/i,
  /best guess/i,
];

beforeEach(() => {
  testRuleScenario.mockReset();
  evaluateScenario.mockReset();
});

afterEach(() => cleanup());

function rule(overrides: Partial<CanonicalRule> = {}): CanonicalRule {
  return {
    schema_version: "1.0",
    policy_set_id: "a-set-id",
    policy_version_id: "a-version-id",
    rule_id: "R-1",
    rule_revision: 1,
    title: "A title",
    description: "A description",
    rule_type: "obligation",
    authority: { owner: "an-owner", source: "", reference: "" },
    scope: { jurisdictions: [], organizational_units: [], processes: [] },
    condition: { type: "all", all: [] },
    evaluation_mode: "ai_ready",
    effect: { type: "require_action" },
    required_facts: [],
    exceptions: [],
    priority: 0,
    effective_from: "2024-01-01",
    effective_to: null,
    machine_executable: false,
    ambiguity_status: "clear",
    review_status: "published",
    evidence: [],
    ...overrides,
  } as CanonicalRule;
}

const readRule = () => rule();

const computedRule = () =>
  rule({
    rule_id: "R-2",
    evaluation_mode: "deterministic",
    machine_executable: true,
  });

function judgeAnswers(applies: "yes" | "no" | "uncertain") {
  return {
    applies,
    reasoning: "A sentence of reasoning about the case.",
    predicted_outcome: "What the rule would require here.",
    missing_facts: [],
    reasoning_effort: "low",
  };
}

function describeACase(text = "Someone did a thing on a day.") {
  const box = screen.getByRole("textbox");
  fireEvent.change(box, { target: { value: text } });
  return box;
}

function submit() {
  fireEvent.click(screen.getByTestId("scenario-run"));
}

describe("a rule on either route can be put to a case", () => {
  it("leaves the case box usable for a rule whose test is stated in words", () => {
    render(<RuleScenarioTester policySetKey="a-key" rule={readRule()} />);

    expect((screen.getByRole("textbox") as HTMLTextAreaElement).disabled).toBe(false);
    describeACase();
    expect((screen.getByTestId("scenario-run") as HTMLButtonElement).disabled).toBe(false);
  });

  it("puts that rule to the judge, and never to the engine", async () => {
    evaluateScenario.mockResolvedValue(judgeAnswers("yes"));
    render(<RuleScenarioTester policySetKey="a-key" rule={readRule()} />);

    describeACase();
    submit();

    await waitFor(() => expect(evaluateScenario).toHaveBeenCalledTimes(1));
    expect(testRuleScenario).not.toHaveBeenCalled();
  });

  it("puts a rule stating a comparison to the engine, and never to the judge", async () => {
    testRuleScenario.mockResolvedValue({
      rule_id: "R-2",
      rule_title: "A title",
      scenario: "",
      inferred_facts: {},
      assumptions: [],
      rule_result: null,
      not_in_effect: false,
      overall_evaluation_status: "SATISFIED",
      missing_facts: [],
      explanation: "An explanation.",
      reasoning_effort: "low",
      evaluation_timestamp: "2024-01-01T00:00:00Z",
      result_hash: "abcdef012345",
      machine_executable: true,
      testability_reason: null,
      dmn_mapping_statuses: [],
      formulation_requirements: [],
    });
    render(<RuleScenarioTester policySetKey="a-key" rule={computedRule()} />);

    describeACase();
    submit();

    await waitFor(() => expect(testRuleScenario).toHaveBeenCalledTimes(1));
    expect(evaluateScenario).not.toHaveBeenCalled();
  });

  it("chooses the decider from the record, so a rule cannot be sent to one that would refuse it", async () => {
    // A rule the engine short-circuits before it reads any case: the route says
    // one thing and the executable flag says another. The judge takes it.
    evaluateScenario.mockResolvedValue(judgeAnswers("no"));
    render(
      <RuleScenarioTester
        policySetKey="a-key"
        rule={rule({ evaluation_mode: "deterministic", machine_executable: false })}
      />,
    );

    describeACase();
    submit();

    await waitFor(() => expect(evaluateScenario).toHaveBeenCalledTimes(1));
    expect(testRuleScenario).not.toHaveBeenCalled();
  });

  it("offers no action until a case has been described, on either route", () => {
    const { unmount } = render(<RuleScenarioTester policySetKey="a-key" rule={readRule()} />);
    expect((screen.getByTestId("scenario-run") as HTMLButtonElement).disabled).toBe(true);
    unmount();

    render(<RuleScenarioTester policySetKey="a-key" rule={computedRule()} />);
    expect((screen.getByTestId("scenario-run") as HTMLButtonElement).disabled).toBe(true);
  });
});

describe("a read verdict is an answer, with three of them", () => {
  it("reports that the case does not settle it as its own verdict", async () => {
    evaluateScenario.mockResolvedValue(judgeAnswers("uncertain"));
    render(<RuleScenarioTester policySetKey="a-key" rule={readRule()} />);

    describeACase();
    submit();

    const verdict = await screen.findByTestId("scenario-verdict");
    expect(verdict.textContent).toBeTruthy();
    // Not an error, and not either of the other two answers.
    expect(screen.queryByRole("alert")?.textContent ?? "").not.toMatch(/verdict/i);
    expect(verdict.textContent).not.toMatch(/^(applies|does not apply)$/i);
  });

  it("gives the three verdicts three different renderings", async () => {
    const seen: string[] = [];
    for (const applies of ["yes", "no", "uncertain"] as const) {
      evaluateScenario.mockResolvedValue(judgeAnswers(applies));
      const view = render(<RuleScenarioTester policySetKey="a-key" rule={readRule()} />);
      describeACase();
      submit();
      seen.push((await screen.findByTestId("scenario-verdict")).textContent ?? "");
      view.unmount();
    }
    expect(new Set(seen).size).toBe(3);
  });

  it("puts no number on a verdict, on either route", async () => {
    evaluateScenario.mockResolvedValue(judgeAnswers("uncertain"));
    render(<RuleScenarioTester policySetKey="a-key" rule={readRule()} />);

    describeACase();
    submit();

    const verdict = await screen.findByTestId("scenario-verdict");
    const answer = screen.getByTestId("scenario-answer").textContent ?? "";
    expect(verdict.textContent ?? "").not.toMatch(/\d/);
    expect(answer).not.toMatch(/%/);
    expect(answer).not.toMatch(/\b0\.\d+\b/);
    expect(answer).not.toMatch(/\bconfidence\b[^.]*\d/i);
  });

  it("says how the answer was reached, on both routes and in the same place", async () => {
    evaluateScenario.mockResolvedValue(judgeAnswers("yes"));
    const view = render(<RuleScenarioTester policySetKey="a-key" rule={readRule()} />);
    describeACase();
    submit();
    const judged = (await screen.findByTestId("scenario-decided-by")).textContent ?? "";
    view.unmount();

    testRuleScenario.mockResolvedValue({
      rule_id: "R-2",
      rule_title: "A title",
      scenario: "",
      inferred_facts: {},
      assumptions: [],
      rule_result: { status: "SATISFIED", effect_action: null, effect_type: null },
      not_in_effect: false,
      overall_evaluation_status: "SATISFIED",
      missing_facts: [],
      explanation: "An explanation.",
      reasoning_effort: "low",
      evaluation_timestamp: "2024-01-01T00:00:00Z",
      result_hash: "abcdef012345",
      machine_executable: true,
      testability_reason: null,
      dmn_mapping_statuses: [],
      formulation_requirements: [],
    });
    render(<RuleScenarioTester policySetKey="a-key" rule={computedRule()} />);
    describeACase();
    submit();
    const computed = (await screen.findByTestId("scenario-decided-by")).textContent ?? "";

    expect(judged.trim()).not.toHaveLength(0);
    expect(computed.trim()).not.toHaveLength(0);
    expect(judged).not.toEqual(computed);
  });
});

describe("neither route is offered as the lesser one", () => {
  it("ranks nothing in what a reader is shown before running, on either route", () => {
    for (const subject of [readRule(), computedRule()]) {
      const view = render(<RuleScenarioTester policySetKey="a-key" rule={subject} />);
      const text = document.body.textContent ?? "";
      for (const banned of RANKING) expect(text).not.toMatch(banned);
      view.unmount();
    }
  });

  it("ranks nothing in a judged answer", async () => {
    evaluateScenario.mockResolvedValue(judgeAnswers("uncertain"));
    render(<RuleScenarioTester policySetKey="a-key" rule={readRule()} />);

    describeACase();
    submit();
    await screen.findByTestId("scenario-verdict");

    const text = document.body.textContent ?? "";
    for (const banned of RANKING) expect(text).not.toMatch(banned);
  });

  it("names the decider in the action, so a reader knows what they are asking", () => {
    const view = render(<RuleScenarioTester policySetKey="a-key" rule={readRule()} />);
    const judged = screen.getByTestId("scenario-run").textContent ?? "";
    view.unmount();

    render(<RuleScenarioTester policySetKey="a-key" rule={computedRule()} />);
    const computed = screen.getByTestId("scenario-run").textContent ?? "";

    expect(judged.trim()).not.toHaveLength(0);
    expect(computed.trim()).not.toHaveLength(0);
    expect(judged).not.toEqual(computed);
  });
});
