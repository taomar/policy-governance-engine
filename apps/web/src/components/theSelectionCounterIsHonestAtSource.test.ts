/**
 * The selection counters are honest about their unit — at the source.
 *
 * WHY A SOURCE-READ TEST
 *
 * `PoliciesTab` and `ReviewQueue` are the two largest components in this app and
 * are never rendered whole under test — their end-to-end behaviour is proven in
 * a browser, and the fragments that must not quietly regress are pinned by
 * reading the source, the same way `aDecisionRefreshesTheStripItReads` pins the
 * status strip. What is pinned here is one clause on each pane: the label the
 * bulk-selection control renders.
 *
 * THE DEFECT THESE GUARD AGAINST
 *
 * A count in this product names its unit — "N policies · M rules" — never a
 * bare number. Two selection counters still read "N selected":
 *
 *   - PoliciesTab named nothing. It now renders `bulkSelectionLabel(...)`, which
 *     leads with the policy and keeps the rule tally (value-checked in
 *     theSelectionCounterNamesItsUnit.test.tsx).
 *
 *   - ReviewQueue already leads with policies when its policies are assembled
 *     ("grouped"). Its other branch fires precisely when they are not, so the
 *     policy figure cannot be vouched for there. The honest move is not to label
 *     that branch "policies" anyway — it does not know that — but to name the
 *     unit it *does* hold: the selected candidates are rules. So the fallback
 *     now reads "N rules selected", the same word the grouped branch one line
 *     above already uses for that same quantity, and never asserts a policy
 *     count the surface cannot stand behind.
 *
 * These read the source rather than the screen, so no string here is a phrase
 * from a document and no number is a measurement of one.
 */
import { describe, expect, it } from "vitest";

const policiesSource = Object.values(
  import.meta.glob("./PoliciesTab.tsx", {
    query: "?raw",
    import: "default",
    eager: true,
  }),
)[0] as string;

const reviewSource = Object.values(
  import.meta.glob("./ReviewQueue.tsx", {
    query: "?raw",
    import: "default",
    eager: true,
  }),
)[0] as string;

/** The span between two literal anchors, so drift in line numbers cannot fool the guard. */
function slice(source: string, from: string, to: string): string {
  const start = source.indexOf(from);
  if (start < 0) throw new Error(`anchor not found: ${from}`);
  const end = source.indexOf(to, start + from.length);
  if (end <= start) throw new Error(`anchor not found after ${from}: ${to}`);
  return source.slice(start, end);
}

describe("the Policies pane's selection counter names its unit", () => {
  it("no longer renders a bare number", () => {
    // The exact defect: "{selectedPolicyKeys.size} selected", a count with no unit.
    expect(policiesSource).not.toMatch(
      /\{\s*selectedPolicyKeys\.size\s*\}\s*selected/,
    );
  });

  it("renders the shared, unit-naming label instead", () => {
    expect(policiesSource).toContain("bulkSelectionLabel(");
  });
});

describe("the Review queue's selection fallback is honest about its unit", () => {
  const bulkBar = slice(reviewSource, 'className="bulk-bar"', "</Checkbox>");

  it("no longer renders a bare number when policies are not assembled", () => {
    // The fallback used to read exactly "`${selectedIds.size} selected`".
    expect(bulkBar).not.toMatch(/`\s*\$\{\s*selectedIds\.size\s*\}\s*selected\s*`/);
  });

  it("names the unit it does know — rules — with the singular right at one", () => {
    // The selected ids are candidate rules; the fallback says so, mirroring the
    // grouped branch's own rule clause one line above rather than inventing a
    // second phrasing.
    expect(bulkBar).toMatch(
      /\$\{\s*selectedIds\.size === 1 \? ["']rule["'] : ["']rules["']\s*\}\s*selected/,
    );
  });

  it("does not claim a policy count in the fallback it cannot vouch for", () => {
    // The word "policy"/"policies" belongs only to the grouped branch, which is
    // led by selectedPolicyCount. The fallback — the `:` branch led by
    // selectedIds.size — must not borrow it. Isolate that one template literal
    // between its opening `${selectedIds.size} and its closing backtick.
    const fallback = slice(bulkBar, ": `${selectedIds.size}", "`");
    expect(fallback).not.toMatch(/polic/);
  });

  it("leaves the grouped branch leading with policies, both counts intact", () => {
    // Regression guard: the established branch is untouched.
    expect(bulkBar).toMatch(
      /\$\{selectedPolicyCount === 1 \? ["']policy["'] : ["']policies["']\}\s*selected · \$\{selectedIds\.size\}/,
    );
  });
});
