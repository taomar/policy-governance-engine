/**
 * The document's words follow the rules that were drawn from them.
 *
 * The card used to open each passage block with the source quotation, so a
 * reviewer met a block of the document's own prose before reaching the first
 * rule of the section. The user asked for the reverse: the rule's name and line
 * first, then the passage it was read from beneath them.
 *
 * WHAT THIS PINS
 *
 *   1. Inside a passage block, every rule row precedes the quotation. The rule
 *      leads; the source it was drawn from follows.
 *   2. Only the position moved. The quotation is still the stored passage,
 *      character for character, and a right-to-left passage still lays out in
 *      its own direction from its new place.
 *   3. A passage of more than one rule carries a short lead between the rules
 *      and the quotation, so a reader can still tell the quotation is the source
 *      of all the rules above it and not merely of the last one.
 *   4. A passage of one rule needs no such lead: there is one rule and one
 *      quotation, and nothing to disambiguate.
 *   5. A passage whose text was not stored still says so — in its new place
 *      below the rules, and without the multi-rule lead, because absent and
 *      present are different states and neither is a passage of several rules
 *      sharing one quotation.
 *
 * Nothing here is a phrase from any document, and no count in it is a
 * measurement of one.
 */
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render } from "@testing-library/react";
import type { CandidateRule, CanonicalRule } from "../api";
import { fromDraftRow } from "../policyCards";
import type { PolicyCard } from "../policyCards";
import { PolicyReviewCard } from "./PolicyReviewCard";

/** A sentence long enough to be a passage, holding none of the titles below. */
const MULTI_SOURCE = "The employer sets out obligations for its staff in this section.";
const SINGLE_SOURCE = "An employee shall give two weeks of notice before any leave.";

/** One rule. Its title is deliberately not a run of its source, so the row
 *  prints the title rather than deferring to a mark inside the quotation. */
function rule(ruleId: string, source: string, title: string): CanonicalRule {
  return {
    rule_id: ruleId,
    title,
    description: source,
    evaluation_mode: "deterministic",
    condition: { type: "all", all: [] },
    effect: { type: "require_action", action: "an action" },
  } as unknown as CanonicalRule;
}

interface PassageSpec {
  /** The source text every rule of the passage was read from, or null when the
   *  document's text was not stored with the rules. */
  source: string | null;
  /** One title per rule the passage states. */
  titles: string[];
}

/** A card of the passages given. Every rule of a passage shares one source and
 *  one stance, so the passage draws exactly one quotation and no stance head. */
function card(passages: readonly PassageSpec[]): PolicyCard {
  let next = 0;
  const built = passages.map((spec, passageIndex) => {
    const rules = spec.titles.map((title) => {
      const index = next++;
      return {
        rule_id: `r${index}`,
        evaluation_mode: "deterministic",
        ...fromDraftRow({
          id: `candidate-${index}`,
          review_status: "pending",
          rule_type: "obligation",
          rule: rule(`r${index}`, spec.source ?? "", title),
        } as unknown as CandidateRule),
      };
    });
    return { passage: { key: `passage-${passageIndex}` }, rules };
  });

  const all = built.flatMap((passage) => passage.rules);
  return {
    policy: {
      key: "a-key",
      heading: "A heading",
      heading_path: ["A heading"],
      topic_label: null,
      persisted: true,
      provision_id: "a-provision-id",
      document_version_id: null,
      source_elements: "p1-E1",
      page: 1,
      rule_count: all.length,
      passage_count: built.length,
      route: "deterministic",
      passages: built.map((passage) => ({
        rules: passage.rules.map(({ rule_id }) => ({ rule_id })),
      })),
      rules: [],
    },
    passages: built,
    rules: all,
    reviewableIds: all.map((one) => one.recordId),
    allIds: all.map((one) => one.recordId),
    hiddenByFilter: 0,
  } as unknown as PolicyCard;
}

