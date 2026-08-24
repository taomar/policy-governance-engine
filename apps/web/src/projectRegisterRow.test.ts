import { describe, expect, it } from "vitest";
import { projectRowClauses, routeClauses, type ProjectRowFacts } from "./projectRegisterRow";

/**
 * Guards on what a project's register row is allowed to claim.
 *
 * TWO DEFECTS ARE BEING CLOSED, AND THEY ARE THE SAME DEFECT
 *
 * 1. A row read "0 rules" beside a badge counting hundreds of records in review.
 *    Both numbers were true. `active_rule_count` counts PUBLISHED rules and
 *    `review_pending` counts candidates awaiting a decision, so they disagree by
 *    design -- they measure different stages of one record's life. The row showed
 *    the stage the work had not reached, so a project holding 411 records read as
 *    empty.
 *
 * 2. The same row rendered `machine_executable / published` as a percentage, and
 *    guarded the divide-by-zero by declaring the answer to be 0%. An undefined
 *    ratio was shown as the worst available grade, for a portfolio behaving
 *    correctly.
 *
 * Both are one mistake: describing a project by a denominator it has not reached.
 *
 * WHY COUNTS AND NOT A BETTER-WORDED PERCENTAGE
 *
 * Whether a policy's test is a comparison or is stated in words is a property of
 * the source document, not a score this system earns. Most real policy prose
 * states it in words. Any ratio between the two routes invites reading one as a
 * shortfall of the other, and no caption repairs that -- a reader who sees a low
 * percentage has concluded something is wrong before reaching the words. So the
 * ratio is banned outright at the surface rather than reworded, and the scan at
 * the bottom of this file enforces that it stays banned.
 */

interface Overrides extends Partial<ProjectRowFacts> {}

/** A project holding live records and nothing published -- the ordinary case for
 *  this product, and the one the old row described as empty. */
function facts(overrides: Overrides = {}): ProjectRowFacts {
  return {
    document_count: 1,
    review_pending_policies: 4,
    review_pending: 40,
    live_policy_count: 4,
    live_candidate_count: 40,
    candidate_direct_count: 0,
    candidate_reading_count: 40,
    active_version_number: null,
    active_rule_count: 0,
    ...overrides,
  };
}

describe("a register row describes the generation a project is actually in", () => {
  it("leads with the policies and rules a project holds, not with the rules it has published", () => {
    const clauses = projectRowClauses(facts());
    // The lead clause is what a reader sees first and skims by.
    expect(clauses[0]).toContain("4 policies");
    expect(clauses[0]).toContain("40 rules");
    // The defect: an unpublished project describing itself by its published count.
    expect(clauses.join(" · ")).not.toMatch(/\b0 rules\b/);
  });

  it("states a unit once, even when publication agrees with the current generation", () => {
    // Reintroduced by the fix for the defect above. Naming both real units in
    // the lead clause put "40 rules" at the start of the row, while the
    // publication clause restated the same count at the end. Both numbers were
    // true and both said "rules", so one row read as two different quantities
    // -- which is the mistake that naming records beside rules had made.
    const row = projectRowClauses(
      facts({
        review_pending: 0,
        review_pending_policies: 0,
        active_version_number: 1,
        active_rule_count: 40,
      }),
    ).join(" · ");

    expect(row).toContain("40 rules");
    expect(row).toContain("v1 published");
    expect(row.match(/\brules\b/g) ?? []).toHaveLength(1);
  });

  it("states the published count when it disagrees with the current generation", () => {
    // The gap is the whole value of the number: records have been added or
    // withdrawn since v1, and that is a thing a reader would act on. Dropping
    // it whenever it repeats must not drop it when it informs.
    const row = projectRowClauses(
      facts({
        review_pending: 0,
        review_pending_policies: 0,
        active_version_number: 1,
        active_rule_count: 12,
      }),
    ).join(" · ");

    expect(row).toContain("40 rules");
    expect(row).toContain("12 rules");
  });

  it("never contradicts itself about how many records a project holds", () => {
    // One project, one number. The old row could show "0 rules" and "411 review"
    // simultaneously; no pair of clauses may now disagree about the size of the
    // same generation.
    const clauses = projectRowClauses(
      facts({ review_pending_policies: 70, review_pending: 411, live_policy_count: 70, live_candidate_count: 411 }),
    );
    const numbers = clauses.join(" · ").match(/\d+/g) ?? [];
    // 411 may appear; 0 as a record count may not.
    expect(numbers).toContain("411");
    expect(clauses.join(" · ")).not.toMatch(/\b0 (rules|records|in review)\b/);
  });

  it("names policies and rules instead of inventing records", () => {
    const line = projectRowClauses(
      facts({
        review_pending: 0,
        review_pending_policies: 0,
        live_policy_count: 38,
        live_candidate_count: 280,
        candidate_direct_count: 2,
        candidate_reading_count: 278,
        active_version_number: 1,
        active_rule_count: 280,
      }),
    ).join(" · ");

    expect(line).toContain("38 policies · 280 rules · none in review");
    expect(line).toContain("2 Deterministic");
    expect(line).toContain("278 AI Ready");
    expect(line).not.toContain("record");
  });

  it("states routes as counts and never as a share of one another", () => {
    const mixed = projectRowClauses(
      facts({ live_candidate_count: 100, candidate_direct_count: 3, candidate_reading_count: 97 }),
    );
    const line = mixed.join(" · ");
    expect(line).toContain("3 Deterministic");
    expect(line).toContain("97 AI Ready");
    expect(line).not.toContain("%");
  });

  it("does not print a zero against a route that simply is not present", () => {
    // "0 Deterministic" is a score against a target nobody set. When every
    // record takes one route, the row says so positively.
    const line = projectRowClauses(facts()).join(" · ");
    expect(line).toContain("all AI Ready");
    expect(line).not.toContain("0 Deterministic");
  });

  it("shows records carrying no recorded route rather than filing them under one", () => {
    // Deriving one route by subtracting the other from the total would assert a
    // routing decision the record does not carry. The remainder is named.
    const line = routeClauses(10, 2, 5).join(", ");
    expect(line).toContain("2 Deterministic");
    expect(line).toContain("5 AI Ready");
    expect(line).toContain("3 without a recorded route");
  });

  // ---- CONTROLS -------------------------------------------------------------
  // A guard holding only offenders cannot tell when it has begun over-reaching.
  // These are cases where the row SHOULD report a zero or a published count, and
  // a fix that suppressed them everywhere would be wrong in the other direction.

  it("CONTROL: a project with no document still says so plainly", () => {
    const line = projectRowClauses(
      facts({ document_count: 0, review_pending: 0, live_candidate_count: 0, candidate_reading_count: 0 }),
    ).join(" · ");
    expect(line).toContain("No document loaded yet");
  });

  it("CONTROL: a loaded document that produced no records is distinguished from one never loaded", () => {
    // Collapsing these two into one phrase would hide an ingestion that found
    // nothing behind the same words as an empty project.
    const line = projectRowClauses(
      facts({ document_count: 1, review_pending: 0, live_candidate_count: 0, candidate_reading_count: 0 }),
    ).join(" · ");
    expect(line).toContain("No policies or rules yet");
    expect(line).not.toContain("No document loaded yet");
  });

  it("CONTROL: a published project still reports its published rules", () => {
    // The fix demoted publication; it must not have deleted it.
    const line = projectRowClauses(
      facts({ active_version_number: 2, active_rule_count: 128 }),
    ).join(" · ");
    expect(line).toContain("v2 published");
    expect(line).toContain("128 rules");
  });

  it("CONTROL: a project whose records are all directly evaluable says so", () => {
    const line = projectRowClauses(
      facts({ live_candidate_count: 12, candidate_direct_count: 12, candidate_reading_count: 0 }),
    ).join(" · ");
    expect(line).toContain("all Deterministic");
    expect(line).not.toContain("0 AI Ready");
  });
});

