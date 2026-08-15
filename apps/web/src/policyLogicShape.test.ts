import { describe, expect, it } from "vitest";

import type { CanonicalPolicyRule, PolicyAttribute } from "./api";
import type {
  PolicyCard,
  PolicyCardPassage,
  PolicyCardRule,
} from "./policyCards";
import { policyLogicShape } from "./policyLogicShape";

/**
 * THE RE-ARRANGEMENT CARRIES EVERY FACT THE COMPARISON HELD, AND ADDS NONE.
 *
 * `policyLogic` decides what the rules of a policy say and where they differ.
 * This module decides only how that is arranged for reading. So every test here
 * is one of two questions: did the arrangement lose something the comparison
 * held, or did it invent something no rule said.
 *
 * Fixtures are built at several sizes rather than one, because a view that is
 * right on seven rules and wrong on eighty is wrong. No size below is special to
 * any document: the shapes are generated, and the only reason a large one is
 * named is that a policy that size exists and is the witness.
 */

function core(parts: Partial<CanonicalPolicyRule>): CanonicalPolicyRule {
  return parts as CanonicalPolicyRule;
}

function cardRule(
  ruleId: string,
  parts: Partial<CanonicalPolicyRule> | null,
  options: {
    route?: string;
    ruleType?: string;
    attributes?: { applies?: PolicyAttribute[]; outcome?: PolicyAttribute[] };
  } = {},
): PolicyCardRule {
  return {
    rule_id: ruleId,
    evaluation_mode: options.route ?? "ai_ready",
    candidate: {
      id: `record-${ruleId}`,
      review_status: "candidate",
      rule: {
        rule_id: ruleId,
        rule_type: options.ruleType ?? "obligation",
        effect: { type: "require_action", action: "" },
        condition: { type: "all", all: [] },
        formulation:
          parts === null ? undefined : { canonical: { rule: core(parts) } },
        attributes: options.attributes
          ? {
              applies: options.attributes.applies ?? [],
              outcome: options.attributes.outcome ?? [],
            }
          : undefined,
      },
    },
  } as unknown as PolicyCardRule;
}

function card(blocks: { key: string; rules: PolicyCardRule[] }[]): PolicyCard {
  const passages: PolicyCardPassage[] = blocks.map((block) => ({
    passage: { key: block.key } as PolicyCardPassage["passage"],
    rules: block.rules,
  }));
  const rules = blocks.flatMap((block) => block.rules);
  return {
    policy: {
      key: "policy-1",
      rule_count: rules.length,
    } as PolicyCard["policy"],
    passages,
    rules,
    hiddenByFilter: 0,
    reviewableIds: rules.map((rule) => rule.candidate.id),
    allIds: rules.map((rule) => rule.candidate.id),
    reviewStatuses: ["candidate"],
  };
}

describe("what each rule states survives the re-arrangement", () => {
  it("keeps every stated value under the attribute it was recorded in", () => {
    const shape = policyLogicShape(
      card([
        {
          key: "p1",
          rules: [
            cardRule("a", { subject: "one", predicate: "shall be" }),
            cardRule("b", {
              subject: "two",
              predicate: "shall be",
              temporal_constraint: "each quarter",
            }),
          ],
        },
      ]),
    );

    const rules = shape.blocks.flatMap((block) => block.rules);
    expect(rules).toHaveLength(2);
    expect(rules[0].stated.map((row) => [row.attribute, row.text])).toEqual([
      ["subject", "one"],
    ]);
    expect(rules[1].stated.map((row) => [row.attribute, row.text])).toEqual([
      ["subject", "two"],
      ["temporal_constraint", "each quarter"],
    ]);
    // Said by both, the same way, so it is stated once above and is not a
    // difference between them.
    expect(shape.shared.map((fact) => fact.text)).toEqual(["shall be"]);
  });

  it("names what a rule does not state instead of repeating it per attribute", () => {
    const shape = policyLogicShape(
      card([
        {
          key: "p1",
          rules: [
            cardRule("a", { subject: "one", temporal_constraint: "on Fridays" }),
            cardRule("b", { subject: "two" }),
          ],
        },
      ]),
    );

    const rules = shape.blocks.flatMap((block) => block.rules);
    expect(rules[0].absent).toEqual([]);
    expect(rules[1].absent).toEqual(["temporal_constraint"]);
    // Absence is a claim about the rule's decomposition, so it is only made
    // where there is one.
    expect(rules[1].unrecorded).toBe(false);
  });

  it("says only that it does not know for a rule carrying no decomposition", () => {
    const shape = policyLogicShape(
      card([
        {
          key: "p1",
          rules: [
            cardRule("a", { subject: "one", temporal_constraint: "on Fridays" }),
            cardRule("b", null),
          ],
        },
      ]),
    );

    const rules = shape.blocks.flatMap((block) => block.rules);
    expect(rules[1].unrecorded).toBe(true);
    // Not absence. A record we never decomposed states nothing about what the
    // document leaves out, and folding the two together would report a gap the
    // document may not have.
    expect(rules[1].absent).toEqual([]);
    expect(rules[1].shape).toBeNull();
    expect(shape.unrecorded).toBe(1);
  });
});

