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
 * The first fix drew that control only where it opens, and left computed rules
 * "waiting on publication". That was still wrong, and wrong in a way worth
 * recording, because it looked correct: it collapsed two independent facts into
 * one. WHO DECIDES a rule comes from the rule's own route. WHAT IS DECIDED
 * ABOUT comes from the version the record is read at. The engine does not need
 * a published version to compute a comparison — it needs a rule — and
 * `compute-scenario` takes exactly that. Only the batch endpoint genuinely
 * needs a version, because only it builds its rule list out of one.
 *
 * So a record with nothing published is not a record with untestable rules. All
 * four combinations answer, and the two axes are pinned separately below.
 *
 * WHAT THESE PIN, AND WHY EACH WOULD OTHERWISE COME BACK
 *
 *  - A version-scoped call is never reachable without a version. Not guarded by
 *    a disabled button or an error handler: the verb is absent, so no later
 *    edit can wire a control to it by accident.
 *  - Every rule can be put to a case, published or not, on either route. This
 *    is the route most policy text arrives on, so a surface that waits for
 *    publication before offering any test offers almost nothing.
 *  - A result says what it ran against. A reviewer's answer is about the draft
 *    and a policy admin's is about a named version; the same rule and the same
 *    case can honestly return two different answers, and a verdict whose target
 *    the reader has to infer from the page they are on is not evidence. The
 *    same failure has already happened once here, where a published question
 *    silently resolved against draft rows and the answer looked grounded.
 *  - A draft answer never reads as a published one. A candidate that passed is
 *    `untested` after publication, not `passing`; carrying it over would be a
 *    false assurance that is green.
 *  - The default target is the draft. A surface that names no version is
 *    reading the record as it stands, which is the honest answer for a reviewer
 *    and the only possible one for a set that has never published.
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
const computeScenario = vi.fn();
const evaluateScenario = vi.fn();
const generateBatch = vi.fn();

vi.mock("../api", async () => {
  const actual = await vi.importActual<typeof import("../api")>("../api");
  return {
    ...actual,
    aiApi: {
      ...actual.aiApi,
      testRuleScenario: (...args: unknown[]) => testRuleScenario(...args),
      computeScenario: (...args: unknown[]) => computeScenario(...args),
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
const { RuleScenarioTester } = await import("./RuleScenarioTester");
const { putCaseToRule, ruleDecider, testTarget, targetLabel, DRAFT_TARGET, usePolicyTesting } =
  await import("./policyTesting");
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
  computeScenario.mockReset();
  evaluateScenario.mockReset();
  generateBatch.mockReset();
});

/**
 * A version id and number that no document supplies and no count measures. The
 * number exists only so the target can be named in a sentence rather than
 * printed as a uuid.
 */
const A_VERSION = testTarget("a-published-version", 3);

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
    target: A_VERSION,
    busy: new Set<string>(),
    working: false,
    error: null,
    dismissError: vi.fn(),
    ...overrides,
  } as PolicyTestingVerbs;
}

/** What an unpublished record's verbs look like, produced by the hook's own rule. */
function unpublishedVerbs(overrides: Partial<PolicyTestingVerbs> = {}): PolicyTestingVerbs {
  return verbs({ generate: null, target: DRAFT_TARGET, ...overrides });
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
  // The route this fix deleted. A rule is never waiting on a publication to be
  // checked; a batch of pre-written scenarios is, and that is a different thing.
  /await\w*\s+publication/i,
  /once (it is |this is )?published/i,
  /not yet published.{0,40}(test|check)/i,
];

/** A number presented as how sure a decider is. */
const CONFIDENCE_NUMBER = [/\bconfidence\b[^.]*\d/i, /\d+\s*%/, /\b0\.\d+\b/];

/**
 * Wordings that would let a draft answer be read as a fact about what is in
 * force. The dangerous direction: a reviewer's green result surviving into
 * publication as an assurance nobody gave.
 */
