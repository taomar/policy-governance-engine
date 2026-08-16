/**
 * One case, one answer from a policy — and the answer told apart from a verdict.
 *
 * WHY THESE TESTS
 *
 * A case put to a policy used to come back as a row per rule, most of them
 * saying the case did not settle them, with the one row that answered the
 * question buried among the ones that could not. Worse, a question that only
 * asked what the policy *provides* was run as a determination: the rule that
 * states the answer was reported unsettled because, read as a determination, it
 * wanted the very quantity being asked about as an input.
 *
 * So a case is now classified before it is answered, and the answer is given at
 * the policy level over the rules it rests on, with the per-rule detail kept
 * beneath it rather than in place of it. These pin the two halves of that:
 *
 *  - An informational request is answered from the rules that state the answer,
 *    in the app's own words marked as the app's, quoting each rule verbatim, and
 *    never fanned out to the per-rule deciders — so a rule with an unmet required
 *    fact is reported by what it states, not by a demand for the fact.
 *  - A determination is read at the policy level: it leads with the rules that
 *    settle the case and names them, says plainly when those rules do not all
 *    point the same way, keeps every rule reachable below, and — this is the
 *    behaviour the deterministic route must not lose — still demands an unmet
 *    required fact rule by rule.
 *  - The four informational states are kept apart, and a classification that did
 *    not arrive falls closed to the determination path without reading as an
 *    error.
 *
 * The intent itself is decided by the model, on the backend, and the test with
 * teeth against a phrase list lives there
 * (`tests/unit/test_case_intent_is_read_from_the_question.py`): it classifies
 * questions of equal meaning and different words and fails if a vocabulary is
 * ever introduced. Nothing here names any real policy: the defect that prompted
 * this is a regression witness, never a fixture.
 */
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { CanonicalRule } from "../api";

const testRuleScenario = vi.fn();
const computeScenario = vi.fn();
const evaluateScenario = vi.fn();
const ruleNames = vi.fn();
const answerPolicyCase = vi.fn();

vi.mock("../api", async () => {
  const actual = await vi.importActual<typeof import("../api")>("../api");
  return {
    ...actual,
    aiApi: {
      ...actual.aiApi,
      testRuleScenario: (...args: unknown[]) => testRuleScenario(...args),
      computeScenario: (...args: unknown[]) => computeScenario(...args),
      evaluateScenario: (...args: unknown[]) => evaluateScenario(...args),
      // Held so the generated rule-name handle never reaches the network in a
      // test: it resolves to nothing, and `RuleName` renders nothing, which is
      // exactly what a rule with no generated name should do.
      ruleNames: (...args: unknown[]) => ruleNames(...args),
    },
  };
});

vi.mock("./policyCaseIntent", async () => {
  const actual = await vi.importActual<typeof import("./policyCaseIntent")>("./policyCaseIntent");
  return {
    ...actual,
    answerPolicyCase: (...args: unknown[]) => answerPolicyCase(...args),
  };
});

const { PolicyCaseRunner } = await import("./PolicyCaseRunner");
const { testTarget, DRAFT_TARGET } = await import("./policyTesting");

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

beforeEach(() => {
  cleanup();
  testRuleScenario.mockReset();
  computeScenario.mockReset();
  evaluateScenario.mockReset();
  answerPolicyCase.mockReset();
  ruleNames.mockReset();
  ruleNames.mockResolvedValue({ names: {}, names_by_rule_id: {} });
});

const A_VERSION = testTarget("a-published-version", 3);

/** A rule as the surface holds it. Which decider it calls for is derived from
 *  the pair of `evaluation_mode` and `machine_executable`, so both are set. */
function rule(id: string, title: string, mode: "deterministic" | "ai_ready"): CanonicalRule {
  return {
    rule_id: id,
    title,
    effect: "allow",
    evaluation_mode: mode,
    machine_executable: mode === "deterministic",
    condition: { type: "all", all: [] },
    obligations: [],
    exceptions: [],
    scope: {},
    source: { document_id: "d", quotes: [] },
    lineage: { extraction_run_id: "r" },
  } as unknown as CanonicalRule;
}

function type(scenario: string): void {
  fireEvent.change(screen.getByTestId("policy-case-scenario"), { target: { value: scenario } });
  fireEvent.click(screen.getByTestId("policy-case-run"));
}

