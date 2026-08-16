/**
 * No door that cannot open, and no answer that outranks another.
 *
 * WHY THESE TESTS
 *
 * A reviewer pressed "Write scenarios for the rules with no test" on a policy
 * set nothing had been published from, and was told the set "has no active
 * approved version to propose tests against". Every word of that was true. The
 * defect was that the control existed at all: the batch endpoint takes a
 * published version and builds its rule list from that version's package, so
 * before anything is published there is no request to make — not a request that
 * gets turned down.
 *
 * The way out was already in the schemas. The judge is handed the rule itself
 * and needs no version, which is the whole reason the route exists: a rule
 * stated in words can be decided from the moment it is drafted. So a record
 * with nothing published is not an untestable record. It is a record where one
 * of two instruments has nothing to compute against yet.
 *
 * WHAT THESE PIN, AND WHY EACH WOULD OTHERWISE COME BACK
 *
 *  - A version-scoped call is never reachable without a version. Not guarded by
 *    a disabled button or an error handler: the verb is absent, so no later
 *    edit can wire a control to it by accident.
 *  - A rule stated in words can be put to a case whether or not anything has
 *    been published. This is the route most policy text arrives on, so a
 *    surface that waits for publication before offering any test offers almost
 *    nothing.
 *  - A rule waiting on publication is described as waiting, never as failing,
 *    untestable, or lesser. The instrument is not ready; the rule is fine.
 *  - A policy can be put to a case as a whole, and its rules' answers are not
 *    totalled. The engine computes whether a case satisfies a rule; the judge
 *    reads whether a rule applies to a case. Those are different questions, and
 *    a single "9 of 12 passed" would be an average of two things that are not
 *    the same thing.
 *  - No answer carries a number. A model asked for a confidence supplies one,
 *    and `0.87` reads as measurement when it is invention — and printed beside
 *    a computed answer it reads as the judged route apologising for itself.
 *    `contracts/correlation.py` states the rule; this applies it where the
 *    temptation is strongest.
 *
 * Nothing here is a phrase from any document, and no number in it measures one.
 */
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { AssembledPolicy, CanonicalRule } from "../api";

const testRuleScenario = vi.fn();
const evaluateScenario = vi.fn();
const generateBatch = vi.fn();

vi.mock("../api", async () => {
  const actual = await vi.importActual<typeof import("../api")>("../api");
  return {
    ...actual,
    aiApi: {
      ...actual.aiApi,
      testRuleScenario: (...args: unknown[]) => testRuleScenario(...args),
      evaluateScenario: (...args: unknown[]) => evaluateScenario(...args),
    },
    policyTestApi: {
      ...actual.policyTestApi,
      generateBatch: (...args: unknown[]) => generateBatch(...args),
    },
  };
});

const { PolicyTestsPane } = await import("./policyTabPanes");
const { PolicyCaseRunner } = await import("./PolicyCaseRunner");
const { putCaseToRule, testingDoor, usePolicyTesting } = await import("./policyTesting");
type PolicyRecordView = import("./policyTabPanes").PolicyRecordView;
type PolicyTestingVerbs = import("./policyTabPanes").PolicyTestingVerbs;

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
  evaluateScenario.mockReset();
  generateBatch.mockReset();
});

/**
 * `evaluation_mode` and `machine_executable` are both explicit, because which
 * decider a rule calls for is derived from the pair. A fixture stating one and
 * defaulting the other describes a rule the server would refuse.
 */
