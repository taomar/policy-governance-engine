/**
 * A card leads with what it decides, without losing where anything came from.
 *
 * WHAT THIS IS FOR
 *
 * Documents introduce their terms and state their rules in the same section. On
 * the live corpus, 34 policies hold both, and in 32 of them the two are
 * interleaved rather than blocked: a reviewer scanning for what a policy
 * actually binds someone to reads past the definitions to find it. That is the
 * burying an earlier split into two queues was built to stop, and it was the
 * right problem read at the wrong level — the cure belongs inside the card,
 * where nothing has to be hidden to apply it.
 *
 * WHAT IT MAY NOT COST
 *
 * Two things are load-bearing and are what most of this file tests:
 *
 *   1. A rule stays with the quotation it was drawn from. The rule and its
 *      source are the two halves of the evidence a reviewer is checking, and no
 *      ordering is worth separating them. So grouping happens inside a passage
 *      and passages move whole.
 *
 *      Which of the two comes first is a presentation decision and is not
 *      pinned here: the passage's words now follow the rules they gave, headed
 *      by a caption naming them as the source. What this file tests is that
 *      they stay in the same passage block, whichever order they are drawn in.
 *
 *   2. The numbers keep the document's order. They are the only record on the
 *      card of where the source states each rule, so after a re-ordering they
 *      read out of sequence — which is itself the signal that the display order
 *      is ours and the document's order is still knowable.
 *
 * Nothing here is a phrase from any document, and no count in it is a
 * measurement of one.
 */
import { afterEach, describe, expect, it } from "vitest";
import type { CandidateRule } from "../api";
import { fromDraftRow } from "../policyCards";
import { cleanup, render } from "@testing-library/react";
import { PolicyReviewCard } from "./PolicyReviewCard";
import type { CanonicalRule } from "../api";
import type { PolicyCard } from "../policyCards";

/** One rule, distinguished by the effect its record states and by its id. */
function rule(ruleId: string, effectType: string | null): CanonicalRule {
  return {
    rule_id: ruleId,
    title: `statement ${ruleId}`,
    // Deliberately not the statement. A passage whose text is the statement
    // word for word is drawn a different way, and that path is another file's
    // subject; here the statements need to be legible so the order can be read.
    description: "a sentence of the source",
    evaluation_mode: "deterministic",
    condition: { type: "all", all: [] },
    // `null` is the fourth state: an effect the record carries but never typed.
    // The record always has an effect object — a record without one crashes the
    // passage reader long before it reaches this card, which is its own risk and
    // not this file's subject.
    effect: effectType === null ? { action: "an action" } : { type: effectType, action: "an action" },
  } as unknown as CanonicalRule;
}

/**
 * A card whose passages hold the effects given, in the order given.
 *
 * `[["deny", "informational"], ["informational"]]` is two passages: one holding
 * a rule then a definition, one holding a definition alone.
 */
