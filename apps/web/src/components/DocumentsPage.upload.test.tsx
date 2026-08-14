import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { DocumentsPage } from "./DocumentsPage";
import {
  formatElapsed,
  formatFileSize,
  uploadOutcome,
  uploadWaitState,
} from "../uploadFeedback";

/**
 * While an upload is in flight the page must say something a reviewer can act
 * on, and when it finishes it must report what actually came back.
 *
 * The complaint this guards: the control showed a bare "Uploading…" for about
 * ninety seconds. No file, no size, no clock, no statement of what the server
 * was doing or what would happen next. The reviewer's real question during
 * that wait is not "how far along is it" — it is "is this still running, or
 * has it hung?", and nothing on screen answered that.
 *
 * WHAT MAKES THE CLOCK ASSERTION THE IMPORTANT ONE
 *
 * A presence check alone is weak here. A panel that renders a frozen "0:00"
 * satisfies "the elapsed time is shown" while failing the only thing the
 * elapsed time is for. So the test below advances fake timers and asserts the
 * rendered value CHANGED to a specific later value. If the interval is
 * removed, the panel still renders and still contains a clock, and this test
 * still fails — which is the point.
 *
 * FLOOR PLACEMENT
 *
 * The verdicts in this file are presence-and-value assertions, not an offender
 * list and not a set difference, so neither placement rule applies directly.
 * The equivalent risk is the one that has bitten this codebase before: a query
 * that matches nothing in BOTH the fixed and the broken build, so the test
 * "fails before and passes after" by accident of which assertion tripped
 * first. Two defences against that:
 *
 *   - every query goes through `screen`, which reads document.body, so a
 *     surface that moves into a portal is still found;
 *   - `renders the upload form at all` runs as its own test, so a wholesale
 *     render failure reports as a render failure rather than masquerading as a
 *     missing field.
 */

let resolveUpload: ((value: Response) => void) | null = null;

/** Bytes chosen to render as a clean, unambiguous "2.0 MB". */
const FILE_BYTES = 2 * 1024 * 1024;
const FILE_NAME = "staff-handbook.pdf";

/** Counts the stub endpoint reports back. Arbitrary, and never hardcoded in src. */
const CLAUSES_READ = 412;
const CLAUSES_INDEXED = 409;

function jsonResponse(body: unknown) {
  return {
    ok: true,
    status: 200,
    json: async () => body,
  } as unknown as Response;
}

function attachFile() {
  const input = document.querySelector('input[type="file"]') as HTMLInputElement;
  expect(input, "the upload control renders no file input").not.toBeNull();
  const file = new File(["x".repeat(64)], FILE_NAME, { type: "application/pdf" });
  // jsdom's File reports the byte length of its parts; the page reads
  // `file.size`, so pin it to the size this test reasons about.
  Object.defineProperty(file, "size", { value: FILE_BYTES });
  fireEvent.change(input, { target: { files: [file] } });
  return file;
}

async function startUpload() {
  attachFile();
  const button = await screen.findByRole("button", { name: /^Upload$/ });
  await act(async () => {
    fireEvent.click(button);
  });
}

beforeEach(() => {
  resolveUpload = null;

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
    }))
  );
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    }
  );

  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/api/documents/upload")) {
        // Held open so the in-flight state can be observed, exactly as it is
        // during the real ninety-second parse.
        return new Promise<Response>((resolve) => {
          resolveUpload = resolve;
        });
      }
      if (url.includes("/api/documents")) return jsonResponse([]);
      if (url.includes("/api/policy-sets")) return jsonResponse([]);
      return jsonResponse([]);
    })
  );
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("what the reviewer is told during the wait", () => {
  it("renders the upload form at all", async () => {
    render(<DocumentsPage />);
    expect(await screen.findByRole("button", { name: /^Upload$/ })).toBeTruthy();
    expect(document.querySelector('input[type="file"]')).not.toBeNull();
  });

  it("names the file and its size while the request is open", async () => {
    render(<DocumentsPage />);
    await startUpload();

    const panel = await screen.findByRole("status");
    expect(panel.textContent).toContain(FILE_NAME);
    expect(panel.textContent).toContain("2.0 MB");
  });

  it("says what the server is doing and what happens next", async () => {
    render(<DocumentsPage />);
    await startUpload();

    const panel = await screen.findByRole("status");
    // Not a verbatim copy of the sentences — that would only assert the string
    // equals itself. These are the two facts the sentences have to carry.
    expect(panel.textContent).toMatch(/clause/i);
    expect(panel.textContent).toMatch(/version/i);
  });

  it("advances the elapsed clock, so a hung request is distinguishable from a slow one", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    render(<DocumentsPage />);
    await startUpload();

    const panel = await screen.findByRole("status");
    const atStart = panel.textContent ?? "";
    expect(atStart).toContain("0:00");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(65_000);
    });

    const later = (await screen.findByRole("status")).textContent ?? "";
    // The specific value matters: it proves the clock is being recomputed from
    // wall time rather than re-rendered at a fixed string.
    expect(later).toContain("1:05");
    expect(later).not.toContain("0:00");
  });

  it("keeps the wait panel out of the way once the request returns", async () => {
    render(<DocumentsPage />);
    await startUpload();
    expect(await screen.findByRole("status")).toBeTruthy();

    await act(async () => {
      resolveUpload?.(
        jsonResponse({
          version_number: 3,
          clause_count: CLAUSES_READ,
          clauses_indexed: CLAUSES_INDEXED,
          extraction_error: null,
          ingestion_diagnostics: [],
        })
      );
    });

    await waitFor(() => {
      expect(screen.queryByRole("status")).toBeNull();
    });
  });
});