describe("an informational request is answered from the rules that state it", () => {
  it("marks the answer as the app's, quotes each rule verbatim, and keeps every rule reachable", async () => {
    answerPolicyCase.mockResolvedValue({
      intent: "informational",
      classification_reasoning: "reads as a request for what the policy provides",
      reasoning_effort: "low",
      informational: {
        status: "answered",
        answer: "This policy sets a weekly ceiling for the class of employee asked about.",
        citations: [
          { rule_id: "cap", title: "The weekly ceiling", quote: "not more than 24 hrs per week" },
        ],
        note: "",
      },
    });

    render(
      <PolicyCaseRunner
        policySetKey="a-key"
        target={A_VERSION}
        rules={[
          rule("cap", "The weekly ceiling", "deterministic"),
          rule("x", "A second rule", "ai_ready"),
          rule("y", "A third rule", "ai_ready"),
        ]}
      />,
    );

    type("How many hours may this kind of employee work?");

    await waitFor(() => expect(screen.getByTestId("policy-case-answer")).toBeTruthy());

    // The synthesised answer is ours: carried in the marked-as-generated block,
    // named as composed by this app, never dressed as the document's words.
    const answer = screen.getByTestId("policy-case-answer-text");
    expect(answer.getAttribute("data-generated")).toBe("true");
    expect(answer.textContent ?? "").toMatch(/composed by this app/i);
    expect(answer.textContent ?? "").toContain(
      "This policy sets a weekly ceiling for the class of employee asked about.",
    );

    // The rule it rests on is cited, with the document's own sentence verbatim.
    const citation = screen.getByTestId("policy-case-citation");
    expect(citation.textContent ?? "").toContain("not more than 24 hrs per week");

    // Every rule of the policy stays reachable, and it says how many were read.
    const allRules = screen.getByTestId("policy-case-all-rules");
    expect(allRules.textContent ?? "").toMatch(/All 3 rules of this policy were read/i);
    expect(allRules.textContent ?? "").toContain("A second rule");
    expect(allRules.textContent ?? "").toContain("A third rule");
  });

  it("never fans an informational request out to the per-rule deciders, so an unmet required fact is reported by what the rule states, not demanded", async () => {
    // The acceptance behaviour, from the client's side: because the case is
    // classified informational, it is answered by gathering what the rules
    // state and is never run through `putCaseToRule`. So no rule can come back
    // "the case would have to state X" — the demand that turned this question's
    // own answer into a missing input. The stated content is shown instead.
    answerPolicyCase.mockResolvedValue({
      intent: "informational",
      classification_reasoning: "asks what the policy provides",
      reasoning_effort: "low",
      informational: {
        status: "answered",
        answer: "The ceiling is stated directly by the rule below.",
        citations: [
          { rule_id: "cap", title: "The weekly ceiling", quote: "not more than 24 hrs per week" },
        ],
        note: "",
      },
    });

    render(
      <PolicyCaseRunner
        policySetKey="a-key"
        target={A_VERSION}
        rules={[rule("cap", "The weekly ceiling", "deterministic")]}
      />,
    );

    type("How many hours may this kind of employee work?");
    await waitFor(() => expect(screen.getByTestId("policy-case-answer")).toBeTruthy());

    expect(evaluateScenario).not.toHaveBeenCalled();
    expect(computeScenario).not.toHaveBeenCalled();
    expect(testRuleScenario).not.toHaveBeenCalled();
    expect(document.body.textContent ?? "").not.toMatch(/would have to state/i);
    // The determination surface is not drawn for an informational answer.
    expect(screen.queryByTestId("policy-case-rollup")).toBeNull();
  });

  it("keeps the four informational states apart, each still listing every rule", async () => {
    const cases = [
      { status: "no_rule_bears", headline: /No rule in this policy bears on your question/i },
      { status: "declined", headline: /No answer was composed/i },
      { status: "failed", headline: /answer could not be composed/i },
    ] as const;

    for (const { status, headline } of cases) {
      cleanup();
      answerPolicyCase.mockResolvedValue({
        intent: "informational",
        classification_reasoning: "reads as a request for what the policy provides",
        reasoning_effort: "low",
        informational: { status, answer: "", citations: [], note: "" },
      });

      render(
        <PolicyCaseRunner
          policySetKey="a-key"
          target={A_VERSION}
          rules={[rule("a", "A rule", "ai_ready"), rule("b", "Another rule", "deterministic")]}
        />,
      );

      type("A described question");
      await waitFor(() => expect(screen.getByTestId("policy-case-answer")).toBeTruthy());

      expect(document.body.textContent ?? "").toMatch(headline);
      // No state but `answered` carries a synthesised answer, so the marked-ours
      // block is absent for the other three — none is dressed as an answer.
      expect(screen.queryByTestId("policy-case-answer-text")).toBeNull();
      // Rules stay reachable in every state, so "we could not answer" never
      // reads as "there is nothing to read".
      expect(screen.getByTestId("policy-case-all-rules")).toBeTruthy();
    }
  });
});