const DRAFT_READ_AS_PUBLISHED = [
  /this (is|shows) (what is )?in force/i,
  /(applies|holds) (to|for) the published/i,
  /remains? (true|valid) (once|after) publish/i,
];

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

  it("offers a computed rule a case too, with nothing published", () => {
    render(
      <PolicyTestsPane
        record={record([rule("a", "A computed rule", "deterministic")])}
        tests={[]}
        testing={unpublishedVerbs()}
      />,
    );

    // The engine computes a comparison from the rule it is handed. Nothing
    // about that waits on a publication, and a row with no verb at all was the
    // defect this replaced.
    expect(screen.getByTestId("put-case-a")).toBeTruthy();
    const text = document.body.textContent ?? "";
    for (const banned of RANKING) expect(text).not.toMatch(banned);
  });

  it("leaves no rule of any route without a live verb", () => {
    render(
      <PolicyTestsPane
        record={record([
          rule("a", "A rule stated in words", "ai_ready"),
          rule("b", "A computed rule", "deterministic"),
        ])}
        tests={[]}
        testing={unpublishedVerbs()}
      />,
    );

    for (const id of ["a", "b"]) {
      const acted =
        screen.queryByTestId(`put-case-${id}`) ??
        screen.queryByTestId(`generate-rule-test-${id}`) ??
        screen.queryByTestId(`run-rule-tests-${id}`);
      expect(acted).toBeTruthy();
    }
  });

  it("routes a computed rule to the engine without a version, never through the set", async () => {
    computeScenario.mockResolvedValue({
      rule_id: "a",
      rule_result: { status: "SATISFIED" },
      inferred_facts: {},
      assumptions: [],
      missing_facts: [],
      explanation: "An account of why",
      reasoning_effort: "low",
      evaluation_timestamp: "2024-01-01T00:00:00Z",
      result_hash: "abcdef012345",
    });

    const answer = await putCaseToRule(rule("a", "A computed rule", "deterministic"), {
      scenario: "A described situation",
      reasoningEffort: "low",
      policySetKey: "a-key",
      target: DRAFT_TARGET,
    });

    expect(testRuleScenario).not.toHaveBeenCalled();
    expect(computeScenario).toHaveBeenCalledTimes(1);
    expect(answer.decidedBy).toBe("engine");
    expect(answer.unanswered).toBeNull();
    expect(answer.testedAgainst.kind).toBe("draft");
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
    expect(seen[0].target.kind).toBe("draft");

    cleanup();
    render(<Probe versionId="a-published-version" />);
    expect(seen[seen.length - 1].generate).not.toBeNull();
    expect(seen[seen.length - 1].target.kind).toBe("published_version");
  });
});

