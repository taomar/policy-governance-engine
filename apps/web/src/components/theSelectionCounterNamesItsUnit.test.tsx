/**
 * The bulk-selection counter names the unit it counts: policies, with rules.
 *
 * WHY THIS TEST
 *
 * A count in this product reads "N policies · M rules" — the policy leads,
 * because a policy is what is reviewed, approved, published and exported, and
 * the rule tally follows it, never instead of it, so a reader who counts in
 * rules is not left thinking they were dropped. Every surface was brought to
 * that one during this session; the Policies pane's selection counter was the
 * last that still read a bare "N selected", a number with no unit at all.
 *
 * `bulkSelectionLabel` is the phrase the counter now renders, made callable so
 * it can be pinned here rather than only seen in a browser — a phrase nobody
 * can call from a test is a phrase that gets quietly reworded. It is built from
 * `policyUnit`/`ruleUnit`, the same two helpers the rest of the page already
 * words this bar with, so its singular is right at one and it cannot drift from
 * the vocabulary beside it. The string it returns is, deliberately, the one the
 * review queue already words the same control with: "N policies selected · M
 * rules". The two surfaces teach one vocabulary for one act.
 *
 * Nothing here is a phrase from any document, and no number in it is a
 * measurement of one.
 */
import { describe, expect, it } from "vitest";
import { bulkSelectionLabel } from "./PoliciesTab";

describe("the bulk-selection counter names its unit", () => {
  it("names one policy in the singular, with its one rule", () => {
    // The failure a plural at one would be: "1 policies selected · 1 rules".
    expect(bulkSelectionLabel(1, 1)).toBe("1 policy selected · 1 rule");
  });

  it("names many policies in the plural, keeping the rule tally beside them", () => {
    expect(bulkSelectionLabel(3, 12)).toBe("3 policies selected · 12 rules");
  });

  it("never reports a bare number without its unit", () => {
    // The defect this closes, stated as an assertion: the counter used to read
    // exactly "N selected".
    expect(bulkSelectionLabel(5, 20)).not.toMatch(/^\d+ selected$/);
    expect(bulkSelectionLabel(5, 20)).toContain("policies");
  });

  it("keeps both counts, never dropping the rules to make room for the policies", () => {
    const label = bulkSelectionLabel(7, 40);
    expect(label).toContain("7 policies");
    expect(label).toContain("40 rules");
  });

  it("leads with the policy, because the policy is what the page selects", () => {
    const label = bulkSelectionLabel(2, 9);
    expect(label.indexOf("policies")).toBeLessThan(label.indexOf("rules"));
  });

  it("states both counts exactly, rounding and abbreviating nothing", () => {
    const label = bulkSelectionLabel(38, 412);
    expect(label).toBe("38 policies selected · 412 rules");
    expect(label).not.toMatch(/[~kKmM+]/);
  });
});
