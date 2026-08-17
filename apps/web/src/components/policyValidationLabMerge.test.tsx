/**
 * Tests and Regression are one Validation surface.
 *
 * WHY THIS TEST
 *
 * The two were a single component split by a `mode` prop: one tab built and
 * verified scenarios, the other managed the guards those scenarios became. A
 * guard is nothing but a verified scenario with is_active=true, so the split
 * gave one property its own page — which is exactly why the surface could not
 * say, in a sentence, what it was for. These pin the merge:
 *
 *  - One surface names its purpose in a compliance-officer sentence and shows
 *    both halves at once: the guard register (what protects the policy) and the
 *    lab beneath it (build and verify more).
 *  - Auto-re-run-on-publish reads as a PROPERTY of a guard, stated where the
 *    guards are, not as a separate "Regression" concept.
 *  - Constraint 5: the header names WHICH of the four guard states the policy is
 *    in — no guard exists, a guard passed, a guard failed, or a guard exists and
 *    has never run — rather than collapsing them into one number.
 *
 * The re-run itself is pinned on the server, where it happens
 * (`tests/unit/test_publishing_reruns_active_guards.py`). Nothing here names a
 * real policy.
 */
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { App } from "antd";
import { ActorProvider } from "../ActorContext";
import type { PolicyTestListItem } from "../api";

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
  getVersionRules.mockResolvedValue([]);
  aiStatus.mockResolvedValue({ search_enabled: false });
});

function renderLab() {
  return render(
    <App>
      <ActorProvider>
        <PolicyValidationLab policySetKey="a-key" />
      </ActorProvider>
    </App>,
  );
}

function activeVersion() {
  return {
    id: "v1",
    policy_set_id: "s1",
    version_number: 1,
    effective_from: "2024-01-01T00:00:00Z",
    effective_to: null,
    is_active: true,
    approved_by: "someone",
    approved_at: "2024-01-01T00:00:00Z",
    rule_count: 3,
  };
}

function guard(partial: Partial<PolicyTestListItem["test"]>, latestRun: PolicyTestListItem["latest_run"]): PolicyTestListItem {
  return {
    test: {
      id: "t1",
      policy_set_id: "s1",
      name: "A kept scenario",
      description: "",
      test_kind: "negative",
      input_facts: { "hours-per-week": 30 },
      evaluation_timestamp: null,
      scenario_text: "A described situation",
      generation_batch_id: null,
      expectation_hash: null,
      expectation_revealed: true,
      expected_overall_status: "NOT_SATISFIED",
      expected_rule_id: "cap",
      expected_rule_status: "NOT_SATISFIED",
      expected_missing_facts: null,
      proposed_by: "human",
      review_status: "active",
      reviewed_by: null,
      reviewed_at: null,
      review_notes: null,
      is_active: true,
      created_at: "2024-01-01T00:00:00Z",
      ...partial,
    },
    latest_run: latestRun,
    runs: latestRun ? [latestRun] : [],
  };
}

describe("Tests and Regression are one Validation surface", () => {
  it("names its purpose once and shows both halves — the guard register and the lab — with no guard present", async () => {
    listPolicyVersions.mockResolvedValue([]);
    listTests.mockResolvedValue([]);

    renderLab();

    // One compliance-officer sentence saying what the page is for — verifying
    // behavior and keeping the proofs as guards that re-run on publish.
    expect(
      await screen.findByText(/Prove a policy behaves as written/i),
    ).toBeTruthy();

    // Constraint 5: with nothing kept, the surface says WHICH state this is —
    // no guard exists — not merely "0".
    expect(screen.getByText(/No guard protects this policy yet/i)).toBeTruthy();

    // Both halves are on the one surface: the guard register's empty state and
    // the lab that builds new scenarios, together, no tab to switch.
    expect(screen.getByText(/No active regression guards yet/i)).toBeTruthy();
    expect(screen.getByText(/Build and verify a scenario/i)).toBeTruthy();
  });

  it("names the never-run state distinctly from passed or failed when a guard exists but has not run", async () => {
    listPolicyVersions.mockResolvedValue([activeVersion()]);
    // A guard exists (is_active) but has never run — a fourth state, distinct
    // from passing and failing, and the surface must say so.
    listTests.mockResolvedValue([guard({}, null)]);

    renderLab();

    expect(await screen.findByText(/Prove a policy behaves as written/i)).toBeTruthy();

    await waitFor(() => expect(screen.getByText(/1 active guard/i)).toBeTruthy());
    // The four states are not collapsed: never-run reads as awaiting a first
    // run, not as passing and not as failing.
    expect(screen.getByText(/awaiting a first run/i)).toBeTruthy();
    expect(screen.queryByText(/No guard protects this policy yet/i)).toBeNull();
    expect(screen.queryByText(/All guards passing/i)).toBeNull();
  });
});
