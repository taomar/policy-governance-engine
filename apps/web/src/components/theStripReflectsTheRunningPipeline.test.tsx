import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen, waitForElementToBeRemoved } from "@testing-library/react";
import type { ExtractionProgress } from "../api";
import ExtractionProgressPanel from "./ExtractionProgressPanel";

/** Must match the component's own POLL_MS. It is not exported (nothing else
 * needs it), so the interval is restated here for the timer-based tests; if the
 * component's changes, these two move together or the idle-poll test fails
 * loudly, which is the drift being guarded against. */
const POLL_MS = 2000;

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
  // Some tests below drive the poll loop with fake timers; make sure a real
  // clock is restored before the next test regardless of how this one ended.
  vi.useRealTimers();
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

/**
 * A run must be discoverable by any viewer of the document, not only by the tab
 * that started it. The panel is handed `documentVersionId` — everything it needs
 * to ask — so on mount it queries the server directly, regardless of whether
 * this tab has an extract in flight (`running`). The prior panel bailed out of
 * its poll on `!running`, so a run started elsewhere, or one still going after a
 * navigate-away-and-back, rendered as nothing: the server held a complete record
 * and no consumer read it.
 *
 * Three of constraint 5's four discovery states are pinned here:
 *   - not-asked-yet must not render as asked-and-idle;
 *   - a run this tab did not start must render;
 *   - an idle document must settle after one read, not poll on forever.
 * The fourth, "running but not moving", is the gone-quiet block below.
 */
