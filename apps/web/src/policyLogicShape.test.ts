import { describe, expect, it } from "vitest";

import type { PolicyAttribute } from "./api";
import type {
  PolicyCard,
  PolicyCardPassage,
  PolicyCardRule,
} from "./policyCards";
import { policyLogicShape } from "./policyLogicShape";

/**
 * THE ARRANGEMENT CARRIES EVERY FACT THE RECORD HELD, AND ADDS NONE.
 *
 * The record decides what a rule states, which half of the rule states it, and
 * which identifier a case supplies a value for. This module decides only how
 * that is arranged so a policy's worth of it can be read. So every test here is
 * one of two questions: did the arrangement lose something the record held, or
 * did it invent something no record said.
 *
 * Fixtures are built at several sizes rather than one, because a view that is
 * right on two rules and wrong on eighty is wrong. No size below is special to
 * any document: the shapes are generated, and the only reason a large one
 * appears is that a policy that size exists and is the witness.
 */

/** A row exactly as the record serves it. */
function row(
  attribute: string,
  text: string,
  fact: string | null = null,
  dataType: string | null = null,
): PolicyAttribute {
  return { attribute, text, fact, data_type: dataType } as PolicyAttribute;
}

function cardRule(
  ruleId: string,
  table: { applies?: PolicyAttribute[]; outcome?: PolicyAttribute[] } | null,
  options: { route?: string; ruleType?: string; effect?: string } = {},
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
        effect: { type: options.effect ?? "require_action", action: "" },
        condition: { type: "all", all: [] },
        attributes:
          table === null
            ? undefined
            : { applies: table.applies ?? [], outcome: table.outcome ?? [] },
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

/** One passage holding rules, the ordinary case. */
function onePassage(rules: PolicyCardRule[]): PolicyCard {
  return card([{ key: "p1", rules }]);
}

function readings(shape: ReturnType<typeof policyLogicShape>) {
  return shape.blocks.flatMap((block) => block.rules);
}

describe("what each rule states survives the arrangement", () => {
  it("keeps every stated value under the attribute and the half it was recorded in", () => {
    const shape = policyLogicShape(
      onePassage([
        cardRule("a", {
          applies: [row("subject", "one")],
          outcome: [row("predicate", "shall be")],
        }),
        cardRule("b", {
          applies: [row("subject", "two"), row("condition", "each quarter")],
          outcome: [row("predicate", "shall be")],
        }),
      ]),
    );

    const rules = readings(shape);
    expect(rules).toHaveLength(2);
    expect(
      rules[0].branches.map((branch) => [
        branch.side,
        branch.rows.map((entry) => [entry.attribute, entry.text]),
      ]),
    ).toEqual([
      ["applies", [["subject", "one"]]],
      ["outcome", [["predicate", "shall be"]]],
    ]);
    expect(
      rules[1].branches[0].rows.map((entry) => [entry.attribute, entry.text]),
    ).toEqual([
      ["subject", "two"],
      ["condition", "each quarter"],
    ]);
  });

  it("puts an attribute only in the half the record put it in", () => {
    // Which half an attribute belongs to is a decision the record makes and
    // this module reads. Inferring it from the name would give one answer for
    // records that say otherwise, and no reviewer could tell which they were
    // looking at.
    const shape = policyLogicShape(
      onePassage([
        cardRule("a", { applies: [row("assigner", "the issuing body")] }),
        cardRule("b", { outcome: [row("assigner", "the issuing body")] }),
      ]),
    );

    const rules = readings(shape);
    expect(rules[0].branches[0].rows.map((entry) => entry.attribute)).toEqual([
      "assigner",
    ]);
    expect(rules[0].branches[1].rows).toEqual([]);
    expect(rules[1].branches[0].rows).toEqual([]);
    expect(rules[1].branches[1].rows.map((entry) => entry.attribute)).toEqual([
      "assigner",
    ]);
    // Counted once per half, because that is how many places the reviewer has
    // to look for it.
    expect(shape.columns.map((column) => [column.attribute, column.side])).toEqual(
      [
        ["assigner", "applies"],
        ["assigner", "outcome"],
      ],
    );
  });

  it("names what a half of a rule does not state instead of repeating it per attribute", () => {
    const shape = policyLogicShape(
      onePassage([
        cardRule("a", {
          applies: [row("subject", "one"), row("condition", "on Fridays")],
          outcome: [row("predicate", "apply")],
        }),
        cardRule("b", { applies: [row("subject", "two")] }),
      ]),
    );

    const rules = readings(shape);
    expect(rules[0].branches.map((branch) => branch.absent)).toEqual([[], []]);
    expect(rules[1].branches[0].absent).toEqual(["condition"]);
    expect(rules[1].branches[1].absent).toEqual(["predicate"]);
    // Absence is a claim about the rule's own table, so it is only made where
    // there is one.
    expect(rules[1].unrecorded).toBe(false);
  });

  it("says only that it does not know for a rule carrying no table", () => {
    const shape = policyLogicShape(
      onePassage([
        cardRule("a", {
          applies: [row("subject", "one"), row("condition", "on Fridays")],
        }),
        cardRule("b", null),
      ]),
    );

    const rules = readings(shape);
    expect(rules[1].unrecorded).toBe(true);
    // Not absence. A record we never decomposed states nothing about what the
    // document leaves out, and folding the two together would report a gap the
    // document may not have.
    expect(rules[1].branches.map((branch) => branch.absent)).toEqual([[], []]);
    expect(rules[1].shape).toBeNull();
    expect(shape.unrecorded).toBe(1);
  });

  it("keeps a rule that states one half and not the other", () => {
    const shape = policyLogicShape(
      onePassage([
        cardRule("a", { outcome: [row("predicate", "apply")] }),
        cardRule("b", {
          applies: [row("subject", "two")],
          outcome: [row("predicate", "apply")],
        }),
      ]),
    );

    const rules = readings(shape);
    // Both halves are drawn either way: "this rule attaches no conditions" is a
    // fact a reviewer checking completeness needs to be able to see.
    expect(rules[0].branches).toHaveLength(2);
    expect(rules[0].branches[0].rows).toEqual([]);
    expect(rules[0].branches[0].absent).toEqual(["subject"]);
  });
});

describe("the identifier a case supplies a value for", () => {
  it("is read from the record rather than derived again here", () => {
    const shape = policyLogicShape(
      onePassage([
        cardRule("a", {
          applies: [row("subject", "an employee", "employee")],
          outcome: [row("threshold", "three days", "elapsed", "duration")],
        }),
        cardRule("b", { applies: [row("subject", "a supplier")] }),
      ]),
    );

    expect(readings(shape)[0].stated).toEqual([
      {
        attribute: "subject",
        side: "applies",
        text: "an employee",
        fact: "employee",
        dataType: null,
      },
      {
        attribute: "threshold",
        side: "outcome",
        text: "three days",
        fact: "elapsed",
        dataType: "duration",
      },
    ]);
  });

  it("leaves the identifier empty where the record states none", () => {
    const shape = policyLogicShape(
      onePassage([
        cardRule("a", { applies: [row("subject", "an employee")] }),
        cardRule("b", { applies: [row("subject", "a supplier")] }),
      ]),
    );

    expect(readings(shape)[0].branches[0].rows[0].fact).toBeNull();
  });
});

describe("the order the attributes are counted in", () => {
  it("is recovered from the orders the records themselves state", () => {
    // No list of attribute names is kept anywhere in this system's view layer.
    // The records state precedences; sorting on them recovers the whole order,
    // including for a pair no single record states together.
    const shape = policyLogicShape(
      onePassage([
        cardRule("a", { applies: [row("alpha", "x"), row("beta", "y")] }),
        cardRule("b", { applies: [row("beta", "y"), row("gamma", "z")] }),
        cardRule("c", { applies: [row("gamma", "z"), row("delta", "w")] }),
      ]),
    );

    expect(shape.columns.map((column) => column.attribute)).toEqual([
      "alpha",
      "beta",
      "gamma",
      "delta",
    ]);
  });

  it("keeps every attribute when the records contradict each other", () => {
    // Two records that disagree about which comes first leave no order the
    // records support. Falling back to first appearance is still the document's
    // order and still stable; dropping the attribute would lose a fact.
    const shape = policyLogicShape(
      onePassage([
        cardRule("a", { applies: [row("alpha", "x"), row("beta", "y")] }),
        cardRule("b", { applies: [row("beta", "y"), row("alpha", "x")] }),
      ]),
    );

    expect(shape.columns.map((column) => column.attribute)).toEqual([
      "alpha",
      "beta",
    ]);
    for (const rule of readings(shape)) {
      expect(rule.marks).toEqual(["stated", "stated"]);
    }
  });

  it("counts every attribute any rule states, not only the ones they disagree on", () => {
    const shape = policyLogicShape(
      onePassage([
        cardRule("a", {
          applies: [row("subject", "same")],
          outcome: [row("predicate", "one")],
        }),
        cardRule("b", {
          applies: [row("subject", "same")],
          outcome: [row("predicate", "two")],
        }),
      ]),
    );

    expect(
      shape.columns.map((column) => [
        column.attribute,
        column.filled,
        column.uniform,
      ]),
    ).toEqual([
      ["subject", 2, true],
      ["predicate", 2, false],
    ]);
    // Reported as agreement, and still drawn in every rule, because a rule's
    // block is one record's table and not a diff against its neighbours.
    expect(shape.shared.map((fact) => [fact.attribute, fact.text])).toEqual([
      ["subject", "same"],
    ]);
    for (const rule of readings(shape)) {
      expect(rule.branches[0].rows.map((entry) => entry.attribute)).toEqual([
        "subject",
      ]);
    }
  });
});

describe("the heading each half wears", () => {
  it("takes the outcome's heading from the effect the record declares", () => {
    const shape = policyLogicShape(
      onePassage([
        cardRule("a", { outcome: [row("predicate", "be filed")] }, {
          effect: "require_action",
        }),
        cardRule("b", { outcome: [row("predicate", "be disclosed")] }, {
          effect: "deny",
        }),
        cardRule("c", { outcome: [row("predicate", "be granted")] }, {
          effect: "allow",
        }),
        cardRule("d", { outcome: [row("predicate", "mean")] }, {
          effect: "informational",
        }),
      ]),
    );

    expect(
      readings(shape).map((rule) => rule.branches.map((branch) => branch.heading)),
    ).toEqual([
      ["APPLIES", "REQUIRES"],
      ["APPLIES", "PROHIBITS"],
      ["APPLIES", "PERMITS"],
      ["APPLIES", "DEFINES"],
    ]);
  });

  it("names an effect this app has not seen rather than calling it nothing", () => {
    const shape = policyLogicShape(
      onePassage([
        cardRule("a", { outcome: [row("predicate", "be filed")] }, {
          effect: "some_new_effect",
        }),
      ]),
    );

    expect(readings(shape)[0].branches[1].heading).toBe("SOME NEW EFFECT");
  });
});

describe("the shape of a policy", () => {
  it("groups rules that state the same set of attributes", () => {
    const alike = (index: number) =>
      cardRule(`same-${index}`, {
        applies: [row("subject", `party ${index}`)],
        outcome: [row("predicate", "shall be")],
      });
    const shape = policyLogicShape(
      onePassage([
        alike(1),
        alike(2),
        cardRule("odd", {
          applies: [row("subject", "party 3")],
          outcome: [row("predicate", "shall be"), row("exception", "unless agreed")],
        }),
        alike(3),
      ]),
    );

    expect(shape.shapes).toHaveLength(2);
    expect(shape.shapes[0].attributes).toEqual(["subject", "predicate"]);
    expect(shape.shapes[0].ruleOrdinals).toEqual([1, 2, 4]);
    expect(shape.shapes[1].attributes).toEqual([
      "subject",
      "predicate",
      "exception",
    ]);
    expect(shape.shapes[1].ruleOrdinals).toEqual([3]);
  });

  it("tells apart two rules that state one attribute in different halves", () => {
    const shape = policyLogicShape(
      onePassage([
        cardRule("a", { applies: [row("assigner", "the body")] }),
        cardRule("b", { outcome: [row("assigner", "the body")] }),
      ]),
    );

    expect(shape.shapes).toHaveLength(2);
  });

  it("orders shapes by first appearance and not by how many rules fill them", () => {
    // Ordering by size would put the fullest arrangement first every time, which
    // ranks rules by completeness — and a rule its document states in words
    // would sit at the bottom of every policy in the system.
    const shape = policyLogicShape(
      onePassage([
        cardRule("first", {
          applies: [row("subject", "alone")],
          outcome: [row("exception", "save one")],
        }),
        cardRule("second", { applies: [row("subject", "one of many")] }),
        cardRule("third", { applies: [row("subject", "one of many")] }),
        cardRule("fourth", { applies: [row("subject", "one of many")] }),
      ]),
    );

    expect(shape.shapes.map((group) => group.ruleOrdinals)).toEqual([
      [1],
      [2, 3, 4],
    ]);
  });

  it("gives every rule a mark for every attribute, in column order", () => {
    const shape = policyLogicShape(
      onePassage([
        cardRule("a", {
          applies: [row("subject", "one")],
          outcome: [row("exception", "save one")],
        }),
        cardRule("b", { applies: [row("subject", "two")] }),
        cardRule("c", null),
      ]),
    );

    const attributes = shape.columns.map((column) => column.attribute);
    expect(attributes).toEqual(["subject", "exception"]);
    for (const rule of readings(shape)) {
      expect(rule.marks).toHaveLength(attributes.length);
    }
    const [first, second, third] = readings(shape);
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
            cardRule("a", {
              applies: [row("subject", "one")],
              outcome: [row("exception", "save one")],
            }),
            cardRule("b", { applies: [row("subject", "two")] }),
          ],
        },
        { key: "p2", rules: [cardRule("c", { applies: [row("subject", "three")] })] },
      ]),
    );

    expect(shape.blocks.map((block) => block.passageKey)).toEqual(["p1", "p2"]);
    expect(shape.blocks[0].rules.map((rule) => rule.ordinal)).toEqual([1, 2]);
    expect(shape.blocks[1].rules.map((rule) => rule.ordinal)).toEqual([3]);
  });

  it("keeps a passage that states rules in two runs as two runs", () => {
    const shape = policyLogicShape(
      card([
        {
          key: "p1",
          rules: [
            cardRule("a", {
              applies: [row("subject", "one")],
              outcome: [row("exception", "x")],
            }),
          ],
        },
        { key: "p2", rules: [cardRule("b", { applies: [row("subject", "two")] })] },
        { key: "p1", rules: [cardRule("c", { applies: [row("subject", "three")] })] },
      ]),
    );

    expect(shape.blocks.map((block) => block.passageKey)).toEqual([
      "p1",
      "p2",
      "p1",
    ]);
  });

  it("does not reorder rules by how much they state, at any size", () => {
    const rules = Array.from({ length: 84 }, (_, index) =>
      cardRule(`r${index}`, {
        applies: [row("subject", `party ${index}`)],
        // Only the last rule states the extra attribute; ranking by fullness
        // would move it, and a reviewer would lose the document's sequence.
        outcome:
          index === 83
            ? [row("predicate", "apply"), row("exception", "save one")]
            : [row("predicate", "apply")],
      }),
    );
    const shape = policyLogicShape(onePassage(rules));

    expect(readings(shape).map((rule) => rule.ruleId)).toEqual(
      rules.map((rule) => rule.rule_id),
    );
    expect(readings(shape).map((rule) => rule.ordinal)).toEqual(
      rules.map((_, index) => index + 1),
    );
  });
});
