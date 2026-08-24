/**
 * The Evaluate form's empty state names its cause instead of guessing one.
 *
 * WHY THESE TESTS
 *
 * The facts form is built from the union of the selected version's rules'
 * `required_facts`. When that union is empty the form has no fields, and a
 * single guard — `factFields.length === 0` — used to render one sentence for
 * it: "No required facts found — this version may have no rules yet."
 *
 * Four different situations reach an empty form, and that sentence answered for
 * all of them:
 *
 *   - the rules are still loading,
 *   - the load failed,
 *   - the policy set has no active version to read, and
 *   - the version has rules, and none of them names a fact.
 *
 * The last is the ordinary case for a rule whose test is words rather than a
 * comparison of named quantities: there is nothing for the form to collect
 * because the rule states no quantities, not because the version is empty. On a
 * version of such rules the old sentence contradicted the results table the same
 * screen renders from those very rules, and told the reader a populated version
 * "may have no rules". That is a route presented as an absence, which is exactly
 * what this project's copy guards exist to stop — and it slipped past them
 * because the sentence never names the route, so the polarity scanners never
 * engaged.
 *
 * WHAT THESE PIN, AND WHY EACH WOULD OTHERWISE COME BACK
 *
 *   - A version whose rules name no facts is not described as empty or lacking.
 *     Its message says the rules state their tests in words, so the form has
 *     nothing to collect, and points at Run Evaluation — which still returns a
 *     full result, as the button's continued presence here asserts.
 *   - A version with genuinely no rules keeps its own, definite sentence.
 *   - A failed load says it failed rather than borrowing the empty-version copy;
 *     collapsing "failed" onto "absent" is the constraint this fix restores.
 *   - A set with no active version says so rather than claiming no rules.
 *   - While the rules are loading, the form does not assert anything about their
 *     count.
 *
 * Nothing here is a phrase from any policy document, and no number in it measures
 * one.
 */
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import type { ApprovedPolicyVersion, CanonicalRule, PolicySet, RequiredFact } from "../api";

const listPolicySets = vi.fn();
const listPolicyVersions = vi.fn();
const getVersionRules = vi.fn();

vi.mock("../api", async () => {
  const actual = await vi.importActual<typeof import("../api")>("../api");
  return {
    ...actual,
    api: {
      ...actual.api,
      listPolicySets: (...args: unknown[]) => listPolicySets(...args),
      listPolicyVersions: (...args: unknown[]) => listPolicyVersions(...args),
      getVersionRules: (...args: unknown[]) => getVersionRules(...args),
    },
  };
});

const { EvaluatePage } = await import("./EvaluatePage");

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

beforeEach(() => {
  listPolicySets.mockReset();
  listPolicyVersions.mockReset();
  getVersionRules.mockReset();
});

afterEach(() => cleanup());

const AIS = { key: "ais-employee-handbook", name: "AIS Employee Handbook" } as PolicySet;

function version(overrides: Partial<ApprovedPolicyVersion> = {}): ApprovedPolicyVersion {
  return {
    id: "version-5",
    policy_set_id: "ais-set-id",
    version_number: 5,
    effective_from: "2024-01-01",
    effective_to: null,
    is_active: true,
    approved_by: "an-approver",
    approved_at: "2024-01-01T00:00:00Z",
    rule_count: 40,
    ...overrides,
  } as ApprovedPolicyVersion;
}

function fact(overrides: Partial<RequiredFact> = {}): RequiredFact {
  return { name: "annual_salary", data_type: "number", required: true, ...overrides };
}

function rule(overrides: Partial<CanonicalRule> = {}): CanonicalRule {
  return {
    rule_id: "R-1",
    required_facts: [],
    scope: { jurisdictions: [], organizational_units: [], processes: [] },
    ...overrides,
  } as unknown as CanonicalRule;
}

/** Wire the two lookups the page runs before it fetches rules. */
function withSetAndActiveVersion(versions: ApprovedPolicyVersion[] = [version()]) {
  listPolicySets.mockResolvedValue([AIS]);
  listPolicyVersions.mockResolvedValue(versions);
}