describe("the identifier a case supplies a value for", () => {
  it("is read from the record rather than derived again here", () => {
    const shape = policyLogicShape(
      card([
        {
          key: "p1",
          rules: [
            cardRule(
              "a",
              { subject: "an employee", threshold: "three days" },
              {
                attributes: {
                  applies: [
                    {
                      attribute: "subject",
                      text: "an employee",
                      fact: "employee",
                      data_type: null,
                    },
                  ],
                  outcome: [
                    {
                      attribute: "threshold",
                      text: "three days",
                      fact: "elapsed",
                      data_type: "duration",
                    },
                  ],
                },
              },
            ),
            cardRule("b", { subject: "a supplier" }),
          ],
        },
      ]),
    );

    const first = shape.blocks[0].rules[0];
    expect(first.stated).toEqual([
      {
        attribute: "subject",
        text: "an employee",
        fact: "employee",
        dataType: null,
      },
      {
        attribute: "threshold",
        text: "three days",
        fact: "elapsed",
        dataType: "duration",
      },
    ]);
  });

  it("is withheld where the record's own table names different words", () => {
    // Two readings of one rule that disagree is not something a view can
    // reconcile, and pairing a quotation with an identifier derived from
    // different words would assert a link neither reading makes.
    const shape = policyLogicShape(
      card([
        {
          key: "p1",
          rules: [
            cardRule(
              "a",
              { subject: "an employee" },
              {
                attributes: {
                  applies: [
                    {
                      attribute: "subject",
                      text: "a contractor",
                      fact: "contractor",
                      data_type: null,
                    },
                  ],
                },
              },
            ),
            cardRule("b", { subject: "a supplier" }),
          ],
        },
      ]),
    );

    expect(shape.blocks[0].rules[0].stated).toEqual([
      { attribute: "subject", text: "an employee", fact: null, dataType: null },
    ]);
  });
});

describe("the shape of a policy", () => {
  it("groups rules that state the same set of attributes", () => {
    const alike = (index: number) =>
      cardRule(`same-${index}`, {
        subject: `party ${index}`,
        predicate: "shall be",
      });
    const shape = policyLogicShape(
      card([
        {
          key: "p1",
          rules: [
            alike(1),
            alike(2),
            cardRule("odd", {
              subject: "party 3",
              predicate: "shall be",
              exception: "unless agreed otherwise",
            }),
            alike(3),
          ],
        },
      ]),
    );

    expect(shape.shapes).toHaveLength(2);
    expect(shape.shapes[0].attributes).toEqual(["subject"]);
    expect(shape.shapes[0].ruleOrdinals).toEqual([1, 2, 4]);
    expect(shape.shapes[1].attributes).toEqual(["subject", "exception"]);
    expect(shape.shapes[1].ruleOrdinals).toEqual([3]);
  });

  it("orders shapes by first appearance and not by how many rules fill them", () => {
    // Ordering by size would put the fullest arrangement first every time, which
    // ranks rules by completeness — and a rule its document states in words
    // would sit at the bottom of every policy in the system.
    const shape = policyLogicShape(
      card([
        {
          key: "p1",
          rules: [
            cardRule("first", { subject: "alone", exception: "save one" }),
            cardRule("second", { subject: "one of many" }),
            cardRule("third", { subject: "one of many" }),
            cardRule("fourth", { subject: "one of many" }),
          ],
        },
      ]),
    );

    expect(shape.shapes.map((group) => group.ruleOrdinals)).toEqual([
      [1],
      [2, 3, 4],
    ]);
  });

  it("gives every rule a mark for every attribute, in column order", () => {
    const shape = policyLogicShape(
      card([
        {
          key: "p1",
          rules: [
            cardRule("a", { subject: "one", exception: "save one" }),
            cardRule("b", { subject: "two" }),
            cardRule("c", null),
          ],
        },
      ]),
    );

    const attributes = shape.columns.map((column) => column.attribute);
    for (const rule of shape.blocks.flatMap((block) => block.rules)) {
      expect(rule.marks).toHaveLength(attributes.length);
    }
    const [first, second, third] = shape.blocks.flatMap((block) => block.rules);
    expect(first.marks).toEqual(["stated", "stated"]);
    expect(second.marks).toEqual(["stated", "absent"]);
    expect(third.marks).toEqual(["unrecorded", "unrecorded"]);
  });
});

describe("rules stay where the document put them", () => {
  it("keeps document order and groups by the passage that states them", () => {
    const shape = policyLogicShape(
      card([
        {
          key: "p1",
          rules: [
            cardRule("a", { subject: "one", exception: "save one" }),
            cardRule("b", { subject: "two" }),
          ],
        },
        { key: "p2", rules: [cardRule("c", { subject: "three" })] },
      ]),
    );

    expect(shape.blocks.map((block) => block.passageKey)).toEqual(["p1", "p2"]);
    expect(shape.blocks[0].rules.map((rule) => rule.ordinal)).toEqual([1, 2]);
    expect(shape.blocks[1].rules.map((rule) => rule.ordinal)).toEqual([3]);
  });

  it("keeps a passage that states rules in two runs as two runs", () => {
    const shape = policyLogicShape(
      card([
        { key: "p1", rules: [cardRule("a", { subject: "one", exception: "x" })] },
        { key: "p2", rules: [cardRule("b", { subject: "two" })] },
        { key: "p1", rules: [cardRule("c", { subject: "three" })] },
      ]),
    );

    expect(shape.blocks.map((block) => block.passageKey)).toEqual([
      "p1",
      "p2",
      "p1",
    ]);
  });
});
