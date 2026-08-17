import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import type { ExtractionProgress } from "../api";
import ExtractionProgressPanel from "./ExtractionProgressPanel";

/**
 * The strip has to say what the run is actually doing, and two states are the
 * ones it is most prone to blur.
 *
 * 1. COMPARING is not FINISHED. The run's last act is a comparison against the
 *    previous extraction (ai_extraction.py emits "Comparing against the previous
 *    extraction…" while the run's status is still `running`, deliberately after
 *    every rule is drafted, linked and committed). The chain's throughput really
 *    is done by then — but the run is not, and the strip must not read as though
 *    it is. The prior panel had no branch for the sentence, so it fell through to
 *    lighting the *first* box, making a finished chain look like it had jumped
 *    back to reading the document.
 *
 * 2. A stage NOT YET REACHED is not a stage that FOUND NOTHING. Both used to
 *    print "0", so a reviewer could not tell "the run has not got here" from
 *    "the run got here and drew a blank". A `0` that can mean either is the
 *    defect this panel is most prone to, so the two now read apart: an unreached
 *    stage shows an em dash, a reached-but-empty stage shows 0.
 */

const extractionProgress = vi.fn();

vi.mock("../api", async () => {
  const actual = await vi.importActual<typeof import("../api")>("../api");
  return {
    ...actual,
    aiApi: {
      extractionProgress: (...args: unknown[]) => extractionProgress(...args),
    },
  };
});

/** A full payload with everything zeroed; each test overrides only what it means. */
function payload(overrides: Partial<ExtractionProgress> = {}): ExtractionProgress {
  return {
    active: true,
    status: "running",
    stage: "",
    total_clauses: 374,
    processed_clauses: 0,
    total_batches: 38,
    processed_batches: 0,
    total_pages: 43,
    processed_pages: 0,
    passages_found: 0,
    rules_drafted: 0,
    rules_committed: 0,
    skipped: 0,
    linked: 0,
    superseded: 0,
    delta_new: 0,
    delta_changed: 0,
    delta_unchanged: 0,
    delta_removed: 0,
    run_reference: "RUN-TEST",
    elapsed_seconds: 90,
    ...overrides,
  };
}

async function renderWith(p: ExtractionProgress) {
  extractionProgress.mockResolvedValue(p);
  render(<ExtractionProgressPanel documentVersionId="v1" running />);
  // The panel shows "Starting…" until its first poll resolves; wait for the run
  // reference, which only appears once a real payload has landed.
  await screen.findByText("RUN-TEST");
}

/** The value rendered inside the box whose label is `label`. */
function boxValue(label: string): string {
  const box = screen.getByText(label).closest(".extract-stage");
  if (!box) throw new Error(`no stage box for "${label}"`);
  return box.querySelector(".extract-stage-value")?.textContent ?? "";
}

function box(label: string): HTMLElement {
  const el = screen.getByText(label).closest(".extract-stage");
  if (!el) throw new Error(`no stage box for "${label}"`);
  return el as HTMLElement;
}

beforeEach(() => {
  extractionProgress.mockReset();
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
});

afterEach(() => {
  cleanup();
});

describe("comparing is a running state, not a finished one", () => {
  const comparing = payload({
    status: "running",
    stage: "Comparing against the previous extraction…",
    processed_batches: 38,
    processed_clauses: 374,
    processed_pages: 43,
    passages_found: 190,
    rules_drafted: 190,
    rules_committed: 190,
    linked: 150,
  });

  const done = payload({
    status: "completed",
    stage: "Done — 3 new, 2 changed since the previous extraction.",
    processed_batches: 38,
    processed_clauses: 374,
    processed_pages: 43,
    passages_found: 190,
    rules_drafted: 190,
    rules_committed: 190,
    linked: 150,
    delta_new: 3,
    delta_changed: 2,
    delta_unchanged: 185,
    delta_removed: 0,
  });

  it("does not re-light the first box while comparing", async () => {
    await renderWith(comparing);
    // The whole defect: the comparison sentence had no branch, so the strip lit
    // the intake box as if the run had started over.
    expect(box("Document").className).not.toContain("extract-stage--active");
  });

  it("shows the throughput chain as settled while comparing", async () => {
    await renderWith(comparing);
    for (const label of ["Document", "Policy statements", "Rules drafted", "Linked", "In review queue"]) {
      expect(box(label).className).toContain("extract-stage--done");
      expect(box(label).className).not.toContain("extract-stage--active");
    }
  });

  it("marks comparing as still working, distinct from done", async () => {
    await renderWith(comparing);
    // A comparison-in-progress affordance is present…
    expect(screen.getByText(/checking this run against the previous extraction/i)).toBeTruthy();
    // …and the settled delta summary, which is the OUTPUT of comparison, is not
    // shown yet — that only appears once the run is done.
    expect(screen.queryByText("Since the previous extraction")).toBeNull();
  });

  it("swaps the working affordance for the delta once done", async () => {
    await renderWith(done);
    expect(screen.getByText("Since the previous extraction")).toBeTruthy();
    expect(screen.queryByText(/checking this run against the previous extraction/i)).toBeNull();
  });
});

describe("a stage not reached reads apart from a stage that found nothing", () => {
  it("shows an em dash for a stage the run has not reached", async () => {
    // Reading batch 2: the scan stage is live and has found nothing yet, but the
    // formulate/link/review stages have not been reached at all.
    await renderWith(
      payload({
        stage: "Reading batch 2 of 38 · pages 5–8 — finding policy statements",
        processed_batches: 1,
        processed_clauses: 15,
        processed_pages: 4,
        passages_found: 0,
        rules_drafted: 0,
        linked: 0,
        rules_committed: 0,
      }),
    );

    // Reached, drew a blank: a real zero.
    expect(boxValue("Policy statements")).toBe("0");
    // Not reached: an em dash, so the zero above cannot be mistaken for "not yet".
    expect(boxValue("Rules drafted")).toBe("—");
    expect(boxValue("Linked")).toBe("—");
    expect(boxValue("In review queue")).toBe("—");

    // The point of the test, stated as the inequality it guards.
    expect(boxValue("Policy statements")).not.toBe(boxValue("Rules drafted"));
  });

  it("keeps a real zero once a stage is reached and stays empty", async () => {
    // A completed run that linked nothing: "Linked 0" is now a fact about the
    // finished run, not "not reached", so it must read as 0, never an em dash.
    await renderWith(
      payload({
        status: "completed",
        stage: "Done — no changes.",
        processed_batches: 38,
        passages_found: 190,
        rules_drafted: 190,
        rules_committed: 190,
        linked: 0,
        delta_unchanged: 190,
      }),
    );
    expect(boxValue("Linked")).toBe("0");
    expect(boxValue("Rules drafted")).toBe("190");
  });
});