describe("the panel finds a run it did not start, and settles when there is none", () => {
  it("renders a running extraction discovered on mount with running=false", async () => {
    // The producer's live shape: a run this tab did not start, mid-formulation.
    extractionProgress.mockResolvedValue(
      payload({
        stage: "Formulating rules from batch 9 of 38 · pages 17–18 — 11 policy statement(s) found",
        processed_batches: 8,
        processed_clauses: 89,
        processed_pages: 17,
        passages_found: 36,
        rules_drafted: 20,
        rules_deterministic: 0,
        rules_ai_ready: 20,
        rules_committed: 20,
        skipped: 4,
        superseded: 298,
      }),
    );
    render(<ExtractionProgressPanel documentVersionId="v1" running={false} />);
    // Pre-fix this never appears — the poll bailed on `!running`.
    expect(await screen.findByText("RUN-TEST")).toBeTruthy();
    expect(document.querySelector(".extract-pipeline")).not.toBeNull();
  });

  it("renders the lopsided 0-Deterministic / 20-AI-Ready split as two plain counts", async () => {
    // The real corpus shape, discovered on mount. It must read as two counts,
    // never a bar or percentage that would draw the 0 as a shortfall.
    extractionProgress.mockResolvedValue(
      payload({
        stage: "Formulating rules from batch 9 of 38 · pages 17–18 — 11 policy statement(s) found",
        processed_batches: 8,
        rules_drafted: 20,
        rules_deterministic: 0,
        rules_ai_ready: 20,
        rules_committed: 20,
      }),
    );
    render(<ExtractionProgressPanel documentVersionId="v1" running={false} />);
    await screen.findByText("RUN-TEST");
    const region = document.querySelector(".extract-routes");
    expect(region).not.toBeNull();
    const chip = (name: string) =>
      Array.from(region!.querySelectorAll(".extract-route")).find((c) =>
        c.textContent?.includes(name),
      );
    // 0 Deterministic is a real "no rule took this route" — shown, not hidden.
    expect(chip("Deterministic")?.querySelector(".extract-stage-value")?.textContent).toBe("0");
    expect(chip("AI Ready")?.querySelector(".extract-stage-value")?.textContent).toBe("20");
    // Nothing ranks one route against the other.
    expect(region!.querySelector(".ant-progress")).toBeNull();
    expect(region!.textContent ?? "").not.toMatch(/%/);
  });

  it("asks once on an idle document and does not schedule further polls", async () => {
    vi.useFakeTimers();
    try {
      extractionProgress.mockResolvedValue({ active: false } as unknown as ExtractionProgress);
      render(<ExtractionProgressPanel documentVersionId="v1" running={false} />);
      // Flush the mount read and advance past several poll intervals.
      await vi.advanceTimersByTimeAsync(POLL_MS * 3 + 100);
      // Asked exactly once: an idle document settles, it does not poll on.
      expect(extractionProgress).toHaveBeenCalledTimes(1);
      // And renders nothing — there is no run for this document.
      expect(screen.queryByText("RUN-TEST")).toBeNull();
      expect(document.querySelector(".extract-pipeline")).toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });

  it("does not claim there is no run before it has asked", async () => {
    // "Not asked yet" must read apart from "asked, nothing running": before the
    // mount read resolves the panel shows a checking affordance, not the blank
    // it settles to once the server has said there is nothing.
    let resolvePoll: (p: ExtractionProgress) => void = () => {};
    extractionProgress.mockImplementation(
      () =>
        new Promise<ExtractionProgress>((res) => {
          resolvePoll = res;
        }),
    );
    render(<ExtractionProgressPanel documentVersionId="v1" running={false} />);
    // Mount read in flight: a distinct checking state, not silence.
    expect(await screen.findByText(/checking for an extraction/i)).toBeTruthy();
    // Server answers "nothing running" → the checking state clears to blank.
    resolvePoll({ active: false } as unknown as ExtractionProgress);
    await waitForElementToBeRemoved(() => screen.queryByText(/checking for an extraction/i));
    expect(document.querySelector(".extract-pipeline")).toBeNull();
  });
});

/**
 * The fourth discovery state: the server still calls the run "running", but has
 * not written to it in longer than the quiet policy allows. finish() stamps
 * updated_at, so a completed or failed run never reads as quiet; an abandoned
 * one keeps its record (pruned only when the next extraction starts) reading
 * active:true, status running, elapsed_seconds climbing while updated_at stays
 * frozen. The panel must not animate that as a live run — the same class of lie
 * as a chain that reads finished mid-work.
 *
 * But the inverse error is worse and more common. A batch is one model call with
 * no intermediate write, so a *healthy* run's updated_at legitimately sits still
 * for the length of a batch — 45–64s on the live corpus. A threshold in the tens
 * of seconds would accuse working runs constantly, so the policy is in minutes
 * and two guards keep it off a slow batch: the silence must cross the minutes
 * policy, and the frozen write-time must be seen on two consecutive polls, so no
 * run is flagged on a single first reading. The copy states the fact ("No update
 * for N"), never a verdict of death — so a slow batch that does cross the line
 * still reads true and clears itself when the next write lands.
 *
 * The silence is computed only from server-stamped values —
 * elapsed_seconds − (updated_at − started_at) — so no client clock enters it.
 */
describe("a run that stopped writing reads as gone quiet, not as working", () => {
  type WireProgress = ExtractionProgress & { started_at?: number; updated_at?: number };

  /** A running payload whose last write was `silence` seconds of server time ago.
   * updated_at is deterministic in `silence`, so two calls with the same silence
   * return the same frozen write-time — what a stopped run looks like across
   * polls — and a different silence returns a fresh write-time. */
  const withSilence = (silence: number, over: Partial<ExtractionProgress> = {}): WireProgress => {
    const started = 1_000_000;
    const elapsed = 600;
    // now = started + elapsed, and silence = elapsed − (updated − started),
    // so updated = started + elapsed − silence.
    const updated = started + elapsed - silence;
    return {
      ...payload({
        stage: "Formulating rules from batch 9 of 38 · pages 17–18 — 11 policy statement(s) found",
        processed_batches: 8,
        processed_clauses: 89,
        rules_drafted: 20,
        rules_deterministic: 0,
        rules_ai_ready: 20,
        rules_committed: 20,
        elapsed_seconds: elapsed,
        ...over,
      }),
      started_at: started,
      updated_at: updated,
    };
  };

  it("does not flag a run on a single reading, even one already over the policy", async () => {
    vi.useFakeTimers();
    try {
      // 400s of silence — over the policy — but seen only once. A run must never
      // be called quiet on first sight: it may have mounted mid-long-batch, and a
      // batch has no intermediate write to prove otherwise yet.
      extractionProgress.mockResolvedValue(withSilence(400));
      render(<ExtractionProgressPanel documentVersionId="v1" running={false} />);
      await act(async () => {
        await vi.advanceTimersByTimeAsync(1); // flush the mount read only
      });
      expect(screen.queryByText(/no update for/i)).toBeNull();
      expect(document.querySelector(".extract-progress--quiet")).toBeNull();
      // Still presented as working until a second reading confirms the freeze.
      expect(document.querySelector(".anticon-loading")).not.toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });

  it("reads as gone quiet once a frozen write-time persists across two polls", async () => {
    vi.useFakeTimers();
    try {
      extractionProgress.mockResolvedValue(withSilence(400));
      render(<ExtractionProgressPanel documentVersionId="v1" running={false} />);
      await act(async () => {
        await vi.advanceTimersByTimeAsync(1); // poll 1: first sight, not yet quiet
      });
      expect(document.querySelector(".extract-progress--quiet")).toBeNull();
      await act(async () => {
        await vi.advanceTimersByTimeAsync(POLL_MS); // poll 2: same frozen write-time
      });
      // The plain fact, stated — not a verdict of failure.
      expect(screen.getByText(/no update for/i)).toBeTruthy();
      // Nothing animates as alive: no spinner anywhere, and the progress bar is
      // out of its "active" (animated) state.
      expect(document.querySelector(".anticon-loading")).toBeNull();
      expect(document.querySelector(".ant-progress-status-active")).toBeNull();
      expect(document.querySelector(".extract-progress--quiet")).not.toBeNull();
      // Not failed: the run may yet resume, so it must not read as an error.
      expect(document.querySelector(".anticon-close-circle")).toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });

  it("never reads the 45-second healthy gap as quiet, however many polls", async () => {
    vi.useFakeTimers();
    try {
      // The producer's own measurement: a healthy, advancing run whose updated_at
      // sat still for 45s+ because a batch is one model call. Even with the
      // write-time frozen across many polls, 45s is far under the minutes policy,
      // so this must never read as quiet — the false accusation that would
      // otherwise fire on every real run.
      extractionProgress.mockResolvedValue(withSilence(45));
      render(<ExtractionProgressPanel documentVersionId="v1" running={false} />);
      await act(async () => {
        await vi.advanceTimersByTimeAsync(POLL_MS * 6 + 100);
      });
      expect(screen.queryByText(/no update for/i)).toBeNull();
      expect(document.querySelector(".extract-progress--quiet")).toBeNull();
      expect(document.querySelector(".anticon-loading")).not.toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });

  it("never reads a finished run as quiet, however long since its last write", async () => {
    vi.useFakeTimers();
    try {
      // A completed run whose updated_at is ancient (finish() stamped it, then the
      // 15-minute retention window kept elapsed_seconds climbing — exactly the live
      // shape: ~32 min of "silence" on a run that is simply done). done must win:
      // the quiet affordance is for running runs only.
      extractionProgress.mockResolvedValue(
        withSilence(9999, {
          status: "completed",
          stage: "Done — no changes.",
          processed_batches: 38,
          rules_committed: 20,
          delta_unchanged: 20,
        }),
      );
      render(<ExtractionProgressPanel documentVersionId="v1" running={false} />);
      await act(async () => {
        await vi.advanceTimersByTimeAsync(POLL_MS * 2 + 100);
      });
      expect(screen.queryByText(/no update for/i)).toBeNull();
      expect(document.querySelector(".extract-progress--quiet")).toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });

  it("clears the quiet read the moment the run writes again", async () => {
    vi.useFakeTimers();
    try {
      // Frozen over the policy for two polls → quiet; then a fresh write (a new
      // updated_at, silence reset) → back to working. Quiet is a snapshot of the
      // last two readings, not a latch: recovery is visible, so a slow batch that
      // briefly crossed the line is not stuck reading dead once it resumes.
      extractionProgress
        .mockResolvedValueOnce(withSilence(400))
        .mockResolvedValueOnce(withSilence(400))
        .mockResolvedValue(withSilence(5));
      render(<ExtractionProgressPanel documentVersionId="v1" running={false} />);
      await act(async () => {
        await vi.advanceTimersByTimeAsync(1); // poll 1: first sight
      });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(POLL_MS); // poll 2: frozen → quiet
      });
      expect(document.querySelector(".extract-progress--quiet")).not.toBeNull();
      await act(async () => {
        await vi.advanceTimersByTimeAsync(POLL_MS); // poll 3: fresh write → working
      });
      expect(document.querySelector(".extract-progress--quiet")).toBeNull();
      expect(document.querySelector(".anticon-loading")).not.toBeNull();
      expect(screen.queryByText(/no update for/i)).toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });
});

describe("the chain names every phase the run performs, in the order they run", () => {
  /**
   * The strip's boxes used to describe four of the run's seven phases. Traced
   * against ai_extraction.py in execution order, the pipeline is:
   *
   *   1 read a batch and identify policy statements   ("Reading batch N of M…")
   *   2 formulate rules from the batch                ("Formulating rules from…")
   *   3 commit them to the review queue               (rules_committed, per batch)
   *   4 recovery: re-read batches a transient blip lost (recovered; only if any)
   *   5 relationship discovery                        ("Linking rule variations…")
   *   6 continuation adjudication                     (folded into `linked`; only
   *                                                    when governing stems span
   *                                                    batches; no counter of its
   *                                                    own on the record)
   *   7 compare against the previous extraction       ("Comparing against the…")
   *
   * Phases 4, 6 and 7 had no representation, so a run doing them read as either
   * finished (7) or as nothing-happening (4, 6). The chain now groups the work
   * it does into four named phases — Reading, Drafting, Connecting, Comparing —
   * so every phase is visible and the reviewer can tell which one a number
   * belongs to, without the chain growing into seven peer boxes.
   */
  type WireRecovered = ExtractionProgress & { recovered?: number };

  const compareNode = () => document.querySelector(".extract-compare-node");

  it("names all four phases of the pipeline, always", async () => {
    await renderWith(
      payload({
        stage: "Formulating rules from batch 9 of 38 — 11 policy statement(s) found",
        processed_batches: 8,
        rules_drafted: 20,
        rules_committed: 20,
      }),
    );
    for (const phase of ["Reading", "Drafting", "Connecting", "Comparing"]) {
      expect(screen.getByText(phase)).toBeTruthy();
    }
  });

  it("groups the drafting figures ahead of the connecting figure, in run order", async () => {
    // Commit-to-queue happens per batch DURING drafting; linking runs once at
    // the very end. So while the run is formulating, the review queue is filling
    // and nothing has been linked yet — the queue count is live, Linked is an em
    // dash for "not reached", and the two must not read alike.
    await renderWith(
      payload({
        stage: "Formulating rules from batch 9 of 38 — 11 policy statement(s) found",
        processed_batches: 8,
        rules_drafted: 20,
        rules_committed: 20,
        linked: 0,
      }),
    );
    expect(boxValue("In review queue")).toBe("20");
    expect(boxValue("Linked")).toBe("—");
    expect(boxValue("In review queue")).not.toBe(boxValue("Linked"));
  });

  it("shows the comparison as a phase not yet reached while the run is still reading", async () => {
    await renderWith(
      payload({
        stage: "Reading batch 2 of 38 · pages 5–8 — finding policy statements",
        processed_batches: 1,
        passages_found: 0,
      }),
    );
    const node = compareNode();
    expect(node).not.toBeNull();
    // Present but neither working nor settled: it is a phase the run will reach,
    // drawn as pending, not as done (which would be the "says finished when it is
    // not" defect one level up in the chain).
    expect(node!.className).not.toContain("extract-compare-node--active");
    expect(node!.className).not.toContain("extract-compare-node--done");
  });

  it("shows the comparison as the working phase while the run is comparing", async () => {
    await renderWith(
      payload({
        status: "running",
        stage: "Comparing against the previous extraction…",
        processed_batches: 38,
        rules_drafted: 190,
        rules_committed: 190,
        linked: 150,
      }),
    );
    const node = compareNode();
    expect(node).not.toBeNull();
    expect(node!.className).toContain("extract-compare-node--active");
    expect(node!.className).not.toContain("extract-compare-node--done");
  });

  it("shows the comparison as settled once the run is done", async () => {
    await renderWith(
      payload({
        status: "completed",
        stage: "Done — 3 new, 2 changed since the previous extraction.",
        processed_batches: 38,
        rules_drafted: 190,
        rules_committed: 190,
        linked: 150,
        delta_new: 3,
        delta_changed: 2,
        delta_unchanged: 185,
      }),
    );
    const node = compareNode();
    expect(node).not.toBeNull();
    expect(node!.className).toContain("extract-compare-node--done");
    expect(node!.className).not.toContain("extract-compare-node--active");
  });

  it("says nothing about recovery when no batch needed re-reading", async () => {
    // Recovery only fires after a transient failure loses a batch. On the common
    // run where nothing was lost it must be absent, not a "0" that would invent a
    // failure mode the run never hit (did-not-need-to-run ≠ ran-and-found-none).
    await renderWith(
      payload({
        stage: "Linking rule variations across the document…",
        processed_batches: 38,
        rules_drafted: 190,
        rules_committed: 190,
        linked: 150,
      }),
    );
    expect(document.querySelector(".extract-recovered")).toBeNull();
  });

  it("says how many batches were re-read after a transient blip, when any were", async () => {
    extractionProgress.mockResolvedValue({
      ...payload({
        status: "completed",
        stage: "Done — 190 rule(s).",
        processed_batches: 38,
        rules_drafted: 190,
        rules_committed: 190,
        linked: 150,
      }),
      recovered: 2,
    } as WireRecovered);
    render(<ExtractionProgressPanel documentVersionId="v1" running />);
    await screen.findByText("RUN-TEST");
    const chip = document.querySelector(".extract-recovered");
    expect(chip).not.toBeNull();
    expect(chip!.querySelector(".extract-stage-value")?.textContent).toBe("2");
  });
});
