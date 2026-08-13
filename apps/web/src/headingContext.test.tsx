import { describe, expect, it, beforeAll, afterEach, vi } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import {
  HEADING_CONTEXT_LABEL,
  HEADING_NOT_RECORDED,
  headingContext,
} from "./headingContext";
import { EvidenceHeadingContext } from "./components/EvidenceHeadingContext";

/**
 * Heading context has to survive being absent.
 *
 * The behaviour this guards is not "the heading renders" — that already worked,
 * as ` · {section}` glued onto the citation line. It is that the row renders
 * when there is no heading, because the previous code emitted the empty string
 * there and a reviewer could not tell an unrecorded heading from a passage
 * that needed none.
 *
 * Every check below that could be satisfied by rendering nothing is paired with
 * something that fails when nothing renders. An `expect(...).not.toContain`
 * against a blank page passes, and so does a loop over an empty list.
 */

/** Citations measured in one real document. A floor for the loops below. */
const CITATIONS_AT_WRITING = 3;

beforeAll(() => {
  // antd reads both of these on mount and jsdom implements neither.
  vi.stubGlobal(
    "matchMedia",
    (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }),
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
  vi.unstubAllGlobals();
});

describe("headingContext", () => {
  it("reads a heading the document supplied", () => {
    const context = headingContext("7.3. DOCUMENTS REQUIRED TO BE ON FILE");

    expect(context.known).toBe(true);
    expect(context.heading).toBe("7.3. DOCUMENTS REQUIRED TO BE ON FILE");
  });

  it("treats every shape of nothing as not recorded, and says so", () => {
    // null is what the payload actually carries; the rest are shapes the same
    // field has taken elsewhere in this codebase.
    const nothings: Array<string | null | undefined> = [null, undefined, "", "   "];

    let checked = 0;
    for (const value of nothings) {
      const context = headingContext(value);
      expect(context.known, JSON.stringify(value)).toBe(false);
      expect(context.heading, JSON.stringify(value)).toBe("");
      // There is always something to say. A blank absence string would put the
      // row back to being invisible by another route.
      expect(context.absence.length, JSON.stringify(value)).toBeGreaterThan(0);
      checked += 1;
    }
    expect(checked).toBe(nothings.length);
    expect(checked).toBeGreaterThan(0);
  });

  it("never paraphrases — the heading comes back exactly as given", () => {
    // Headings in this corpus include lead-in stems with trailing colons and
    // numbered headings in caps. Neither may be tidied on the way through.
    const awkward = "in order to complete your personal file:";

    expect(headingContext(awkward).heading).toBe(awkward);
    expect(headingContext(`  ${awkward}  `).heading).toBe(awkward);
  });
});

describe("EvidenceHeadingContext", () => {
  it("shows the heading, quoted, when the citation has one", () => {
    const heading = "7.3. DOCUMENTS REQUIRED TO BE ON FILE";
    render(<EvidenceHeadingContext section={heading} />);

    expect(screen.getByText(HEADING_CONTEXT_LABEL, { exact: false })).toBeTruthy();
    // Quoted rather than paraphrased, so the assertion is on the exact words.
    expect(screen.getByText(`“${heading}”`)).toBeTruthy();
  });

  it("still shows the row when the document supplied no heading", () => {
    // The regression this file exists for. The old code rendered "" here and
    // the field vanished, so "we do not know" was indistinguishable from
    // "there is nothing to know".
    render(<EvidenceHeadingContext section={null} />);

    expect(screen.getByText(HEADING_CONTEXT_LABEL, { exact: false })).toBeTruthy();
    expect(screen.getByText(HEADING_NOT_RECORDED)).toBeTruthy();
  });

  it("does not invent a heading when there is none", () => {
    render(<EvidenceHeadingContext section={null} />);
    const body = document.body.textContent ?? "";

    // Positive control first: without it, every assertion below passes against
    // a component that rendered nothing at all.
    expect(body).toContain(HEADING_CONTEXT_LABEL);
    // No placeholder heading, and no leaked internal value.
    expect(body).not.toContain("“”");
    expect(body).not.toContain("null");
    expect(body).not.toContain("undefined");
  });

  it("reads as a recorded fact, not as a fault in the record", () => {
    render(<EvidenceHeadingContext section={null} />);
    const body = (document.body.textContent ?? "").toLowerCase();

    expect(body).toContain(HEADING_CONTEXT_LABEL.toLowerCase());
    for (const blame of ["missing", "failed", "error", "incomplete", "unsupported"]) {
      expect(body, blame).not.toContain(blame);
    }
  });

  it("tells the two states apart in the text a reviewer reads", () => {
    // Not a styling assertion: if both states produced the same words, the row
    // would be present in both and still answer nothing.
    const { unmount } = render(
      <EvidenceHeadingContext section="7.3. DOCUMENTS REQUIRED TO BE ON FILE" />,
    );
    const known = document.body.textContent ?? "";
    unmount();

    render(<EvidenceHeadingContext section={null} />);
    const unknown = document.body.textContent ?? "";

    expect(known.length).toBeGreaterThan(0);
    expect(unknown.length).toBeGreaterThan(0);
    expect(known).not.toBe(unknown);
  });

  it("gives every citation its own row instead of choosing one for the record", () => {
    // Measured shape: one record carried a numbered heading, a null, and
    // repeats of a lead-in stem across its citations. Any single answer for
    // the record would have been a claim the evidence does not make.
    const sections: Array<string | null> = [
      "7.3. DOCUMENTS REQUIRED TO BE ON FILE",
      null,
      "in order to complete your personal file:",
    ];

    render(
      <div data-testid="citations">
        {sections.map((section, idx) => (
          <EvidenceHeadingContext key={idx} section={section} />
        ))}
      </div>,
    );

    const rows = within(screen.getByTestId("citations")).getAllByText(
      HEADING_CONTEXT_LABEL,
      { exact: false },
    );

    // One row per citation. Fewer means the component collapsed or deduplicated
    // them; this is the assertion that fails if a future change picks one
    // heading for the whole record.
    expect(rows.length).toBe(sections.length);
    // And the detector still sees: a selector that matched nothing would make
    // the equality above unreachable but a `>= 0` style check pass silently.
    expect(rows.length).toBeGreaterThanOrEqual(CITATIONS_AT_WRITING);

    const body = document.body.textContent ?? "";
    expect(body).toContain("“7.3. DOCUMENTS REQUIRED TO BE ON FILE”");
    expect(body).toContain("“in order to complete your personal file:”");
    expect(body).toContain(HEADING_NOT_RECORDED);
  });
});
