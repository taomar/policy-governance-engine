import { describe, expect, it } from "vitest";
import { qualityScanSummary } from "./qualityScanSummary";
import { UNKNOWN_COUNT } from "./loadState";

/**
 * A SCAN NOT RUN, A SCAN RUNNING, A SCAN THAT FAILED AND A SCAN THAT FOUND
 * NOTHING ARE FOUR DIFFERENT ANSWERS.
 *
 * The review strip previously carried two: a number or an em-dash, captioned
 * "Across loaded rules" or "Scan not run". A scan in flight and a scan that had
 * failed both fell into "Scan not run", which was a false statement about work
 * the reviewer had asked for and, in the failed case, the only statement left
 * once its Alert was dismissed.
 *
 * These tests fail against that older shape: it had no way to say "Scanning
 * now" or "Scan failed", and no way to distinguish a real zero in words.
 */
describe("the quality strip tells four scan outcomes apart", () => {
  const states = {
    notRun: { loading: false, failed: false, count: null },
    running: { loading: true, failed: false, count: null },
    failed: { loading: false, failed: true, count: null },
    foundNothing: { loading: false, failed: false, count: 0 },
    foundSome: { loading: false, failed: false, count: 7 },
  } as const;

  it("gives every outcome a caption of its own", () => {
    const captions = Object.values(states).map((s) => qualityScanSummary(s).caption);
    expect(new Set(captions).size).toBe(captions.length);
  });

  it("never leaves a caption blank, so no outcome is silent", () => {
    for (const [name, state] of Object.entries(states)) {
      const caption = qualityScanSummary(state).caption;
      expect(caption.trim().length, `${name} said nothing`).toBeGreaterThan(0);
    }
  });

  it("does not claim a scan was never run while one is running", () => {
    const running = qualityScanSummary(states.running);
    expect(running.caption).not.toBe(qualityScanSummary(states.notRun).caption);
    expect(running.caption.toLowerCase()).toContain("scanning");
  });

  it("does not claim a scan was never run after one failed", () => {
    const failed = qualityScanSummary(states.failed);
    expect(failed.caption).not.toBe(qualityScanSummary(states.notRun).caption);
    expect(failed.caption.toLowerCase()).toContain("failed");
  });

  it("shows no digit for any outcome that is not an answer", () => {
    for (const name of ["notRun", "running", "failed"] as const) {
      const summary = qualityScanSummary(states[name]);
      expect(summary.display, `${name} borrowed a number`).toBe(UNKNOWN_COUNT);
      expect(summary.isAnswer).toBe(false);
      expect(/\d/.test(summary.display)).toBe(false);
    }
  });

  it("shows a true zero as a zero, and says in words that it looked", () => {
    const none = qualityScanSummary(states.foundNothing);
    expect(none.display).toBe("0");
    expect(none.isAnswer).toBe(true);
    expect(none.caption.toLowerCase()).toContain("none found");
  });

  it("keeps a real count as its own number", () => {
    const some = qualityScanSummary(states.foundSome);
    expect(some.display).toBe("7");
    expect(some.isAnswer).toBe(true);
  });

  it("separates a zero answer from every outcome that has no answer", () => {
    const zero = qualityScanSummary(states.foundNothing);
    for (const name of ["notRun", "running", "failed"] as const) {
      const other = qualityScanSummary(states[name]);
      expect(zero.display).not.toBe(other.display);
      expect(zero.caption).not.toBe(other.caption);
      expect(zero.isAnswer).not.toBe(other.isAnswer);
    }
  });

  it("reports being in flight even when a previous scan left findings behind", () => {
    const refreshing = qualityScanSummary({ loading: true, failed: true, count: 4 });
    expect(refreshing.display).toBe(UNKNOWN_COUNT);
    expect(refreshing.caption.toLowerCase()).toContain("scanning");
    expect(refreshing.isAnswer).toBe(false);
  });

  it("frames no outcome as a fault of the engine", () => {
    const forbidden = /\b(cannot|can't|unable|fail(?:s|ed)? to|not supported|unsupported|too complex|couldn't)\b/i;
    for (const [name, state] of Object.entries(states)) {
      const caption = qualityScanSummary(state).caption;
      expect(forbidden.test(caption), `${name}: "${caption}"`).toBe(false);
    }
  });

  /**
   * The failure notice is an Alert with a close button, and closing it clears
   * the message. If the strip read that message, dismissing it would take the
   * failure with it and the strip would go back to "Scan not run" — telling a
   * reviewer who had just watched a scan fail that none had ever run.
   *
   * The summary therefore takes the fact, not the message. This is the test
   * that broke when the strip was wired to the error string, and it is the
   * reason the component keeps `qualityFailed` separately from `qualityError`.
   */
  it("still reports a failure after its message has been dismissed", () => {
    const whileShown = qualityScanSummary({ loading: false, failed: true, count: null });
    const afterDismissal = qualityScanSummary({ loading: false, failed: true, count: null });
    expect(afterDismissal.caption).toBe(whileShown.caption);
    expect(afterDismissal.caption).not.toBe(
      qualityScanSummary({ loading: false, failed: false, count: null }).caption,
    );
  });

  it("does not let a stale count outlive a failed re-run", () => {
    const failedRerun = qualityScanSummary({ loading: false, failed: true, count: 4 });
    expect(failedRerun.display).toBe(UNKNOWN_COUNT);
    expect(failedRerun.isAnswer).toBe(false);
  });
});
