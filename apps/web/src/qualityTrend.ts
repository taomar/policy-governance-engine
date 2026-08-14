/**
 * Whether two quality runs may be subtracted from one another.
 *
 * The history list draws a delta beside each run and tells the reader that it
 * is a trend. A trend claims that the difference between two numbers came from
 * the policy set changing. That is only true when the same instrument produced
 * both numbers, so every way the instrument can differ has to disqualify the
 * pair — otherwise the page reports a change in how we measure as a change in
 * what we measured.
 *
 * Three ways it can differ, and all three are checked here:
 *
 *   scope       - candidate rules and a published version are different
 *                 populations, not two readings of one.
 *   methodology - the detector suite. Derived rather than declared, so it moves
 *                 when the suite does (see `infrastructure/quality/methodology.py`).
 *   AI review   - whether a model was asked. This one was missing, and it is
 *                 the one with a measured cost: six AI reviews over an
 *                 identical, unchanged 273-record set returned 30, 31, 32, 33
 *                 and 34 findings. A number that moves by four without a
 *                 single record changing cannot be a point on a trend line.
 *                 Subtracting it from a deterministic run's 23 renders sampling
 *                 noise as a direction of travel.
 *
 * A deterministic run is reproducible, so two of them may be compared. An AI
 * run may not be compared with anything, including another AI run: the
 * variation is in the reading, so it is present on both sides.
 *
 * The cost is that runs which used to show a delta now show none. That is the
 * correction, not a regression — those deltas were never meaningful. A reader
 * shown fewer trends they can trust is better served than one shown a
 * confident line through noise.
 */

/** The fields of a quality run that decide comparability. */
export type ComparableRun = {
  scope: string;
  methodology_version: string;
  ai_review_used: boolean;
  finding_count: number;
};

/** Why no trend is shown, in terms the reader can act on. */
export type NoTrendReason = "ai-review" | "no-comparable-prior";

export type TrendVerdict<Run extends ComparableRun> =
  | { comparable: true; prior: Run; delta: number }
  | { comparable: false; reason: NoTrendReason };

/**
 * Whether two runs measured the same way.
 *
 * Deliberately excludes `rule_count`: a set gaining records is exactly the
 * change a trend is meant to show, so it must not disqualify the comparison.
 */
export function measuredTheSameWay(a: ComparableRun, b: ComparableRun): boolean {
  return (
    a.scope === b.scope &&
    a.methodology_version === b.methodology_version &&
    a.ai_review_used === b.ai_review_used
  );
}

/**
 * The verdict for `run` against `older`, which must be ordered newest-first and
 * contain only runs strictly older than `run`.
 */
export function trendAgainstPrior<Run extends ComparableRun>(
  run: Run,
  older: readonly Run[],
): TrendVerdict<Run> {
  // Checked before looking for a prior, so the reader is told the reason that
  // is true of this run rather than one about the runs before it.
  if (run.ai_review_used) {
    return { comparable: false, reason: "ai-review" };
  }

  const prior = older.find((candidate) => measuredTheSameWay(candidate, run));
  if (!prior) {
    return { comparable: false, reason: "no-comparable-prior" };
  }

  return { comparable: true, prior, delta: run.finding_count - prior.finding_count };
}

/** The tag shown in place of a delta. */
export const NO_TREND_LABEL: Record<NoTrendReason, string> = {
  "ai-review": "AI review — not comparable",
  "no-comparable-prior": "method baseline",
};

/** The explanation behind that tag. */
export const NO_TREND_EXPLANATION: Record<NoTrendReason, string> = {
  "ai-review":
    "This run asked a model, and repeated reviews of an unchanged rule set do not " +
    "return the same count. Its findings stand on their own; the difference from " +
    "another run would be partly the review varying, so none is shown.",
  "no-comparable-prior":
    "No earlier run measured this scope the same way. A change to the detector " +
    "suite changes what can be found at all, so it starts a new baseline rather " +
    "than reading as policy improvement or regression.",
};

/**
 * What population a quality evaluation was carried out on.
 *
 * The register used to show published-scope results only, so on a portfolio
 * where nothing has been published it reported "Not evaluated" over the top of
 * real stored findings. Both scopes now reach the surface, which means the
 * surface has to say which one it is showing: candidate records and a published
 * package are different populations, and a finding count that silently switched
 * between them would be the same defect as drawing a trend across them.
 *
 * Backend emits the code, this map owns the words. Scope is a plain column
 * (`quality_runs.scope`, documented at `domain/models.py` as "published" |
 * "candidates"), so a code added later would arrive here unmapped: it degrades
 * to a phrase that admits the gap rather than printing a raw identifier at a
 * reviewer or rendering nothing so the field looks absent.
 */
export const QUALITY_SCOPE_LABELS: Record<string, string> = {
  candidates: "candidate records",
  published: "the published package",
};

export function qualityScopeLabel(scope: string | null | undefined): string {
  if (!scope) return "an unrecorded scope";
  return QUALITY_SCOPE_LABELS[scope] ?? "a scope this view does not recognise";
}
