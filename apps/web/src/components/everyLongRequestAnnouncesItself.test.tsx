/** Every long request announces itself, and says so the same way.
 *
 * THE DEFECT THIS PREVENTS
 *
 * Five surfaces in this app open a request that can run for minutes. Two of
 * them — document upload and the project case runner — announced the wait
 * properly: a live region, a running clock, what the server is doing, and how
 * long it usually takes. Quality, the validation lab and the rule scenario
 * tester showed a spinning button and nothing else.
 *
 * The three without were the three slowest: an AI quality evaluation over a
 * whole published version, sealed-scenario generation, and a judged scenario
 * read. Measured on the live app, a quality run passes ten seconds with no
 * statement of any kind beyond a spinner. A reader who cannot tell a working
 * request from a hung one reloads the page, and on these surfaces reloading
 * loses the run.
 *
 * A screen-reader user learned nothing at all: with no live region there is no
 * announcement that a request is open, in progress, or finished.
 */
import { describe, expect, it, afterEach } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { LongRunWait } from "./LongRunWait";

/** The source of every component this file makes a claim about.
 *
 *  Vite's `?raw` glob rather than `node:fs`: this package's tsconfig carries no
 *  node types, so reading from disk compiles only by adding a dependency for a
 *  test — and `import.meta.url` points at the transformed module, not the file.
 *  This is the idiom `inspectorTabs.test.tsx` already uses for its own
 *  source-level guards.
 */
const SOURCES = import.meta.glob(
  [
    "./QualityPage.tsx",
    "./PolicyValidationLab.tsx",
    "./RuleScenarioTester.tsx",
    "./DocumentsPage.tsx",
    "./ProjectCaseRunner.tsx",
  ],
  { query: "?raw", import: "default", eager: true },
) as Record<string, string>;

function componentSource(file: string): string {
  const source = SOURCES[`./${file}`];
  // A source guard that cannot find its source would otherwise pass on an
  // empty string the moment the assertion were softened.
  expect(source, `${file} source was not loaded`).toBeTruthy();
  return source;
}

afterEach(() => cleanup());

describe("the shared wait panel", () => {
  it("is announced, so a request in flight is not silent", () => {
    render(<LongRunWait headline="Doing the thing" detail="Because of a reason" elapsedMs={0} />);
    const region = screen.getByRole("status");
    expect(region.getAttribute("aria-live")).toBe("polite");
  });

  it("shows a clock that is true rather than a percentage that is guessed", () => {
    render(<LongRunWait headline="Doing the thing" detail="d" elapsedMs={75_000} />);
    expect(screen.getByText(/1:15 elapsed/)).toBeTruthy();
  });

  it("states the expected duration when there is a measured one", () => {
    render(<LongRunWait headline="h" detail="d" expected="one to three minutes" elapsedMs={0} />);
    expect(screen.getByText(/one to three minutes/)).toBeTruthy();
  });

  it("says nothing about duration when no range was given", () => {
    // An invented estimate is worse than none: it is a claim the surface
    // cannot support, and the reader has no way to know it was invented.
    render(<LongRunWait headline="h" detail="d" elapsedMs={0} />);
    expect(screen.queryByText(/usually takes/)).toBeNull();
  });
});

describe("every slow surface uses it", () => {
  // Read from source. Rendering each of these to a pending request would mean
  // standing up four component harnesses to assert one property they share,
  // and the property is precisely "this file reaches for the shared panel".
  const SLOW_SURFACES = [
    "QualityPage.tsx",
    "PolicyValidationLab.tsx",
    "RuleScenarioTester.tsx",
  ];

  it.each(SLOW_SURFACES)("%s renders the shared wait panel", (file) => {
    const source = componentSource(file);
    expect(source).toContain("LongRunWait");
  });

  it.each(SLOW_SURFACES)("%s tracks an elapsed clock to feed it", (file) => {
    const source = componentSource(file);
    // A panel wired to a frozen zero would render "0:00 elapsed" forever, which
    // reads as a hang rather than as progress.
    expect(source).toMatch(/setInterval/);
    expect(source).toMatch(/ElapsedMs|setElapsedMs/);
  });

  it("the two surfaces that already had a wait panel still have one", () => {
    // Guards the refactor in the other direction: extracting a shared panel
    // must not quietly remove the two implementations it was modelled on.
    for (const [file, marker] of [
      ["DocumentsPage.tsx", "upload-wait"],
      ["ProjectCaseRunner.tsx", "project-case-wait"],
    ] as const) {
      const source = componentSource(file);
      expect(source, file).toContain(marker);
      expect(source, file).toContain('role="status"');
    }
  });
});
