import { describe, expect, it } from "vitest";

import type { CanonicalPolicyRule } from "./api";
import type {
  PolicyCard,
  PolicyCardPassage,
  PolicyCardRule,
} from "./policyCards";
import { policyLogic } from "./policyLogic";

/**
 * THE COMPARISON SHOWS WHAT THE RULES SAY, ARRANGED — AND NOTHING ELSE.
 *
 * The Logic tab exists so a reviewer can see, at a glance across twenty rules,
 * that one names a time and nineteen do not. Every test here is about the two
 * ways that can go wrong: the table saying something no rule said, and the table
 * losing something a rule did say.
 *
 * Fill rates in the fixtures follow the live corpus, where they are uneven by an
 * order of magnitude — `predicate` on 100% of 692 rules, `exception` on 1%.
 */

function core(parts: Partial<CanonicalPolicyRule>): CanonicalPolicyRule {
  return parts as CanonicalPolicyRule;
}

function cardRule(
  ruleId: string,
  parts: Partial<CanonicalPolicyRule> | null,
  overrides: {
    ruleType?: string;
    effectType?: string;
    route?: string;
    reviewStatus?: string;
  } = {},
): PolicyCardRule {
  return {
    rule_id: ruleId,
    evaluation_mode: overrides.route ?? "ai_ready",
    candidate: {
      id: `record-${ruleId}`,
      review_status: overrides.reviewStatus ?? "candidate",
      rule: {
        rule_id: ruleId,
        rule_type: overrides.ruleType ?? "obligation",
        effect: { type: overrides.effectType ?? "require_action", action: "" },
        condition: { type: "all", all: [] },
        formulation:
          parts === null ? undefined : { canonical: { rule: core(parts) } },
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

describe("which attributes become columns", () => {
  it("draws a column for a slot one rule states and nineteen do not", () => {
    // The owner's case exactly: on the live manpower policy `temporal_constraint`
    // is filled by 1 rule of 20. It is the most informative cell on the card and
    // it is invisible while the rules are read as paragraphs.
    const rules = Array.from({ length: 20 }, (_, index) =>
      cardRule(`r${index}`, {
        subject: `subject ${index}`,
        predicate: "shall be",
        ...(index === 7
          ? { temporal_constraint: "on a calendar year basis" }
          : {}),
      }),
    );
    const logic = policyLogic(card([{ key: "p1", rules }]));

    const time = logic.columns.find(
      (column) => column.attribute === "temporal_constraint",
    );
    expect(time).toBeDefined();
    expect(time!.filled).toBe(1);
    expect(logic.total).toBe(20);
    expect(logic.rows[7].cells[logic.columns.indexOf(time!)]).toEqual({
      state: "stated",
      text: "on a calendar year basis",
    });
  });

  it("omits a slot no rule states rather than drawing a column of blanks", () => {
    const rules = [
      cardRule("a", { subject: "The employee", predicate: "must attend" }),
      cardRule("b", { subject: "The manager", predicate: "must approve" }),
    ];
    const logic = policyLogic(card([{ key: "p1", rules }]));
    expect(logic.columns.map((column) => column.attribute)).toEqual([
      "subject",
      "predicate",
    ]);
    expect(
      logic.columns.some((column) => column.attribute === "currency"),
    ).toBe(false);
  });

  it("gives a one-rule policy its attributes as facts, not as a one-row table", () => {
    // With one rule there is nothing to compare, so every slot it fills is
    // trivially shared and the view degrades to a plain list of what that rule
    // says. Most policies in the corpus are small; a table of one row with
    // sixteen columns would be a comparison with nothing on the other side.
    const logic = policyLogic(
      card([
        {
          key: "p1",
          rules: [
            cardRule("a", {
              subject: "The employee",
              predicate: "must attend",
            }),
          ],
        },
      ]),
    );
    expect(logic.columns).toEqual([]);
    expect(logic.shared.map((fact) => fact.value)).toEqual([
      "The employee",
      "must attend",
    ]);
    expect(logic.rows).toHaveLength(1);
  });

  it("states a slot every rule fills identically once, instead of down a column", () => {
    // Twenty cells carrying one value is the "three identical badge pairs
    // stacked" defect in a wider format. The value is not dropped; it moves.
    const rules = [
      cardRule("a", { subject: "GMU", predicate: "recruits" }),
      cardRule("b", { subject: "GMU", predicate: "reviews" }),
    ];
    const logic = policyLogic(card([{ key: "p1", rules }]));

    expect(logic.columns.map((column) => column.attribute)).toEqual([
      "predicate",
    ]);
    expect(logic.shared).toEqual([
      { label: "Subject", attribute: "subject", value: "GMU" },
    ]);
  });

  it("keeps the column order fixed regardless of how many rules fill each slot", () => {
    // A column that moves between policies cannot be scanned down a queue. The
    // count in the header is what makes a rare slot stand out, not its position.
    const rules = [
      cardRule("a", { condition: "if the post is new", subject: "s1" }),
      cardRule("b", { subject: "s2" }),
      cardRule("c", { subject: "s3", condition: "if a vacancy arises" }),
    ];
    const logic = policyLogic(card([{ key: "p1", rules }]));
    expect(logic.columns.map((column) => column.attribute)).toEqual([
      "subject",
      "condition",
    ]);
  });
});

describe("absence is not emptiness", () => {
  it("distinguishes a rule that states no condition from one we did not record", () => {
    const rules = [
      cardRule("stated", { subject: "s", condition: "if the post is new" }),
      cardRule("silent", { subject: "s" }),
      cardRule("norecord", null),
    ];
    const logic = policyLogic(card([{ key: "p1", rules }]));
    const condition = logic.columns.findIndex(
      (column) => column.attribute === "condition",
    );

    expect(logic.rows[0].cells[condition]).toEqual({
      state: "stated",
      text: "if the post is new",
    });
    expect(logic.rows[1].cells[condition]).toEqual({ state: "absent" });
    expect(logic.rows[2].cells[condition]).toEqual({ state: "unrecorded" });
    expect(logic.unrecorded).toBe(1);
  });

  it("counts only stated values towards a column's coverage", () => {
    const rules = [
      cardRule("a", { subject: "s", condition: "when hired" }),
      cardRule("b", { subject: "s" }),
      cardRule("c", null),
    ];
    const logic = policyLogic(card([{ key: "p1", rules }]));
    const condition = logic.columns.find(
      (column) => column.attribute === "condition",
    );
    // Two rules say nothing here for two different reasons, and neither is a
    // rule that stated a condition.
    expect(condition!.filled).toBe(1);
  });
});

describe("nothing is aggregated that no rule states", () => {
  it("reports every rule as its own row and never merges two", () => {
    const rules = Array.from({ length: 14 }, (_, index) =>
      cardRule(`r${index}`, {
        subject: "The employee",
        predicate: `does ${index}`,
      }),
    );
    const logic = policyLogic(card([{ key: "p1", rules }]));
    expect(logic.rows).toHaveLength(14);
    expect(new Set(logic.rows.map((row) => row.ruleId)).size).toBe(14);
  });

  it("compares the largest policy in the database without dropping a rule", () => {
    // 72 rules across 50 passages on `Table of Violations and Penalties`. A
    // table built for five would meet this data and quietly show a page of it.
    const rules = Array.from({ length: 72 }, (_, index) =>
      cardRule(`r${index}`, {
        subject: `violation ${index}`,
        predicate: "results in",
        object: `penalty ${index}`,
        ...(index % 9 === 0 ? { threshold: "1st Time" } : {}),
      }),
    );
    const blocks = Array.from({ length: 50 }, (_, index) => ({
      key: `p21-E${index}`,
      rules: rules.slice(index === 49 ? 49 : index, index === 49 ? 72 : index + 1),
    }));
    const logic = policyLogic(card(blocks));

    expect(logic.rows).toHaveLength(72);
    expect(logic.total).toBe(72);
    expect(logic.rows[71].ordinal).toBe(72);
    expect(logic.columns.find((column) => column.attribute === "threshold")?.filled).toBe(8);
  });

  it("carries the document's words through unchanged", () => {    const words =
      "Employees should pay half of the cost of moving their sponsorship to AIS.";
    const logic = policyLogic(
      card([
        {
          key: "p1",
          rules: [cardRule("a", { subject: words, predicate: "p" })],
        },
      ]),
    );
    expect(
      logic.shared.find((fact) => fact.attribute === "subject")?.value,
    ).toBe(words);
  });
});

describe("the passage boundary survives the comparison", () => {
  it("records which passage states each rule, and numbers rules across the card", () => {
    const logic = policyLogic(
      card([
        { key: "p9-E000074", rules: [cardRule("a", { subject: "s1" })] },
        {
          key: "p9-E000075",
          rules: [
            cardRule("b", { subject: "s2" }),
            cardRule("c", { subject: "s3" }),
          ],
        },
      ]),
    );
    expect(logic.rows.map((row) => row.passageKey)).toEqual([
      "p9-E000074",
      "p9-E000075",
      "p9-E000075",
    ]);
    // Continuous across the card, so "rule 3" means the same thing here as on
    // the card and in the detail panel.
    expect(logic.rows.map((row) => row.ordinal)).toEqual([1, 2, 3]);
  });
});

describe("route, kind and effect follow the card's rule", () => {
  it("leaves them off the rows when every rule agrees", () => {
    const rules = [
      cardRule("a", { subject: "s1" }),
      cardRule("b", { subject: "s2" }),
    ];
    const logic = policyLogic(card([{ key: "p1", rules }]));
    expect(logic.rows.every((row) => row.route === null)).toBe(true);
    expect(logic.rows.every((row) => row.ruleType === null)).toBe(true);
  });

  it("shows each rule's own route when the policy holds both", () => {
    // A policy holding one rule the engine compares and one the source states in
    // words is the ordinary shape of a real document. Both are reported; neither
    // is ranked.
    const rules = [
      cardRule("a", { subject: "s1" }, { route: "deterministic" }),
      cardRule("b", { subject: "s2" }, { route: "ai_ready" }),
    ];
    const logic = policyLogic(card([{ key: "p1", rules }]));
    expect(logic.rows.map((row) => row.route)).toEqual([
      "deterministic",
      "ai_ready",
    ]);
  });

  it("orders rows by the document and never by how much a rule filled in", () => {
    // A table sorted by fill count is a completeness score under another name,
    // and a rule stated in words would sink to the bottom of every one of them.
    const rules = [
      cardRule("sparse", { subject: "s" }),
      cardRule("dense", {
        subject: "s",
        condition: "c",
        constraint: "k",
        deadline: "d",
        location: "l",
      }),
    ];
    const logic = policyLogic(card([{ key: "p1", rules }]));
    expect(logic.rows.map((row) => row.ruleId)).toEqual(["sparse", "dense"]);
  });
});
