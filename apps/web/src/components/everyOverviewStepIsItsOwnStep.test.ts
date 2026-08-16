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
