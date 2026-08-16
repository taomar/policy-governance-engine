/**
 * The status strip counts in the unit the work is decided in.
 *
 * THE FAILURE THIS EXISTS TO PREVENT
 *
 * A strip of pills reading `279 All / 266 Needs review / 13 Published` over a
 * queue whose unit of review is the policy. Three separate things go wrong at
 * once, and every one of them renders perfectly:
 *
 *   1. The number is the rule count wearing the policy count's name. Four
 *      hundred rules can be seventy decisions. A reviewer sizing the job from
 *      the pill is told the wrong size, and nothing on screen says which unit
 *      the number is in — a pill has no room for a sentence.
 *
 *   2. The rule count disappears when the policy count arrives. A policy is
 *      made of rules, and a reviewer wants both: one says how many decisions,
 *      the other how much text. Replacing one with the other trades a wrong
 *      answer for a different wrong answer.
 *
 *   3. A missing policy figure becomes a nought. A server that does not serve
 *      the figure yet has said nothing about how many policies are waiting.
 *      Rendering `0 policies` over a queue holding 279 rules is a measurement
 *      nobody took, and it is indistinguishable on screen from an empty queue.
 *
 * Each is asserted below against a strip built to expose it, and each assertion
 * is paired with a control that fails if nothing rendered at all — because a
 * blank page also satisfies "does not say 0 policies".
 */

import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { ReviewStatusTabs } from "./components/ReviewStatusTabs";

afterEach(cleanup);

const RULE_COUNTS = {
  candidate: 266,
  changes_requested: 0,
  approved: 0,
  rejected: 0,
  published: 13,
};

const POLICY_COUNTS = {
  candidate: 24,
  changes_requested: 0,
  approved: 0,
  rejected: 0,
  published: 5,
};

/** Every pill on the strip, as `{ lead, unit, label, sub }`. */
function pills() {
  return screen.getAllByRole("tab").map((tab) => ({
    lead: tab.querySelector(".review-status-tab-count")?.textContent ?? null,
    unit: tab.querySelector(".review-status-tab-unit")?.textContent ?? null,
    label: tab.querySelector(".review-status-tab-label")?.textContent ?? null,
    sub: tab.querySelector(".review-status-tab-sub")?.textContent ?? null,
    title: tab.getAttribute("title") ?? "",
  }));
}

function renderStrip(props: Partial<Parameters<typeof ReviewStatusTabs>[0]> = {}) {
  return render(
    <ReviewStatusTabs
      value="candidate"
      onChange={vi.fn()}
      counts={RULE_COUNTS}
      total={279}
      {...props}
    />,
  );
}

describe("a pill with no room for a unit still names one", () => {
  it("puts a unit beside every leading number", () => {
    renderStrip({ policyCounts: POLICY_COUNTS, totalPolicies: 32 });
    const shown = pills();
    // The control: a blank strip would pass the per-pill assertion vacuously.
    expect(shown.length).toBeGreaterThan(3);
    for (const pill of shown) {
      expect(pill.lead).toMatch(/^\d+$/);
      expect(pill.unit).toMatch(/^(policy|policies|rule|rules)$/);
    }
  });

  it("names both counts in the hover, whatever the pill had room for", () => {
    renderStrip({ policyCounts: POLICY_COUNTS, totalPolicies: 32 });
    const all = pills().find((pill) => pill.label === "All");
    expect(all).toBeDefined();
    expect(all?.title).toContain("32 policies");
    expect(all?.title).toContain("279 rules");
  });

  it("agrees with itself: the pill leads with the number the hover leads with", () => {
    renderStrip({ policyCounts: POLICY_COUNTS, totalPolicies: 32 });
    const shown = pills();
    expect(shown.length).toBeGreaterThan(3);
    for (const pill of shown) {
      expect(pill.title).toContain(`${pill.lead} ${pill.unit}`);
    }
  });
});

describe("policies lead and rules stay", () => {
  it("leads with the policy count", () => {
    renderStrip({ policyCounts: POLICY_COUNTS, totalPolicies: 32 });
    const all = pills().find((pill) => pill.label === "All");
    expect(all?.lead).toBe("32");
    expect(all?.unit).toBe("policies");
  });

  it("keeps the rule count rather than replacing it", () => {
    renderStrip({ policyCounts: POLICY_COUNTS, totalPolicies: 32 });
    const all = pills().find((pill) => pill.label === "All");
    expect(all?.sub).toBe("279 rules");
  });

  it("joins the two rather than summing them", () => {
    renderStrip({ policyCounts: POLICY_COUNTS, totalPolicies: 32 });
    const all = pills().find((pill) => pill.label === "All");
    expect(all?.title).not.toContain("311");
  });

  it("reads in the singular when one policy holds one rule", () => {
    renderStrip({
      counts: { ...RULE_COUNTS, candidate: 1 },
      total: 1,
      policyCounts: { ...POLICY_COUNTS, candidate: 1 },
      totalPolicies: 1,
    });
    const all = pills().find((pill) => pill.label === "All");
    expect(all?.unit).toBe("policy");
    expect(all?.sub).toBe("1 rule");
  });
});

describe("absent is not zero", () => {
  it("falls back to the rule count and says it is rules", () => {
    renderStrip({ policyCounts: null, totalPolicies: null });
    const all = pills().find((pill) => pill.label === "All");
    expect(all?.lead).toBe("279");
    expect(all?.unit).toBe("rules");
  });

  it("never reports no policies over a queue plainly holding work", () => {
    renderStrip({ policyCounts: null, totalPolicies: null });
    const shown = pills();
    expect(shown.length).toBeGreaterThan(3);
    for (const pill of shown) {
      expect(`${pill.lead} ${pill.unit}`).not.toBe("0 policies");
      expect(pill.title).not.toMatch(/\b0 policies\b/);
    }
  });

  it("shows no trailing rule count when there is no leading policy count to trail", () => {
    // The sub-line exists to keep the rule count once policies have taken the
    // lead. With no policy figure the lead *is* the rule count, and repeating
    // it underneath would read as two measurements of different things.
    renderStrip({ policyCounts: null, totalPolicies: null });
    for (const pill of pills()) expect(pill.sub).toBeNull();
  });

  it("keeps a genuinely empty status distinct from an unmeasured one", () => {
    renderStrip({ policyCounts: POLICY_COUNTS, totalPolicies: 32 });
    const rejected = pills().find((pill) => pill.label === "Rejected");
    // Nought policies, measured, and said in the unit it was measured in.
    expect(rejected?.lead).toBe("0");
    expect(rejected?.unit).toBe("policies");
    expect(rejected?.sub).toBe("0 rules");
  });
});

describe("the strip does not frame either route as a shortfall", () => {
  it("says nothing about routes at all", () => {
    renderStrip({ policyCounts: POLICY_COUNTS, totalPolicies: 32 });
    const shown = pills();
    expect(shown.length).toBeGreaterThan(3);
    for (const pill of shown) {
      expect(`${pill.label} ${pill.title}`).not.toMatch(
        /decided.by.reading|evaluated.directly|human.judg/i,
      );
    }
  });
});
