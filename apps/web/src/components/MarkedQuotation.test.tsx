import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { MarkedQuotation } from "./MarkedQuotation";

/**
 * THE QUOTATION IS THE DOCUMENT, UNALTERED.
 *
 * Marking is the one place on this card where the interface writes *into* the
 * source's own block. The invariant that keeps it honest is that the marks are
 * offsets, never content: whatever the reader sees, selects and copies is the
 * stored passage character for character. A rule ordinal spliced into the text
 * would be an interface word inside a quotation, which is exactly the thing
 * this screen may not do.
 *
 * The second invariant is direction. One of the two documents is bilingual, and
 * cutting a right-to-left sentence into fragments and laying them out in DOM
 * order reverses it. `5fb33b3` fixed that for whole runs; splitting them again
 * for marks must not undo it.
 */

afterEach(cleanup);

const PASSAGE =
  "In order to process your Iqama, you will be needed to take a medical test.";

describe("a marked quotation is still the passage", () => {
  it("renders the text exactly, marks and all", () => {
    render(
      <MarkedQuotation
        text={PASSAGE}
        marks={[{ start: 32, end: 72, ordinal: 1 }]}
        testId="q"
      />,
    );
    expect(screen.getByTestId("q").textContent).toBe(PASSAGE);
  });

  it("keeps the ordinal out of the text", () => {
    // Drawn by the stylesheet from `data-rule`. A reviewer copying the
    // quotation into a mail must not paste "1" into the middle of a sentence.
    render(
      <MarkedQuotation
        text={PASSAGE}
        marks={[{ start: 32, end: 73, ordinal: 7 }]}
        testId="q"
      />,
    );
    const marked = screen.getByTestId("q").querySelector("mark")!;
    expect(marked.textContent).toBe("you will be needed to take a medical test");
    expect(marked.getAttribute("data-rule")).toBe("7");
    expect(screen.getByTestId("q").textContent).not.toContain("7");
  });

  it("renders an unmarked passage whole", () => {
    render(<MarkedQuotation text={PASSAGE} marks={[]} testId="q" />);
    const block = screen.getByTestId("q");
    expect(block.textContent).toBe(PASSAGE);
    expect(block.querySelectorAll("mark")).toHaveLength(0);
  });

  it("survives several marks with gaps between them", () => {
    const passage =
      "Contracts will normally begin at the beginning of the academic year. " +
      "If an employee begins work on a different date, a temporary contract will be issued.";
    render(
      <MarkedQuotation
        text={passage}
        marks={[
          { start: 0, end: 29, ordinal: 1 },
          { start: 116, end: 152, ordinal: 2 },
        ]}
        testId="q"
      />,
    );
    expect(screen.getByTestId("q").textContent).toBe(passage);
    expect(screen.getByTestId("q").querySelectorAll("mark")).toHaveLength(2);
  });
});

describe("direction survives the split", () => {
  it("lays a right-to-left passage out in its own direction", () => {
    const arabic = "يجب على الموظف تقديم طلب الإجازة قبل أسبوعين من تاريخ الإجازة.";
    render(
      <MarkedQuotation text={arabic} marks={[{ start: 0, end: 14, ordinal: 1 }]} testId="q" />,
    );
    const block = screen.getByTestId("q");
    expect(block.getAttribute("dir")).toBe("rtl");
    expect(block.textContent).toBe(arabic);
  });

  it("leaves a left-to-right passage alone", () => {
    render(<MarkedQuotation text={PASSAGE} marks={[]} testId="q" />);
    expect(screen.getByTestId("q").getAttribute("dir")).toBe("ltr");
  });

  it("isolates each fragment so a Latin run inside Arabic keeps its direction", () => {
    // The failure this catches is subtle and real: `AIS` inside an Arabic
    // sentence, rendered as a bare fragment, joins the surrounding run and
    // reverses. Each fragment carries its own isolation.
    const mixed = "يجب على الموظف إبلاغ AIS قبل السفر.";
    render(<MarkedQuotation text={mixed} marks={[{ start: 21, end: 24, ordinal: 1 }]} testId="q" />);
    const block = screen.getByTestId("q");
    expect(block.textContent).toBe(mixed);
    // Every fragment is wrapped; none is a naked text node of the block.
    for (const node of Array.from(block.childNodes)) {
      expect(node.nodeType).toBe(Node.ELEMENT_NODE);
    }
  });
});
