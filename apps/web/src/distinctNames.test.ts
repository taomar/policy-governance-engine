import { describe, expect, it } from "vitest";
import { distinctLabels, distinctLabelsByKey, elideMiddle, ELLIPSIS } from "./distinctNames";

/** The shape that broke navigation: one document, several annotated extractions. */
const SHARED_PREFIX = [
  "Staff Handbook (Metro Group University) 2024 (full extraction)",
  "Staff Handbook (Metro Group University) 2024 (pilot subset)",
  "Staff Handbook (Metro Group University) 2024 (Phase 2 re-run)",
  "Staff Handbook (Metro Group University) 2024 (phase 2 re-run)",
  "Staff Handbook (Metro Group University) 2024 (with appendices)",
];

describe("elideMiddle", () => {
  it("leaves a name that fits exactly as it is", () => {
    expect(elideMiddle("Travel Policy", 24)).toBe("Travel Policy");
  });

  it("keeps a head and a tail rather than dropping the end", () => {
    const label = elideMiddle("Staff Handbook (Metro Group University) 2024 (pilot subset)", 24);
    expect(label.length).toBe(24);
    expect(label.startsWith("Staff")).toBe(true);
    expect(label.endsWith("subset)")).toBe(true);
    expect(label).toContain(ELLIPSIS);
  });

  it("never cuts a code point in half", () => {
    // Four astral-plane characters and a tail. Slicing by UTF-16 index would
    // split a surrogate pair and render a replacement glyph.
    const label = elideMiddle("🏛️🏛️🏛️🏛️ Handbook (annexe)", 12);
    expect(label).not.toContain("\uFFFD");
    expect(Array.from(label).length).toBeLessThanOrEqual(12);
  });
});

describe("distinctLabels", () => {
  it("reproduces the failure end-truncation causes, then does not have it", () => {
    // What the browser does today, at the width the navigation gives it.
    const endTruncated = SHARED_PREFIX.map((name) =>
      name.length > 24 ? `${name.slice(0, 23)}${ELLIPSIS}` : name,
    );
    expect(new Set(endTruncated).size).toBe(1); // all five identical

    const { labels } = distinctLabels(SHARED_PREFIX, 24);
    expect(new Set(labels).size).toBe(SHARED_PREFIX.length);
  });

  it("tells apart names differing only in letter case", () => {
    const { labels, hasCollisions } = distinctLabels(
      [
        "Staff Handbook (Metro Group University) 2024 (Phase 2 re-run)",
        "Staff Handbook (Metro Group University) 2024 (phase 2 re-run)",
      ],
      22,
    );
    expect(labels[0]).not.toBe(labels[1]);
    expect(hasCollisions).toBe(false);
  });

  it("distinguishes names that share a suffix as well as a prefix", () => {
    const { labels } = distinctLabels(
      [
        "Information Security Standard v4 — extraction of 12 March, appendices included",
        "Information Security Standard v7 — extraction of 12 March, appendices included",
      ],
      28,
    );
    expect(labels[0]).not.toBe(labels[1]);
  });

  it("only re-divides the labels that collide", () => {
    const names = [
      "Travel and Expense Policy 2025 (full extraction)",
      "Travel and Expense Policy 2025 (pilot subset)",
      "Data Retention",
    ];
    const { labels } = distinctLabels(names, 22);
    expect(labels[2]).toBe("Data Retention"); // fits, untouched
    expect(new Set(labels).size).toBe(3);
  });

  it("anchors the second run at the difference when the ends are identical", () => {
    // Same head, same tail, one character apart 39 in. No division of a
    // two-part label reaches it, so the second run has to move off the end.
    const stem = "Procurement and Supplier Code — annexe ";
    const { labels, hasCollisions } = distinctLabels(
      [`${stem}A of the 2025 consolidated review`, `${stem}B of the 2025 consolidated review`],
      21,
    );
    expect(labels[0]).not.toBe(labels[1]);
    expect(hasCollisions).toBe(false);
    expect(Array.from(labels[0]).length).toBeLessThanOrEqual(21);
  });

  it("stays inside the budget for every label it produces", () => {
    const names = [
      ...SHARED_PREFIX,
      "Information Security Standard v4 — extraction of 12 March, appendices included",
      "Information Security Standard v7 — extraction of 12 March, appendices included",
      "Short",
    ];
    for (const budget of [10, 14, 18, 22, 26, 30, 40]) {
      const { labels } = distinctLabels(names, budget);
      for (const label of labels) {
        const original = names[labels.indexOf(label)];
        // A label is either the untouched name or within the budget.
        expect(Array.from(label).length <= budget || label === original).toBe(true);
      }
    }
  });

  it("reports a collision it cannot solve rather than inventing a difference", () => {
    const { labels, hasCollisions } = distinctLabels(["Same Name", "Same Name"], 20);
    expect(hasCollisions).toBe(true);
    expect(labels[0]).toBe(labels[1]); // no counter, no suffix, no fabrication
  });

  it("holds at a hundred names sharing one prefix", () => {
    const many = Array.from(
      { length: 100 },
      (_, i) => `Procurement and Supplier Code — extraction run ${i + 1} of the 2025 review`,
    );
    const { labels, hasCollisions } = distinctLabels(many, 26);
    expect(hasCollisions).toBe(false);
    expect(new Set(labels).size).toBe(100);
  });

  it("leaves an empty set alone", () => {
    expect(distinctLabels([], 20)).toEqual({ labels: [], hasCollisions: false });
  });
});

describe("distinctLabelsByKey", () => {
  it("reads a label back by the record's own key", () => {
    const items = SHARED_PREFIX.map((name, i) => ({ key: `p-${i}`, name }));
    const { labelFor, hasCollisions } = distinctLabelsByKey(
      items,
      (i) => i.key,
      (i) => i.name,
      24,
    );
    expect(hasCollisions).toBe(false);
    expect(new Set(items.map((i) => labelFor(i.key))).size).toBe(items.length);
  });

  it("returns the key itself for a key it was not given", () => {
    const { labelFor } = distinctLabelsByKey(
      [{ key: "a", name: "Alpha" }],
      (i) => i.key,
      (i) => i.name,
      20,
    );
    expect(labelFor("z")).toBe("z");
  });
});
