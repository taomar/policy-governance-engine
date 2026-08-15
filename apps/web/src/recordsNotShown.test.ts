/**
 * A reviewer reading "15 more rules of this policy are outside the current
 * filter" had to ask what it meant. This is the test that the message now
 * answers the question it used to raise: what is out of view, and where.
 *
 * Nothing here is a phrase from any document. The kinds used are `rule_type`
 * values the schema already defines; the counts are invented for the test and
 * are not a measurement of any corpus.
 */
import { afterEach, describe, expect, it } from "vitest";
import {
  forgetRecordKinds,
  noteRecordKinds,
  notShownSentence,
  recordsNotShown,
  registerRecordDestinations,
  type PolicyLikeCard,
} from "./recordsNotShown";

function record(ruleId: string, kind: string) {
  return { rule_type: kind, rule: { rule_id: ruleId } };
}

function card(shownIds: string[], allIds: string[]): PolicyLikeCard {
  return {
    hiddenByFilter: allIds.length - shownIds.length,
    rules: shownIds.map((rule_id) => ({ rule_id })),
    policy: { passages: [{ rules: allIds.map((rule_id) => ({ rule_id })) }] },
  };
}

afterEach(() => {
  forgetRecordKinds();
});

describe("naming what a card is not showing", () => {
  it("says what kind the out-of-view records are", () => {
    noteRecordKinds([record("a", "obligation"), record("b", "definition"), record("c", "definition")]);

    const shown = recordsNotShown(card(["a"], ["a", "b", "c"]));

    expect(shown.count).toBe(2);
    expect(shown.groups).toEqual([{ kind: "definition", phrase: "definitions", count: 2 }]);
    expect(shown.unnamed).toBe(0);
    expect(notShownSentence(shown)).toBe(
      "2 more rules of this policy are definitions. A different filter on this page shows them.",
    );
  });

  it("states a mixture as a mixture rather than picking the majority", () => {
    // Saying "definitions" when three of them are not is the failure this
    // whole change exists to stop. A reviewer told the wrong kind goes to the
    // wrong place to find them.
    noteRecordKinds([
      record("a", "obligation"),
      record("b", "definition"),
      record("c", "definition"),
      record("d", "prohibition"),
    ]);

    const sentence = notShownSentence(recordsNotShown(card(["a"], ["a", "b", "c", "d"])));

    expect(sentence).toBe(
      "3 more rules of this policy are 2 definitions and 1 prohibition. " +
        "A different filter on this page shows them.",
    );
  });

  it("counts records whose kind it never loaded apart from the kinds it did", () => {
    // A kind nobody has seen is not a kind of zero, and it is not a definition
    // either. The reviewer is told the difference.
    noteRecordKinds([record("a", "obligation"), record("b", "definition")]);

    const shown = recordsNotShown(card(["a"], ["a", "b", "c", "d"]));

    expect(shown.groups).toEqual([{ kind: "definition", phrase: "definition", count: 1 }]);
    expect(shown.unnamed).toBe(2);
    expect(notShownSentence(shown)).toBe(
      "3 more rules of this policy are 1 definition and 2 whose kind this view has not loaded. " +
        "A different filter on this page shows them.",
    );
  });

  it("still says how many when it can name none of them", () => {
    // The count and the consequence are the load-bearing parts and survive
    // knowing nothing else.
    const sentence = notShownSentence(recordsNotShown(card(["a"], ["a", "b", "c"])));

    expect(sentence).toBe("2 more rules of this policy are not shown by the current filters.");
  });

  it("says nothing at all when the card shows the whole policy", () => {
    expect(notShownSentence(recordsNotShown(card(["a", "b"], ["a", "b"])))).toBe("");
  });

  it("reads one record as one record", () => {
    noteRecordKinds([record("a", "obligation"), record("b", "definition")]);

    expect(notShownSentence(recordsNotShown(card(["a"], ["a", "b"])))).toBe(
      "1 more rule of this policy is a definition. A different filter on this page shows them.",
    );
  });
});

