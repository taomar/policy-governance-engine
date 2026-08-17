/**
 * A guard that has never run still names the rule it guards.
 *
 * WHY THIS TEST
 *
 * The guard register resolved a guard's rule only against the version its LAST
 * RUN evaluated. A guard kept from the case dialog and not yet run has no last
 * run, so that lookup found nothing and the row read "Policy record loading…"
 * forever — a permanent loading state that is indistinguishable from a failure,
 * the exact constraint-5 collapse the surface avoids everywhere else.
 *
 * The rule is not missing: it lives in the active published version, whose rules
 * the surface already holds. A never-run guard must resolve its rule against that
 * version and NAME it. And a guard whose rule genuinely is not in the shown
 * version must say so — "this rule is not in this version" — because guards
 * outlive the versions they cite. Neither is a spinner.
 *
 * Nothing here names a real policy.
 */
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { App } from "antd";
import { ActorProvider } from "../ActorContext";
import type { ApprovedPolicyVersion, CanonicalRule, PolicyTestListItem } from "../api";

const listPolicyVersions = vi.fn();
const getVersionRules = vi.fn();
const listBatches = vi.fn();
const listTests = vi.fn();
const aiStatus = vi.fn();

vi.mock("../api", async () => {
  const actual = await vi.importActual<typeof import("../api")>("../api");
  return {
    ...actual,
    api: {
      ...actual.api,
      listPolicyVersions: (...args: unknown[]) => listPolicyVersions(...args),
      getVersionRules: (...args: unknown[]) => getVersionRules(...args),
    },
    policyTestApi: {
      ...actual.policyTestApi,
      listBatches: (...args: unknown[]) => listBatches(...args),
      list: (...args: unknown[]) => listTests(...args),
    },
    aiApi: {
      ...actual.aiApi,
      status: (...args: unknown[]) => aiStatus(...args),
    },
  };
});

const { PolicyValidationLab } = await import("./PolicyValidationLab");

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
  listPolicyVersions.mockReset();
  getVersionRules.mockReset();
  listBatches.mockReset();
  listTests.mockReset();
  aiStatus.mockReset();
  listBatches.mockResolvedValue([]);
  aiStatus.mockResolvedValue({ search_enabled: false });
});

function activeVersion(): ApprovedPolicyVersion {
  return {
    id: "v1",
    policy_set_id: "s1",
    version_number: 1,
    effective_from: "2024-01-01T00:00:00Z",
    effective_to: null,
    is_active: true,
    approved_by: "someone",
    approved_at: "2024-01-01T00:00:00Z",
    rule_count: 1,
  } as unknown as ApprovedPolicyVersion;
}

function rule(id: string, title: string): CanonicalRule {
  return {
    rule_id: id,
    title,
    description: "",
    rule_type: "obligation",
    effect: { type: "deny", action: "work" },
    evaluation_mode: "deterministic",
    machine_executable: true,
    condition: { type: "all", all: [] },
    required_facts: [],
    evidence: [],
    exceptions: [],
    scope: {
      personas: [],
      organizational_units: [],
      jurisdictions: [],
      processes: [],
    },
    source: { document_id: "d", quotes: [] },
    lineage: { extraction_run_id: "r" },
  } as unknown as CanonicalRule;
}

function neverRunGuard(expectedRuleId: string): PolicyTestListItem {
  return {
    test: {
      id: "t1",
      policy_set_id: "s1",
      name: "A kept case",
      description: "",
      test_kind: "negative",
      input_facts: { "cap-days": 75 },
      evaluation_timestamp: null,
      scenario_text: "An employee requests 75 days",
      generation_batch_id: null,
      expectation_hash: null,
      expectation_revealed: true,
      expected_overall_status: "NOT_SATISFIED",
      expected_rule_id: expectedRuleId,
      expected_rule_status: "NOT_SATISFIED",
      expected_missing_facts: null,
      proposed_by: "human",
      review_status: "active",
      reviewed_by: null,
      reviewed_at: null,
      review_notes: null,
      is_active: true,
      created_at: "2024-01-01T00:00:00Z",
    },
    latest_run: null,
    runs: [],
  } as unknown as PolicyTestListItem;
}

function renderLab() {
  return render(
    <App>
      <ActorProvider>
        <PolicyValidationLab policySetKey="a-key" />
      </ActorProvider>
    </App>,
  );
}

describe("a never-run guard still names its rule", () => {
  it("resolves the rule from the active published version, not from a run it never had", async () => {
    listPolicyVersions.mockResolvedValue([activeVersion()]);
    getVersionRules.mockResolvedValue([rule("cap", "Part-time hours are capped at 24 per week")]);
    listTests.mockResolvedValue([neverRunGuard("cap")]);

    renderLab();

    // The guard is present and never-run...
    await waitFor(() => expect(screen.getByText(/1 active guard/i)).toBeTruthy());

    // ...and its rule is NAMED in the guard row from the active version, not
    // left spinning. Scope to the register row: the version's rule list names
    // the same rule elsewhere, which is legitimate and not what this asserts.
    await waitFor(() => {
      const row = document.querySelector(".validation-suite-row");
      expect(row).toBeTruthy();
      expect(row?.textContent).toMatch(/Part-time hours are capped at 24 per week/i);
    });
    const row = document.querySelector(".validation-suite-row");
    expect(row?.textContent).not.toMatch(/Policy record loading/i);
  });

  it("says a rule is not in the shown version rather than spinning, because guards outlive versions", async () => {
    listPolicyVersions.mockResolvedValue([activeVersion()]);
    // The active version holds a different rule; the guard cites one no longer here.
    getVersionRules.mockResolvedValue([rule("other", "Some other rule")]);
    listTests.mockResolvedValue([neverRunGuard("cap-retired")]);

    renderLab();

    await waitFor(() => expect(screen.getByText(/1 active guard/i)).toBeTruthy());

    await waitFor(() => {
      const row = document.querySelector(".validation-suite-row");
      expect(row).toBeTruthy();
      expect(row?.textContent).toMatch(/not in this version/i);
    });
    const row = document.querySelector(".validation-suite-row");
    expect(row?.textContent).not.toMatch(/Policy record loading/i);
  });
});
