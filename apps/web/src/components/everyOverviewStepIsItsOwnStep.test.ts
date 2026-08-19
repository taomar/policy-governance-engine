/**
 * Every step in the project-overview flow is its own step.
 *
 * WHY THIS TEST
 *
 * The overview draws the project lifecycle as a row of steps, and React reconciles
 * that row by each step's `key`. Two of the steps -- "awaiting review" and
 * "approved, not yet live" -- are both worked from the same Review tab, and both
 * once carried the key "review". Two siblings sharing a key is a real defect:
 * React keys the row by it, so on a re-render one of the pair can be dropped or can
 * inherit the other's state. The failure that matters to a reviewer is the first:
 * four stages in the data, three on the screen, and the missing one is a number --
 * "how many are approved but not yet live" -- not just a console warning.
 *
 * The assertion is over the whole array, not the two known offenders, so it keeps
 * holding when a fifth step is added. Sharing a *destination* is legitimate and
 * stays legitimate; sharing an *identity* is what this forbids.
 */
import { describe, expect, it } from "vitest";
import { buildOverviewSteps, type Stats } from "./ProjectOverviewTab";
import { describePolicyIndexState, policyIndexRepairable } from "../policyIndexHealth";
import type { PolicyIndexState } from "../api";

/** A fully-loaded stats object. `activeVersion` is null because the flow reads only
 *  its `rule_count`, and the last step falls back to 0 without it -- none of which
 *  bears on a step's identity, which is what these tests pin. */
const loadedStats: Stats = {
  documentCount: 6,
  activeVersion: null,
  versionCount: 0,
  pendingCandidateCount: 9,
  approvedCandidateCount: 4,
  pendingPolicyCount: 5,
  approvedPolicyCount: 3,
  directRouteCount: 0,
  readingRouteCount: 0,
  liveRuleCount: 0,
  sourceGroundedRuleCount: 0,
};

describe("every overview step keeps its own key", () => {
  it("gives no two steps the same key, so React reconciles and drops none", () => {
    const keys = buildOverviewSteps(loadedStats, loadedStats.pendingCandidateCount).map(
      (step) => step.key,
    );
    expect(new Set(keys).size).toBe(keys.length);
  });

  it("keeps keys distinct in the not-yet-loaded state too", () => {
    // Before stats arrive every value is a placeholder and the awaiting-review
    // label flips to its empty wording. Identity must survive that unchanged.
    const keys = buildOverviewSteps(null, 0).map((step) => step.key);
    expect(new Set(keys).size).toBe(keys.length);
  });

  it("does not let a key ride on a label that changes with the data", () => {
    // The awaiting-review step's label toggles with `pending`; its identity must
    // not. Same steps, same order, same keys, whatever the state.
    const loaded = buildOverviewSteps(loadedStats, 9).map((s) => s.key);
    const empty = buildOverviewSteps(null, 0).map((s) => s.key);
    expect(loaded).toEqual(empty);
  });
});

describe("two steps may share a destination without sharing an identity", () => {
  it("sends both review-stage steps to the Review tab, as two distinct steps", () => {
    const steps = buildOverviewSteps(loadedStats, 9);
    const toReview = steps.filter((s) => s.nav === "review");
    // Awaiting-review and approved-not-live are both decided from Review, so both
    // navigate there -- which is exactly why they once collided on the key.
    expect(toReview).toHaveLength(2);
    // ...and yet they are two separate steps.
    expect(new Set(toReview.map((s) => s.key)).size).toBe(2);
  });

  it("points every step at a real, reachable project tab", () => {
    // A key renamed only to silence the React warning must never leak into the
    // click target: ProjectWorkspace's navigate guard silently drops an unknown
    // page, so a mistyped nav would strand the step. These are the tabs this flow
    // legitimately reaches.
    const destinations = new Set(["documents", "review", "policies"]);
    for (const step of buildOverviewSteps(loadedStats, 9)) {
      expect(destinations.has(step.nav)).toBe(true);
    }
  });
});

function policyIndexState(
  last_attempt: PolicyIndexState["last_attempt"],
  freshness: PolicyIndexState["freshness"],
  overrides: Partial<PolicyIndexState> = {},
): PolicyIndexState {
  return {
    policy_set_key: "a-set",
    index_name: "policy-cases-a-set",
    last_attempt,
    freshness,
    active_version_number: 2,
    indexed_version_number: null,
    attempted_version_number: null,
    document_count: 0,
    built_at: null,
    attempted_at: null,
    error: null,
    source: "recorded_build_state",
    live_probe: false,
    ...overrides,
  };
}

describe("policy index state is composed for a reader", () => {
  it("states a current built index quietly", () => {
    const copy = describePolicyIndexState(
      policyIndexState("built", "current", { indexed_version_number: 6, document_count: 10 }),
    );
    expect(copy.title).toContain("up to date");
    expect(copy.statusLabel).toBe("Current");
    expect(copy.tone).toBe("success");
  });

  it("turns never attempted plus stale into never built and offers repair", () => {
    const state = policyIndexState("never_attempted", "stale");
    const copy = describePolicyIndexState(state);
    // Pins the fact, not the sentence: no build has been recorded. The copy
    // deliberately stops short of predicting live retrieval, which this
    // recorded state never probed.
    expect(copy.statusLabel).toBe("Never built");
    expect(copy.tone).toBe("warning");
    expect(policyIndexRepairable(state)).toBe(true);
  });

  it("does not alarm when a failed attempt leaves a current index usable", () => {
    const state = policyIndexState("failed", "current", { indexed_version_number: 2, document_count: 12 });
    const copy = describePolicyIndexState(state);
    expect(copy.statusLabel).toBe("Current despite failed attempt");
    expect(copy.tone).toBe("success");
    expect(policyIndexRepairable(state)).toBe(false);
  });

  it("does not present nothing-to-index as broken or repairable", () => {
    const state = policyIndexState("built", "nothing_to_index", {
      active_version_number: null,
      indexed_version_number: null,
    });
    const copy = describePolicyIndexState(state);
    expect(copy.statusLabel).toBe("Nothing to index");
    expect(copy.tone).toBe("info");
    expect(policyIndexRepairable(state)).toBe(false);
  });

  it("treats skipped as search configuration, not a project defect", () => {
    const state = policyIndexState("skipped", "unknown", { indexed_version_number: null });
    const copy = describePolicyIndexState(state);
    expect(copy.title).toContain("not configured");
    expect(copy.tone).toBe("info");
    expect(policyIndexRepairable(state)).toBe(false);
  });

  it("still says the index is behind when a skipped attempt left a known version", () => {
    // Skipping does not erase what was last indexed, so a version the record
    // can prove is behind is stated rather than withheld. Saying only "not
    // configured" beside an Active v3 / Indexed v2 facts list would deny what
    // the panel is showing.
    const state = policyIndexState("skipped", "stale", {
      active_version_number: 3,
      indexed_version_number: 2,
    });
    const copy = describePolicyIndexState(state);
    expect(copy.title).toContain("not configured");
    expect(copy.detail).toContain("v2");
    expect(copy.detail).toContain("v3");
    expect(copy.tone).toBe("info");
    // Still not repairable here: no rebuild succeeds while Search is absent.
    expect(policyIndexRepairable(state)).toBe(false);
  });
});
