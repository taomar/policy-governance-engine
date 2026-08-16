import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, waitFor } from "@testing-library/react";
import { App } from "antd";
import { ActorProvider } from "../ActorContext";
import { CorrelationPage } from "./CorrelationPage";
import { baseDirection } from "../directionalText";
import type { CorrelationFinding } from "../api";

/**
 * A cited quote must read as one line, not three.
 *
 * On the Correlation review page each finding prints the source text of a rule
 * wrapped in curly quotation marks. The marks were emitted as bare text nodes
 * *around* a `<DirectionalText align>`, and `align` gives that element the
 * `.directional-text--block` class, which is `display: block`. A block element
 * dropped between two inline siblings pushes them onto their own lines, so the
 * opening mark, the quote, and the closing mark each landed on a separate line
 * and the citation looked broken. This is the twin of the case-runner defect
 * fixed in commit 0a6cd59; the cure is the same: the single block element must
 * *carry* the marks, with the quote inline inside it.
 *
 * What this test can and cannot catch: jsdom performs no layout, so it cannot
 * measure that the three parts share one rendered line. It asserts the
 * structural cause instead — that the one `display: block` element in the
 * citation contains BOTH marks (rather than sitting between them as a sibling).
 * With the marks inside a single inline formatting context there is no block to
 * force a break; with the block wedged between them there necessarily is. It
 * also pins Constraint 4 (the quote is verbatim): the block's text must equal
 * the exact source text framed by the two marks, with nothing trimmed, clipped
 * or reordered.
 */

const POLICY_SET_KEY = "policy-set-under-test";

// Escaped so the assertion can never be silently mangled by a re-encode of this
// file: U+201C LEFT and U+201D RIGHT DOUBLE QUOTATION MARK.
const OPEN = "\u201C";
const CLOSE = "\u201D";

// A Latin-only citation: DirectionalText leaves it untouched and baseDirection
// reads it as "ltr" — the shape of every quote in today's live corpus.
const SOURCE_LTR = "A processor shall not retain personal data beyond 30 days.";

// A synthetic Arabic-leading citation, present ONLY to prove the direction is
// derived from the text rather than hard-coded. It is not representative of the
// current data: the producer confirmed every Arabic-bearing quote in the live
// corpus begins with a Latin character (a row number or English column), so in
// production baseDirection returns "ltr" and this attribute changes nothing
// visible. baseDirection("...") for this string returns "rtl".
const SOURCE_RTL = "\u0634\u0631\u0637 \u0627\u0644\u0627\u062D\u062A\u0641\u0627\u0638 \u0628\u0627\u0644\u0628\u064A\u0627\u0646\u0627\u062A";

const listCorrelationRuns = vi.fn();
const getCorrelationFindings = vi.fn();

vi.mock("../api", async () => {
  const actual = await vi.importActual<typeof import("../api")>("../api");
  return {
    ...actual,
    aiApi: {
      listCorrelationRuns: (...args: unknown[]) => listCorrelationRuns(...args),
      getCorrelationFindings: (...args: unknown[]) => getCorrelationFindings(...args),
    },
  };
});

function makeFinding(id: string, classification: string, sourceText: string): CorrelationFinding {
  return {
    id,
    run_id: "run-1",
    classification,
    analysis_status: "confirmed",
    severity: "high",
    rule_ids: ["R-1", "R-2"],
    reason: "Two rules disagree on the retention period.",
    evidence: [{ policy_index: 1, rule_id: "R-1", source_text: sourceText }],
    overlap: null,
    requirements: [],
    disposition: "open",
    disposition_by: null,
    disposition_at: null,
    disposition_notes: null,
    created_at: null,
  };
}

function respondWith(findings: CorrelationFinding[]) {
  listCorrelationRuns.mockResolvedValue({ runs: [], count: 0, truncated: false });
  getCorrelationFindings.mockResolvedValue({
    run_id: "run-1",
    findings,
    by_classification: {},
    by_severity: {},
  });
}

function renderPage() {
  return render(
    <ActorProvider>
      <App>
        <CorrelationPage policySetKey={POLICY_SET_KEY} />
      </App>
    </ActorProvider>,
  );
}

/**
 * The `.directional-text--block` element inside the evidence item whose text
 * contains `sourceText`. That is the one `display: block` element in the
 * citation — before the fix it is the inner `align` wrapper (holding only the
 * quote, with the marks as its siblings); after the fix it is the outer element
 * that wraps the whole citation. Selecting it the same way in both states is
 * what lets the assertion flip.
 */
function citationBlockFor(sourceText: string): HTMLElement | null {
  const items = Array.from(document.querySelectorAll<HTMLElement>(".correlation-evidence-item"));
  const item = items.find((el) => el.textContent?.includes(sourceText)) ?? null;
  return item?.querySelector<HTMLElement>(".directional-text--block") ?? null;
}

afterEach(() => {
  cleanup();
  listCorrelationRuns.mockReset();
  getCorrelationFindings.mockReset();
});

describe("CorrelationPage cited quote marks", () => {
  it("keeps both quote marks inside the citation's one block element (verbatim)", async () => {
    respondWith([makeFinding("f-ltr", "contradiction", SOURCE_LTR)]);
    renderPage();

    let block: HTMLElement | null = null;
    await waitFor(() => {
      block = citationBlockFor(SOURCE_LTR);
      expect(block).not.toBeNull();
    });

    // Structural cause of the three-line break: the block must WRAP the marks,
    // not sit between them. If the marks are its siblings this holds neither at
    // the start nor the end.
    expect(block!.textContent?.startsWith(OPEN)).toBe(true);
    expect(block!.textContent?.endsWith(CLOSE)).toBe(true);

    // Constraint 4: the quote is exact — the source text, framed by the two
    // marks, with nothing trimmed, clipped or reordered.
    expect(block!.textContent).toBe(`${OPEN}${SOURCE_LTR}${CLOSE}`);
  });

  it("reads the citation's dir from its text, not a hard-coded value", async () => {
    respondWith([
      makeFinding("f-ltr", "contradiction", SOURCE_LTR),
      makeFinding("f-rtl", "conflict", SOURCE_RTL),
    ]);
    renderPage();

    await waitFor(() => {
      expect(citationBlockFor(SOURCE_LTR)).not.toBeNull();
      expect(citationBlockFor(SOURCE_RTL)).not.toBeNull();
    });

    const ltrBlock = citationBlockFor(SOURCE_LTR)!;
    const rtlBlock = citationBlockFor(SOURCE_RTL)!;

    // The attribute is computed from the citation text. On the live corpus this
    // is always "ltr" (Latin-leading), so it is invisible today; the Arabic
    // sample only proves the value tracks the text instead of being fixed.
    expect(ltrBlock.getAttribute("dir")).toBe(baseDirection(SOURCE_LTR));
    expect(ltrBlock.getAttribute("dir")).toBe("ltr");
    expect(rtlBlock.getAttribute("dir")).toBe(baseDirection(SOURCE_RTL));
    expect(rtlBlock.getAttribute("dir")).toBe("rtl");

    // Verbatim holds for non-Latin text too.
    expect(rtlBlock.textContent).toBe(`${OPEN}${SOURCE_RTL}${CLOSE}`);
  });
});
