import { describe, expect, it } from "vitest";

import type { CanonicalRule } from "./api";
import { containsPhrase, findSpan, readPassage } from "./policyReading";

/**
 * THE CARD SAYS EACH THING ONCE, AND NEVER SAYS LESS THAN THE RECORD HOLDS.
 *
 * The reduction this file guards is the one the owner asked for: a single-rule
 * policy printed its sentence three times — quoted, restated, and split across
 * `WHEN … → THEN …` — and a reviewer learned nothing on the second or third
 * reading.
 *
 * Every case below is drawn from a real record on `AIS Employee Handbook` or
 * `GMU Staff Handbook 2024`, because the reductions are only safe at the rates
 * the corpus actually shows: the outcome sits inside the statement for 86% and
 * 91% of their rules, and two fifths of statements are an exact run of their
 * own passage.
 *
 * THE FLOOR, WHICH MATTERS MORE THAN THE REDUCTION
 *
 * Withholding is only ever allowed when the identical words are on screen
 * already, marked, in the quotation directly above the row. So the tests here
 * come in pairs: one that the row stops repeating, and one that the words are
 * still somewhere a reviewer reads without clicking.
 */

function rule(overrides: Partial<CanonicalRule> & { title: string }): CanonicalRule {
  return {
    title: overrides.title,
    description: overrides.description ?? "",
    rule_type: "obligation",
    effect: { type: "require_action", action: "", ...(overrides.effect ?? {}) },
    condition: { type: "all", all: [] },
    formulation: overrides.formulation,
    evidence: [],
  } as unknown as CanonicalRule;
}

/** A rule as the extraction produces one: a decomposition, no compiled tree. */
function stated(title: string, action: string, parts: Record<string, string> = {}) {
  return rule({
    title,
    effect: { type: "require_action", action },
    formulation: { canonical: { rule: { subject: "", ...parts } } },
  } as never);
}

describe("finding the document's own run", () => {
  it("locates a statement inside the sentence it was read from", () => {
    const passage =
      "In order to process your Iqama, you will be needed to take a medical test.";
    const span = findSpan(passage, "you will be needed to take a medical test");
    expect(span).not.toBeNull();
    expect(passage.slice(span!.start, span!.end)).toBe(
      "you will be needed to take a medical test",
    );
  });

  it("tolerates the line breaks a passage keeps and a title does not", () => {
    // A passage carries the wrapping of the page it came off. Four AIS
    // statements match their passage on words and not on characters, and they
    // are the same words.
    const passage = "contracts will normally\n  begin at the beginning of the academic year.";
    const span = findSpan(passage, "contracts will normally begin");
    expect(span).not.toBeNull();
    expect(passage.slice(span!.start, span!.end)).toBe("contracts will normally\n  begin");
  });

  it("refuses a paraphrase", () => {
    // The mark asserts "these are the document's words for this rule". A
    // near-match must not wear it, because that is the one claim this screen
    // cannot make falsely.
    expect(
      findSpan(
        "Employees should pay half of the cost of moving their sponsorship to AIS.",
        "Employees must pay 50% of sponsorship transfer costs",
      ),
    ).toBeNull();
  });

  it("refuses a fragment too short to be anyone's statement", () => {
    expect(findSpan("AIS pays the fee. AIS keeps the receipt.", "AIS")).toBeNull();
  });

  it("matches whole words only", () => {
    expect(containsPhrase("a testimony was given", "test")).toBe(false);
    expect(containsPhrase("you will take a medical test", "take a medical test")).toBe(true);
  });
});

describe("what the rule row still has to say", () => {
  it("drops the outcome when the statement already contains it", () => {
    const { rules } = readPassage(
      ["In order to process your Iqama, you will be needed to take a medical test."],
      [
        stated("you will be needed to take a medical test", "take a medical test", {
          condition: "In order to process your Iqama",
        }),
      ],
      1,
    );
    expect(rules[0].outcome).toBeNull();
    expect(rules[0].condition).toBe("In order to process your Iqama");
  });

  it("keeps the outcome when it says something the statement does not", () => {
    const { rules } = readPassage(
      ["The Human Resources Department will provide you with a contract copy."],
      [stated("the Human Resources Department is responsible", "provide a contract copy")],
      1,
    );
    expect(rules[0].outcome).toBe("provide a contract copy");
  });

  it("reports an unnarrowed rule as unconditional rather than as the word Always", () => {
    // 84 AIS rules and 174 GMU rules narrow nothing. `WHEN Always` is a slot
    // filled with the absence of a value; the surface phrases the absence.
    const { rules } = readPassage(
      ["Employees should pay half of the cost of moving their sponsorship to AIS."],
      [
        stated(
          "Employees should pay half of the cost of moving their sponsorship to AIS",
          "pay half of the cost of moving their sponsorship to AIS",
        ),
      ],
      1,
    );
    expect(rules[0].condition).toBeNull();
  });
});