function rule(
  id: string,
  title: string,
  mode: "deterministic" | "ai_ready",
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

function verbs(overrides: Partial<PolicyTestingVerbs> = {}): PolicyTestingVerbs {
  return {
    generate: vi.fn().mockResolvedValue(undefined),
    run: vi.fn().mockResolvedValue(undefined),
    publishedVersionId: "a-published-version",
    busy: new Set<string>(),
    working: false,
    error: null,
    dismissError: vi.fn(),
    ...overrides,
  } as PolicyTestingVerbs;
}

/** What an unpublished record's verbs look like, produced by the hook's own rule. */
function unpublishedVerbs(overrides: Partial<PolicyTestingVerbs> = {}): PolicyTestingVerbs {
  return verbs({ generate: null, publishedVersionId: null, ...overrides });
}

/**
 * Wordings that would put one route, or one state, below another. Checked as
 * vocabulary rather than left to a reviewer noticing, because ranking is the
 * failure this project keeps reproducing under pressure and it arrives in a
 * different sentence every time.
 */
const RANKING = [
  /not testable/i,
  /cannot be tested/i,
  /untestable/i,
  /unsupported/i,
  /guesswork/i,
  /real engine/i,
  /advisory only/i,
  /just an opinion/i,
  /less reliable/i,
  /weaker/i,
  /best guess/i,
  /only a/i,
];

/** A number presented as how sure a decider is. */
const CONFIDENCE_NUMBER = [/\bconfidence\b[^.]*\d/i, /\d+\s*%/, /\b0\.\d+\b/];

describe("a control is drawn only where it can act", () => {
  it("offers no scenario-writing at all when nothing has been published", () => {
    render(
      <PolicyTestsPane
        record={record([rule("a", "A computed rule", "deterministic")])}
        tests={[]}
        testing={unpublishedVerbs()}
      />,
    );

    expect(screen.queryByTestId("policy-generate-tests")).toBeNull();
    expect(screen.queryByTestId("generate-rule-test-a")).toBeNull();
  });

  it("restores scenario-writing once a version exists to compute against", () => {
    render(
      <PolicyTestsPane
        record={record([rule("a", "A computed rule", "deterministic")])}
        tests={[]}
        testing={verbs()}
      />,
    );

    expect(screen.getByTestId("policy-generate-tests")).toBeTruthy();
    expect(screen.getByTestId("generate-rule-test-a")).toBeTruthy();
  });

  it("still offers a case to every rule stated in words, unpublished", () => {
    render(
      <PolicyTestsPane
        record={record([rule("a", "A rule stated in words", "ai_ready")])}
        tests={[]}
        testing={unpublishedVerbs()}
      />,
    );

    expect(screen.getByTestId("put-case-a")).toBeTruthy();
    expect(screen.getByTestId("policy-put-case")).toBeTruthy();
  });

  it("says a computed rule is waiting on publication, not that it has failed", () => {
    render(
      <PolicyTestsPane
        record={record([rule("a", "A computed rule", "deterministic")])}
        tests={[]}
        testing={unpublishedVerbs()}
      />,
    );

    expect(screen.getByTestId("awaits-publication-a")).toBeTruthy();
    const text = document.body.textContent ?? "";
    for (const banned of RANKING) expect(text).not.toMatch(banned);
  });

  it("never lets a version-scoped call be made without a version", async () => {
    const answer = await putCaseToRule(rule("a", "A computed rule", "deterministic"), {
      scenario: "A described situation",
      reasoningEffort: "low",
      policySetKey: "a-key",
      publishedVersionId: null,
    });

    expect(testRuleScenario).not.toHaveBeenCalled();
    expect(answer.decidedBy).toBe("nobody");
    expect(answer.unanswered).toBeTruthy();
    for (const banned of RANKING) expect(answer.unanswered ?? "").not.toMatch(banned);
  });

  it("gives the hook no scenario-writing verb at all without a version", () => {
    const seen: Array<ReturnType<typeof usePolicyTesting>> = [];
    function Probe({ versionId }: { versionId: string | null }) {
      seen.push(
        usePolicyTesting({
          policySetKey: "a-key",
          policyVersionId: versionId,
          actor: "someone",
          onChanged: () => {},
        }),
      );
      return null;
    }

    render(<Probe versionId={null} />);
    expect(seen[0].generate).toBeNull();
    expect(seen[0].publishedVersionId).toBeNull();

    cleanup();
    render(<Probe versionId="a-published-version" />);
    expect(seen[seen.length - 1].generate).not.toBeNull();
  });
});

describe("each route is asked of its own decider", () => {
  it("sends a rule stated in words to the judge, with no version anywhere", async () => {
    evaluateScenario.mockResolvedValue({
      applies: "yes",
      reasoning: "An account of why",
      predicted_outcome: "",
      missing_facts: [],
      reasoning_effort: "low",
    });

    const answer = await putCaseToRule(rule("a", "A rule stated in words", "ai_ready"), {
      scenario: "A described situation",
      reasoningEffort: "low",
      policySetKey: null,
      publishedVersionId: null,
    });

    expect(evaluateScenario).toHaveBeenCalledTimes(1);
    expect(testRuleScenario).not.toHaveBeenCalled();
    expect(answer.decidedBy).toBe("judge");
    expect(answer.label).toBeTruthy();
  });

  it("sends a computed rule to the engine when a version exists", async () => {
    testRuleScenario.mockResolvedValue({
      rule_id: "a",
      rule_result: { status: "SATISFIED" },
      inferred_facts: {},
      assumptions: [],
      missing_facts: [],
      explanation: "An account of why",
      reasoning_effort: "low",
    });

    const answer = await putCaseToRule(rule("a", "A computed rule", "deterministic"), {
      scenario: "A described situation",
      reasoningEffort: "low",
      policySetKey: "a-key",
      publishedVersionId: "a-published-version",
    });

    expect(testRuleScenario).toHaveBeenCalledTimes(1);
    expect(evaluateScenario).not.toHaveBeenCalled();
    expect(answer.decidedBy).toBe("engine");
  });

  it("derives the door from the record, both halves of it", () => {
    expect(testingDoor(rule("a", "t", "ai_ready"), null)).toBe("judge-case");
    expect(testingDoor(rule("a", "t", "ai_ready"), "a-version")).toBe("judge-case");
    expect(testingDoor(rule("a", "t", "deterministic"), "a-version")).toBe("engine-scenario");
    expect(testingDoor(rule("a", "t", "deterministic"), null)).toBe("engine-awaits-publication");
  });
});

describe("a policy can be put to a case, and the answers are not totalled", () => {
  it("asks every rule through its own door and reports each in its own terms", async () => {
    evaluateScenario.mockResolvedValue({
      applies: "no",
      reasoning: "An account of why",
      predicted_outcome: "",
      missing_facts: [],
      reasoning_effort: "low",
    });
    testRuleScenario.mockResolvedValue({
      rule_id: "b",
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
        publishedVersionId="a-published-version"
        rules={[rule("a", "A rule stated in words", "ai_ready"), rule("b", "A computed rule", "deterministic")]}
      />,
    );

    fireEvent.change(screen.getByTestId("policy-case-scenario"), {
      target: { value: "A described situation" },
    });
    fireEvent.click(screen.getByTestId("policy-case-run"));

    await waitFor(() => expect(screen.getByTestId("policy-case-rollup")).toBeTruthy());
    expect(evaluateScenario).toHaveBeenCalledTimes(1);
    expect(testRuleScenario).toHaveBeenCalledTimes(1);

    const text = document.body.textContent ?? "";
    // Two questions, two answers, and no arithmetic joining them.
    expect(text).not.toMatch(/\d+\s*(of|\/)\s*\d+\s*(passed|failed)/i);
    expect(text).not.toMatch(/overall verdict/i);
    for (const banned of RANKING) expect(text).not.toMatch(banned);
    for (const banned of CONFIDENCE_NUMBER) expect(text).not.toMatch(banned);
  });

  it("lists a rule waiting on publication without sending it to the wrong decider", async () => {
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
        publishedVersionId={null}
        rules={[rule("a", "A rule stated in words", "ai_ready"), rule("b", "A computed rule", "deterministic")]}
      />,
    );

    fireEvent.change(screen.getByTestId("policy-case-scenario"), {
      target: { value: "A described situation" },
    });
    fireEvent.click(screen.getByTestId("policy-case-run"));

    await waitFor(() => expect(screen.getByTestId("policy-case-rollup")).toBeTruthy());
    expect(evaluateScenario).toHaveBeenCalledTimes(1);
    expect(testRuleScenario).not.toHaveBeenCalled();
    expect(screen.getByTestId("policy-case-awaits-publication")).toBeTruthy();

    const text = document.body.textContent ?? "";
    for (const banned of RANKING) expect(text).not.toMatch(banned);
  });

  it("keeps the third answer as its own answer, not an error", async () => {
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
        publishedVersionId={null}
        rules={[rule("a", "A rule stated in words", "ai_ready")]}
      />,
    );

    fireEvent.change(screen.getByTestId("policy-case-scenario"), {
      target: { value: "A described situation" },
    });
    fireEvent.click(screen.getByTestId("policy-case-run"));

    await waitFor(() => expect(screen.getByTestId("policy-case-rollup")).toBeTruthy());
    const text = document.body.textContent ?? "";
    expect(text).toMatch(/does not settle it/i);
    expect(text).not.toMatch(/error/i);
    expect(text).not.toMatch(/failed/i);
  });

  it("says plainly that nothing it shows was saved", async () => {
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
        publishedVersionId={null}
        rules={[rule("a", "A rule stated in words", "ai_ready")]}
      />,
    );

    fireEvent.change(screen.getByTestId("policy-case-scenario"), {
      target: { value: "A described situation" },
    });
    fireEvent.click(screen.getByTestId("policy-case-run"));

    await waitFor(() => expect(screen.getByTestId("policy-case-not-saved")).toBeTruthy());
  });
});
