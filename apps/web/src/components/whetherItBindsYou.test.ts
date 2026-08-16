/**
 * Whether a published policy applies, and from and until when.
 *
 * A reader arriving at a policy asks whether it binds them. The record answers
 * with three separate facts that are easy to conflate: when a version was
 * approved, when it starts applying, and whether it is the version in force.
 * These tests hold them apart.
 *
 * The witness that made this necessary is a real one and is why an absent end
 * date must never be reported as an open end: a superseded version was found
 * carrying a start date and no end date at all, because it stopped applying
 * when a later version replaced it rather than by reaching a date. Read
 * naively, that version claims to apply forever.
 *
 * No date here is a date this app has ever seen in a document; they are chosen
 * to be orderable and unambiguous, and every expectation is computed from the
 * fixture rather than written down.
 */
import { describe, expect, it } from "vitest";

import { formatDay, today, whenItApplies } from "./policyProvenance";

/** A published sighting, with only the fields this derivation reads. */
function publishedIn(overrides: {
  isActive: boolean;
  effectiveFrom?: string | null;
  effectiveTo?: string | null;
}) {
  return {
    isActive: overrides.isActive,
    effectiveFrom: overrides.effectiveFrom ?? null,
    effectiveTo: overrides.effectiveTo ?? null,
  };
}

/** A day offset from a fixed reference, so "past" and "future" are relative. */
const REFERENCE = "2400-06-15";
function dayBefore(day: string): string {
  const [y, m, d] = day.split("-").map(Number);
  const at = new Date(y, m - 1, d - 1);
  return `${at.getFullYear()}-${`${at.getMonth() + 1}`.padStart(2, "0")}-${`${at.getDate()}`.padStart(2, "0")}`;
}
function dayAfter(day: string): string {
  const [y, m, d] = day.split("-").map(Number);
  const at = new Date(y, m - 1, d + 1);
  return `${at.getFullYear()}-${`${at.getMonth() + 1}`.padStart(2, "0")}-${`${at.getDate()}`.padStart(2, "0")}`;
}

describe("a version that applies says so, and says since when", () => {
  it("reports the active version as in force, from the day it started", () => {
    const started = dayBefore(REFERENCE);
    const said = whenItApplies(publishedIn({ isActive: true, effectiveFrom: started }), REFERENCE);

    expect(said).toContain("in force");
    expect(said).toContain(formatDay(started));
  });

  it("does not claim a version applies yet when its day has not arrived", () => {
    const starts = dayAfter(REFERENCE);
    const said = whenItApplies(publishedIn({ isActive: true, effectiveFrom: starts }), REFERENCE);

    expect(said).toContain("takes effect");
    expect(said).not.toContain("in force");
    expect(said).toContain(formatDay(starts));
  });

  it("treats the first day it applies as a day it applies, not one still to come", () => {
    const said = whenItApplies(
      publishedIn({ isActive: true, effectiveFrom: REFERENCE }),
      REFERENCE,
    );

    expect(said).toContain("in force");
    expect(said).not.toContain("takes effect");
  });

  it("names the end where the record holds one", () => {
    const ends = dayAfter(REFERENCE);
    const said = whenItApplies(
      publishedIn({ isActive: true, effectiveFrom: dayBefore(REFERENCE), effectiveTo: ends }),
      REFERENCE,
    );

    expect(said).toContain(`until ${formatDay(ends)}`);
  });
});

describe("a version that no longer applies is not described as one that does", () => {
  it("speaks of a superseded version in the past", () => {
    const said = whenItApplies(
      publishedIn({ isActive: false, effectiveFrom: dayBefore(REFERENCE) }),
      REFERENCE,
    );

    expect(said).toContain("applied from");
    expect(said).not.toContain("in force");
    expect(said).not.toContain("takes effect");
  });

  it("says nothing about an end a superseded version does not record", () => {
    // The witness: superseded, started, no end date. Read naively this version
    // claims to run forever, which is the one thing it must not say.
    const said = whenItApplies(
      publishedIn({ isActive: false, effectiveFrom: dayBefore(REFERENCE), effectiveTo: null }),
      REFERENCE,
    );

    expect(said).not.toMatch(/until/i);
    expect(said).not.toMatch(/no end|open|ongoing|indefinit|still/i);
  });

  it("still names an end where a superseded version does record one", () => {
    const ended = dayBefore(REFERENCE);
    const said = whenItApplies(
      publishedIn({
        isActive: false,
        effectiveFrom: dayBefore(ended),
        effectiveTo: ended,
      }),
      REFERENCE,
    );

    expect(said).toContain(`until ${formatDay(ended)}`);
  });
});

describe("absent is not empty", () => {
  it("returns nothing at all when the record holds no start day", () => {
    expect(whenItApplies(publishedIn({ isActive: true }), REFERENCE)).toBeNull();
    expect(whenItApplies(publishedIn({ isActive: false }), REFERENCE)).toBeNull();
  });

  it("does not invent a start from an end alone", () => {
    const said = whenItApplies(
      publishedIn({ isActive: true, effectiveTo: dayAfter(REFERENCE) }),
      REFERENCE,
    );

    expect(said).toBeNull();
  });
});

describe("a day is written as a day", () => {
  it("carries no time of day", () => {
    expect(formatDay(REFERENCE)).not.toMatch(/\d{1,2}:\d{2}/);
  });

  it("does not shift a plain day into the one before it", () => {
    const [y, m, d] = REFERENCE.split("-").map(Number);
    const asLocalDay = new Date(y, m - 1, d).toLocaleDateString();

    expect(formatDay(REFERENCE)).toBe(asLocalDay);
  });

  it("returns anything that is not a plain day untouched rather than as an invalid date", () => {
    const notADay = "whenever the committee decides";

    expect(formatDay(notADay)).toBe(notADay);
    expect(formatDay(notADay)).not.toMatch(/invalid/i);
  });

  it("reads today as a plain day, comparable against the days a record holds", () => {
    expect(today()).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });
});
