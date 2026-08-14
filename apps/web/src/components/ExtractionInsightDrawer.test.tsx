import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import ExtractionInsightDrawer from "./ExtractionInsightDrawer";

/**
 * A count or a list this drawer presents as whole must be whole.
 *
 * The canonical endpoint answers with a window of elements and the true total
 * beside it. Reading the window and ignoring the total gives a viewer that
 * shows the start of a document and calls it the document — a list that is
 * short and a count that agrees with the short list, so nothing on screen
 * contradicts anything else on screen. (That is not hypothetical; it shipped.)
 *
 * Everything here is sized from the two constants below, and nothing depends on
 * which document is being viewed. `TOTAL_ELEMENTS` deliberately spans several
 * windows and does not divide evenly by one, because both of those are where
 * the walk can go wrong:
 *
 *   - more than two windows, so a client that fetches a fixed number of pages
 *     and stops cannot pass;
 *   - a short final window, so a client that advances by the size it asked for
 *     rather than by the size it received cannot pass.
 *
 * The stub server answers in its own window size whatever the client asks for,
 * which is what proves the client carries no assumption about how much a
 * request returns.
 */

const VERSION_ID = "version-under-test";

/** The stub server's window. The client is not told this and must not assume it. */
const SERVER_PAGE_SIZE = 10;

/** Spans four windows, the last one short. */
const TOTAL_ELEMENTS = 33;

const EXPECTED_REQUESTS = Math.ceil(TOTAL_ELEMENTS / SERVER_PAGE_SIZE);

/** Leaves in the coverage report, two of which received no disposition. */
const LEAF_TOTAL = 7;
const UNACCOUNTED_IDS = ["leaf-3", "leaf-6"];

const elementText = (sequence: number) => `Element ${sequence}`;

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
    element_id: `element-${sequence}`,
    element_type: "paragraph",
    sequence,
    section: null,
    page: 1,
    clause_ref: `clause-${sequence}`,
    text: elementText(sequence),
    source_fragments: [],
  };
}

const ALL_ELEMENTS = Array.from({ length: TOTAL_ELEMENTS }, (_, index) => element(index));

/** The canonical endpoint: a window of elements, and the true total beside it.
 *
 * The window is this stub's own size. Any `limit` the client sends is ignored
 * on purpose — a real server is free to answer in a size of its choosing, and a
 * client that only works when its own number is honoured is broken. */
function canonicalResponse(url: string) {
  const offset = Number(new URL(url, "http://localhost").searchParams.get("offset") ?? 0);
  return {
    document_version_id: VERSION_ID,
    total_elements: TOTAL_ELEMENTS,
    offset,
    elements: ALL_ELEMENTS.slice(offset, offset + SERVER_PAGE_SIZE),
  };
}

const coverageResponse = {
  document_version_id: VERSION_ID,
  total_leaf_elements: LEAF_TOTAL,
  accounted: LEAF_TOTAL - UNACCOUNTED_IDS.length,
  unresolved: 0,
  unaccounted_element_ids: UNACCOUNTED_IDS,
  is_complete: false,
  // The server lists only the elements it recorded a disposition for, so this
  // is shorter than the leaf count by exactly the unaccounted ones.
  elements: Array.from({ length: LEAF_TOTAL - UNACCOUNTED_IDS.length }, (_, index) => ({
    element_id: `leaf-${index}`,
    disposition: "policy_target",
    reason: "target of a reading unit",
  })),
};

const readingPlanResponse = {
  document_version_id: VERSION_ID,
  unit_count: 4,
  is_exhaustive: true,
  uncovered_target_ids: [],
  units: [],
};

const structureResponse = {
  document_version_id: VERSION_ID,
  node_count: TOTAL_ELEMENTS,
  edge_count: TOTAL_ELEMENTS - 1,
  leaf_element_ids: [],
  governing_stems: [],
  unsatisfied_promises: [],
  nodes: [],
  edges: [],
};

/** Every canonical URL the component asked for, in order. */
let canonicalRequests: string[] = [];

function jsonResponse(body: unknown) {
  return { ok: true, status: 200, json: async () => body } as unknown as Response;
}

beforeEach(() => {
  canonicalRequests = [];

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
      if (url.includes("/canonical")) {
        canonicalRequests.push(url);
        return jsonResponse(canonicalResponse(url));
      }
      if (url.includes("/coverage")) return jsonResponse(coverageResponse);
      if (url.includes("/reading-plan")) return jsonResponse(readingPlanResponse);
      if (url.includes("/structure")) return jsonResponse(structureResponse);
      // There is deliberately no route for the persisted-stage endpoint. The
      // drawer no longer fetches it, and the throw below is what proves that:
      // re-add the fetch without re-adding a route here and every test in this
      // file fails by name.
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
      documentTitle="Document under test"
    />
  );
}

/** The page controls antd renders under the element table.
 *
 * Queried from the document rather than the render container: the drawer is a
 * portal, so its content is not inside the node React Testing Library created.
 */
function paginationItems() {
  return Array.from(document.querySelectorAll("li.ant-pagination-item"));
}

describe("ExtractionInsightDrawer", () => {
  it("keeps asking until it holds every element, and names no page size of its own", async () => {
    openDrawer();

    await waitFor(() => expect(screen.getByText(/^Document \(/)).toBeTruthy());

    // One window is not a collection. Derived from the fixture, so changing
    // either constant changes what this expects rather than breaking it.
    await waitFor(() => expect(canonicalRequests).toHaveLength(EXPECTED_REQUESTS));
    expect(canonicalRequests.map((url) => new URL(url, "http://localhost").searchParams.get("offset"))).toEqual(
      Array.from({ length: EXPECTED_REQUESTS }, (_, index) => String(index * SERVER_PAGE_SIZE))
    );

    // Position, not page size. Asking for a specific window size would be a
    // claim about the server this client is in no position to make.
    for (const url of canonicalRequests) {
      expect(new URL(url, "http://localhost").searchParams.has("limit")).toBe(false);
    }
  });

  it("counts the document by the server's total, not by the rows in hand", async () => {
    openDrawer();

    await waitFor(() => expect(screen.getByText(`Document (${TOTAL_ELEMENTS})`)).toBeTruthy());
    // The size of one window is what the count used to be.
    expect(screen.queryByText(`Document (${SERVER_PAGE_SIZE})`)).toBeNull();
  });

  it("lets a reviewer reach the last element of the collection", async () => {
    openDrawer();

    // Wait on a table row rather than the tab label, so a failure here is the
    // rows being missing and not the count above them.
    await waitFor(() => expect(screen.getByText(elementText(0))).toBeTruthy());

    // The collection is larger than one table page, and the control to leave
    // the first page exists. A viewer holding only the first window would show
    // a single page here and offer nowhere to go.
    const pages = paginationItems();
    expect(pages.length).toBeGreaterThan(1);

    fireEvent.click(pages[pages.length - 1]);

    await waitFor(() =>
      expect(screen.getByText(elementText(TOTAL_ELEMENTS - 1))).toBeTruthy()
    );
  });

  it("counts coverage by the report's leaf total, including elements with no disposition", async () => {
    openDrawer();

    // The dispositioned list is short by exactly the elements nobody looked at,
    // so counting that list would hide them in the count as well as the table.
    await waitFor(() => expect(screen.getByText(`Coverage (${LEAF_TOTAL})`)).toBeTruthy());
    expect(
      screen.queryByText(`Coverage (${LEAF_TOTAL - UNACCOUNTED_IDS.length})`)
    ).toBeNull();
  });
});
