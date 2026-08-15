/**
 * What sorts a policy's rules, tested without a screen.
 *
 * The question is only ever "does this record constrain anyone". It is answered
 * by reading the effect the extractor recorded and nothing else — no word of the
 * rule's text is examined here, and none may be, because any test that reads the
 * words needs a vocabulary and a vocabulary belongs to one domain and one
 * language.
 *
 * Nothing in this file is a phrase from any document, and no count in it is a
 * measurement of one.
 */
import { describe, expect, it } from "vitest";
import {
  STANCE_ORDER,
  composeFocus,
  compositionPhrase,
  groupByStance,
  recordStance,
  stanceComposition,
  stanceHeading,
  stanceOfMany,
} from "./recordStance";

type EffectBearing = { effect?: { type?: string | null } | null };

const withEffect = (type: unknown): EffectBearing =>
  ({ effect: { type } }) as EffectBearing;

describe("what a record does", () => {
  it("calls the one effect that constrains nobody a supplier of meaning", () => {
    expect(recordStance(withEffect("informational"))).toBe("supplies-meaning");
  });

  it("calls every effect that binds someone a decider", () => {
    for (const type of ["require_action", "deny", "allow"]) {
      expect(recordStance(withEffect(type))).toBe("decides");
    }
  });

  it("calls an effect kind it has never met a decider, so it surfaces where it is read", () => {
    // Stated as "informational is context, anything else constrains" rather than
    // as a list of the kinds that constrain. A fifth kind added to the schema
    // must land among the rules a reviewer reads, not in the group they may
    // reasonably skim.
    expect(recordStance(withEffect("a_kind_added_after_this_test_was_written"))).toBe("decides");
  });

  it("does not answer at all when the record carries no effect to read", () => {
    // The fourth state. Folding it into either side would file a record the app
    // knows nothing about under a heading that claims to know something.
    expect(recordStance({})).toBe("unstated");
    expect(recordStance({ effect: null })).toBe("unstated");
    expect(recordStance(withEffect(null))).toBe("unstated");
    expect(recordStance(withEffect(""))).toBe("unstated");
    expect(recordStance(withEffect(7))).toBe("unstated");
    expect(recordStance(null)).toBe("unstated");
    expect(recordStance(undefined)).toBe("unstated");
  });

  it("reads the effect and never the rule's words", () => {
    // Two records whose text differs in every way but whose effect is the same
    // are the same to this function. If that ever stops being true, something
    // has started reading meaning out of language.
    const a = { effect: { type: "deny" }, title: "one wording", description: "one wording" };
    const b = { effect: { type: "deny" }, title: "\u0646\u0635 \u0622\u062e\u0631", description: "\u0646\u0635 \u0622\u062e\u0631" };
    expect(recordStance(a)).toBe(recordStance(b));
  });
});

describe("grouping records by what they do", () => {
  const stanceOf = (item: EffectBearing) => recordStance(item);

  it("puts what binds someone first, and the open question last", () => {
    const groups = groupByStance(
      [{}, withEffect("informational"), withEffect("deny")],
      stanceOf,
    );
    expect(groups.map((group) => group.stance)).toEqual([
      "decides",
      "supplies-meaning",
      "unstated",
    ]);
  });

  it("keeps the order records arrived in, inside each group", () => {
    // The incoming order is the document's, and it is the only record on a card
    // of where the source states each rule. Grouping re-orders across stances
    // and never within one.
    const items = [
      { id: "a", effect: { type: "deny" } },
      { id: "b", effect: { type: "informational" } },
      { id: "c", effect: { type: "allow" } },
      { id: "d", effect: { type: "informational" } },
      { id: "e", effect: { type: "require_action" } },
    ];
    const groups = groupByStance(items, stanceOf);
    expect(groups[0].items.map((item) => item.id)).toEqual(["a", "c", "e"]);
    expect(groups[1].items.map((item) => item.id)).toEqual(["b", "d"]);
  });

  it("loses nothing and duplicates nothing", () => {
    const items = Array.from({ length: 40 }, (_, index) => ({
      id: `r${index}`,
      effect: { type: ["deny", "informational", "allow"][index % 3] },
    }));
    const grouped = groupByStance(items, stanceOf).flatMap((group) => group.items);
    expect(grouped).toHaveLength(items.length);
    expect(new Set(grouped.map((item) => item.id)).size).toBe(items.length);
  });

  it("leaves an empty group out rather than showing it as a count of zero", () => {
    const groups = groupByStance([withEffect("deny"), withEffect("allow")], stanceOf);
    expect(groups).toHaveLength(1);
    expect(groups[0].stance).toBe("decides");
  });

  it("has nothing to group when there are no records", () => {
    expect(groupByStance([], stanceOf)).toEqual([]);
  });
});

describe("the stance of several records read together", () => {
  it("says mixed rather than picking the majority", () => {
    // A passage that both defines a term and states a rule is not a definitions
    // passage with an exception. Reporting its majority would file it under a
    // kind it only mostly holds.
    expect(stanceOfMany(["supplies-meaning", "supplies-meaning", "decides"])).toBe("mixed");
  });

  it("answers plainly when they agree", () => {
    expect(stanceOfMany(["decides", "decides"])).toBe("decides");
    expect(stanceOfMany(["unstated"])).toBe("unstated");
  });

  it("has no answer about nothing", () => {
    expect(stanceOfMany([])).toBeNull();
  });
});

