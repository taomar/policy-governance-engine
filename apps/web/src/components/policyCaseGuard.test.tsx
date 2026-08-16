/**
 * Keeping a settled determination as a regression guard — the deliberate act,
 * and the line it must not cross.
 *
 * WHY THESE TESTS
 *
 * The case dialog is the front door to a guard: a reviewer reads an answer, and
 * if it is right, keeps it so it re-runs on every future publish. But only one
 * kind of answer can become one, and the surface must say why the others cannot
 * rather than greying a control out in silence. These pin that boundary:
 *
 *  - A determination the ENGINE settled carries what a deterministic PolicyTest
 *    needs — the facts it read and the status it must keep returning — so it is
 *    keepable, and keeping it calls the create endpoint with exactly those, and
 *    nothing reaches the evaluation audit trail.
 *  - An INFORMATIONAL answer is this app's synthesis across several rules, not
 *    one rule's verdict, so it cannot be kept — and the surface says so, naming
 *    the reason, never offering a dead control.
 *  - A determination settled only by the JUDGE states no facts, so there is
 *    nothing deterministic to re-run; it too is named, not offered.
 *  - Keeping is distinct from asking: no create call is ever made by reading a
 *    case, only by the explicit keep action.
 *
 * The re-run itself — that a kept guard actually fires on publish and records a
 * result — is pinned on the server, where it happens
 * (`tests/unit/test_publishing_reruns_active_guards.py`). Nothing here names any
 * real policy: the witness that prompted this is a regression fixture, never a
 * document.
 */
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { CanonicalRule } from "../api";
import type { CaseAnswer, CaseGuardSeed } from "./policyTesting";

const testRuleScenario = vi.fn();
const computeScenario = vi.fn();
const evaluateScenario = vi.fn();
const ruleNames = vi.fn();
const answerPolicyCase = vi.fn();
const createPolicyTest = vi.fn();

