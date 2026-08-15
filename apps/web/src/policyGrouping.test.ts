/**
 * Tests for the words a passage's route and rule count are given.
 *
 * This suite used to also cover indexing and banding — arranging a flat list of
 * rules under the passage each came from. That arrangement was removed with the
 * band it fed: the queue now draws one card per passage with its rules inside
 * it, so there is no run, no page boundary through a policy, and no
 * continuation to describe. `policyCards.test.ts` covers what replaced it.
 *
 * What is left is wording, and wording is exactly where this has gone wrong
 * before. Three phrasings have already evaded the Python guard by restatement,
 * so these assert on the labels themselves rather than on a file scan.
 */

import { describe, expect, it } from "vitest";
import {
  POLICY_ROUTE_LABELS,
  policyRouteLabel,
  policyRuleCountLabel,
} from "./policyGrouping";

describe("route wording", () => {
  it("names every route the assembling view can summarise", () => {
    // The server's summary has three outcomes and each needs words. A missing
    // one would surface a bare identifier to a reviewer.
    for (const route of ["deterministic", "ai_ready", "mixed"]) {
      const label = policyRouteLabel(route);
      expect(label).toBeTruthy();
      expect(label).not.toBe(route);
      expect(label).not.toMatch(/_/);
    }
  });

  it("says something rather than nothing for a route it does not know", () => {
    const label = policyRouteLabel("some_future_route");
    expect(label).toBeTruthy();
    expect(label).not.toContain("some_future_route");
  });

  it("says something rather than nothing when no route was recorded", () => {
    expect(policyRouteLabel(null)).toBeTruthy();
    expect(policyRouteLabel(undefined)).toBeTruthy();
    expect(policyRouteLabel("")).toBeTruthy();
  });

  it("describes a mixed policy as carrying both routes, not as compromised", () => {
    // A policy stating one computable rule and one read rule is the ordinary
    // shape of a real document. Wording that implied otherwise would make the
    // common case look like a defect.
    const label = POLICY_ROUTE_LABELS.mixed;
    expect(label).toContain("directly");
    expect(label).toContain("reading");
  });

  it("keeps every route label free of deficit framing", () => {
    const forbidden = /cannot|could not|unable|fail|missing|lack|not enough|incomplete|unsupported|only/i;
    for (const label of Object.values(POLICY_ROUTE_LABELS)) {
      expect(label).not.toMatch(forbidden);
    }
    expect(policyRouteLabel("some_future_route")).not.toMatch(forbidden);
    expect(policyRouteLabel(null)).not.toMatch(forbidden);
  });
});

describe("policyRuleCountLabel", () => {
  it("reads as an ordinary sentence for the common single-rule policy", () => {
    expect(policyRuleCountLabel(1)).toBe("1 rule");
  });

  it("pluralises beyond one", () => {
    expect(policyRuleCountLabel(3)).toBe("3 rules");
    expect(policyRuleCountLabel(11)).toBe("11 rules");
  });

  it("does not render a negative count if one ever arrives", () => {
    expect(policyRuleCountLabel(-2)).toBe("0 rules");
  });
});
