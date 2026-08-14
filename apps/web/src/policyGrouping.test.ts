/**
 * Tests for arranging the review queue by passage.
 *
 * The population here is synthetic on purpose. The shapes it must survive --
 * a policy of one rule, a policy split by pagination, a rule the server did not
 * place -- are properties of the arrangement rather than of any document, and
 * pinning them to a measured corpus would make the suite depend on a database
 * that has already been emptied once this session.
 *
 * Controls sit beside offenders throughout. A suite containing only the cases
 * that were wrong cannot tell you when a fix has begun over-reaching, and one
 * did exactly that earlier today.
 */

import { describe, expect, it } from "vitest";
import type { AssembledPolicy } from "./api";
import {
  POLICY_ROUTE_LABELS,
  indexPoliciesByRule,
  policyBands,
  policyHeaderSummary,
  policyRouteLabel,
  policyRuleCountLabel,
} from "./policyGrouping";

function policy(
  key: string,
  ruleIds: string[],
  overrides: Partial<AssembledPolicy> = {},
): AssembledPolicy {
  return {
    key,
    source_elements: key,
    page: 4,
    rule_count: ruleIds.length,
    route: "ai_ready",
    rules: ruleIds.map((rule_id) => ({
      rule_id,
      title: `title ${rule_id}`,
      evaluation_mode: "ai_ready",
    })),
    ...overrides,
  };
}

describe("indexPoliciesByRule", () => {
  it("finds the policy for every rule the server placed", () => {
    const index = indexPoliciesByRule([
      policy("p4-E000007", ["read", "understand", "comply"]),
      policy("p5-E000011", ["notice"]),
    ]);

    expect(index.size).toBe(4);
    expect(index.get("read")?.key).toBe("p4-E000007");
    expect(index.get("understand")?.key).toBe("p4-E000007");
    expect(index.get("comply")?.key).toBe("p4-E000007");
    expect(index.get("notice")?.key).toBe("p5-E000011");
  });

  it("puts the three obligations of one sentence under one policy", () => {
    // The owner's case: one sentence, three cards. They must resolve to a
    // single key or the queue will keep showing them as unrelated.
    const index = indexPoliciesByRule([
      policy("p4-E000007", ["686a7fff", "8517388a", "e702bb79"]),
    ]);

    const keys = new Set(
      ["686a7fff", "8517388a", "e702bb79"].map((id) => index.get(id)?.key),
    );
    expect(keys.size).toBe(1);
  });

  it("leaves a rule the server did not place unindexed rather than guessing", () => {
    const index = indexPoliciesByRule([policy("p4-E000007", ["read"])]);
    expect(index.get("unplaced")).toBeUndefined();
  });

  it("is empty for an empty assembly, without throwing", () => {
    expect(indexPoliciesByRule([]).size).toBe(0);
  });
});

