import { describe, expect, it } from "vitest";
import {
  NO_TREND_EXPLANATION,
  NO_TREND_LABEL,
  QUALITY_SCOPE_LABELS,
  measuredTheSameWay,
  qualityScopeLabel,
  trendAgainstPrior,
  type ComparableRun,
} from "./qualityTrend";

/**
 * That a delta on the quality history means what the page says it means.
 *
 * The page tells the reader each row is compared against the run before it and
 * calls that a trend. The claim inside a trend is that the difference came from
 * the policy set changing. So the test that matters is not "does it subtract" —
 * it is "does it refuse to subtract two numbers produced by different
 * instruments", because that is the only way the sentence can be false.
 *
 * The AI case has a measured cost behind it: six reviews over one unchanged
 * 273-record set returned 30, 31, 32, 33 and 34 findings. Any delta drawn
 * through those is reporting the review varying as the policy set improving.
 */

const RUN: ComparableRun = {
  scope: "candidate",
  methodology_version: "3-92eb08dfdf4a",
  ai_review_used: false,
  finding_count: 20,
};

function run(overrides: Partial<ComparableRun> = {}): ComparableRun {
  return { ...RUN, ...overrides };
}

describe("what disqualifies a comparison", () => {
  it("subtracts two runs that measured the same way", () => {
    const verdict = trendAgainstPrior(run({ finding_count: 20 }), [
      run({ finding_count: 26 }),
    ]);

    expect(verdict.comparable).toBe(true);
    if (!verdict.comparable) return;
    expect(verdict.delta).toBe(-6);
  });

  it("refuses a trend for a run that asked a model", () => {
    // Its own number is not reproducible, so nothing may be subtracted from
    // it — including another AI run, where the variation sits on both sides.
    const verdict = trendAgainstPrior(run({ ai_review_used: true }), [
      run({ ai_review_used: true, finding_count: 34 }),
    ]);

    expect(verdict.comparable).toBe(false);
    if (verdict.comparable) return;
    expect(verdict.reason).toBe("ai-review");
  });

  it("does not subtract a deterministic run from an AI one", () => {
    // The defect this file exists for: 23 deterministic against 34 AI-reviewed
    // rendered as "+11", which is sampling noise shown as a direction.
    const verdict = trendAgainstPrior(run({ finding_count: 23 }), [
      run({ ai_review_used: true, finding_count: 34 }),
    ]);

    expect(verdict.comparable).toBe(false);
    if (verdict.comparable) return;
    expect(verdict.reason).toBe("no-comparable-prior");
  });

  it("does not subtract across a change to the detector suite", () => {
    const verdict = trendAgainstPrior(run({ finding_count: 99 }), [
      run({ methodology_version: "2", finding_count: 23 }),
    ]);

    expect(verdict.comparable).toBe(false);
    if (verdict.comparable) return;
    expect(verdict.reason).toBe("no-comparable-prior");
  });

  it("does not subtract across scopes", () => {
    const verdict = trendAgainstPrior(run(), [
      run({ scope: "published", finding_count: 5 }),
    ]);

    expect(verdict.comparable).toBe(false);
  });

  it("skips past a disqualified run to reach a comparable one", () => {
    // Ordered newest-first. An AI run in the middle of the history must not
    // sever the sequence between two deterministic runs either side of it.
    const verdict = trendAgainstPrior(run({ finding_count: 20 }), [
      run({ ai_review_used: true, finding_count: 34 }),
      run({ methodology_version: "2", finding_count: 23 }),
      run({ finding_count: 27 }),
    ]);

    expect(verdict.comparable).toBe(true);
    if (!verdict.comparable) return;
    expect(verdict.delta).toBe(-7);
  });
});

describe("what must not disqualify a comparison", () => {
  it("still compares when the record count changed", () => {
    // A set gaining or losing records is precisely the change a trend exists
    // to show. Excluding it would make the delta unreachable in normal use.
    expect(
      measuredTheSameWay(run(), run({ finding_count: 999 })),
    ).toBe(true);
  });
});

