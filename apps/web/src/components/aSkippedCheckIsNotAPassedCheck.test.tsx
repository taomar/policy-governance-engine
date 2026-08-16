import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { QualityRouteApplicability } from "./QualityPage";

/**
 * A CHECK THAT DID NOT APPLY IS NOT A CHECK THAT PASSED.
 *
 * A stored quality run records its findings. A route-specific check that had
 * nothing in scope to speak to is not a finding, so before this it left no
 * trace on the stored run at all: the page showed the findings and, by showing
 * only those, implied every other check ran and was clean. That is the
 * overclaim in docs/failures/display-overclaims.md -- a convenient absence read
 * as a positive result.
 *
 * The disclosure has three inputs and they are three different states, which
 * this component must keep apart:
 *   undefined / null -> the run predates the disclosure; nothing is known.
 *   []               -> the run recorded it, and every check applied.
 *   [entry, ...]     -> the run recorded it, and these checks did not apply.
 *
 * WHY THE FLOOR RUNS FIRST
 *
 * The cheap way to pass "never says a skipped check passed" is to render
 * nothing for the skipped check. That hides the very fact the reader needs. So
 * `names the check that did not apply, and to how many records` runs FIRST and
 * asserts the check's identity and its scope are actually on the page. Every
 * absence assertion below is only worth anything while that presence holds.
 */

/** antd measures the viewport; jsdom provides neither of these. */
function stubBrowserMeasurements() {
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  );
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  );
}

/**
 * One route-specific check with records on the other route in scope. The count
 * is a value this test supplies and reads back, not a claim about any corpus.
 */
const SKIPPED_CHECK = {
  check: "not_runnable_as_stored",
  route: "ai_ready",
  applicability: "not_applicable",
  records_in_scope: 3,
  applies_to_routes: ["deterministic"],
};

const CHECK_NAME = /Not Runnable As Stored/;

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("a stored run says which checks did not apply, and never that they passed", () => {
  // FLOOR. Runs first and must stay first: the absence assertions below only
  // mean something while the skipped check and its scope are actually shown.
  it("names the check that did not apply, and to how many records", () => {
    stubBrowserMeasurements();
    render(<QualityRouteApplicability disclosure={[SKIPPED_CHECK]} />);

    expect(screen.getByText(CHECK_NAME)).toBeTruthy();
    expect(
      document.body.textContent,
      "summarised the skipped check without leaving its record scope reachable",
    ).toContain(String(SKIPPED_CHECK.records_in_scope));
  });

  it("says the check did not apply, and never that it passed", () => {
    stubBrowserMeasurements();
    render(<QualityRouteApplicability disclosure={[SKIPPED_CHECK]} />);

    expect(document.body.textContent).toMatch(/did not apply/i);
    expect(
      document.body.textContent,
      "drew a check that had nothing in scope as one that passed",
    ).not.toMatch(/passed/i);
  });

  // Recorded-and-all-applied is a positive fact and is stated as one.
  it("states plainly when every check applied", () => {
    stubBrowserMeasurements();
    render(<QualityRouteApplicability disclosure={[]} />);

    expect(screen.getByText(/Every quality check applied to all records/i)).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/did not apply/i);
  });

  // Not-recorded is its own state. It must not borrow the words of the
  // all-applied state, or a run that never recorded the disclosure would read
  // as one that recorded a clean sweep.
  it("says the disclosure was not recorded, without claiming every check applied", () => {
    stubBrowserMeasurements();
    render(<QualityRouteApplicability disclosure={null} />);

    expect(screen.getByText(/not recorded/i)).toBeTruthy();
    expect(
      document.body.textContent,
      "an unrecorded disclosure was drawn as an all-applied one",
    ).not.toMatch(/Every quality check applied to all records/i);
    expect(document.body.textContent).not.toMatch(/passed/i);
  });
});
