import { describe, expect, it } from "vitest";
import { recordScaleBadge, reviewBacklogBadge } from "./policyRecordFacts";

/**
 * THE POLICIES TAB IS BADGED IN POLICIES.
 *
 * The project tab strip badged its "Policies" tab with the endpoint's rule count
 * for the active published version: on a version of two policies holding
 * twenty-eight rules the pill read "Policies 28", four times the two policies
 * that are actually live. A count under a policy label has to be policies —
 * *the policy is the currency* — with the rule count carried beside it, never
 * standing in for it.
 *
 * The Review tab already solved this with `reviewBacklogBadge`: the pill leads
 * with the policy count and the hover names both numbers. `recordScaleBadge` is
 * that same lead-with-policies logic made general, so the publish tab cannot say
 * the same thing a second, divergent way. These tests pin it for the Policies
 * tab's wording.
 *
 * THE SECOND FAILURE THIS GUARDS
 *
 * The policy figure comes from a server field a not-yet-restarted server does
 * not send. Reading that absence as zero would badge an empty tab over a version
 * that plainly holds rules. Absent must fall back to the rule count and say it is
 * showing rules; it must never invent a policy figure or a zero nobody measured.
 */

const PUBLISHED = "in the currently active published version.";

describe("recordScaleBadge — the Policies tab badge", () => {
  it("leads with policies, not the rule count under a policy label", () => {
    expect(recordScaleBadge(28, 2, PUBLISHED).value).toBe(2);
  });

  it("keeps the rule count beside it, because a policy is made of rules", () => {
    const badge = recordScaleBadge(28, 2, PUBLISHED);
    expect(badge.hint).toContain("2 policies");
    expect(badge.hint).toContain("28 rules");
  });

  it("says what the pair is being counted for", () => {
    expect(recordScaleBadge(28, 2, PUBLISHED).hint).toBe(
      `2 policies · 28 rules ${PUBLISHED}`,
    );
  });

  it("shows the same number the hint leads with, so the two cannot disagree", () => {
    for (const [rules, policies] of [
      [28, 2],
      [40, 8],
      [1, 1],
    ] as const) {
      const badge = recordScaleBadge(rules, policies, PUBLISHED);
      expect(badge.hint.startsWith(String(badge.value))).toBe(true);
    }
  });

  it("agrees with itself about one", () => {
    expect(recordScaleBadge(1, 1, PUBLISHED).hint).toContain("1 policy · 1 rule");
  });

  it("falls back to the rule count, and names it, when policies are not served", () => {
    const badge = recordScaleBadge(28, undefined, PUBLISHED);
    expect(badge.value).toBe(28);
    expect(badge.hint).toContain("28 rules");
  });

  it("does not read an unserved policy count as none published", () => {
    const badge = recordScaleBadge(28, undefined, PUBLISHED);
    expect(badge.value).not.toBe(0);
    expect(badge.value).not.toBeNull();
    expect(badge.hint).not.toContain("0 polic");
  });

  it("does not claim a policy unit it was not given", () => {
    expect(recordScaleBadge(28, undefined, PUBLISHED).hint).not.toMatch(/polic/i);
  });

  it("withholds the pill when the version really is empty, but states the measured zero", () => {
    // No active version: the server measured zero of both. The pill is withheld
    // (a row of "0" pills is clutter), yet the hover still reports the zero it
    // measured -- which a reader can tell apart from the rule-count fallback above.
    const badge = recordScaleBadge(0, 0, PUBLISHED);
    expect(badge.value).toBeNull();
    expect(badge.hint).toBe(`0 policies · 0 rules ${PUBLISHED}`);
  });

  it("withholds the pill for zero policies over rules, without inventing a number", () => {
    expect(recordScaleBadge(28, 0, PUBLISHED).value).toBeNull();
  });

  it("says something even before any count has arrived", () => {
    const badge = recordScaleBadge(undefined, undefined, PUBLISHED);
    expect(badge.value).toBeNull();
    expect(badge.hint.trim().length).toBeGreaterThan(0);
    expect(badge.hint).not.toMatch(/\d/);
  });

  it("ranks no route and calls no version a shortfall", () => {
    for (const badge of [
      recordScaleBadge(28, 2, PUBLISHED),
      recordScaleBadge(28, undefined, PUBLISHED),
      recordScaleBadge(undefined, undefined, PUBLISHED),
    ]) {
      expect(badge.hint).not.toMatch(
        /deterministic|ai.ready|unread|cannot|fail|gap|limitation|incomplete|missing/i,
      );
    }
  });
});

describe("reviewBacklogBadge still reads the review wording after generalisation", () => {
  it("keeps its exact clause, so the review tab is unchanged", () => {
    expect(reviewBacklogBadge(398, 70).hint).toBe("70 policies · 398 rules waiting for a decision.");
  });

  it("still leads with policies", () => {
    expect(reviewBacklogBadge(398, 70).value).toBe(70);
  });
});