describe("saying where the out-of-view records are", () => {
  it("names the filter that holds them, by the name on screen", () => {
    noteRecordKinds([record("a", "obligation"), record("b", "definition")]);
    registerRecordDestinations([
      { label: "Policies & Rules (265)", holds: (kind) => kind !== "definition", isCurrent: true },
      { label: "Definitions & Glossary (14)", holds: (kind) => kind === "definition" },
    ]);

    expect(notShownSentence(recordsNotShown(card(["a"], ["a", "b"])))).toBe(
      "1 more rule of this policy is a definition. Read them under Definitions & Glossary (14).",
    );
  });

  it("never sends the reviewer to the filter they are already on", () => {
    noteRecordKinds([record("a", "obligation"), record("b", "obligation")]);
    registerRecordDestinations([
      { label: "Policies & Rules (265)", holds: () => true, isCurrent: true },
    ]);

    expect(recordsNotShown(card(["a"], ["a", "b"])).destinations).toEqual([]);
  });

  it("takes as many filters as a surface offers, and assumes no number of them", () => {
    // Today there are two tabs. The mechanism must not be why there cannot be
    // a third, for the same reason the language toggle must not assume two
    // languages.
    noteRecordKinds([
      record("a", "obligation"),
      record("b", "definition"),
      record("c", "retention"),
    ]);
    registerRecordDestinations([
      { label: "First (1)", holds: (kind) => kind === "obligation", isCurrent: true },
      { label: "Second (2)", holds: (kind) => kind === "definition" },
      { label: "Third (3)", holds: (kind) => kind === "retention" },
    ]);

    const shown = recordsNotShown(card(["a"], ["a", "b", "c"]));

    expect(shown.destinations.map((one) => one.label)).toEqual(["Second (2)", "Third (3)"]);
    expect(notShownSentence(shown)).toBe(
      "2 more rules of this policy are 1 definition and 1 retention. " +
        "Read them under Second (2) and Third (3).",
    );
  });

  it("names no destination for a kind no registered filter holds", () => {
    noteRecordKinds([record("a", "obligation"), record("b", "definition")]);
    registerRecordDestinations([
      { label: "First (1)", holds: (kind) => kind === "obligation", isCurrent: true },
      { label: "Second (2)", holds: (kind) => kind === "retention" },
    ]);

    expect(recordsNotShown(card(["a"], ["a", "b"])).destinations).toEqual([]);
  });

  it("forgets a surface's filters when that surface says what it is offering now", () => {
    noteRecordKinds([record("a", "obligation"), record("b", "definition")]);
    registerRecordDestinations([{ label: "Stale (9)", holds: () => true }]);
    registerRecordDestinations([{ label: "Current (2)", holds: (kind) => kind === "definition" }]);

    expect(recordsNotShown(card(["a"], ["a", "b"])).destinations.map((one) => one.label)).toEqual([
      "Current (2)",
    ]);
  });
});

describe("the count on the card and the count in the sentence", () => {
  it("uses the card's own number, so the header and the sentence cannot disagree", () => {
    // The assembly here accounts for one out-of-view record; the card says two.
    // The card governs, and the record the assembly cannot account for is
    // carried as unnamed rather than dropped.
    noteRecordKinds([record("a", "obligation"), record("b", "definition")]);
    const drifted: PolicyLikeCard = {
      hiddenByFilter: 2,
      rules: [{ rule_id: "a" }],
      policy: { passages: [{ rules: [{ rule_id: "a" }, { rule_id: "b" }] }] },
    };

    const shown = recordsNotShown(drifted);

    expect(shown.count).toBe(2);
    expect(shown.unnamed).toBe(1);
  });

  it("survives a policy that carries no passages at all", () => {
    const bare: PolicyLikeCard = { hiddenByFilter: 3, rules: [], policy: {} };

    expect(notShownSentence(recordsNotShown(bare))).toBe(
      "3 more rules of this policy are not shown by the current filters.",
    );
  });
});
