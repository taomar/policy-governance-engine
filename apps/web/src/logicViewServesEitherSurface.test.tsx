/**
 * One policy-level logic view, for a policy under review and a policy already
 * published.
 *
 * WHY THIS FILE EXISTS
 *
 * This application grew two surfaces that show records — a queue of things
 * awaiting a decision, and a page of things already decided — and they drifted
 * into two renderings of one record. Closing that drift means the components
 * that draw a record must not know which surface fetched it.
 *
 * The queue's cards name the row a rule was read from. A published version has
 * no such row: it carries the rule itself. A view that reaches through the
 * first shape to find the rule therefore works on one surface and throws on the
 * other, and the only way to get a policy-level logic view onto the second
 * surface is to write it a second time. That second copy is the thing these
 * tests exist to make unnecessary.
 *
 * So the claim under test is not "it renders" but the stronger one: **the same
 * policy produces the same arrangement and the same markup whichever shape of
 * card carries it.** A reviewer moving between the two surfaces is looking at
 * one record and must see one reading of it.
 *
 * HOW THESE TESTS FAIL
 *
 * Every test below builds its published card by *deleting* the row-naming field
 * outright rather than by leaving it empty, so a reading that reaches through it
 * throws rather than quietly returning nothing. Absent and empty are different
 * states here as everywhere, and a test that passed an empty row would prove
 * only that the view tolerates an empty row.
 */
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render } from "@testing-library/react";

import type { PolicyAttribute } from "./api";
import type { PolicyCard, PolicyCardPassage, PolicyCardRule } from "./policyCards";
import { policyLogicShape } from "./policyLogicShape";
import { PolicyLogicTable } from "./components/PolicyLogicTable";

afterEach(cleanup);

/** Slots named so that nothing here reads as one document's vocabulary. */
const SLOTS = [
  "subject",
  "condition",
  "constraint",
  "modality",
  "predicate",
  "object",
  "assigner",
] as const;

function row(
  attribute: string,
  text: string,
  fact: string | null = null,
): PolicyAttribute {
  return { attribute, text, fact, data_type: null } as PolicyAttribute;
}

interface Stated {
  ruleId: string;
  ruleType: string;
  effect: string;
  route: string;
  applies: PolicyAttribute[];
  outcome: PolicyAttribute[];
}

/** The rule itself, identical in both shapes of card below. */
function statedRule(stated: Stated) {
  return {
    rule_id: stated.ruleId,
    rule_type: stated.ruleType,
    rule_revision: 3,
    effect: { type: stated.effect, action: "" },
    condition: { type: "all", all: [] },
    attributes: { applies: stated.applies, outcome: stated.outcome },
  };
}

/** A card rule shaped the way a queue builds one: it names the row it read. */
function reviewShaped(stated: Stated): PolicyCardRule {
  return {
    rule_id: stated.ruleId,
    evaluation_mode: stated.route,
    candidate: {
      id: `row-${stated.ruleId}`,
      review_status: "candidate",
      rule: statedRule(stated),
    },
  } as unknown as PolicyCardRule;
}

/** A card rule shaped the way a published version supplies one: the rule
 *  itself, its identity, and the status that decides what may be done to it.
 *  There is deliberately no row-naming field at all. */
function publishedShaped(stated: Stated): PolicyCardRule {
  const built = {
    rule_id: stated.ruleId,
    ruleId: stated.ruleId,
    evaluation_mode: stated.route,
    reviewStatus: "published",
    rule: statedRule(stated),
  };
  return built as unknown as PolicyCardRule;
}

function cardOf(rules: PolicyCardRule[], perPassage = 3): PolicyCard {
  const passages: PolicyCardPassage[] = [];
  for (let index = 0; index < rules.length; index += perPassage) {
    passages.push({
      passage: { key: `passage-${index / perPassage}` } as PolicyCardPassage["passage"],
      rules: rules.slice(index, index + perPassage),
    });
  }
  return {
    policy: { key: "policy-1", rule_count: rules.length } as PolicyCard["policy"],
    passages,
    rules,
    hiddenByFilter: 0,
  } as unknown as PolicyCard;
}

/** A policy whose rules fill an uneven share of the slots, so the arrangement
 *  being compared is a real one — several distinct shapes, some slots stated by
 *  one rule only, and a rule that records nothing at all. */
function policy(size: number): Stated[] {
  return Array.from({ length: size }, (_, index) => {
    const applies: PolicyAttribute[] = [];
    const outcome: PolicyAttribute[] = [];
    SLOTS.forEach((slot, slotIndex) => {
      if ((index + slotIndex) % 3 === 0) return;
      const entry = row(
        slot,
        `${slot} as rule ${index + 1} states it, at whatever length the record used`,
        slotIndex % 2 === 0 ? `${slot}-${index}` : null,
      );
      if (slotIndex < 3) applies.push(entry);
      else outcome.push(entry);
    });
    return {
      ruleId: `rule-${index + 1}`,
      ruleType: index % 4 === 0 ? "permission" : "obligation",
      effect: index % 5 === 0 ? "deny" : "require_action",
      route: index % 2 === 0 ? "ai_ready" : "deterministic",
      applies,
      outcome,
    };
  });
}

function both(size: number): { review: PolicyCard; published: PolicyCard } {
  const stated = policy(size);
  return {
    review: cardOf(stated.map(reviewShaped)),
    published: cardOf(stated.map(publishedShaped)),
  };
}