describe("how a group is introduced", () => {
  it("names every stance, so a new one cannot render as an empty heading", () => {
    for (const stance of STANCE_ORDER) {
      for (const count of [1, 2, 17]) {
        expect(stanceHeading(stance, count).trim().length).toBeGreaterThan(0);
      }
    }
  });

  it("agrees with itself on number", () => {
    for (const stance of STANCE_ORDER) {
      expect(stanceHeading(stance, 1)).not.toBe(stanceHeading(stance, 2));
    }
  });

  it("says what the records do, never how much they are worth", () => {
    // Adjacent to the route-not-fault rule and not covered by it. A definition
    // is a record like any other: a wrong one is a real defect and needs the
    // same review as a wrong prohibition. No heading may suggest otherwise, and
    // no heading may rank one group against another.
    const RANKING =
      /\b(only|just|merely|minor|lesser|less important|unimportant|incidental|trivial|ignorab\w*|safely|skip\w*|optional|non-?essential|supplement\w*|extra|leftover|remaining|other|misc\w*|rest)\b/i;
    for (const stance of STANCE_ORDER) {
      for (const count of [1, 4]) {
        expect(stanceHeading(stance, count)).not.toMatch(RANKING);
      }
    }
  });

  it("says nothing about how a rule is decided", () => {
    // The other axis. A rule read by a judge is not thereby a rule that supplies
    // meaning, and no heading may blur the two.
    for (const stance of STANCE_ORDER) {
      expect(stanceHeading(stance, 3)).not.toMatch(/\b(ai|deterministic|ai.?ready|automat\w*|manual)\b/i);
    }
  });
});

describe("what a policy is made of", () => {
  it("counts every record exactly once, whatever effect it carries", () => {
    // The load-bearing property. A reviewer reads the parts against the head
    // count, so parts that do not sum are worse than no parts at all: they look
    // checkable and are not. Includes an effect this app has never met and a
    // record with no effect at all, because a shape with a fixed number of slots
    // has to put those somewhere, and wherever it puts them the sum still adds
    // up — which is exactly what makes that error invisible.
    const records = [
      withEffect("require_action"),
      withEffect("deny"),
      withEffect("informational"),
      withEffect("informational"),
      withEffect("an_effect_kind_from_a_later_schema"),
      {},
      withEffect(null),
    ];

    const tally = stanceComposition(records, recordStance);
    const counted = tally.reduce((total, entry) => total + entry.count, 0);

    expect(counted).toBe(records.length);
    // And no stance is counted twice, which is the other way a sum can be right
    // while the parts are wrong.
    expect(new Set(tally.map((entry) => entry.stance)).size).toBe(tally.length);
  });

  it("reports a record with no effect apart, rather than as a kind it is not", () => {
    const tally = stanceComposition([withEffect("deny"), {}], recordStance);

    expect(tally).toEqual([
      { stance: "decides", count: 1 },
      { stance: "unstated", count: 1 },
    ]);
  });

  it("leaves out a stance no record takes, rather than printing a zero", () => {
    const tally = stanceComposition([withEffect("deny"), withEffect("allow")], recordStance);

    expect(tally).toEqual([{ stance: "decides", count: 2 }]);
  });

  it("reads the stances in the order they are shown in", () => {
    // The phrase and the groups below it must agree, or the reviewer has to
    // work out that "3 decide cases" refers to the group headed "Decide cases".
    const tally = stanceComposition(
      [{}, withEffect("informational"), withEffect("deny")],
      recordStance,
    );

    expect(tally.map((entry) => entry.stance)).toEqual([
      "decides",
      "supplies-meaning",
      "unstated",
    ]);
  });

  it("says nothing when every record answers the same way", () => {
    // The head already carries the total. The only thing a phrase could add
    // here is a zero for the kind the policy does not hold, and a zero reads as
    // a shortfall against something that was never expected.
    expect(compositionPhrase(stanceComposition([withEffect("deny")], recordStance))).toBeNull();
    expect(compositionPhrase(stanceComposition([], recordStance))).toBeNull();
  });

  it("names every stance present, not a fixed pair of them", () => {
    const said = compositionPhrase(
      stanceComposition(
        [withEffect("deny"), withEffect("informational"), {}],
        recordStance,
      ),
    );

    expect(said).toBe("1 decides a case · 1 supplies a meaning · 1 does not state which");
  });

  it("agrees with itself on number", () => {
    const many = compositionPhrase(
      stanceComposition(
        [withEffect("deny"), withEffect("deny"), withEffect("informational"), withEffect("informational")],
        recordStance,
      ),
    );

    expect(many).toBe("2 decide cases · 2 supply meanings");
  });

  it("never rounds, approximates or hedges a count", () => {
    // "about 15", "~15", "15+" and "many" are all ways of buying a shorter line
    // with a number the reviewer cannot check against the head count.
    const said =
      compositionPhrase(
        stanceComposition(
          [
            ...Array.from({ length: 15 }, () => withEffect("informational")),
            ...Array.from({ length: 3 }, () => withEffect("require_action")),
            {},
          ],
          recordStance,
        ),
      ) ?? "";

    expect(said).toBe("3 decide cases · 15 supply meanings · 1 does not state which");
    expect(said).not.toMatch(/\b(about|around|approx\w*|roughly|nearly|over|under|some|many|several|most|few)\b/i);
    expect(said).not.toMatch(/[~+]|\.{3}|…/);
  });

  it("says what the records do, never how much they are worth", () => {
    // Same guard as the group headings, on the phrase that now carries the
    // whole shape of a policy before it is opened.
    const RANKING =
      /\b(only|just|merely|minor|lesser|less important|unimportant|incidental|trivial|ignorab\w*|safely|skip\w*|optional|non-?essential|supplement\w*|extra|leftover|remaining|other|misc\w*|rest)\b/i;
    const shapes = [
      [withEffect("deny"), withEffect("informational")],
      [withEffect("deny"), {}],
      [withEffect("informational"), {}],
      [withEffect("deny"), withEffect("informational"), {}],
    ];

    for (const shape of shapes) {
      const said = compositionPhrase(stanceComposition(shape, recordStance)) ?? "";
      expect(said).not.toMatch(RANKING);
      expect(said).not.toMatch(/\b(ai|deterministic|ai.?ready|automat\w*|manual)\b/i);
    }
  });
});

