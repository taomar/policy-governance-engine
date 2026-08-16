/**
 * The review tabs and the decision-progress line count one population, and they
 * must count it in policies whenever they honestly can (constraint 2 — a policy
 * is the unit of counting).
 *
 * Two populations are in play. `facetTotals` is the server's tally over the whole
 * policy set. The local counts are assembled from the rows the queue holds, which
 * `loadCandidates` scopes to the selected document or run server-side (review
 * status and delta status are never sent — they narrow which rows are *shown*, not
 * which are *loaded*, so the local counts are always of whole policies).
 *
 * The defect these tests pin: under a document/run scope the whole-set facet tally
 * counts a *different* population than the scoped rows the policy figures come
 * from. The queue used to lead the tabs with that whole-set tally and then, seeing
 * it disagree with the scoped local rule counts, withhold the policy figures
 * altogether — so a scoped queue read "398 rules" with the policy count gone, when
 * the scoped policy count was sitting right there, honest and paired with the
 * scoped rule count. The fix counts the scoped population: rules and policies from
 * the one set of rows, a matched pair, so policies lead under the filter too.
 */
import { describe, expect, it } from "vitest";

import { reviewTabCounts } from "./reviewTabCounts";

// A document scope (e.g. one handbook). The whole set is larger and its per-status
// rule totals differ from the scoped rows'.
const WHOLE_SET_FACETS = { candidate: 340, approved: 4, published: 55 }; // sum 399
const SCOPED_RULE_COUNTS = { candidate: 366, approved: 4, published: 28 }; // sum 398
const SCOPED_POLICY_COUNTS = { candidate: 18, approved: 1, published: 13 };
const SCOPED_TOTAL_RULES = 398;
const SCOPED_TOTAL_POLICIES = 32;

describe("under a document or run scope, the scoped policy figures are not withheld", () => {
  it("shows the scoped policy counts even though the whole-set facets disagree", () => {
    const result = reviewTabCounts({
      scopeActive: true,
      facetTotals: WHOLE_SET_FACETS,
      localRuleCounts: SCOPED_RULE_COUNTS,
      localPolicyCounts: SCOPED_POLICY_COUNTS,
      totalRules: SCOPED_TOTAL_RULES,
      totalPolicyUnits: SCOPED_TOTAL_POLICIES,
    });
    // The crux: policies survive the filter. Under a scope the tabs must still be
    // able to lead with policies, because the scoped rule count and the scoped
    // policy count are two measurements of the one set of rows.
    expect(result.policyCounts).not.toBeNull();
    expect(result.policyCounts?.candidate).toBe(18);
    expect(result.totalPolicies).toBe(32);
  });

  it("shows the scoped rule counts, not the whole-set facet tally", () => {
    const result = reviewTabCounts({
      scopeActive: true,
      facetTotals: WHOLE_SET_FACETS,
      localRuleCounts: SCOPED_RULE_COUNTS,
      localPolicyCounts: SCOPED_POLICY_COUNTS,
      totalRules: SCOPED_TOTAL_RULES,
      totalPolicyUnits: SCOPED_TOTAL_POLICIES,
    });
    // Under a scope the queue shows the scoped population, so a reviewer never
    // reads a whole-set number (399) over a queue filtered to one document (398).
    expect(result.counts.candidate).toBe(366);
    expect(result.total).toBe(398);
  });

  it("pairs the rule counts and the policy counts from the same population", () => {
    // With no facets loaded at all the local counts are all there is, and they are
    // internally consistent by construction, so policies lead here too.
    const result = reviewTabCounts({
      scopeActive: true,
      facetTotals: null,
      localRuleCounts: SCOPED_RULE_COUNTS,
      localPolicyCounts: SCOPED_POLICY_COUNTS,
      totalRules: SCOPED_TOTAL_RULES,
      totalPolicyUnits: SCOPED_TOTAL_POLICIES,
    });
    expect(result.counts).toBe(SCOPED_RULE_COUNTS);
    expect(result.total).toBe(398);
    expect(result.policyCounts).not.toBeNull();
    expect(result.totalPolicies).toBe(32);
  });
});

describe("with no scope, the whole-set facet tally leads", () => {
  it("leads the tabs with the server's whole-set rule tally when it agrees", () => {
    // Unscoped, the local rows are the whole set, so the two agree and both the
    // authoritative rule tally and the policy figures are shown.
    const wholeSetRules = { candidate: 340, approved: 4, published: 55 };
    const result = reviewTabCounts({
      scopeActive: false,
      facetTotals: wholeSetRules,
      localRuleCounts: wholeSetRules,
      localPolicyCounts: { candidate: 30, approved: 1, published: 51 },
      totalRules: 399,
      totalPolicyUnits: 82,
    });
    expect(result.counts).toBe(wholeSetRules);
    expect(result.total).toBe(399);
    expect(result.policyCounts).not.toBeNull();
    expect(result.totalPolicies).toBe(82);
  });

  it("withholds the policy figures when the whole-set tally and the local rows disagree", () => {
    // For a moment after an approval the server facets lag the rows the queue
    // holds. Pairing a stale whole-set rule count with a fresh local policy count
    // would put two measurements of one thing on one strip, so the policy figures
    // are withheld and every tab falls back to its (whole-set) rule count.
    const result = reviewTabCounts({
      scopeActive: false,
      facetTotals: { candidate: 340, approved: 4, published: 55 },
      localRuleCounts: { candidate: 339, approved: 5, published: 55 },
      localPolicyCounts: { candidate: 29, approved: 2, published: 51 },
      totalRules: 399,
      totalPolicyUnits: 82,
    });
    expect(result.policyCounts).toBeNull();
    expect(result.totalPolicies).toBeNull();
    // The rule counts still come from the server's whole-set tally.
    expect(result.counts.candidate).toBe(340);
  });
});

describe("the delta filter never enters this count", () => {
  it("counts whole policies under a scope regardless of any delta narrowing", () => {
    // A delta filter ("New"/"Changed"/"Unchanged") narrows which rows are shown,
    // not which are loaded, so it never reaches these inputs: there is no delta
    // parameter here. A policy with some rules matching a delta filter is still
    // one whole policy in this count, which agrees with the queue's own sentence
    // that each policy lists every rule, including rules the filter did not select.
    const result = reviewTabCounts({
      scopeActive: true,
      facetTotals: WHOLE_SET_FACETS,
      localRuleCounts: SCOPED_RULE_COUNTS,
      localPolicyCounts: SCOPED_POLICY_COUNTS,
      totalRules: SCOPED_TOTAL_RULES,
      totalPolicyUnits: SCOPED_TOTAL_POLICIES,
    });
    expect(result.policyCounts?.candidate).toBe(18);
    expect(result.totalPolicies).toBe(32);
  });
});