describe("policyBands", () => {
  it("gives the header to the first row of each policy and to no other", () => {
    const index = indexPoliciesByRule([
      policy("p4-E000007", ["read", "understand", "comply"]),
    ]);
    const bands = policyBands(["read", "understand", "comply"], index);

    expect(bands.get("read")?.isStart).toBe(true);
    expect(bands.get("understand")?.isStart).toBe(false);
    expect(bands.get("comply")?.isStart).toBe(false);
  });

  it("treats a policy of one rule as an ordinary policy", () => {
    // CONTROL. Most policies hold one rule. If this shape needed different
    // handling the common case would be the exception, which is backwards.
    const index = indexPoliciesByRule([policy("p9-E000042", ["single"])]);
    const bands = policyBands(["single"], index);
    const band = bands.get("single");

    expect(band).toBeDefined();
    expect(band?.isStart).toBe(true);
    expect(band?.inView).toBe(1);
    expect(band?.total).toBe(1);
    expect(band?.continuesAbove).toBe(false);
    expect(band?.continuesBelow).toBe(false);
  });

  it("says so when a page shows only the start of a policy", () => {
    const index = indexPoliciesByRule([
      policy("p4-E000007", ["read", "understand", "comply"]),
    ]);
    const bands = policyBands(["read"], index);

    expect(bands.get("read")?.inView).toBe(1);
    expect(bands.get("read")?.total).toBe(3);
    expect(bands.get("read")?.continuesAbove).toBe(false);
    expect(bands.get("read")?.continuesBelow).toBe(true);
  });

  it("says so when a page shows only the end of a policy", () => {
    const index = indexPoliciesByRule([
      policy("p4-E000007", ["read", "understand", "comply"]),
    ]);
    const bands = policyBands(["comply"], index);

    expect(bands.get("comply")?.continuesAbove).toBe(true);
    expect(bands.get("comply")?.continuesBelow).toBe(false);
  });

  it("says so when a filter removes a rule from the middle of a policy", () => {
    // The missing rule is neither above nor below the run's edges, so the
    // count is the only thing that reveals it. It must still not read as whole.
    const index = indexPoliciesByRule([
      policy("p4-E000007", ["read", "understand", "comply"]),
    ]);
    const bands = policyBands(["read", "comply"], index);

    expect(bands.get("read")?.inView).toBe(2);
    expect(bands.get("read")?.total).toBe(3);
  });

  it("reports a whole policy as whole", () => {
    // CONTROL against the three fragmentation cases above. If continuation is
    // reported on a complete policy, every header gains a caveat it has not
    // earned and the signal stops meaning anything.
    const index = indexPoliciesByRule([
      policy("p4-E000007", ["read", "understand", "comply"]),
    ]);
    const bands = policyBands(["read", "understand", "comply"], index);

    for (const id of ["read", "understand", "comply"]) {
      expect(bands.get(id)?.continuesAbove).toBe(false);
      expect(bands.get(id)?.continuesBelow).toBe(false);
    }
  });

  it("skips a rule the server placed in no policy without dropping its neighbours", () => {
    const index = indexPoliciesByRule([policy("p4-E000007", ["read", "comply"])]);
    const bands = policyBands(["read", "unplaced", "comply"], index);

    expect(bands.has("unplaced")).toBe(false);
    expect(bands.get("read")?.isStart).toBe(true);
    expect(bands.get("comply")?.isStart).toBe(false);
  });

  it("bands each policy independently when several are interleaved on a page", () => {
    const index = indexPoliciesByRule([
      policy("p4-E000007", ["read", "comply"]),
      policy("p5-E000011", ["notice"]),
    ]);
    const bands = policyBands(["read", "notice", "comply"], index);

    expect(bands.get("read")?.isStart).toBe(true);
    expect(bands.get("notice")?.isStart).toBe(true);
    expect(bands.get("comply")?.isStart).toBe(false);
    expect(bands.get("comply")?.policy.key).toBe("p4-E000007");
  });

  it("holds up at the scale a real document reaches", () => {
    // Designed for a hundred rather than for the witness. 400 rules in 180
    // policies is the order of magnitude measured on a single 27-page document.
    const policies: AssembledPolicy[] = [];
    const order: string[] = [];
    for (let p = 0; p < 180; p += 1) {
      const ruleIds = [`r${p}a`, `r${p}b`];
      policies.push(policy(`p-${p}`, ruleIds));
      order.push(...ruleIds);
    }

    const index = indexPoliciesByRule(policies);
    const bands = policyBands(order, index);

    expect(bands.size).toBe(360);
    expect([...bands.values()].filter((b) => b.isStart)).toHaveLength(180);
    // Conservation: every rule is banded exactly once, as the server's own
    // partition assertion guarantees upstream.
    expect(new Set(bands.keys()).size).toBe(order.length);
  });
});

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
    // The same rule the Python guard enforces, applied where these words are
    // actually defined. Three phrasings have evaded a pattern check already, so
    // this asserts on the labels themselves rather than on a file scan.
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

describe("policyHeaderSummary", () => {
  const whole = policyBands(
    ["read", "understand", "comply"],
    indexPoliciesByRule([policy("p4-E000007", ["read", "understand", "comply"])]),
  ).get("read")!;

  it("states the count, the page and the route", () => {
    const summary = policyHeaderSummary(whole);
    expect(summary).toContain("3 rules");
    expect(summary).toContain("page 4");
    expect(summary).toContain("Decided by reading");
  });

  it("does not claim a partial view is the whole passage", () => {
    const partial = policyBands(
      ["read"],
      indexPoliciesByRule([policy("p4-E000007", ["read", "understand", "comply"])]),
    ).get("read")!;

    expect(policyHeaderSummary(partial)).toContain("3 rules");
    expect(policyHeaderSummary(partial)).toContain("1 shown here");
  });

  it("stays quiet about partiality when the policy is whole", () => {
    // CONTROL for the caveat above.
    expect(policyHeaderSummary(whole)).not.toContain("shown here");
  });

  it("omits the page rather than inventing one when it is not recorded", () => {
    const band = policyBands(
      ["read"],
      indexPoliciesByRule([policy("p4-E000007", ["read"], { page: null })]),
    ).get("read")!;

    expect(policyHeaderSummary(band)).not.toContain("page");
    expect(policyHeaderSummary(band)).toContain("1 rule");
  });
});