describe("narrowing which records are on screen", () => {
  const policy = [
    withEffect("require_action"),
    withEffect("deny"),
    withEffect("informational"),
    withEffect("informational"),
    withEffect("informational"),
  ];

  it("shows every record until the reviewer asks for less", () => {
    const focused = composeFocus(policy, recordStance, null);

    expect(focused.focus).toBeNull();
    expect(focused.shown).toHaveLength(policy.length);
    expect(focused.total).toBe(policy.length);
  });

  it("counts the chips and picks the records in one pass, so they cannot disagree", () => {
    // The fault this shape exists to prevent: a chip reading "3 supply meanings"
    // over a list holding two. Two derivations agree until one of them is
    // edited, and nothing on screen shows which is right.
    for (const entry of composeFocus(policy, recordStance, null).tally) {
      const focused = composeFocus(policy, recordStance, entry.stance);
      expect(focused.shown).toHaveLength(entry.count);
    }
  });

  it("counts every record exactly once across the choices offered", () => {
    const { tally, total } = composeFocus(policy, recordStance, null);
    expect(tally.reduce((sum, entry) => sum + entry.count, 0)).toBe(total);
  });

  it("offers nothing to choose when the policy holds one kind", () => {
    // A control whose only state is the one it is already in teaches a reviewer
    // nothing and costs them a click to find that out.
    const oneKind = [withEffect("deny"), withEffect("require_action")];
    expect(composeFocus(oneKind, recordStance, null).choosable).toBe(false);
    expect(composeFocus(policy, recordStance, null).choosable).toBe(true);
  });

  it("offers a choice for a record stating no effect, rather than hiding it in another", () => {
    const withUnstated = [withEffect("deny"), {}];
    const { tally } = composeFocus(withUnstated, recordStance, null);

    expect(tally.map((entry) => entry.stance)).toEqual(["decides", "unstated"]);
  });

  it("never offers a choice the policy holds no records for", () => {
    const { tally } = composeFocus([withEffect("deny"), withEffect("informational")], recordStance, null);

    expect(tally.every((entry) => entry.count > 0)).toBe(true);
    expect(tally.some((entry) => entry.stance === "unstated")).toBe(false);
  });

  it("shows everything when asked for a kind this policy does not hold", () => {
    // View state outlives what it describes: a reviewer focuses the definitions
    // of one policy and opens another that has none. Answering with everything
    // is the only response that cannot hide a record.
    const noMeanings = [withEffect("deny"), {}];
    const focused = composeFocus(noMeanings, recordStance, "supplies-meaning");

    expect(focused.shown).toHaveLength(noMeanings.length);
  });

  it("reports the focus it applied rather than the one it was asked for", () => {
    // So the buttons a caller draws describe the list it actually has. Reporting
    // the request back would leave a chip pressed over a list it does not
    // describe, which is the one state a reviewer cannot recover from by
    // looking.
    const noMeanings = [withEffect("deny"), {}];
    expect(composeFocus(noMeanings, recordStance, "supplies-meaning").focus).toBeNull();
    expect(composeFocus(noMeanings, recordStance, "unstated").focus).toBe("unstated");
  });

  it("leaves the records themselves untouched, whatever is shown", () => {
    // Narrowing is a reading aid. Nothing it does may reach a record, because
    // everything that decides, exports, approves or publishes reads records.
    const before = JSON.stringify(policy);
    for (const stance of [null, ...STANCE_ORDER]) {
      composeFocus(policy, recordStance, stance);
    }
    expect(JSON.stringify(policy)).toBe(before);
  });
});
