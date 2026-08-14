import { describe, expect, it } from "vitest";
import {
  NO_TREND_EXPLANATION,
  NO_TREND_LABEL,
  measuredTheSameWay,
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
