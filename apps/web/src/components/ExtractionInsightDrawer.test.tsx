import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import ExtractionInsightDrawer from "./ExtractionInsightDrawer";

/**
 * The document viewer shows the whole document, and says how big it is.
 *
 * Written against a real failure. A 27-page handbook extracted to 522 canonical
 * elements; the viewer asked for one 500-element window, listed those, and
 * labelled the tab "Document (500)". The 22 elements it dropped were pages
 * 26-27 — the disciplinary schedule. A reviewer checking extraction against the
 * source could not reach the end of the document and was told nothing was
 * missing, on precisely the pages where extraction had done worst.
 *
 * Both halves are asserted here, because either one alone would have passed
 * while the defect was live: the count must come from the server's
 * `total_elements`, and the rows must go all the way to the last element.
 *
 * The numbers are the real ones. 522 elements against a 500-element window is
 * the case that shipped.
 */

const VERSION_ID = "209c8c85-be2d-4f46-b2f2-ba5cf26944c2";
const TOTAL_ELEMENTS = 522;
const SERVER_WINDOW = 500;

/** Text of the final element, unique so finding it proves the last page rendered. */
const LAST_ELEMENT_TEXT = "Dismissal following a finding of gross misconduct";

/** Leaves in the coverage report, three of which received no disposition. */
const TOTAL_LEAF_ELEMENTS = 359;
const UNACCOUNTED_IDS = ["E000101", "E000102", "E000103"];

interface CanonicalElementPayload {
  element_id: string;
  element_type: string;
  sequence: number;
  section: string | null;
  page: number;
  clause_ref: string;
  text: string;
  source_fragments: never[];
}

function element(sequence: number): CanonicalElementPayload {
  return {
    element_id: `E${String(sequence).padStart(6, "0")}`,
    element_type: "paragraph",
    sequence,
    section: null,
    page: sequence >= SERVER_WINDOW ? 27 : 1,
    clause_ref: `clause-${sequence}`,
    text: sequence === TOTAL_ELEMENTS - 1 ? LAST_ELEMENT_TEXT : `Element ${sequence}`,
    source_fragments: [],
  };
}

const ALL_ELEMENTS = Array.from({ length: TOTAL_ELEMENTS }, (_, index) => element(index));

/** The canonical endpoint: a window of elements, and the true total beside it. */
function canonicalResponse(url: string) {
  const params = new URL(url).searchParams;
  const offset = Number(params.get("offset") ?? 0);
  const limit = Math.min(Number(params.get("limit") ?? SERVER_WINDOW), SERVER_WINDOW);
  return {
    document_version_id: VERSION_ID,
    total_elements: TOTAL_ELEMENTS,
    offset,
    elements: ALL_ELEMENTS.slice(offset, offset + limit),
  };
}

const coverageResponse = {
  document_version_id: VERSION_ID,
  total_leaf_elements: TOTAL_LEAF_ELEMENTS,
  accounted: TOTAL_LEAF_ELEMENTS - UNACCOUNTED_IDS.length,
  unresolved: 0,
  unaccounted_element_ids: UNACCOUNTED_IDS,
  is_complete: false,
  // The server omits elements it recorded no disposition for, so this list is
  // shorter than the document's leaf count by exactly those three.
  elements: Array.from({ length: TOTAL_LEAF_ELEMENTS - UNACCOUNTED_IDS.length }, (_, index) => ({
    element_id: `L${String(index).padStart(6, "0")}`,
    disposition: "policy_target",
    reason: "target of a reading unit",
  })),
};

const readingPlanResponse = {
  document_version_id: VERSION_ID,
  unit_count: 157,
  is_exhaustive: true,
  uncovered_target_ids: [],
  units: [],
};

const structureResponse = {
  document_version_id: VERSION_ID,
  node_count: TOTAL_ELEMENTS,
  edge_count: 480,
  leaf_element_ids: [],
  governing_stems: [],
  unsatisfied_promises: [],
  nodes: [],
  edges: [],
};

const stagesResponse = { document_version_id: VERSION_ID, stages: [] };

/** Every canonical URL the component asked for, in order. */
let canonicalRequests: string[] = [];

function jsonResponse(body: unknown) {
  return { ok: true, status: 200, json: async () => body } as unknown as Response;
}

beforeEach(() => {
  canonicalRequests = [];

  // antd measures the viewport; jsdom has neither of these.
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
      if (url.includes("/canonical")) {
        canonicalRequests.push(url);
        return jsonResponse(canonicalResponse(url));
      }
      if (url.includes("/coverage")) return jsonResponse(coverageResponse);
      if (url.includes("/reading-plan")) return jsonResponse(readingPlanResponse);
      if (url.includes("/structure")) return jsonResponse(structureResponse);
      if (url.includes("/stages")) return jsonResponse(stagesResponse);
      throw new Error(`unexpected request: ${url}`);
    })
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function openDrawer() {
  return render(
    <ExtractionInsightDrawer
      open
      onClose={() => {}}
      documentVersionId={VERSION_ID}
      documentTitle="AIS Employee Handbook"
    />
  );
}

describe("ExtractionInsightDrawer", () => {
  it("keeps asking for elements until it holds the whole document", async () => {
    openDrawer();

    await waitFor(() => expect(screen.getByText(/^Document \(/)).toBeTruthy());

    // One window is not a document. The second request is what the pre-fix
    // component never made.
    expect(canonicalRequests).toHaveLength(2);
    expect(canonicalRequests[0]).toContain("offset=0");
    expect(canonicalRequests[1]).toContain(`offset=${SERVER_WINDOW}`);
  });

  it("counts the document by the server's total, not by the rows in hand", async () => {
    openDrawer();

    // 522, not 500: the tab reports what the version contains, and the pre-fix
    // component reported the length of the window it happened to receive.
    await waitFor(() =>
      expect(screen.getByText(`Document (${TOTAL_ELEMENTS})`)).toBeTruthy()
    );
    expect(screen.queryByText(`Document (${SERVER_WINDOW})`)).toBeNull();
  });

  it("lets a reviewer reach the last element of the document", async () => {
    openDrawer();
    // Wait for the table rather than the tab label, so this fails on the
    // pagination cliff itself rather than on the count above it.
    await waitFor(() => expect(screen.getByText("Element 0")).toBeTruthy());

    // 522 rows at 25 a page is 21 pages. The pre-fix component held 500 rows,
    // so it stopped at 20 and the last page of the handbook was unreachable —
    // with no control offering to go there.
    const lastPage = screen.getByTitle("21");
    fireEvent.click(lastPage);

    await waitFor(() => expect(screen.getByText(LAST_ELEMENT_TEXT)).toBeTruthy());
  });

  it("counts coverage by the report's leaf count, including elements with no disposition", async () => {
    openDrawer();

    // The dispositioned list is short by exactly the elements nobody looked at,
    // so counting it would hide them in the count as well as the table.
    await waitFor(() =>
      expect(screen.getByText(`Coverage (${TOTAL_LEAF_ELEMENTS})`)).toBeTruthy()
    );
    expect(
      screen.queryByText(`Coverage (${TOTAL_LEAF_ELEMENTS - UNACCOUNTED_IDS.length})`)
    ).toBeNull();
  });
});