describe("what the reader is told instead of a delta", () => {
  it("gives a distinct reason for each way a comparison fails", () => {
    // A run withheld because a model was asked and one withheld because the
    // suite changed are different facts. Labelling both "method baseline"
    // would tell the reader the wrong thing about their own run.
    expect(NO_TREND_LABEL["ai-review"]).not.toBe(
      NO_TREND_LABEL["no-comparable-prior"],
    );
  });

  it("explains every reason it can report", () => {
    const reasons = Object.keys(NO_TREND_LABEL);

    for (const reason of reasons) {
      const label = NO_TREND_LABEL[reason as keyof typeof NO_TREND_LABEL];
      const explanation =
        NO_TREND_EXPLANATION[reason as keyof typeof NO_TREND_EXPLANATION];

      expect(label.trim().length).toBeGreaterThan(0);
      // A reason with no explanation reads as the page being broken rather
      // than as a deliberate refusal, which invites someone to "fix" it.
      expect(explanation, `no explanation for "${reason}"`).toBeTruthy();
      expect(explanation.trim().length).toBeGreaterThan(40);
      // Whatever it says, it must not surface the internal key.
      expect(label).not.toContain(reason);
    }
  });
});

/**
 * That a scope code reaches a reviewer as words, whatever the code turns out
 * to be.
 *
 * This is asserted by calling the function rather than by reading its source.
 * A first version of this check lived in the Python guard and inspected the
 * returned expression textually; a leak written as `?? `scope ${scope}`` did
 * not match its pattern, so the check passed while the identifier reached the
 * surface. Behaviour cannot be evaded by restatement, and the two failure
 * modes here are both silent ones a reviewer would never report: an internal
 * code shown as though it were English, or an empty string where the
 * explanation belongs.
 *
 * The companion guard `tests/unit/test_quality_scopes_have_wording.py`
 * enumerates the codes that exist today from the model definition and requires
 * each to be mapped. Between them: every current code has words, and any
 * future one degrades into words instead of into an identifier or a blank.
 */
describe("qualityScopeLabel", () => {
  it("words every scope it knows", () => {
    for (const [code, label] of Object.entries(QUALITY_SCOPE_LABELS)) {
      expect(qualityScopeLabel(code)).toBe(label);
      // Not `not.toContain(code)`: a first draft asserted that and failed on
      // `published` -> "the published package", where the code happens to be
      // an ordinary English word and belongs in its own label. Echoing the
      // identifier is the defect, not sharing a word with it.
      expect(label).not.toBe(code);
      expect(label).not.toMatch(/_/);
    }
  });

  // CONTROL: the map is not empty, so the loop above is not passing vacuously.
  it("has scopes to word at all", () => {
    expect(Object.keys(QUALITY_SCOPE_LABELS).length).toBeGreaterThan(0);
  });

  it("never renders an unrecognised code as the code itself", () => {
    const future = "provisional_snapshot";
    const rendered = qualityScopeLabel(future);
    expect(rendered).not.toContain(future);
    expect(rendered.trim().length).toBeGreaterThan(0);
  });

  it("says something rather than nothing when no scope was recorded", () => {
    for (const absent of [null, undefined, ""]) {
      const rendered = qualityScopeLabel(absent);
      expect(rendered.trim().length).toBeGreaterThan(0);
      expect(rendered).not.toContain("undefined");
      expect(rendered).not.toContain("null");
    }
  });

  it("describes a population without grading it", () => {
    // A scope names which records were checked. It is not a verdict on them,
    // and wording that implied one would put a judgement on the surface that
    // the data does not carry.
    const forbidden = /incomplete|insufficient|only|merely|not yet|failed|unfinished/i;
    for (const label of Object.values(QUALITY_SCOPE_LABELS)) {
      expect(label).not.toMatch(forbidden);
    }
  });
});