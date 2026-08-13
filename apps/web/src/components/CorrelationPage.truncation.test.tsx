import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, waitFor } from "@testing-library/react";
import { App } from "antd";
import { ActorProvider } from "../ActorContext";
import { CorrelationPage } from "./CorrelationPage";

/**
 * A capped list must look capped on screen, not only in the response.
 *
 * The server now returns `{runs, count, truncated}` for lists it may have cut
 * short, and a backend guard holds it to that. But an honest response read by
 * a silent client is still a screen that lies: this page feeds the list into a
 * run picker, and an option missing from a dropdown does not look withheld, it
 * looks like it never existed. A reviewer hunting an older run would conclude
 * it was never performed.
 *
 * So the claim under test is the one the backend cannot make: that `truncated`
 * reaches the reader. Both directions are asserted, because a notice that is
 * always on carries no more information than one that is never on.
 *
 * The numbers are local constants and every expectation is derived from them,
 * so nothing here depends on any particular policy set, run history or cap.
 */

const POLICY_SET_KEY = "policy-set-under-test";

/** How many runs the stub returns. Any positive number works. */
const RETURNED_RUNS = 3;

const listCorrelationRuns = vi.fn();
const getCorrelationFindings = vi.fn();

vi.mock("../api", async () => {
  const actual = await vi.importActual<typeof import("../api")>("../api");
  return {
    ...actual,
    aiApi: {
      listCorrelationRuns: (...args: unknown[]) => listCorrelationRuns(...args),
      getCorrelationFindings: (...args: unknown[]) => getCorrelationFindings(...args),
    },
  };
});

function run(index: number) {
  return {
    id: `run-${index}`,
    status: "completed",
    rules_analyzed: index,
    groups_analyzed: 0,
    groups_available: 0,
    rules_uncompared: 0,
    rules_budget_skipped: 0,
    prompt_version: "v1",
    error_message: null,
    created_at: `2024-01-0${index + 1}T00:00:00+00:00`,
    completed_at: `2024-01-0${index + 1}T00:01:00+00:00`,
  };
}

function respondWith(truncated: boolean) {
  const runs = Array.from({ length: RETURNED_RUNS }, (_, index) => run(index));
  listCorrelationRuns.mockResolvedValue({
    runs,
    count: runs.length,
    truncated,
  });
  getCorrelationFindings.mockResolvedValue({
    findings: [],
    run: null,
    counts: {},
  });
}

function renderPage() {
  return render(
    <ActorProvider>
      <App>
        <CorrelationPage policySetKey={POLICY_SET_KEY} />
      </App>
    </ActorProvider>,
  );
}

/**
 * Leaf elements only. A `textContent` match walks ancestors too, and every
 * wrapper up to `<body>` would answer to it.
 */
const leaves = () =>
  Array.from(document.querySelectorAll("*")).filter(
    (element) => element.children.length === 0,
  );

const notices = () =>
  leaves().filter((element) =>
    (element.textContent ?? "").startsWith(`Most recent ${RETURNED_RUNS} runs`),
  );

/**
 * The run picker, which the notice is rendered beside and behind the same
 * `runs.length > 0` guard as.
 *
 * This is the floor under the absence check below. "No notice found" is also
 * what an unmounted picker, a changed wrapper condition or a broken leaf scan
 * produce, and those are indistinguishable from a correct silence. Counting
 * what was examined separates them.
 *
 * The picker is matched by an explicit hook rather than by its option text or
 * by a class. Nothing selects a run on load, so no option label is ever in the
 * DOM to match on; and this page has two header rows and two selects, the
 * second of which renders whether or not any run exists. Both earlier attempts
 * at this floor passed against exactly the blindness they were added to detect
 * — one page-wide count and one scoped to a class shared by another region. A
 * floor that cannot go to zero is not a floor.
 */
const runPickers = () =>
  document.querySelectorAll('[data-testid="correlation-run-picker"]');

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("a correlation run list the server cut short", () => {
  it("says so next to the picker", async () => {
    respondWith(true);
    renderPage();

    await waitFor(() => expect(listCorrelationRuns).toHaveBeenCalled());
    await waitFor(() =>
      expect(
        notices().length,
        "the server reported the run list was cut short and the page showed no sign of it",
      ).toBe(1),
    );
  });

  it("stays quiet when the list is complete", async () => {
    respondWith(false);
    renderPage();

    // Settle both loads before asserting an absence, so "not drawn yet" cannot
    // masquerade as "correctly withheld".
    await waitFor(() => expect(listCorrelationRuns).toHaveBeenCalled());
    await waitFor(() => expect(getCorrelationFindings).toHaveBeenCalled());

    // Floor first: prove the region that would carry the notice is on screen,
    // and that the leaf scan the assertion below depends on is seeing any DOM
    // at all. Placed here rather than folded into the assertion below so that a
    // real regression still fails on the notice and names it, instead of
    // failing on the count and reading like a broken fixture.
    await waitFor(() =>
      expect(
        runPickers().length,
        "the run picker never rendered, so the absence check below would pass " +
          "against an empty screen and prove nothing",
      ).toBeGreaterThan(0),
    );
    expect(
      leaves().length,
      "the leaf scan matched no elements at all, so it cannot be trusted to " +
        "report that one particular element is missing",
    ).toBeGreaterThan(0);

    expect(
      notices().length,
      "every run was listed, so a partial-list warning here would teach the reader to ignore the one that matters",
    ).toBe(0);
  });
});
