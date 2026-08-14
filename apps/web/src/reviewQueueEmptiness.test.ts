import { describe, expect, it } from "vitest";

import {
  filtersAreDefault,
  reviewQueueIsEmpty,
  type ReviewFilterState,
} from "./reviewQueueEmptiness";

const OPEN: ReviewFilterState = {
  status: "all",
  document: "",
  run: "",
  delta: "all",
  showRemoved: false,
  search: "",
};

describe("filtersAreDefault", () => {
  it("is true when nothing is narrowing the queue", () => {
    expect(filtersAreDefault(OPEN)).toBe(true);
  });

  // The two spellings of "off" are the trap. Delta is off at "all", not "";
  // document and run are off at "", not "all". Each of these would silently
  // invert the verdict if the wrong constant were used.
  it("treats a delta of \"all\" as off and a delta of anything else as on", () => {
    expect(filtersAreDefault({ ...OPEN, delta: "all" })).toBe(true);
    expect(filtersAreDefault({ ...OPEN, delta: "new" })).toBe(false);
    expect(filtersAreDefault({ ...OPEN, delta: "unchanged" })).toBe(false);
  });

  it("treats an empty document or run as off", () => {
    expect(filtersAreDefault({ ...OPEN, document: "" })).toBe(true);
    expect(filtersAreDefault({ ...OPEN, document: "doc-1" })).toBe(false);
    expect(filtersAreDefault({ ...OPEN, run: "run-1" })).toBe(false);
  });

  it("counts a status other than \"all\" as narrowing", () => {
    expect(filtersAreDefault({ ...OPEN, status: "approved" })).toBe(false);
  });

  it("counts showing retired rules as narrowing", () => {
    expect(filtersAreDefault({ ...OPEN, showRemoved: true })).toBe(false);
  });

  it("ignores whitespace-only search text", () => {
    expect(filtersAreDefault({ ...OPEN, search: "   " })).toBe(true);
    expect(filtersAreDefault({ ...OPEN, search: "retention" })).toBe(false);
  });
});

describe("reviewQueueIsEmpty", () => {
  it("is true for a project with no rules and no filters", () => {
    expect(reviewQueueIsEmpty(0, OPEN, false)).toBe(true);
  });

  it("is false as soon as the project holds a rule", () => {
    expect(reviewQueueIsEmpty(1, OPEN, false)).toBe(false);
    expect(reviewQueueIsEmpty(2735, OPEN, false)).toBe(false);
  });

  /**
   * The case that must never regress. A reviewer who searches for something
   * that does not exist, or opens a status tab that is currently unoccupied,
   * gets an empty list -- and the controls are how they get back. Collapsing
   * the surface there would strand them with no way to clear the filter that is
   * hiding the rules.
   */
  it("is false when the emptiness was caused by a filter", () => {
    expect(reviewQueueIsEmpty(0, { ...OPEN, search: "no such rule" }, false)).toBe(false);
    expect(reviewQueueIsEmpty(0, { ...OPEN, status: "rejected" }, false)).toBe(false);
    expect(reviewQueueIsEmpty(0, { ...OPEN, delta: "changed" }, false)).toBe(false);
    expect(reviewQueueIsEmpty(0, { ...OPEN, document: "doc-1" }, false)).toBe(false);
    expect(reviewQueueIsEmpty(0, { ...OPEN, run: "run-1" }, false)).toBe(false);
    expect(reviewQueueIsEmpty(0, { ...OPEN, showRemoved: true }, false)).toBe(false);
  });

  it("withholds the verdict while the queue is still loading", () => {
    // Otherwise the surface collapses on first paint and expands again a
    // moment later, which reads as a glitch and moves everything under the
    // pointer.
    expect(reviewQueueIsEmpty(0, OPEN, true)).toBe(false);
  });

  /**
   * Nothing here may key on a project, a name or a particular count. The rule
   * is a function of the queue length and the filter state only, so the same
   * inputs must give the same answer whatever the queue is called.
   */
  it("depends on nothing but the count, the filters and the load state", () => {
    for (const count of [0, 1, 2, 9, 50, 100, 2735]) {
      expect(reviewQueueIsEmpty(count, OPEN, false)).toBe(count === 0);
    }
  });
});
