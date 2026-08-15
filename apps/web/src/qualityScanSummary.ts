import { UNKNOWN_COUNT } from "./loadState";

/**
 * What the review strip says about the quality scan.
 *
 * The strip used to read `count ?? "—"` with the caption
 * `count === null ? "Scan not run" : "Across loaded rules"`. That is two
 * statements covering four situations, and two of the four came out false:
 *
 *   - while the scan was running, the strip said it had not been run;
 *   - after the scan failed, the strip said it had not been run.
 *
 * The failure did announce itself, in an Alert the reviewer can close. Once
 * closed, the only remaining claim about the scan was the wrong one, and a
 * reviewer who had asked for a scan was left reading that none had happened.
 * That is why this takes `failed` as a fact rather than reading the error
 * message: dismissing a message silences the message, it does not undo the
 * attempt.
 *
 * Absent, in flight, failed and a true zero are four different things. Three of
 * them are not numbers, so they keep `UNKNOWN_COUNT` instead of borrowing a
 * digit, and they are told apart by the sentence underneath. The fourth is a
 * real zero and says so in words as well, because "0" alone next to a caption
 * about loaded rules reads to some people as "nothing happened" rather than
 * "we looked and there was nothing".
 *
 * This lives outside the component so the four cases can be stated as four
 * cases, rather than only being reachable by driving a queue into each state.
 */
export type QualityScanSummary = {
  /** The number to show, or `UNKNOWN_COUNT` when there is honestly no number. */
  readonly display: string;
  /** The sentence under it. Always present; never blank. */
  readonly caption: string;
  /** True only when a scan completed and this is its real answer, zero included. */
  readonly isAnswer: boolean;
};

export function qualityScanSummary(input: {
  /** A scan is in flight right now. */
  readonly loading: boolean;
  /**
   * The last scan attempt failed. This is the *fact*, not the message: the
   * message is dismissible and the fact is not, so a reviewer who closes the
   * error notice is not told afterwards that no scan ever ran.
   */
  readonly failed: boolean;
  /** Findings across loaded rules, or `null` when no scan has completed. */
  readonly count: number | null;
}): QualityScanSummary {
  if (input.loading) {
    return { display: UNKNOWN_COUNT, caption: "Scanning now", isAnswer: false };
  }
  if (input.failed) {
    return { display: UNKNOWN_COUNT, caption: "Scan failed — not re-run", isAnswer: false };
  }
  if (input.count === null) {
    return { display: UNKNOWN_COUNT, caption: "Scan not run", isAnswer: false };
  }
  if (input.count === 0) {
    return { display: "0", caption: "None found across loaded rules", isAnswer: true };
  }
  return { display: String(input.count), caption: "Across loaded rules", isAnswer: true };
}
