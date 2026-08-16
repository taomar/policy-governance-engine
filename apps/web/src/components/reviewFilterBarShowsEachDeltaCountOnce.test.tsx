/**
 * One fact, one control: the delta counts are shown once.
 *
 * THE REDUNDANCY THIS PINS
 *
 * The filter bar used to state each delta count twice, stacked:
 *
 *   - a segmented view-selector reading `Everything | New 37 | Changed 263 |
 *     Unchanged 98`, which *filters* the queue to that slice; and
 *   - directly beneath it, a row of read-only chips reading `37 new`,
 *     `263 changed`, `98 unchanged` — the very same numbers, doing nothing.
 *
 * Two controls for one fact is exactly the clutter a reviewer has to read past
 * before they can act. The segmented control keeps the counts because selecting
 * one is how the queue is narrowed; the read-only restatement is removed.
 *
 * This is de-duplication, not information loss (constraint 11): the number a
 * chip carried is still on screen, in the control that also *does* something
 * with it. What is genuinely unique to the lower row — the "No longer found"
 * door onto superseded rules, and the informational "not compared" count that
 * the selector does not offer as a slice — has to survive, and is asserted to.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

import { ReviewFilterBar } from "./ReviewFilterBar";
import type { ReviewFacets } from "../api";

afterEach(cleanup);

function facets(overrides: Partial<ReviewFacets> = {}): ReviewFacets {
  return {
    documents: [{ id: "doc-1", title: "A document", rule_count: 398 }],
    runs: [],
    delta_totals: { new: 37, changed: 263, unchanged: 98, baseline: 0, unclassified: 5 },
    removed: [
      {
        id: "rm-1",
        title: "A dropped rule",
        rule_type: "obligation",
        review_status: "candidate",
        superseded_at: null,
        superseded_by_run_id: null,
        superseded_by_reference: null,
        source_text: "",
      },
    ],
    status_totals: { candidate: 398 },
    ...overrides,
  };
}

function renderBar(over: Partial<ReviewFacets> = {}) {
  return render(
    <ReviewFilterBar
      facets={facets(over)}
      documentFilter=""
      runFilter=""
      deltaFilter="all"
      showRemoved={false}
      onDocument={vi.fn()}
      onRun={vi.fn()}
      onDelta={vi.fn()}
      onToggleRemoved={vi.fn()}
      onRefresh={vi.fn()}
    />,
  );
}

describe("the delta counts are stated once, in the control that acts on them", () => {
  it("keeps every count in the view-selector", () => {
    const { container } = renderBar();
    const segmented = container.querySelector(".ant-segmented") as HTMLElement;
    // Control: the selector is the one place the counts belong, so it must hold
    // them — otherwise "shown once" could be satisfied by showing them nowhere.
    expect(segmented).not.toBeNull();
    expect(segmented.textContent).toContain("New");
    expect(segmented.textContent).toContain("37");
    expect(segmented.textContent).toContain("Changed");
    expect(segmented.textContent).toContain("263");
    expect(segmented.textContent).toContain("Unchanged");
    expect(segmented.textContent).toContain("98");
  });

  it("does not restate them as a second row of read-only chips", () => {
    renderBar();
    // The removed duplication: these are the chip spellings that sat under the
    // selector saying the same thing a second time.
    expect(screen.queryByText("37 new")).toBeNull();
    expect(screen.queryByText("263 changed")).toBeNull();
    expect(screen.queryByText("98 unchanged")).toBeNull();
  });

  it("renders no read-only delta chip — the numbers live only in the selector", () => {
    renderBar();
    // A chip reads "<count> <label>" (e.g. "263 changed"); a selector option
    // reads "<label> <count>" (e.g. "Changed 263"). Anchoring the pattern to the
    // chip word-order matches the read-only restatement wherever it is nested —
    // even when an icon sits inside the tag — without matching the selector.
    const chipPattern = /^\s*\d+\s+(new|changed|unchanged)\s*$/i;
    expect(screen.queryAllByText(chipPattern)).toHaveLength(0);
  });
});

describe("what only the lower row carried still survives", () => {
  it("keeps the door onto rules the latest extraction no longer produces", () => {
    renderBar();
    expect(screen.getByRole("button", { name: /No longer found/i })).toBeTruthy();
  });

  it("keeps the informational not-compared count the selector does not offer", () => {
    // `unclassified` is not a slice the segmented can select — it is a fact
    // about rules with no predecessor to compare against — so removing the chip
    // row must not take it with them.
    renderBar();
    expect(screen.getByText("5 not compared")).toBeTruthy();
  });

  it("still tells the reviewer when nothing changed since the last extraction", () => {
    renderBar({
      delta_totals: { new: 0, changed: 0, unchanged: 12, baseline: 0, unclassified: 0 },
      removed: [],
    });
    expect(screen.getByText(/No changes since the previous extraction/i)).toBeTruthy();
  });
});