describe("a determination is read at the policy level, over the rules it rests on", () => {
  it("leads with the rules that settle the case, names them, and keeps every rule reachable below", async () => {
    answerPolicyCase.mockResolvedValue({
      intent: "decision",
      classification_reasoning: "describes a situation for a determination",
      reasoning_effort: "low",
      informational: null,
    });
    evaluateScenario.mockResolvedValue({
      applies: "yes",
      reasoning: "An account of why",
      predicted_outcome: "",
      missing_facts: [],
      reasoning_effort: "low",
    });
    testRuleScenario.mockResolvedValue({
      rule_id: "cap",
      rule_result: { status: "SATISFIED" },
      inferred_facts: {},
      assumptions: [],
      missing_facts: [],
      explanation: "An account of why",
      reasoning_effort: "low",
    });

    render(
      <PolicyCaseRunner
        policySetKey="a-key"
        target={A_VERSION}
        rules={[
          rule("applies", "A rule stated in words", "ai_ready"),
          rule("cap", "A computed rule", "deterministic"),
        ]}
      />,
    );

    type("Someone in this situation asks whether they may proceed");
    await waitFor(() => expect(screen.getByTestId("policy-case-rollup")).toBeTruthy());

    const text = document.body.textContent ?? "";
    expect(text).toMatch(/settle this case/i);
    // The rules the answer rests on are named by their own titles.
    expect(text).toContain("A rule stated in words");
    expect(text).toContain("A computed rule");
    // The per-rule detail stays beneath the reading — the "Decided by" column of
    // the table is proof every rule remains reachable, not reduced away.
    expect(text).toMatch(/Decided by/i);
    // Nothing is totalled into one policy-wide score.
    expect(text).not.toMatch(/\d+\s*(of|\/)\s*\d+\s*(passed|failed)/i);
    expect(text).not.toMatch(/overall verdict/i);
  });

  it("still demands an unmet required fact rule by rule on the determination path", async () => {
    answerPolicyCase.mockResolvedValue({
      intent: "decision",
      classification_reasoning: "describes a situation for a determination",
      reasoning_effort: "low",
      informational: null,
    });
    testRuleScenario.mockResolvedValue({
      rule_id: "cap",
      rule_result: { status: "INDETERMINATE" },
      inferred_facts: {},
      assumptions: [],
      missing_facts: ["hours-per-week"],
      explanation: "An account of why",
      reasoning_effort: "low",
    });

    render(
      <PolicyCaseRunner
        policySetKey="a-key"
        target={A_VERSION}
        rules={[rule("cap", "A computed rule", "deterministic")]}
      />,
    );

    type("A described situation for a determination");
    await waitFor(() => expect(screen.getByTestId("policy-case-rollup")).toBeTruthy());

    const text = document.body.textContent ?? "";
    expect(text).toMatch(/would have to state/i);
    expect(text).toContain("hours-per-week");
  });

  it("says plainly when the rules that settle the case do not all point the same way", async () => {
    answerPolicyCase.mockResolvedValue({
      intent: "decision",
      classification_reasoning: "describes a situation for a determination",
      reasoning_effort: "low",
      informational: null,
    });
    evaluateScenario.mockResolvedValue({
      applies: "yes",
      reasoning: "An account of why",
      predicted_outcome: "",
      missing_facts: [],
      reasoning_effort: "low",
    });
    testRuleScenario.mockResolvedValue({
      rule_id: "breach",
      rule_result: { status: "NOT_SATISFIED" },
      inferred_facts: {},
      assumptions: [],
      missing_facts: [],
      explanation: "An account of why",
      reasoning_effort: "low",
    });

    render(
      <PolicyCaseRunner
        policySetKey="a-key"
        target={A_VERSION}
        rules={[
          rule("applies", "A rule stated in words", "ai_ready"),
          rule("breach", "A computed rule", "deterministic"),
        ]}
      />,
    );

    type("A situation two rules both settle, differently");
    await waitFor(() => expect(screen.getByTestId("policy-case-rollup")).toBeTruthy());

    const text = document.body.textContent ?? "";
    expect(text).toMatch(/do not all point the same way/i);
    // Divergence is stated, not resolved into a single ruling for the reader.
    expect(text).not.toMatch(/overall verdict/i);
  });
});

describe("a classification that did not arrive falls closed to the determination path", () => {
  it("puts the case to the rules and never reads as an error", async () => {
    answerPolicyCase.mockRejectedValue(new Error("unreachable"));
    evaluateScenario.mockResolvedValue({
      applies: "uncertain",
      reasoning: "An account of why",
      predicted_outcome: "",
      missing_facts: ["something the case did not state"],
      reasoning_effort: "low",
    });

    render(
      <PolicyCaseRunner
        policySetKey="a-key"
        target={DRAFT_TARGET}
        rules={[rule("a", "A rule stated in words", "ai_ready")]}
      />,
    );

    type("A described situation");
    await waitFor(() => expect(screen.getByTestId("policy-case-rollup")).toBeTruthy());

    // The determination path ran, because the classification did not arrive.
    expect(evaluateScenario).toHaveBeenCalledTimes(1);
    const text = document.body.textContent ?? "";
    expect(text).not.toMatch(/error/i);
    expect(text).not.toMatch(/failed/i);
  });
});