function card(passages: readonly (readonly (string | null)[])[]): PolicyCard {
  let next = 0;
  const built = passages.map((effects, passageIndex) => {
    const rules = effects.map((effectType) => {
      const index = next++;
      return {
        rule_id: `r${index}`,
        evaluation_mode: "deterministic",
        ...fromDraftRow({
          id: `candidate-${index}`,
          review_status: "pending",
          rule_type: "obligation",
          rule: rule(`r${index}`, effectType),
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

function draw(passages: readonly (readonly (string | null)[])[]) {
  const { container } = render(
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

  const rows = [...container.querySelectorAll('[data-testid="policy-card-rule"]')];
  return {
    container,
    /** The statements, top to bottom, as the reviewer meets them. */
    statements: rows.map(
      (row) => row.querySelector(".policy-card__rule-title")?.textContent?.trim() ?? "",
    ),
    /** The number shown against each row, top to bottom. */
    numbers: rows.map((row) =>
      Number(row.querySelector(".policy-card__rule-ordinal")?.textContent ?? "0"),
    ),
    /** The passage keys, in the order the card draws them. */
    passageKeys: [...container.querySelectorAll('[data-testid="policy-passage"]')].map(
      (section) => section.getAttribute("data-passage") ?? "",
    ),
    /** Which passage each statement was drawn under. */
    statementsByPassage: [...container.querySelectorAll('[data-testid="policy-passage"]')].map(
      (section) =>
        [...section.querySelectorAll('[data-testid="policy-card-rule"]')].map(
          (row) => row.querySelector(".policy-card__rule-title")?.textContent?.trim() ?? "",
        ),
    ),
    headings: [...container.querySelectorAll('[data-testid="rule-group"]')].map((node) => ({
      stance: node.getAttribute("data-stance"),
      text: node.textContent?.trim() ?? "",
    })),
    note: container.querySelector('[data-testid="rule-grouping-note"]')?.textContent ?? null,
  };
}

afterEach(cleanup);

describe("a card leads with what it decides", () => {
  it("puts the rules that bind someone above the ones that supply meaning", () => {
    const drawn = draw([["informational", "deny", "informational", "require_action"]]);
    expect(drawn.statements).toEqual([
      "statement r1",
      "statement r3",
      "statement r0",
      "statement r2",
    ]);
  });

  it("sinks a passage that only supplies meaning below one that states a rule", () => {
    const drawn = draw([["informational", "informational"], ["deny"]]);
    expect(drawn.passageKeys).toEqual(["passage-1", "passage-0"]);
  });

  it("keeps the document's order among passages that rank together", () => {
    // Stability. Three passages that each state a rule are three passages in the
    // order the document states them, and grouping may not disturb that.
    const drawn = draw([["deny"], ["allow"], ["require_action"]]);
    expect(drawn.passageKeys).toEqual(["passage-0", "passage-1", "passage-2"]);
  });
});

describe("what the grouping may not cost", () => {
  it("never separates a rule from the quotation it was drawn from", () => {
    // The one thing this card exists to show. A rule shown beside a passage it
    // did not come from is a false claim about the source, and it would be a
    // false claim made in order to tidy a list.
    const drawn = draw([
      ["informational", "deny"],
      ["require_action", "informational"],
    ]);
    for (const statements of drawn.statementsByPassage) {
      expect(statements).toHaveLength(2);
    }
    expect(drawn.statementsByPassage.map((group) => [...group].sort())).toEqual(
      expect.arrayContaining([
        ["statement r0", "statement r1"],
        ["statement r2", "statement r3"],
      ]),
    );
  });

  it("keeps each rule's number at its place in the document", () => {
    // Re-numbering top to bottom would buy a tidy 1..4 by destroying the only
    // record of where the source states these rules. The numbers read out of
    // sequence instead, which is how a reviewer can see the order is ours.
    const drawn = draw([["informational", "deny", "informational", "require_action"]]);
    expect(drawn.numbers).toEqual([2, 4, 1, 3]);
  });

  it("draws every rule exactly once", () => {
    const drawn = draw([
      ["informational", "deny"],
      ["informational", "informational", "allow"],
      ["require_action"],
    ]);
    expect(drawn.statements).toHaveLength(6);
    expect(new Set(drawn.statements).size).toBe(6);
    expect([...drawn.numbers].sort((a, b) => a - b)).toEqual([1, 2, 3, 4, 5, 6]);
  });
});

describe("what the card says about the grouping", () => {
  it("heads each run only where the passage holds more than one kind", () => {
    const mixed = draw([["deny", "informational"]]);
    expect(mixed.headings.map((heading) => heading.stance)).toEqual([
      "decides",
      "supplies-meaning",
    ]);

    cleanup();
    const uniform = draw([["deny", "allow"]]);
    expect(uniform.headings).toEqual([]);
  });

  it("explains the order only when the order is not the document's", () => {
    expect(draw([["deny"], ["allow"]]).note).toBeNull();
    cleanup();
    expect(draw([["informational"], ["deny"]]).note).toBeTruthy();
    cleanup();
    expect(draw([["deny", "informational"]]).note).toBeTruthy();
  });

  it("names the record as the source of the answer, not this screen", () => {
    // A reviewer who disagrees with a placement needs to know what decided it,
    // because the thing to correct is the extraction and not the ordering.
    expect(draw([["informational"], ["deny"]]).note).toMatch(/effect/i);
  });
});

describe("a record that states no effect", () => {
  it("is grouped apart rather than filed under a kind it never claimed", () => {
    const drawn = draw([["deny", null, "informational"]]);
    expect(drawn.headings.map((heading) => heading.stance)).toEqual([
      "decides",
      "supplies-meaning",
      "unstated",
    ]);
    expect(drawn.statements).toEqual(["statement r0", "statement r2", "statement r1"]);
  });

  it("still renders, because a record the app cannot classify is still a record", () => {
    const drawn = draw([[null, null]]);
    expect(drawn.statements).toHaveLength(2);
    expect(drawn.headings).toEqual([]);
  });
});

describe("an effect kind this app has never met", () => {
  it("is read among the rules that bind someone", () => {
    // Not a closed set of four. A fifth kind must fail toward being read.
    const drawn = draw([["informational", "a_kind_added_after_this_test_was_written"]]);
    expect(drawn.statements).toEqual(["statement r1", "statement r0"]);
    expect(drawn.headings[0]?.stance).toBe("decides");
  });
});