describe("the Evaluate form's empty state", () => {
  it("names the judged case as words to read, not a missing or empty version", async () => {
    // AIS v5 as measured: 40 rules, every one required_facts: [].
    withSetAndActiveVersion();
    getVersionRules.mockResolvedValue(Array.from({ length: 40 }, (_, i) => rule({ rule_id: `R-${i}` })));

    render(<EvaluatePage />);

    // The honest sentence: there are rules, their tests are words.
    expect(await screen.findByText(/state their tests in words/i, undefined, { timeout: 15000 })).toBeTruthy();
    expect(screen.getByText(/nothing for this form to collect/i)).toBeTruthy();

    // The contradiction the screenshot caught: a 40-rule version must not be
    // told it "may have no rules", and the old collapsed sentence is gone.
    expect(screen.queryByText(/no rules yet/i)).toBeNull();
    expect(screen.queryByText(/No required facts found/i)).toBeNull();

    // The affordance is coherent: nothing to collect does not mean nothing to
    // evaluate. Run Evaluation stays, and stays enabled.
    const run = screen.getByRole("button", { name: /run evaluation/i });
    expect(run).toBeTruthy();
    expect((run as HTMLButtonElement).disabled).toBe(false);
  });

  it("keeps a definite sentence for a version that genuinely has no rules", async () => {
    withSetAndActiveVersion();
    getVersionRules.mockResolvedValue([]);

    render(<EvaluatePage />);

    expect(await screen.findByText(/this version has no rules yet/i, undefined, { timeout: 15000 })).toBeTruthy();
    // The judged copy is for populated versions; an empty one must not borrow it.
    expect(screen.queryByText(/state their tests in words/i)).toBeNull();
    expect(screen.queryByText(/No required facts found/i)).toBeNull();
  });

  it("says a failed load failed rather than reusing the empty-version copy", async () => {
    withSetAndActiveVersion();
    getVersionRules.mockRejectedValue(new Error("network down"));

    render(<EvaluatePage />);

    expect(await screen.findByText(/could not be loaded/i, undefined, { timeout: 15000 })).toBeTruthy();
    // A failure is not an absence: none of the count-based sentences may appear.
    expect(screen.queryByText(/no rules yet/i)).toBeNull();
    expect(screen.queryByText(/state their tests in words/i)).toBeNull();
    expect(screen.queryByText(/No required facts found/i)).toBeNull();
  });

  it("says there is no active version rather than claiming no rules", async () => {
    // A set with versions but none active, viewed as "Active version (current)".
    withSetAndActiveVersion([version({ is_active: false })]);
    getVersionRules.mockResolvedValue([rule()]);

    render(<EvaluatePage />);

    expect(await screen.findByText(/no published version yet/i, undefined, { timeout: 15000 })).toBeTruthy();
    expect(screen.queryByText(/no rules yet/i)).toBeNull();
    expect(screen.queryByText(/No required facts found/i)).toBeNull();
  });

  it("settles an empty version list as no published version instead of loading forever", async () => {
    withSetAndActiveVersion([]);

    render(<EvaluatePage />);

    expect(await screen.findByText(/no published version yet/i, undefined, { timeout: 15000 })).toBeTruthy();
    expect(screen.queryByText(/loading the selected version/i)).toBeNull();
    expect(screen.getByRole("button", { name: /run evaluation/i }).closest("button")?.disabled).toBe(true);
    expect(getVersionRules).not.toHaveBeenCalled();
  });

  it("does not assert a rule count while the rules are still loading", async () => {
    withSetAndActiveVersion();
    // A fetch that never settles keeps the form in its loading state.
    getVersionRules.mockReturnValue(new Promise<CanonicalRule[]>(() => {}));

    render(<EvaluatePage />);

    expect(await screen.findByText(/loading the selected version/i, undefined, { timeout: 15000 })).toBeTruthy();
    expect(screen.queryByText(/no rules yet/i)).toBeNull();
    expect(screen.queryByText(/No required facts found/i)).toBeNull();
  });

  // Non-regression (not red before the fix): when rules do name facts, the form
  // still renders those fields and shows none of the empty-state sentences. The
  // fix leaves this path untouched; this pins that it stayed untouched.
  it("still renders the fact fields when the rules name facts", async () => {
    withSetAndActiveVersion();
    getVersionRules.mockResolvedValue([rule({ required_facts: [fact({ name: "annual_salary" })] })]);

    render(<EvaluatePage />);

    expect(await screen.findByText("annual_salary", undefined, { timeout: 15000 })).toBeTruthy();
    await waitFor(() => {
      expect(screen.queryByText(/no rules yet/i)).toBeNull();
      expect(screen.queryByText(/state their tests in words/i)).toBeNull();
      expect(screen.queryByText(/No required facts found/i)).toBeNull();
    });
  });
});
