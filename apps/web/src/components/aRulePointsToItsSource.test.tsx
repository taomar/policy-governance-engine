/**
 * The row that withholds a rule's words must point at where those words are.
 *
 * WHY THIS FILE EXISTS, AND WHY A STRING TEST WOULD NOT HAVE CAUGHT THE BUG
 *
 * When a rule's statement is the marked run of its passage word for word, the
 * card does not print the sentence a second time. It draws a short row instead —
 * "this rule is the highlighted sentence …, word for word" — and lets the marked
 * quotation carry the words. That trade is only honest while the row points the
 * reviewer at the quotation. A reviewer who follows the pointer, finds nothing,
 * and concludes the rule has no text has been misled by a card being tidy
 * (constraints 3 and 11).
 *
 * `c4473cf` moved the passage quotation to render *below* the rules it grounds,
 * at the user's request. The row's copy still said "above". A test that pinned
 * the literal string would have passed straight through that commit — the string
 * did not change, only the layout it described did — which is precisely how the
 * defect shipped. So this file does not assert the string. It asserts the
 * relationship between the row and the quotation as they actually render:
 *
 *   1. the quotation renders after the rule row it grounds (the order c4473cf
 *      established), so if either moves again this fails and forces a re-read; and
 *   2. the pointer names its source rather than encoding a screen position, so a
 *      future reorder cannot turn its copy into a lie. A card that says "above"
 *      or "below" bakes its own layout into its words; naming the passage removes
 *      that failure mode permanently.
 */

import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render } from "@testing-library/react";
import type { AssembledPolicy, CandidateRule, CanonicalRule } from "../api";
import { buildPolicyCards } from "../policyCards";
import { PolicyReviewCard } from "./PolicyReviewCard";

beforeAll(() => {
  // antd reads both on mount and jsdom implements neither.
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }));
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

/**
 * A rule whose title *is* its source sentence. `passageQuotations` reads the
 * source text from the rule (falling back to its description when no formulation
 * is stored), and `readPassage` marks a statement "whole" when it is that text
 * word for word — so making the two identical is what triggers the restated row.
 * Generic on purpose: a governance sentence with no document's specifics in it.
 */
function ruleWhoseTitleIsItsSource(ruleId: string, statement: string): CanonicalRule {
  return {
    schema_version: "1.0",
    policy_set_id: "set",
    policy_version_id: "draft",
    rule_id: ruleId,
    rule_revision: 1,
    title: statement,
    description: statement,
    rule_type: "obligation",
    authority: { level: "ai_drafted", owner: "formulator", rank: 0 },
    scope: { jurisdictions: [], organizational_units: [], personas: [], processes: [] },
    condition: { type: "all", all: [] },
    effect: { type: "require_action", action: "act" },
    required_facts: [],
    exceptions: [],
    priority: 0,
    effective_from: "2026-01-01",
    effective_to: null,
    machine_executable: false,
    review_status: "candidate",
    evidence: [],
    lineage: {
      extraction_run_id: "run",
      deployment_name: "model",
      prompt_version: "v1",
      parser_version: "v1",
      schema_version: "1.0",
      source_elements: ruleId,
    },
    tags: [],
    ambiguity_status: "clear",
    category: "general",
    group_label: "",
    advice: [],
    related_rule_ids: [],
    is_explicit_override: false,
    supersedes_rule_ids: [],
  } as CanonicalRule;
}

function candidateWhoseTitleIsItsSource(ruleId: string, statement: string): CandidateRule {
  return {
    id: `record-${ruleId}`,
    policy_set_id: "set",
    extraction_run_id: "run",
    rule_type: "obligation",
    revision: 1,
    review_status: "candidate",
    reviewed_by: null,
    reviewed_at: null,
    review_notes: null,
    published_version_id: null,
    created_at: "2026-01-01T00:00:00Z",
    rule: ruleWhoseTitleIsItsSource(ruleId, statement),
  } as CandidateRule;
}

