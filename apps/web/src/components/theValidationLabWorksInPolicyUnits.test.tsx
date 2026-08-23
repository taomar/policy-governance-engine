/**
 * The Validation lab works in policy units, and shows both routes.
 *
 * TWO DEFECTS THIS PINS
 *
 * 1. THE UNIT. A policy is what this product decides as a whole; its rules are
 *    read within it. The lab selected and counted *rules* while calling them
 *    policies in its own copy — the header printed `selectedRuleIds.size`
 *    followed by the word "policies", and the batch line multiplied a rule
 *    count by tests-per-policy and called the product "N policies × M tests".
 *    Whenever one policy held more than one engine-decided rule those numbers
 *    were simply wrong, and a reader had no way to tell which unit any figure
 *    was in.
 *
 * 2. THE ROUTE. `executableRules` filtered out every rule that is not
 *    machine-executable *before the selector saw it*. On the live corpus that
 *    is the whole document: 56 of 56 published rules on the largest project
 *    take the AI Ready route. The reader was shown an empty list and a dead
 *    button, which reads as "this version is empty" rather than "these rules
 *    are decided by a judge". AI Ready is a route, not a gap — it is the
 *    majority route — so the lab has to show it and say what happens to it.
 *
 * These tests use a MIXED policy, because a policy holding both an
 * engine-decided rule and judged ones is the case that separates the two units:
 * one policy, several rules, and the two numbers necessarily differ.
 */
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { App } from "antd";
import { ActorProvider } from "../ActorContext";
import type { CanonicalRule } from "../api";

const listPolicyVersions = vi.fn();
const getVersionRules = vi.fn();
const listVersionPolicies = vi.fn();
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
      listVersionPolicies: (...args: unknown[]) => listVersionPolicies(...args),
    },
    policyTestApi: {
      ...actual.policyTestApi,
      listBatches: (...args: unknown[]) => listBatches(...args),
      list: (...args: unknown[]) => listTests(...args),
    },
    aiApi: { ...actual.aiApi, status: (...args: unknown[]) => aiStatus(...args) },
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

function rule(id: string, engineDecided: boolean, ruleType = "obligation"): CanonicalRule {
  return {
    schema_version: "1.0",
    policy_set_id: "s1",
    policy_version_id: "v1",
    rule_id: id,
    rule_revision: 1,
    title: `Rule ${id}`,
    description: "",
    rule_type: ruleType,
    authority: { owner: "o", source: "", reference: "" },
    scope: { jurisdictions: [], organizational_units: [], processes: [] },
    condition: { type: "all", all: [] },
    evaluation_mode: engineDecided ? "deterministic" : "ai_ready",
    effect: { type: "require_action", action: "do the thing" },
    required_facts: [],
    exceptions: [],
    priority: 0,
    effective_from: "2024-01-01",
    effective_to: null,
    machine_executable: engineDecided,
    ambiguity_status: "clear",
    review_status: "published",
    evidence: [],
  } as unknown as CanonicalRule;
}

/** One policy holding TWO engine-decided rules and three judged ones.
 *
 *  Two engine-decided rules, deliberately. With one, the policy count and the
 *  rule count are both 1 and every assertion below passes whichever unit the
 *  component uses — a fixture that cannot fail is the defect it is meant to
 *  catch, wearing a green tick. With two, the units differ (1 policy, 2 rules)
 *  and printing one where the other belongs is visible.
 */
const MIXED_RULES = [
  rule("R-engine-1", true),
  rule("R-engine-2", true),
  rule("R-a", false),
  rule("R-b", false),
  rule("R-c", false),
];

beforeEach(() => {
  cleanup();
  for (const spy of [listPolicyVersions, getVersionRules, listVersionPolicies, listBatches, listTests, aiStatus]) {
    spy.mockReset();
  }
  listBatches.mockResolvedValue([]);
  listTests.mockResolvedValue([]);
  aiStatus.mockResolvedValue({ search_enabled: false });
  listPolicyVersions.mockResolvedValue([
    {
      id: "v1",
      policy_set_id: "s1",
      version_number: 1,
      effective_from: "2024-01-01T00:00:00Z",
      effective_to: null,
      is_active: true,
      approved_by: "someone",
      approved_at: "2024-01-01T00:00:00Z",
      rule_count: 5,
    },
  ]);
  getVersionRules.mockResolvedValue(MIXED_RULES);
  listVersionPolicies.mockResolvedValue([
    {
      provision_id: "p1",
      key: "2-leave",
      heading: "2. Pregnancy and Maternity Leave",
      heading_path: ["2. Pregnancy and Maternity Leave"],
      document_version_id: "d1",
      source_elements: "",
      page: 1,
      passage_count: 1,
      rule_count: 5,
      route: "mixed",
      passages: [],
      rules: MIXED_RULES.map((r) => ({ rule_id: r.rule_id, title: r.title })),
    },
  ]);
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

describe("the lab presents the version in policy units", () => {
  it("draws one row per policy, not a flat list of rules", async () => {
    const { container } = renderLab();
    await waitFor(() => {
      expect(container.querySelectorAll(".validation-policy-group__head").length).toBe(1);
    });
    expect(screen.getAllByText(/2\. Pregnancy and Maternity Leave/).length).toBeGreaterThan(0);
  });

  it("counts policies in policies and rules in rules, never one as the other", async () => {
    const { container } = renderLab();
    const head = await waitFor(() => {
      const node = container.querySelector(".validation-policy-group__head");
      expect(node).toBeTruthy();
      return node as HTMLElement;
    });

    // The policy's own summary states its composition in rules, under a policy.
    expect(head.textContent).toContain("5 rules");
    expect(head.textContent).toContain("2 engine-decided");
    expect(head.textContent).toContain("3 judged");

    // The scope line leads with the policy count. Before this change it read
    // "Showing N of M rules" while the surrounding heading said "Policies".
    const scope = await screen.findByTestId("validation-lab-scope");
    expect(scope.textContent).toMatch(/Showing 1 policy/);
    expect(scope.textContent).toMatch(/5 rules/);
  });

  it("shows the judged rules rather than filtering them out of existence", async () => {
    const { container } = renderLab();
    await waitFor(() => {
      expect(container.querySelectorAll(".validation-rule-row").length).toBe(5);
    });
    // All three judged rules are on screen. They used to be removed before the
    // selector saw them, so a version of only judged rules looked empty.
    for (const id of ["R-a", "R-b", "R-c"]) {
      expect(screen.getAllByText(new RegExp(id)).length).toBeGreaterThan(0);
    }
  });

  it("names the policy's route rather than calling the judged majority missing", async () => {
    const { container } = renderLab();
    const head = await waitFor(() => {
      const node = container.querySelector(".validation-policy-group__head");
      expect(node).toBeTruthy();
      return node as HTMLElement;
    });
    expect(head.textContent).toContain("Mixed route");
  });
});

describe("selecting works in policy units", () => {
  it("selecting the policy selects the rules within it that the engine runs", async () => {
    const { container } = renderLab();
    const head = await waitFor(() => {
      const node = container.querySelector(".validation-policy-group__head");
      expect(node).toBeTruthy();
      return node as HTMLElement;
    });

    fireEvent.click(within(head).getByRole("checkbox"));

    await waitFor(() => {
      // One policy, one engine-decided rule inside it. Both stated, each in its
      // own unit — the header used to print the rule count and say "policies".
      expect(screen.getByText(/1 of 1 policy selected/)).toBeTruthy();
    });
    expect(screen.getByText(/2 rules the engine will run/)).toBeTruthy();
  });
});