describe("what the reviewer is told when it returns", () => {
  it("reports how much was read out of the document", async () => {
    render(<DocumentsPage />);
    await startUpload();
    await act(async () => {
      resolveUpload?.(
        jsonResponse({
          version_number: 3,
          clause_count: CLAUSES_READ,
          clauses_indexed: CLAUSES_INDEXED,
          extraction_error: null,
          ingestion_diagnostics: [],
        })
      );
    });

    await waitFor(() => {
      expect(document.body.textContent).toContain(String(CLAUSES_READ));
    });
    // The indexed count differs from the read count here, so it is stated.
    expect(document.body.textContent).toContain(String(CLAUSES_INDEXED));
  });

  it("does not present a document that failed to read as a plain success", async () => {
    render(<DocumentsPage />);
    await startUpload();
    await act(async () => {
      resolveUpload?.(
        jsonResponse({
          version_number: 1,
          clause_count: 0,
          clauses_indexed: 0,
          extraction_error: "no extractable text layer",
          ingestion_diagnostics: [{ code: "scanned_pages", message: "12 pages carry no text layer" }],
        })
      );
    });

    await waitFor(() => {
      expect(document.body.textContent).toContain("no extractable text layer");
    });
    expect(document.body.textContent).toContain("12 pages carry no text layer");
  });
});

describe("the pure pieces", () => {
  it("formats sizes across unit boundaries", () => {
    expect(formatFileSize(0)).toBe("0 B");
    expect(formatFileSize(512)).toBe("512 B");
    expect(formatFileSize(1024)).toBe("1.0 KB");
    expect(formatFileSize(1024 * 1024)).toBe("1.0 MB");
    expect(formatFileSize(1024 * 1024 * 1024)).toBe("1.0 GB");
  });

  it("declines to state a size it cannot state honestly", () => {
    expect(formatFileSize(null)).toBeNull();
    expect(formatFileSize(undefined)).toBeNull();
    expect(formatFileSize(-1)).toBeNull();
    expect(formatFileSize(Number.NaN)).toBeNull();
  });

  it("omits the size from the headline rather than printing a placeholder", () => {
    const withSize = uploadWaitState("a.pdf", 2048, 0);
    const without = uploadWaitState("a.pdf", null, 0);
    expect(withSize.headline).toContain("2.0 KB");
    expect(without.headline).toContain("a.pdf");
    expect(without.headline).not.toMatch(/null|undefined|NaN/);
  });

  it("counts up in minutes and seconds and never goes negative", () => {
    expect(formatElapsed(0)).toBe("0:00");
    expect(formatElapsed(9_000)).toBe("0:09");
    expect(formatElapsed(65_000)).toBe("1:05");
    expect(formatElapsed(600_000)).toBe("10:00");
    expect(formatElapsed(-5_000)).toBe("0:00");
  });

  it("promises no percentage it cannot compute", () => {
    const state = uploadWaitState("a.pdf", 1024, 30_000);
    const allText = `${state.headline} ${state.activity} ${state.next}`;
    expect(allText).not.toMatch(/\d+\s?%/);
  });

  it("says nothing about counts the response did not carry", () => {
    const outcome = uploadOutcome("a.pdf", { version_number: 2 });
    expect(outcome.message).toContain("version 2");
    expect(outcome.message).not.toMatch(/clause/i);
    expect(outcome.problem).toBeNull();
    expect(outcome.notes).toEqual([]);
  });

  it("agrees singular and plural with the count", () => {
    expect(uploadOutcome("a.pdf", { version_number: 1, clause_count: 1 }).message).toContain("1 clause ");
    expect(uploadOutcome("a.pdf", { version_number: 1, clause_count: 2 }).message).toContain("2 clauses");
  });

  it("stays quiet about the indexed count when it matches the read count", () => {
    const same = uploadOutcome("a.pdf", { version_number: 1, clause_count: 7, clauses_indexed: 7 });
    expect(same.message).not.toMatch(/searchable/);
    const differs = uploadOutcome("a.pdf", { version_number: 1, clause_count: 7, clauses_indexed: 4 });
    expect(differs.message).toMatch(/searchable/);
  });

  it("reads diagnostic notes whatever shape they arrive in", () => {
    const outcome = uploadOutcome("a.pdf", {
      version_number: 1,
      ingestion_diagnostics: [
        "a bare string",
        { message: "a message field" },
        { detail: "a detail field" },
        { code: "a_code_only" },
        { unrelated: 5 },
      ],
    });
    expect(outcome.notes).toEqual(["a bare string", "a message field", "a detail field", "a_code_only"]);
  });
});