describe("a statement is withheld only when the same words are marked above it", () => {
  const passage = "Employees should pay half of the cost of moving their sponsorship to AIS.";
  const statement = "Employees should pay half of the cost of moving their sponsorship to AIS";

  it("withholds a statement that is the quotation word for word", () => {
    const reading = readPassage([passage], [stated(statement, "pay half of the cost")], 1);
    expect(reading.rules[0].statementIsMarkedWhole).toBe(true);
    // FLOOR. The words are on screen: the quotation is rendered whole and the
    // run that became this rule is marked inside it.
    const [mark] = reading.quotations[0].marks;
    expect(passage.slice(mark.start, mark.end)).toBe(statement);
    expect(mark.ordinal).toBe(1);
    // And the statement is still carried, so nothing downstream has to recover
    // it from an offset.
    expect(reading.rules[0].statement).toBe(statement);
  });

  it("prints a statement that is one obligation out of a longer sentence", () => {
    // `You will receive a bilingual employment contract` is an exact run of its
    // passage and less than half of it. Marked, but printed: a reviewer would
    // otherwise have to work out which part of the sentence rule 1 is.
    const long =
      "You will receive a bilingual employment contract once you have joined, " +
      "which explains the terms and conditions of your job relationship.";
    const reading = readPassage(
      [long],
      [stated("You will receive a bilingual employment contract", "receive a contract")],
      1,
    );
    expect(reading.rules[0].markedIn).toBe(0);
    expect(reading.rules[0].statementIsMarkedWhole).toBe(false);
  });

  it("prints a statement the passage does not contain", () => {
    const reading = readPassage(
      ["Employees should pay half of the cost of moving their sponsorship to AIS."],
      [stated("Employees pay 50% of the sponsorship transfer", "pay 50%")],
      1,
    );
    expect(reading.rules[0].markedIn).toBeNull();
    expect(reading.rules[0].statementIsMarkedWhole).toBe(false);
  });
});

describe("marks stay honest when rules share a sentence", () => {
  it("marks each rule's own run", () => {
    const passage =
      "Contracts will normally begin at the beginning of the academic year. " +
      "If an employee begins work on a different date, a temporary contract will be issued.";
    const { quotations } = readPassage(
      [passage],
      [
        stated("Contracts will normally begin", "begin"),
        stated("a temporary contract will be issued", "be issued"),
      ],
      3,
    );
    expect(quotations[0].marks.map((m) => m.ordinal)).toEqual([3, 4]);
    expect(quotations[0].marks.map((m) => passage.slice(m.start, m.end))).toEqual([
      "Contracts will normally begin",
      "a temporary contract will be issued",
    ]);
  });

  it("gives an overlapping run to one rule only, and prints the other", () => {
    // Two rules cannot both own the same words. The second keeps its statement
    // in its row, which is where it would have been anyway.
    const passage = "Alcohol and drugs are strictly forbidden on the premises.";
    const reading = readPassage(
      [passage],
      [
        stated("Alcohol and drugs are strictly forbidden", "be forbidden"),
        stated("drugs are strictly forbidden on the premises", "be forbidden"),
      ],
      1,
    );
    expect(reading.quotations[0].marks).toHaveLength(1);
    expect(reading.rules[1].markedIn).toBeNull();
    expect(reading.rules[1].statementIsMarkedWhole).toBe(false);
  });

  it("numbers rules from where the passage starts in the card", () => {
    const reading = readPassage(["Anything at all, stated plainly here."], [stated("x", "y")], 9);
    expect(reading.rules[0].ordinal).toBe(9);
  });
});

describe("the marks reconstruct the passage exactly", () => {
  it("partitions the text, losing and adding nothing", () => {
    const passage =
      "Contracts will normally begin at the beginning of the academic year. " +
      "If an employee begins work on a different date, a temporary contract will be issued.";
    const { quotations } = readPassage(
      [passage],
      [
        stated("Contracts will normally begin", "begin"),
        stated("a temporary contract will be issued", "be issued"),
      ],
      1,
    );
    const marks = quotations[0].marks;
    let rebuilt = "";
    let cursor = 0;
    for (const mark of marks) {
      rebuilt += passage.slice(cursor, mark.start) + passage.slice(mark.start, mark.end);
      cursor = mark.end;
    }
    rebuilt += passage.slice(cursor);
    expect(rebuilt).toBe(passage);
    // Ordered and disjoint, which is what makes the rebuild above possible.
    for (let i = 1; i < marks.length; i += 1) {
      expect(marks[i].start).toBeGreaterThanOrEqual(marks[i - 1].end);
    }
  });
});
