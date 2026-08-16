/**
 * The rule's own source sentence is on the test card, not behind a click.
 *
 * WHY THESE TESTS
 *
 * The rule-scope tester tells the reviewer, in its own copy, that a judge
 * decides the case by reading "the source sentence, the facts it names, and the
 * outcome it states" against the case described. It then did not show that
 * sentence: to read it the reviewer had to leave the tab for View source. The
 * one thing the verdict is read from was the one thing missing from the card.
 *
 * That is constraint 6 — the evidence a reader needs to judge a record does not
 * sit behind a menu or a tab. The source sentence is evidence here, because the
 * reviewer's whole job on this card is to decide whether the verdict read from
 * it is right.
 *
 * WHAT THESE PIN, AND WHY EACH WOULD OTHERWISE COME BACK
 *
 *  - The stored source text is shown on the card, quoted whole and unaltered.
 *    A quotation that had gained an ellipsis, a bracket or an outer quote mark
 *    would no longer be the document's words (constraint 4).
 *  - Four states are held apart, none of them an empty box (constraint 5): a
 *    rule with no citation to quote; a citation whose text is still resolving;
 *    a citation whose text was never stored; and a resolved citation. The
 *    "never stored" answer is not the same as the "nothing to quote" answer,
 *    and the test proves they render as different sentences.
 *  - A bilingual clause keeps its per-run direction (constraint 7). The corpus
 *    is English-leading with Arabic runs inside it, so the quotation is tested
 *    against text of that shape, and the Arabic run carries its own direction
 *    without the whole quotation being flipped.
 *  - The source sits above the case input, so the reader's sequence is: read
 *    what the rule says, describe a case, read the verdict against it.
 *
 * The source text used here is invented for the test; no assertion depends on
 * any real document's words.
 */
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import type { CanonicalRule, Clause, EvidenceReference } from "../api";

const resolveClausesById = vi.fn();

vi.mock("../clauseCache", () => ({
  resolveClausesById: (...args: unknown[]) => resolveClausesById(...args),
  getClausesForDocumentVersion: vi.fn(),
}));

const { RuleScenarioTester } = await import("./RuleScenarioTester");