/**
 * The ratio must not come back.
 *
 * FLOOR PLACEMENT: the verdict below is "this list of offenders is empty", and a
 * scan that reads nothing produces an empty list and passes while seeing nothing.
 * So the floor is asserted AFTER the offender list, not before: when there is a
 * real offender the failure names the file and line rather than reporting a count,
 * and when the scan has gone blind the floor still catches it on the next line. A
 * count floor alone is not enough either -- a matcher that reads every file and
 * matches nothing clears any count -- so a positive control asserts the scan can
 * still find something known to be present.
 */
describe("the register surface computes no route ratio", () => {
  // Sources are pulled through Vite's own graph rather than walked with `fs`:
  // the app project does not carry node types, and a path walk can silently
  // resolve to the wrong root and read nothing.
  const sources = import.meta.glob("./**/*.{ts,tsx}", {
    query: "?raw",
    import: "default",
    eager: true,
  }) as Record<string, string>;

  it("has no surface dividing one route count by another", () => {
    let linesRead = 0;
    let positiveControlHits = 0;
    const offenders: string[] = [];

    // A route count used as a denominator, or a percentage built from one.
    const ratio =
      /(machine_executable_count|candidate_direct_count|candidate_reading_count|live_candidate_count|active_rule_count)\s*\)?\s*\*?\s*(\/|\*\s*100)/;

    const files = Object.entries(sources).filter(([path]) => !/\.test\.tsx?$/.test(path));

    for (const [path, text] of files) {
      const lines = text.split("\n");
      linesRead += lines.length;
      // Present in this repository right now; if the scan stops finding it, the
      // scan is broken rather than the tree being clean.
      if (text.includes("projectRowClauses")) positiveControlHits += 1;
      lines.forEach((line, i) => {
        const trimmed = line.trimStart();
        if (trimmed.startsWith("*") || trimmed.startsWith("//")) return;
        if (ratio.test(line)) offenders.push(`${path}:${i + 1}: ${line.trim()}`);
      });
    }

    expect(offenders).toEqual([]);

    // Floors, last. See the note above this describe block.
    expect(files.length).toBeGreaterThan(20);
    expect(linesRead).toBeGreaterThan(5000);
    expect(positiveControlHits).toBeGreaterThan(0);
  });
});
