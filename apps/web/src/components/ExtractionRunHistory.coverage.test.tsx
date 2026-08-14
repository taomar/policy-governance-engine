import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import ExtractionRunHistory from "./ExtractionRunHistory";

/**
 * What a run passed over has to reach the person judging coverage.
 *
 * The run list reported how much came out and nothing about what did not.
 * Material the pipeline declined to extract went onto a skip list that was
 * never stored and never displayed, so a reviewer asking "did this tool see
 * the whole document" was answered with a rule count — which is the same
 * number whether every page was read or three were lost.
 *
 * The harder half is that one count cannot answer the question, because two
 * unrelated events land on that list:
 *
 *   - a batch that failed, meaning roughly fifteen clauses were never read and
 *     the document is not covered; the run should be repeated;
 *   - a sentence that was read and judged to carry no rule, meaning coverage is
 *     whole and a judgement was made that may be worth checking.
 *
 * `skipped: 10` says both. So these tests hold the two apart in the rendered
 * output, and hold the third state — a run that recorded nothing — apart from
 * a run that skipped nothing, because reporting the unknown as zero is how a
 * gap becomes invisible.
 *
 * The skipped entries below are verbatim from run RUN-83257A81 over the GMU
 * staff handbook. The equal-opportunity sentence is the one that matters: it
 * is exactly what a compliance reviewer opens this tool to find, it was not
 * recovered by any other record, and it was not flagged, not low-confidence
 * and not marked uncertain. It was on the list.
 */

const listExtractionRuns = vi.fn();

vi.mock("../api", async () => {
  const actual = await vi.importActual<typeof import("../api")>("../api");
  return {
    ...actual,
    aiApi: {
      listExtractionRuns: (...args: unknown[]) => listExtractionRuns(...args),
    },
  };
});

const EQUAL_OPPORTUNITY =
  "GMU is fully committed to equal opportunity at all levels without discrimination on the " +
  "basis of race, gender, religion, age, family status, or national origin.";

const STUDENT_EMPLOYMENT =
  "It is therefore the policy of GMU to employ students in certain situations with certain " +
  "parameters";

/** Read and declined — coverage is whole, the judgement is the question. */
const READ_NOT_EXTRACTED = [
  { item: EQUAL_OPPORTUNITY, reason: "rule_type 'statement' carries no policy rule", kind: "read_not_extracted" },
  { item: STUDENT_EMPLOYMENT, reason: "rule_type 'statement' carries no policy rule", kind: "read_not_extracted" },
];

/** Never read — the document is not covered. */
const BATCH_UNREAD = [
  { item: "batch 14 of 27", reason: "batch failed: httpx.ReadTimeout", kind: "batch_unread" },
];

function runRow(overrides: Partial<import("../api").ExtractionRunSummary> = {}) {
  return {
    id: "run-1",
    reference: "RUN-83257A81",
    status: "completed",
    started_at: "2024-01-01T10:00:00Z",
    completed_at: "2024-01-01T10:41:46Z",
    error_message: null,
    prompt_version: "v3",
    deployment_name: "gpt-4o",
    rules_total: 411,
    rules_reviewed: 0,
    is_current: true,
    coverage: null,
    ...overrides,
  };
}

function renderWith(coverage: import("../api").RunCoverage | null, status = "completed") {
  listExtractionRuns.mockResolvedValue([runRow({ coverage, status })]);
  render(<ExtractionRunHistory documentVersionId="v1" />);
}

beforeEach(() => {
  listExtractionRuns.mockReset();

  // antd measures the viewport; jsdom provides neither of these.
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
});

afterEach(() => {
  cleanup();
});

describe("what a run passed over", () => {
  it("says coverage is full when nothing was skipped", async () => {
    renderWith({
      complete: true,
      batches_unread: 0,
      passages_discarded: 0,
      read_not_extracted: 0,
      skipped: [],
    });
    expect(await screen.findByText("full")).toBeTruthy();
  });

  it("still says coverage is full when passages were read and declined", async () => {
    // The defect this guards is the opposite of the obvious one: a bare count
    // made a wholly-read run look like it had a hole, which disqualifies it as
    // a delta baseline. Ten benign skips must not read as lost document.
    renderWith({
      complete: true,
      batches_unread: 0,
      passages_discarded: 0,
      read_not_extracted: READ_NOT_EXTRACTED.length,
      skipped: READ_NOT_EXTRACTED,
    });
    expect(await screen.findByText("full")).toBeTruthy();
    expect(screen.queryByText(/unread/)).toBeNull();
  });

  it("reports declined passages separately from coverage", async () => {
    renderWith({
      complete: true,
      batches_unread: 0,
      passages_discarded: 0,
      read_not_extracted: READ_NOT_EXTRACTED.length,
      skipped: READ_NOT_EXTRACTED,
    });
    expect(await screen.findByText(`${READ_NOT_EXTRACTED.length} dropped`)).toBeTruthy();
  });

  it("says the document was not covered when a batch went unread", async () => {
    renderWith(
      {
        complete: false,
        batches_unread: 1,
        passages_discarded: 0,
        read_not_extracted: 0,
        skipped: BATCH_UNREAD,
      },
      "completed_with_gaps",
    );
    expect(await screen.findByText("1 unread")).toBeTruthy();
    expect(screen.queryByText("full")).toBeNull();
  });

  it("distinguishes an unread batch from a declined sentence in one run", async () => {
    // Both kinds at once is the case a single count can never represent.
    renderWith(
      {
        complete: false,
        batches_unread: 1,
        passages_discarded: 0,
        read_not_extracted: READ_NOT_EXTRACTED.length,
        skipped: [...BATCH_UNREAD, ...READ_NOT_EXTRACTED],
      },
      "completed_with_gaps",
    );
    expect(await screen.findByText("1 unread")).toBeTruthy();
    expect(screen.getByText(`${READ_NOT_EXTRACTED.length} dropped`)).toBeTruthy();
  });

  it("reports a run that recorded nothing as unknown, not as nothing skipped", async () => {
    // Runs predating the stored skip list know nothing about what they passed
    // over. Rendering that as "full" would assert coverage from an absence of
    // evidence.
    renderWith(null);
    expect(await screen.findByText("unknown")).toBeTruthy();
    expect(screen.queryByText("full")).toBeNull();
  });

  it("marks a gapped run as needing attention rather than leaving it neutral", async () => {
    renderWith(
      {
        complete: false,
        batches_unread: 1,
        passages_discarded: 0,
        read_not_extracted: 0,
        skipped: BATCH_UNREAD,
      },
      "completed_with_gaps",
    );
    const tag = await screen.findByText("completed_with_gaps");
    // antd renders the colour as a class on the tag element.
    await waitFor(() => {
      expect(tag.className).toContain("orange");
    });
  });
});