vi.mock("../api", async () => {
  const actual = await vi.importActual<typeof import("../api")>("../api");
  return {
    ...actual,
    aiApi: {
      ...actual.aiApi,
      testRuleScenario: (...args: unknown[]) => testRuleScenario(...args),
      computeScenario: (...args: unknown[]) => computeScenario(...args),
      evaluateScenario: (...args: unknown[]) => evaluateScenario(...args),
      ruleNames: (...args: unknown[]) => ruleNames(...args),
    },
    policyTestApi: {
      ...actual.policyTestApi,
      // The write path a kept guard travels. Held at the mock so a test can prove
      // exactly what a keep sends — and prove that reading a case sends nothing.
      create: (...args: unknown[]) => createPolicyTest(...args),
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
const { readPolicyCase } = await import("./policyCaseSummary");
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
  createPolicyTest.mockReset();
  createPolicyTest.mockResolvedValue({});
  ruleNames.mockReset();
  ruleNames.mockResolvedValue({ names: {}, names_by_rule_id: {} });
});

const A_VERSION = testTarget("a-published-version", 3);
const A_PROVISION = "prov-1";

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

/** A minimal CaseAnswer, so a summary-level test can set exactly the two fields
 *  guardability turns on — how the case settled, and whether a seed was carried. */
function answer(partial: Partial<CaseAnswer>): CaseAnswer {
  return {
    ruleId: "r",
    title: "A rule",
    decidedBy: "engine",
    label: "Met",
    color: "green",
    account: "",
    missing: [],
    unanswered: null,
    testedAgainst: DRAFT_TARGET,
    settlement: "settles",
    adverse: false,
    guardSeed: null,
    ...partial,
  };
}

const A_SEED: CaseGuardSeed = {
  ruleId: "cap",
  ruleTitle: "A computed rule",
  scenario: "A described situation",
  inferredFacts: { "hours-per-week": 30 },
  expectedOverallStatus: "NOT_SATISFIED",
  expectedRuleStatus: "NOT_SATISFIED",
};

describe("a policy reading keeps only the seeds of the rules that settle by engine", () => {
  it("carries an engine-settled rule's seed and drops a judge-settled one's", () => {
    const reading = readPolicyCase([
      answer({ ruleId: "cap", decidedBy: "engine", settlement: "settles", guardSeed: A_SEED }),
      // A judge settled this one; it states no facts, so it carries no seed even
      // though it settles the case.
      answer({ ruleId: "applies", decidedBy: "judge", settlement: "settles", guardSeed: null }),
    ]);
    expect(reading.state).toBe("settled");
    expect(reading.guardSeeds).toHaveLength(1);
    expect(reading.guardSeeds[0].ruleId).toBe("cap");
  });

  it("keeps no seed from a rule that bears but does not settle, even with a seed present", () => {
    // A seed can exist on an unsettled engine answer (the engine computed a
    // verdict), but a reading only ever offers the seeds of rules that SETTLE:
    // an unsettled determination is not an answer to keep.
    const reading = readPolicyCase([
      answer({ ruleId: "cap", decidedBy: "engine", settlement: "unsettled", guardSeed: A_SEED }),
    ]);
    expect(reading.state).toBe("bears_unsettled");
    expect(reading.guardSeeds).toHaveLength(0);
  });
});

describe("a determination the engine settled can be kept as a guard", () => {
  it("keeping sends the read facts and computed statuses to the create endpoint, and names the never-run state", async () => {
    answerPolicyCase.mockResolvedValue({
      intent: "decision",
      classification_reasoning: "describes a situation for a determination",
      reasoning_effort: "low",
      informational: null,
    });
    testRuleScenario.mockResolvedValue({
      rule_id: "cap",
      rule_result: { status: "NOT_SATISFIED" },
      inferred_facts: { "hours-per-week": 30 },
      overall_evaluation_status: "NOT_SATISFIED",
      assumptions: [],
      missing_facts: [],
      explanation: "An account of why",
      reasoning_effort: "low",
    });

    render(
      <PolicyCaseRunner
        policySetKey="a-key"
        target={A_VERSION}
        provisionId={A_PROVISION}
        rules={[rule("cap", "A computed rule", "deterministic")]}
      />,
    );

    type("I am part time working 30 hours and checking for overtime");
    await waitFor(() => expect(screen.getByTestId("policy-case-guard-offer")).toBeTruthy());

    // Reading the case has written nothing: the offer is present, but no guard
    // exists until the reviewer acts.
    expect(createPolicyTest).not.toHaveBeenCalled();
    expect(screen.queryByTestId("policy-case-not-guardable")).toBeNull();

    fireEvent.click(screen.getByTestId("policy-case-guard-keep"));

    await waitFor(() => expect(screen.getByTestId("policy-case-guard-kept")).toBeTruthy());

    expect(createPolicyTest).toHaveBeenCalledTimes(1);
    const [key, body] = createPolicyTest.mock.calls[0] as [string, Record<string, unknown>];
    expect(key).toBe("a-key");
    // The seed is exactly what a deterministic re-run needs: the facts the engine
    // read, the statuses it computed, and the rule it computed them for.
    expect(body.input_facts).toEqual({ "hours-per-week": 30 });
    expect(body.expected_overall_status).toBe("NOT_SATISFIED");
    expect(body.expected_rule_id).toBe("cap");
    expect(body.expected_rule_status).toBe("NOT_SATISFIED");
    expect(body.test_kind).toBe("negative");
    // Constraint 8: no generated rule name crosses into the payload; the UI
    // resolves display names elsewhere.
    expect(body).not.toHaveProperty("title");

    // Constraint 5: the kept guard EXISTS but has NOT run — a distinct state from
    // passed or failed, and the surface says which.
    const kept = screen.getByTestId("policy-case-guard-kept");
    expect(kept.textContent ?? "").toMatch(/not run yet/i);
    expect(kept.textContent ?? "").toMatch(/next version you publish/i);
  });
});

describe("an answer that is not one rule's reproducible verdict says why it cannot be kept", () => {
  it("names an informational answer as un-guardable and offers no keep, writing nothing", async () => {
    answerPolicyCase.mockResolvedValue({
      intent: "informational",
      classification_reasoning: "reads as a request for what the policy provides",
      reasoning_effort: "low",
      informational: {
        status: "answered",
        answer: "The ceiling is stated directly by the rule below.",
        citations: [{ rule_id: "cap" }],
        note: "",
      },
    });

    render(
      <PolicyCaseRunner
        policySetKey="a-key"
        target={A_VERSION}
        provisionId={A_PROVISION}
        rules={[rule("cap", "The weekly ceiling", "deterministic")]}
      />,
    );

    type("How many hours may this kind of employee work?");
    await waitFor(() => expect(screen.getByTestId("policy-case-not-guardable")).toBeTruthy());

    const note = screen.getByTestId("policy-case-not-guardable");
    expect(note.textContent ?? "").toMatch(/informational/i);
    expect(note.textContent ?? "").toMatch(/nothing deterministic/i);
    // Named, not offered: there is no keep control, and nothing was written.
    expect(screen.queryByTestId("policy-case-guard-keep")).toBeNull();
    expect(createPolicyTest).not.toHaveBeenCalled();
  });

  it("names a judge-settled determination as un-guardable because it states no facts", async () => {
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

    render(
      <PolicyCaseRunner
        policySetKey="a-key"
        target={A_VERSION}
        provisionId={A_PROVISION}
        rules={[rule("applies", "A rule stated in words", "ai_ready")]}
      />,
    );

    type("A described situation two rules read in words");
    await waitFor(() => expect(screen.getByTestId("policy-case-rollup")).toBeTruthy());

    const note = screen.getByTestId("policy-case-not-guardable");
    expect(note.textContent ?? "").toMatch(/judge/i);
    expect(note.textContent ?? "").toMatch(/states no facts/i);
    expect(screen.queryByTestId("policy-case-guard-keep")).toBeNull();
    expect(createPolicyTest).not.toHaveBeenCalled();
  });
});

describe("a guard re-runs against published versions, so a case put to the draft is not yet keepable", () => {
  it("names an engine-settled draft determination as keep-after-publish, offering no keep and writing nothing", async () => {
    answerPolicyCase.mockResolvedValue({
      intent: "decision",
      classification_reasoning: "describes a situation for a determination",
      reasoning_effort: "low",
      informational: null,
    });
    // A case put to the draft is computed by the engine (computeScenario), not
    // routed to the version's siblings — so it settles and carries a seed, yet it
    // is a single-rule reading of words that may still change before publication.
    computeScenario.mockResolvedValue({
      rule_id: "cap",
      rule_result: { status: "NOT_SATISFIED" },
      inferred_facts: { "hours-per-week": 30 },
      overall_evaluation_status: "NOT_SATISFIED",
      assumptions: [],
      missing_facts: [],
      explanation: "An account of why",
      reasoning_effort: "low",
    });

    render(
      <PolicyCaseRunner
        policySetKey="a-key"
        target={DRAFT_TARGET}
        provisionId={A_PROVISION}
        rules={[rule("cap", "A computed rule", "deterministic")]}
      />,
    );

    type("I am part time working 30 hours and checking for overtime");
    await waitFor(() => expect(screen.getByTestId("policy-case-not-guardable")).toBeTruthy());

    // computeScenario ran (the draft route), not the version route.
    expect(computeScenario).toHaveBeenCalledTimes(1);
    expect(testRuleScenario).not.toHaveBeenCalled();

    const note = screen.getByTestId("policy-case-not-guardable");
    expect(note.textContent ?? "").toMatch(/published/i);
    // The engine settled it — a seed exists — but the draft is no published
    // version, so the keep control is withheld and nothing is written.
    expect(screen.queryByTestId("policy-case-guard-keep")).toBeNull();
    expect(createPolicyTest).not.toHaveBeenCalled();
  });
});