function draw(passages: readonly PassageSpec[]) {
  return render(
    <PolicyReviewCard
      card={card(passages)}
      selected={false}
      indeterminate={false}
      open={false}
      statusColor={() => "default"}
      statusLabel={(status: string) => status}
      findingsFor={() => 0}
      onToggleSelect={() => {}}
      onOpen={() => {}}
    />,
  );
}

/** The first passage block's parts, as the reviewer meets them. */
function firstPassage(container: HTMLElement) {
  const section = container.querySelector('[data-testid="policy-passage"]');
  if (section === null) throw new Error("no passage block rendered");
  return {
    rules: [...section.querySelectorAll('[data-testid="policy-card-rule"]')],
    quotation: section.querySelector('[data-testid="policy-passage-quotation"]'),
    lead: section.querySelector('[data-testid="policy-passage-lead"]'),
    absent: section.querySelector(".policy-card__passage-absent"),
  };
}

/** Whether `later` sits after `earlier` in document order. */
function follows(earlier: Element, later: Element): boolean {
  return Boolean(earlier.compareDocumentPosition(later) & Node.DOCUMENT_POSITION_FOLLOWING);
}

afterEach(cleanup);

describe("the source follows the rules it gave", () => {
  it("draws every rule of a passage before the quotation they were read from", () => {
    const { container } = draw([
      { source: MULTI_SOURCE, titles: ["Statement one", "Statement two", "Statement three"] },
    ]);
    const { rules, quotation } = firstPassage(container);

    expect(rules).toHaveLength(3);
    expect(quotation).not.toBeNull();
    for (const row of rules) {
      expect(follows(row, quotation!)).toBe(true);
    }
  });

  it("moves the words without altering them", () => {
    const { container } = draw([
      { source: MULTI_SOURCE, titles: ["Statement one", "Statement two"] },
    ]);
    const { quotation } = firstPassage(container);
    expect(quotation!.textContent).toBe(MULTI_SOURCE);
  });

  it("leads the trailing quotation so it reads as the source of every rule above it", () => {
    const { container } = draw([
      { source: MULTI_SOURCE, titles: ["Statement one", "Statement two", "Statement three"] },
    ]);
    const { rules, lead, quotation } = firstPassage(container);

    expect(lead).not.toBeNull();
    // The lead sits between the last rule and the quotation.
    expect(follows(rules[rules.length - 1], lead!)).toBe(true);
    expect(follows(lead!, quotation!)).toBe(true);
  });

  it("adds no lead to a passage of one rule, which has nothing to disambiguate", () => {
    const { container } = draw([{ source: SINGLE_SOURCE, titles: ["Statement one"] }]);
    const { rules, lead, quotation } = firstPassage(container);

    expect(rules).toHaveLength(1);
    expect(lead).toBeNull();
    expect(quotation).not.toBeNull();
    // Still rule first, source second — which is exactly the request, undiluted.
    expect(follows(rules[0], quotation!)).toBe(true);
  });

  it("still says a passage's text was not stored, below its rules and without a lead", () => {
    const { container } = draw([
      { source: null, titles: ["Statement one", "Statement two"] },
    ]);
    const { rules, absent, lead, quotation } = firstPassage(container);

    expect(quotation).toBeNull();
    expect(lead).toBeNull();
    expect(absent).not.toBeNull();
    expect(absent!.textContent).toMatch(/not stored/i);
    // It takes the quotation's new place: after the rules, not before them.
    expect(follows(rules[rules.length - 1], absent!)).toBe(true);
  });

  it("lays a right-to-left source out in its own direction from its new position", () => {
    const arabic = "يجب على الموظف تقديم طلب الإجازة قبل أسبوعين من تاريخ الإجازة.";
    const { container } = draw([
      { source: arabic, titles: ["Statement one", "Statement two"] },
    ]);
    const { rules, quotation } = firstPassage(container);

    expect(quotation).not.toBeNull();
    expect(quotation!.getAttribute("dir")).toBe("rtl");
    expect(quotation!.textContent).toBe(arabic);
    expect(follows(rules[rules.length - 1], quotation!)).toBe(true);
  });
});