describe("the arrangement does not depend on which surface fetched the policy", () => {
  it("is comparing two genuinely different shapes of card", () => {
    const { review, published } = both(7);
    // Guards the fixture itself: if the published shape quietly grew the field
    // the review shape uses, every other test here would pass without meaning
    // anything.
    expect(review.rules[0]).toHaveProperty("candidate");
    expect(published.rules[0]).not.toHaveProperty("candidate");
    expect(published.rules[0]).toHaveProperty("rule");
  });

  it.each([1, 7, 63])("arranges %i rules identically from either shape", (size) => {
    const { review, published } = both(size);
    expect(policyLogicShape(published)).toEqual(policyLogicShape(review));
  });

  it("counts, groups and orders the same from either shape", () => {
    const { review, published } = both(63);
    const left = policyLogicShape(review);
    const right = policyLogicShape(published);

    expect(right.total).toBe(left.total);
    expect(right.unrecorded).toBe(left.unrecorded);
    expect(right.columns.map((column) => `${column.side}/${column.attribute}`)).toEqual(
      left.columns.map((column) => `${column.side}/${column.attribute}`),
    );
    expect(right.columns.map((column) => column.filled)).toEqual(
      left.columns.map((column) => column.filled),
    );
    expect(right.shapes.map((shape) => shape.rules.map((member) => member.ordinal))).toEqual(
      left.shapes.map((shape) => shape.rules.map((member) => member.ordinal)),
    );
    // The arrangement it draws is worth comparing only if it is not degenerate.
    expect(left.shapes.length).toBeGreaterThan(1);
    expect(left.columns.length).toBeGreaterThan(5);
  });
});

describe("the reviewer sees the same view on either surface", () => {
  it.each([1, 7, 63])("renders %i rules to the same markup from either shape", (size) => {
    const { review, published } = both(size);

    const first = render(<PolicyLogicTable card={review} />);
    const reviewMarkup = first.container.innerHTML;
    cleanup();

    const second = render(<PolicyLogicTable card={published} />);
    const publishedMarkup = second.container.innerHTML;

    expect(publishedMarkup).toBe(reviewMarkup);
    expect(publishedMarkup.length).toBeGreaterThan(0);
  });

  it("draws every rule of a published policy, and every attribute of them", () => {
    const stated = policy(63);
    const { container } = render(<PolicyLogicTable card={cardOf(stated.map(publishedShaped))} />);

    expect(container.querySelectorAll("[data-rule]")).toHaveLength(63);

    // Every value any rule states is present in full, not shortened to fit.
    const text = container.textContent ?? "";
    for (const rule of stated) {
      for (const entry of [...rule.applies, ...rule.outcome]) {
        expect(text).toContain(entry.text);
      }
    }
    expect(text).not.toContain("\u2026");
  });

  it("still tells a published rule that records nothing from one that records an empty half", () => {
    const nothing: Stated = {
      ruleId: "records-nothing",
      ruleType: "obligation",
      effect: "require_action",
      route: "ai_ready",
      applies: [],
      outcome: [],
    };
    const blank = publishedShaped(nothing) as unknown as { rule: { attributes?: unknown } };
    delete blank.rule.attributes;

    const shape = policyLogicShape(
      cardOf([blank as unknown as PolicyCardRule, ...policy(2).map(publishedShaped)]),
    );

    expect(shape.unrecorded).toBe(1);
    expect(shape.blocks[0].rules[0].unrecorded).toBe(true);
    // A rule that recorded a table holding no rows is a different statement
    // from a rule that recorded no table, on this surface as on the other.
    const empty = policyLogicShape(cardOf([publishedShaped(nothing)]));
    expect(empty.unrecorded).toBe(0);
    expect(empty.blocks[0].rules[0].unrecorded).toBe(false);
  });
});

describe("nothing in this view is written against one surface's shape", () => {
  const sources = import.meta.glob("./{policyLogicShape.ts,components/PolicyLogicTable.tsx}", {
    query: "?raw",
    import: "default",
    eager: true,
  }) as Record<string, string>;

  it("is reading both of its own sources", () => {
    expect(Object.keys(sources)).toHaveLength(2);
    for (const text of Object.values(sources)) expect(text.length).toBeGreaterThan(500);
  });

  /**
   * The one place the two shapes are reconciled is the documented reader in
   * `policyLogicShape`. Anywhere else, reaching through a named row binds this
   * view to the surface that supplies one — which is how the second copy this
   * work is deleting came to be written in the first place.
   *
   * Comments are stripped first so that explaining the rule does not break it.
   */
  it("reaches through no row-naming field outside its one documented reader", () => {
    for (const [name, text] of Object.entries(sources)) {
      const code = text
        .replace(/\/\*[\s\S]*?\*\//g, "")
        .replace(/(^|[^:])\/\/.*$/gm, "$1");
      const reaches = code.match(/\.candidate\b/g) ?? [];
      const allowed = code.includes("bearing.candidate?.rule") ? 1 : 0;
      expect(
        reaches.length,
        `${name} reaches through a row-naming field ${reaches.length} time(s)`,
      ).toBe(allowed);
    }
  });

  it("takes no property that would let a caller decide what a record permits", () => {
    const view = sources["./components/PolicyLogicTable.tsx"];
    const code = view.replace(/\/\*[\s\S]*?\*\//g, "");
    for (const flag of [
      "canReview",
      "canEdit",
      "canApprove",
      "readOnly",
      "isPublished",
      "editable",
      "onApprove",
      "onReject",
    ]) {
      expect(code, `${flag} would make this view answerable to its caller`).not.toContain(flag);
    }
  });
});