describe("a result says what it ran against", () => {
  it("names the draft, and says the answer does not carry into publication", () => {
    render(
      <PolicyTestsPane
        record={record([rule("a", "A rule stated in words", "ai_ready")])}
        tests={[]}
        testing={unpublishedVerbs()}
      />,
    );

    const stated = screen.getByTestId("policy-tests-target").textContent ?? "";
    expect(stated).toMatch(/draft/i);
    expect(stated).toMatch(/does not carry it over/i);
    for (const banned of DRAFT_READ_AS_PUBLISHED) expect(stated).not.toMatch(banned);
  });

  it("names the version by its number rather than printing its id", () => {
    render(
      <PolicyTestsPane
        record={record([rule("a", "A rule stated in words", "ai_ready")])}
        tests={[]}
        testing={verbs()}
      />,
    );

    const stated = screen.getByTestId("policy-tests-target").textContent ?? "";
    expect(stated).toMatch(targetLabel(A_VERSION));
    expect(stated).not.toMatch(/a-published-version/);
    // A published answer is about what is in force, so the draft caveat is not
    // merely unnecessary here — it would be false.
    expect(stated).not.toMatch(/does not carry it over/i);
  });

  it("carries the target on every answer, not only in the copy above it", async () => {
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
      policySetKey: "a-key",
      target: A_VERSION,
    });

    expect(answer.testedAgainst).toEqual(A_VERSION);
  });

  it("defaults a rule tester with no named version to the draft", async () => {
    evaluateScenario.mockResolvedValue({
      applies: "yes",
      reasoning: "An account of why",
      predicted_outcome: "",
      missing_facts: [],
      reasoning_effort: "low",
    });

    // No `target`: this is how the review surface mounts it, and the review
    // surface is asking about the candidate in front of the reviewer.
    render(<RuleScenarioTester policySetKey="a-key" rule={rule("a", "A rule stated in words", "ai_ready")} />);

    expect(screen.getByTestId("scenario-target").textContent ?? "").toMatch(/draft/i);

    fireEvent.change(screen.getByRole("textbox"), { target: { value: "A described situation" } });
    fireEvent.click(screen.getByTestId("scenario-run"));

    await waitFor(() => expect(evaluateScenario).toHaveBeenCalledTimes(1));
    expect(testRuleScenario).not.toHaveBeenCalled();
  });

  it("keeps a computed rule off the version-scoped call when no version is named", async () => {
    computeScenario.mockResolvedValue({
      rule_id: "a",
      rule_result: { status: "SATISFIED" },
      inferred_facts: {},
      assumptions: [],
      missing_facts: [],
      explanation: "An account of why",
      reasoning_effort: "low",
      evaluation_timestamp: "2024-01-01T00:00:00Z",
      result_hash: "abcdef012345",
    });

    render(<RuleScenarioTester policySetKey="a-key" rule={rule("a", "A computed rule", "deterministic")} />);

    fireEvent.change(screen.getByRole("textbox"), { target: { value: "A described situation" } });
    fireEvent.click(screen.getByTestId("scenario-run"));

    await waitFor(() => expect(computeScenario).toHaveBeenCalledTimes(1));
    expect(testRuleScenario).not.toHaveBeenCalled();
  });

  /**
   * The engine's timestamp and result hash are audit handles, not the answer.
   * Reading them unguarded threw during render, which lost the verdict the
   * reader had asked for and took the surrounding panel with it. It surfaced as
   * an unhandled error attributed to an unrelated file, because the throw
   * happens after the call that a routing test awaits.
   *
   * The deterministic route is much the smaller of the two, so a crash confined
   * to it can sit unnoticed for a long time. An answer that arrives without its
   * handles is still an answer, and must still be readable.
   */
  it("still shows a computed verdict when the engine sends no audit handles", async () => {
    computeScenario.mockResolvedValue({
      rule_id: "a",
      rule_result: { status: "SATISFIED" },
      inferred_facts: {},
      assumptions: [],
      missing_facts: [],
      explanation: "An account of why",
      reasoning_effort: "low",
    });

    render(<RuleScenarioTester policySetKey="a-key" rule={rule("a", "A computed rule", "deterministic")} />);

    fireEvent.change(screen.getByRole("textbox"), { target: { value: "A described situation" } });
    fireEvent.click(screen.getByTestId("scenario-run"));

    const said = (await screen.findByTestId("scenario-decided-by")).textContent ?? "";
    expect(said).toMatch(/engine/i);
    // No handle, so nothing announcing one - never the word with an empty space
    // after it, and never the ellipsis left by a hash that was not there.
    expect(said).not.toMatch(/result hash/i);
    expect(said).not.toMatch(/Invalid Date/);
    // The verdict itself survived the missing handles.
    expect(await screen.findByText(/An account of why/)).toBeTruthy();
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
      target: DRAFT_TARGET,
    });

    expect(evaluateScenario).toHaveBeenCalledTimes(1);
    expect(testRuleScenario).not.toHaveBeenCalled();
    expect(computeScenario).not.toHaveBeenCalled();
    expect(answer.decidedBy).toBe("judge");
    expect(answer.label).toBeTruthy();
  });

  it("sends a computed rule to the named version when one is chosen", async () => {
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
      target: A_VERSION,
    });

    expect(testRuleScenario).toHaveBeenCalledTimes(1);
    // The chosen version reaches the call. Omitting it would let the server
    // fall back to whatever is active now, which makes the answer depend on
    // when it was asked rather than on what was asked about.
    expect(testRuleScenario.mock.calls[0]).toContain("a-published-version");
    expect(evaluateScenario).not.toHaveBeenCalled();
    expect(computeScenario).not.toHaveBeenCalled();
    expect(answer.decidedBy).toBe("engine");
  });

  it("derives who decides from the rule, and never from the target", () => {
    for (const target of [null, "a-version"]) {
      expect(ruleDecider(rule("a", "t", "ai_ready"))).toBe("judge");
      expect(ruleDecider(rule("a", "t", "deterministic"))).toBe("engine");
      expect(testTarget(target).kind).toBe(target ? "published_version" : "draft");
    }
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
        target={A_VERSION}
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

  it("asks every rule of an unpublished policy, each of its own decider", async () => {
    evaluateScenario.mockResolvedValue({
      applies: "uncertain",
      reasoning: "An account of why",
      predicted_outcome: "",
      missing_facts: ["something the case did not state"],
      reasoning_effort: "low",
    });
    computeScenario.mockResolvedValue({
      rule_id: "b",
      rule_result: { status: "NOT_APPLICABLE" },
      inferred_facts: {},
      assumptions: [],
      missing_facts: [],
      explanation: "An account of why",
      reasoning_effort: "low",
    });

    render(
      <PolicyCaseRunner
        policySetKey="a-key"
        target={DRAFT_TARGET}
        rules={[rule("a", "A rule stated in words", "ai_ready"), rule("b", "A computed rule", "deterministic")]}
      />,
    );

    fireEvent.change(screen.getByTestId("policy-case-scenario"), {
      target: { value: "A described situation" },
    });
    fireEvent.click(screen.getByTestId("policy-case-run"));

    await waitFor(() => expect(screen.getByTestId("policy-case-rollup")).toBeTruthy());
    // Both answered. Neither reached the version-scoped call, because no
    // version was named — and neither was skipped for want of one.
    expect(evaluateScenario).toHaveBeenCalledTimes(1);
    expect(computeScenario).toHaveBeenCalledTimes(1);
    expect(testRuleScenario).not.toHaveBeenCalled();
    expect(screen.getByTestId("policy-case-target").textContent ?? "").toMatch(/draft/i);

    const text = document.body.textContent ?? "";
    for (const banned of RANKING) expect(text).not.toMatch(banned);
    for (const banned of DRAFT_READ_AS_PUBLISHED) expect(text).not.toMatch(banned);
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
        target={DRAFT_TARGET}
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
        target={DRAFT_TARGET}
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