/** One passage, one rule, and the rule is that passage word for word. */
function markedWholeCard(): { policy: AssembledPolicy; candidates: CandidateRule[] } {
  const statement = "A record is kept of every decision";
  const passage = {
    key: "p1-E000000",
    source_elements: "p1-E000000",
    page: 1,
    rule_count: 1,
    rules: [{ rule_id: "r0", title: statement, evaluation_mode: "ai_ready" as const }],
  };
  const policy: AssembledPolicy = {
    key: "digest-of-the-heading-chain",
    heading: "Schedule of matters",
    heading_path: ["Part four", "Schedule of matters"],
    persisted: true,
    document_version_id: "dv1",
    source_elements: passage.key,
    page: 1,
    rule_count: 1,
    passage_count: 1,
    route: "ai_ready",
    passages: [passage],
    rules: passage.rules,
  };
  const candidates = [candidateWhoseTitleIsItsSource("r0", statement)];
  return { policy, candidates };
}

function renderMarkedWholeCard(): HTMLElement {
  const { policy, candidates } = markedWholeCard();
  const [card] = buildPolicyCards([policy], candidates);
  const { container } = render(
    <PolicyReviewCard
      card={card}
      selected={false}
      indeterminate={false}
      open={false}
      statusColor={() => "default"}
      statusLabel={(status) => status}
      findingsFor={() => 0}
      onToggleSelect={() => {}}
      onOpen={() => {}}
      onApprove={() => {}}
      onReject={() => {}}
    />,
  );
  // The user meets this on the expanded card ("very bad looking after clicking").
  // The body is in the DOM whether collapsed or expanded — jsdom applies none of
  // the card's CSS, so nothing is hidden — but expanding mirrors the surface the
  // reviewer is actually reading when the pointer misleads them.
  const expander = container.querySelector<HTMLElement>('[data-testid="policy-card-expand"]');
  if (!expander) throw new Error("the card drew no expander to open its body");
  fireEvent.click(expander);
  return container;
}

/** The row that stands in for a withheld statement, and the quotation it grounds. */
function pointerAndQuotation(container: HTMLElement): { pointer: HTMLElement; quotation: HTMLElement } {
  const pointer = container.querySelector<HTMLElement>(".policy-card__rule-restated");
  const quotation = container.querySelector<HTMLElement>('[data-testid="policy-passage-quotation"]');
  if (!pointer) throw new Error("the restated row did not render — the fixture is not marked whole");
  if (!quotation) throw new Error("the quotation the row points at did not render");
  return { pointer, quotation };
}

describe("a restated rule points at its quotation as it actually renders", () => {
  it("puts the quotation after the row it grounds, and never lets the copy claim otherwise", () => {
    const container = renderMarkedWholeCard();
    const { pointer, quotation } = pointerAndQuotation(container);

    // Rendered order, not the literal string. c4473cf put the quotation after the
    // rule; if it ever moves back, this fails and the pointer must be re-read with it.
    const relation = pointer.compareDocumentPosition(quotation);
    const quotationIsBelow = Boolean(relation & Node.DOCUMENT_POSITION_FOLLOWING);
    const quotationIsAbove = Boolean(relation & Node.DOCUMENT_POSITION_PRECEDING);
    expect(quotationIsBelow, "the quotation renders after the rule it grounds").toBe(true);

    // The pointer may not claim a direction the layout contradicts. This is the
    // assertion the shipped card fails: it says "above" while the quotation is below.
    const copy = (pointer.textContent ?? "").toLowerCase();
    if (copy.includes("above")) {
      expect(quotationIsAbove, 'the row says "above" but the quotation renders below it').toBe(true);
    }
    if (copy.includes("below") || copy.includes("beneath")) {
      expect(quotationIsBelow, 'the row says "below" but the quotation renders above it').toBe(true);
    }
  });

  it("names its source instead of encoding a screen position", () => {
    // Point 3: a card that says "above"/"below" bakes its own layout into its
    // words, which is exactly what broke. Naming the passage stays true wherever
    // the quotation renders, so this pins the choice: no absolute position word.
    const container = renderMarkedWholeCard();
    const { pointer } = pointerAndQuotation(container);
    const copy = (pointer.textContent ?? "").toLowerCase();

    for (const positionWord of ["above", "below", "beneath", "underneath", "overhead"]) {
      expect(
        copy.includes(positionWord),
        `the pointer must name its source, not its position; found "${positionWord}" in: ${copy}`,
      ).toBe(false);
    }

    // …and it must still name what it points at, so it is not merely emptied of meaning.
    expect(copy, "the pointer must still name the source it stands in for").toMatch(
      /passage|highlighted|marked|quotation/,
    );
  });
});