beforeAll(() => {
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

beforeEach(() => {
  resolveClausesById.mockReset();
  resolveClausesById.mockResolvedValue(new Map<string, Clause>());
});

afterEach(() => cleanup());

function rule(overrides: Partial<CanonicalRule> = {}): CanonicalRule {
  return {
    schema_version: "1.0",
    policy_set_id: "a-set-id",
    policy_version_id: "a-version-id",
    rule_id: "R-1",
    rule_revision: 1,
    title: "A title",
    description: "A description",
    rule_type: "obligation",
    authority: { owner: "an-owner", source: "", reference: "" },
    scope: { jurisdictions: [], organizational_units: [], processes: [] },
    condition: { type: "all", all: [] },
    evaluation_mode: "ai_ready",
    effect: { type: "require_action" },
    required_facts: [],
    exceptions: [],
    priority: 0,
    effective_from: "2024-01-01",
    effective_to: null,
    machine_executable: false,
    ambiguity_status: "clear",
    review_status: "published",
    evidence: [],
    ...overrides,
  } as CanonicalRule;
}

function evidence(overrides: Partial<EvidenceReference> = {}): EvidenceReference {
  return {
    document_version_id: "DV-1",
    source_hash: "a-hash",
    page: 4,
    section: "Part-time employment",
    clause_id: "C-1",
    start_offset: null,
    end_offset: null,
    ...overrides,
  };
}

function clause(overrides: Partial<Clause> = {}): Clause {
  return {
    id: "C-1",
    document_version_id: "DV-1",
    clause_ref: "3.2",
    section: "Part-time employment",
    page: 4,
    text: "Part-time regular employees are employees typically hired to work on hourly basis not more than 24hrs per week.",
    sequence: 1,
    search_document_id: "a-search-id",
    search_index: "an-index",
    ...overrides,
  };
}

describe("the rule text is on the test card", () => {
  it("shows the rule's stored source text on the card, quoted whole and unaltered", async () => {
    const c = clause();
    resolveClausesById.mockResolvedValue(new Map<string, Clause>([[c.id, c]]));

    render(<RuleScenarioTester policySetKey="a-key" rule={rule({ evidence: [evidence()] })} />);

    const quoted = await screen.findByTestId("scenario-source-quotation");
    // The document's words, exactly — no outer quote mark, bracket or ellipsis
    // added, and nothing dropped from either end.
    expect(quoted.textContent).toBe(c.text);

    // None of the other three states is standing in for the shown source.
    expect(screen.queryByTestId("scenario-source-none")).toBeNull();
    expect(screen.queryByTestId("scenario-source-absent")).toBeNull();
  });

  it("does not truncate a long source sentence to make the card fit", async () => {
    const long =
      "Part-time regular employees are employees typically hired to work on an hourly basis not more than twenty-four hours per week, and shall not be scheduled beyond that ceiling in any single week without the prior written approval of the department head and the office of human resources, which approval is granted only in circumstances the university judges to be exceptional and time limited.";
    const c = clause({ text: long });
    resolveClausesById.mockResolvedValue(new Map<string, Clause>([[c.id, c]]));

    render(<RuleScenarioTester policySetKey="a-key" rule={rule({ evidence: [evidence()] })} />);

    const quoted = await screen.findByTestId("scenario-source-quotation");
    expect(quoted.textContent).toBe(long);
    expect(quoted.textContent).not.toContain("…");
    expect(quoted.textContent).not.toContain("...");
  });

  it("says a rule with no citation has nothing to quote, and shows no quotation", async () => {
    render(<RuleScenarioTester policySetKey="a-key" rule={rule({ evidence: [] })} />);

    const none = await screen.findByTestId("scenario-source-none");
    expect(none.textContent ?? "").toMatch(/no source citation/i);
    expect(screen.queryByTestId("scenario-source-quotation")).toBeNull();
    // No citation means no clause to resolve, so the network is never reached.
    expect(resolveClausesById).not.toHaveBeenCalled();
  });

  it("distinguishes a citation whose text was never stored from a rule with nothing to quote", async () => {
    // The citation resolves to no clause: the reference exists, its wording does
    // not. This is a different answer from the no-citation case above.
    resolveClausesById.mockResolvedValue(new Map<string, Clause>());

    render(<RuleScenarioTester policySetKey="a-key" rule={rule({ evidence: [evidence()] })} />);

    const absent = await screen.findByTestId("scenario-source-absent");
    expect(absent.textContent ?? "").toMatch(/not stored/i);
    // It is not the same sentence as "no citation", and it is not a quotation.
    expect(screen.queryByTestId("scenario-source-none")).toBeNull();
    expect(screen.queryByTestId("scenario-source-quotation")).toBeNull();
  });

  it("keeps a bilingual clause's per-run direction and quotes it verbatim", async () => {
    // English-leading with an Arabic run inside it — the shape the corpus takes.
    const bilingual = "Part-time employees may not exceed 24 hours per week (لا يجوز تجاوز هذا الحد).";
    const c = clause({ text: bilingual });
    resolveClausesById.mockResolvedValue(new Map<string, Clause>([[c.id, c]]));

    render(<RuleScenarioTester policySetKey="a-key" rule={rule({ evidence: [evidence()] })} />);

    const quoted = await screen.findByTestId("scenario-source-quotation");
    // Not one character altered, both scripts present in logical order.
    expect(quoted.textContent).toBe(bilingual);
    // The Arabic run carries its own direction rather than the whole quotation
    // being flipped: a right-to-left run is isolated inside the block.
    expect(quoted.querySelector('[dir="rtl"]')).not.toBeNull();
  });

  it("places the source above the case input, so it is read before the case is described", async () => {
    const c = clause();
    resolveClausesById.mockResolvedValue(new Map<string, Clause>([[c.id, c]]));

    render(<RuleScenarioTester policySetKey="a-key" rule={rule({ evidence: [evidence()] })} />);

    await screen.findByTestId("scenario-source-quotation");
    const source = screen.getByTestId("scenario-source");
    const input = screen.getByRole("textbox");
    // The input follows the source in document order.
    expect(source.compareDocumentPosition(input) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});
