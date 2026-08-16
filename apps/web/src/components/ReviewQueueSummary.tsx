/**
 * The review queue's one-line summary.
 *
 * WHY THIS EXISTS
 *
 * The queue header used to carry the same facts more than once. Progress was
 * stated as a publish bar up top *and* as a "Decision progress" card lower down;
 * the record scale (`N policies · M rules`) was printed a third time as a total
 * over the status tabs that already carry it; "Related families" sat as a stat
 * card while the controls bar below shows the same family count as a richer,
 * tooltipped tag. Four stat cards, a progress bar and a scale total is a lot of
 * chrome for a reviewer to read past before the first record.
 *
 * This collapses what is genuinely queue-level and *not* said elsewhere into one
 * quiet line, in the reviewer's order of interest:
 *
 *   1. **Decision progress** — how much of the queue is decided. The aggregate
 *      the per-status tabs do not state on their own.
 *   2. **Ready to publish** — the next thing to act on: approved, not yet live.
 *   3. **Quality findings** — the standing of the last scan.
 *
 * WHAT IT DELIBERATELY DOES NOT DO (constraint 11 — de-duplicate, never delete a
 * distinction):
 *
 *   - It does not restate `N policies · M rules` as a bare total. That scale is
 *     already on the `All` tab. The decided *progress* here ("4 of 32 policies")
 *     is a different statement and keeps both units, because a policy is what
 *     gets decided and rules are what a policy is made of (constraint 2).
 *   - It does not invent a number for the quality scan. `quality` is rendered
 *     exactly as {@link qualityScanSummary} computed it, so *absent* stays "—"
 *     with "Scan not run" beneath, and is never flattened to a `0` that would
 *     read as "we looked and found nothing" (constraint 5). Absent, in-flight,
 *     failed and a true zero remain four different things.
 *
 * It is a pure presentational component: every value is computed by the queue
 * and passed in, so each state can be rendered and asserted directly rather than
 * only by driving a live queue into it.
 */
import type { QualityScanSummary } from "../qualityScanSummary";

interface ReviewQueueSummaryProps {
  /** Share of records decided (approved / rejected / published), 0–100. */
  readonly decisionPercent: number;
  /**
   * Pre-formatted decided-progress detail from `recordProgressLabel`, e.g.
   * "4 of 32 policies · 40 of 398 rules". Kept in both units on purpose.
   */
  readonly progressDetail: string;
  /** Approved-but-not-live records — the next thing to act on. */
  readonly readyToPublish: number;
  /**
   * Four-state quality summary. Rendered verbatim: the component must not
   * second-guess `display`, so "—" for an absent scan stays "—".
   */
  readonly quality: QualityScanSummary;
}

export function ReviewQueueSummary({
  decisionPercent,
  progressDetail,
  readyToPublish,
  quality,
}: ReviewQueueSummaryProps) {
  return (
    <dl className="review-queue-summary" aria-label="Review queue summary">
      <div className="review-queue-summary__item">
        <dt>Decision progress</dt>
        <dd>{decisionPercent}%</dd>
        <small>{progressDetail} decided</small>
      </div>
      <div
        className={
          readyToPublish > 0
            ? "review-queue-summary__item review-operation-attention"
            : "review-queue-summary__item"
        }
      >
        <dt>Ready to publish</dt>
        <dd>{readyToPublish}</dd>
        <small>Approved rules, not live</small>
      </div>
      <div className="review-queue-summary__item">
        <dt>Quality findings</dt>
        <dd>{quality.display}</dd>
        <small>{quality.caption}</small>
      </div>
    </dl>
  );
}
