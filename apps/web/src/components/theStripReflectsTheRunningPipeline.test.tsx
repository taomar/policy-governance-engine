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

describe("the route each drafted rule takes is shown, and a route's 0 reads apart from no rules yet", () => {
  /**
   * Every drafted rule is assigned one of two routes as it is drafted:
   * Deterministic (the source states a test the engine computes over named
   * facts) or AI Ready (the source states its test in words, for a judge to read
   * against the case). The service now carries a run-scoped tally of each —
   * `rules_deterministic` and `rules_ai_ready` — read against `rules_drafted`.
   *
   * Three things this readout must get right, and one it must never do:
   *   - it must not appear before a rule is drafted (nothing to split yet);
   *   - once rules are drafted, a route's 0 is a real "no rule took this one",
   *     not "not reached" — the same trap the stage boxes have, one level down;
   *   - the two counts need not sum to the rules drafted (a rule with no mode is
   *     in neither), and that remainder is information, not to be absorbed;
   *   - neither route may be drawn as a shortfall: no bar, no percentage,
   *     nothing that turns an ordinary 7-to-190 split into a deficiency.
   */

  /** A batch-4 drafting payload carrying the route split. */
  const drafting = (over: Partial<ExtractionProgress> = {}): ExtractionProgress =>
    payload({
      stage: "Formulating rules from batch 4 of 38 — 6 policy statement(s) found",
      processed_batches: 3,
      processed_clauses: 40,
      processed_pages: 12,
      passages_found: 24,
      rules_drafted: 20,
      rules_deterministic: 1,
      rules_ai_ready: 19,
      ...over,
    });

  function routeRegion(): HTMLElement | null {
    return document.querySelector(".extract-routes");
  }

  /** The count rendered on the route chip whose name contains `name`. */
  function routeValue(name: string): string {
    const region = routeRegion();
    if (!region) throw new Error("no route region");
    const chip = Array.from(region.querySelectorAll(".extract-route")).find((c) =>
      c.textContent?.includes(name),
    );
    if (!chip) throw new Error(`no route chip for "${name}"`);
    return chip.querySelector(".extract-stage-value")?.textContent ?? "";
  }

  it("shows the Deterministic and AI Ready counts once rules are drafted", async () => {
    await renderWith(drafting({ rules_drafted: 20, rules_deterministic: 1, rules_ai_ready: 19 }));
    expect(routeRegion()).not.toBeNull();
    expect(routeValue("Deterministic")).toBe("1");
    expect(routeValue("AI Ready")).toBe("19");
  });

  it("does not show a route split before any rule is drafted", async () => {
    // The counters are present and zero, but nothing has been drafted — so there
    // is nothing to split, and a "0 · 0" here would read as a found result.
    await renderWith(
      drafting({
        stage: "Reading batch 1 of 38 · pages 1–4 — finding policy statements",
        processed_batches: 0,
        rules_drafted: 0,
        rules_deterministic: 0,
        rules_ai_ready: 0,
      }),
    );
    expect(routeRegion()).toBeNull();
  });

  it("shows a real 0 for a route no rule took, distinct from not-yet-drafted", async () => {
    // Rules drafted, all of them AI Ready: "0 Deterministic" is now a fact about
    // the run so far, not "not reached". It must render 0, and the split must be
    // present — which is what tells it apart from the not-yet case above.
    await renderWith(drafting({ rules_drafted: 19, rules_deterministic: 0, rules_ai_ready: 19 }));
    expect(routeRegion()).not.toBeNull();
    expect(routeValue("Deterministic")).toBe("0");
    expect(routeValue("AI Ready")).toBe("19");
  });

  it("keeps the split off entirely when the server carries no route counters", async () => {
    // Rules drafted, but neither route field is on the payload (a server older
    // than the counters). The split is a server fact; absent it, the client must
    // show nothing rather than reconstruct or zero-fill it.
    await renderWith(
      payload({
        stage: "Formulating rules from batch 4 of 38 — 6 policy statement(s) found",
        processed_batches: 3,
        rules_drafted: 20,
        // rules_deterministic / rules_ai_ready deliberately absent
      }),
    );
    expect(routeRegion()).toBeNull();
  });

  it("shows the unrouted remainder when the routes do not add up to the rules drafted", async () => {
    // 200 drafted, 7 + 190 routed → 3 in neither. That gap is information: it
    // must be visible, not charged to one side or hidden.
    await renderWith(drafting({ rules_drafted: 200, rules_deterministic: 7, rules_ai_ready: 190 }));
    expect(routeValue("unrouted")).toBe("3");
  });

  it("shows no remainder when the routes account for every drafted rule", async () => {
    await renderWith(drafting({ rules_drafted: 20, rules_deterministic: 1, rules_ai_ready: 19 }));
    const region = routeRegion();
    expect(region).not.toBeNull();
    expect(region!.textContent).not.toMatch(/unrouted/i);
  });

  it("draws neither route as a bar or a percentage", async () => {
    // A bar or a percentage turns a 1-to-19 split into one route filling and the
    // other lagging. AI Ready is what the source states, not a lesser outcome.
    await renderWith(drafting());
    const region = routeRegion();
    expect(region).not.toBeNull();
    expect(region!.querySelector(".ant-progress")).toBeNull();
    expect(region!.textContent ?? "").not.toMatch(/%/);
  });
});
