/**
 * A rule the answer rests on is shown once, not printed twice.
 *
 * WHY THIS TEST
 *
 * The policy-case answer names the rules it rests on and quotes each in full —
 * that is the evidence, and it stays open. Beneath it a completeness list says
 * every rule of the policy was read, so leading with a few never leaves a
 * reviewer believing those few were all there were.
 *
 * The two were printed over each other: a cited rule appeared once under the
 * citations, with its verbatim sentence, and again in the completeness list
 * carrying a "the answer rests on this" chip. Same rule, two places, one screen.
 *
 * Printing one fact twice is duplication, not information (constraint 11:
 * removing a second copy of the same fact is not losing information; removing a
 * distinction is). So the cited rules are shown once, under the citations, and
 * the completeness list carries the *remainder* — the rules not cited above —
 * while the claim that every rule was read stays visible and the count still
 * adds up. This pins both halves: the cited rule is not repeated, and the
 * completeness claim survives the de-duplication.
 *
 * Nothing here names any real policy; the rules are witnesses, not fixtures.
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
      // Held so the generated rule-name handle never reaches the network: it
      // resolves to nothing and `RuleName` renders nothing, which is exactly
      // what a rule with no generated name should do. So this test asserts on
      // each rule's own title, which always renders, not on a generated name.
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
const { testTarget } = await import("./policyTesting");

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
const A_PROVISION = "prov-1";

function rule(
  id: string,
  title: string,
  mode: "deterministic" | "ai_ready",
  sourceText = "",
): CanonicalRule {
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
    formulation: sourceText ? { canonical: { source_text: sourceText } } : undefined,
  } as unknown as CanonicalRule;
}

function type(scenario: string): void {
  fireEvent.change(screen.getByTestId("policy-case-scenario"), { target: { value: scenario } });
  fireEvent.click(screen.getByTestId("policy-case-run"));
}

describe("a rule the answer rests on is cited once, not printed a second time", () => {
  it("shows a cited rule under the citations and not again in the completeness list, while the list still accounts for every rule", async () => {
    answerPolicyCase.mockResolvedValue({
      intent: "informational",
      classification_reasoning: "reads as a request for what the policy provides",
      reasoning_effort: "low",
      informational: {
        status: "answered",
        answer: "A composed answer that does not repeat any rule's own title.",
        citations: [{ rule_id: "cited" }],
        note: "",
        grounding: {
          prompt_version: "ai-case-intent-v2",
          rules_available: 3,
          citations_requested: 1,
          rules_cited: 1,
          fabricated_citations: [],
          oversize: false,
        },
      },
    });

    render(
      <PolicyCaseRunner
        policySetKey="a-key"
        target={A_VERSION}
        provisionId={A_PROVISION}
        rules={[
          rule("cited", "Copying needs written consent", "deterministic", "this document may not be copied without consent"),
          rule("other-1", "Distribution is limited", "ai_ready"),
          rule("other-2", "Storage is internal only", "ai_ready"),
        ]}
      />,
    );

    type("What does this policy say about copying?");

    await waitFor(() => expect(screen.getByTestId("policy-case-answer")).toBeTruthy());

    // The cited rule is evidence: it appears in full under the citations, with
    // its verbatim sentence. It used to be printed a SECOND time in the list of
    // every rule below — a duplicate of one fact, not a second fact. It now
    // appears exactly once.
    expect(screen.getAllByText("Copying needs written consent")).toHaveLength(1);

    // De-duplicating must not buy tidiness with information (constraint 11). The
    // completeness list still says every rule was read, and still accounts for
    // the rules not cited above, so the count adds up and none is made invisible.
    const allRules = screen.getByTestId("policy-case-all-rules");
    expect(allRules.textContent ?? "").toMatch(/All 3 rules of this policy were read/i);
    expect(allRules.textContent ?? "").toContain("Distribution is limited");
    expect(allRules.textContent ?? "").toContain("Storage is internal only");
  });
});
