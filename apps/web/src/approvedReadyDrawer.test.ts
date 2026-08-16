/**
 * THE STAGING LIST NEVER SHOWS FEWER POLICIES THAN THERE ARE.
 *
 * A reviewer approves a policy and it leaves the working queue for a drawer by
 * the Publish action, so they can read what they have cleared before it goes
 * live. The drawer is a *grouping* of the approved records, never a filter over
 * them (constraint 10): a staging list that hid one of the things staged would
 * be worse than no list, because the reviewer would publish believing the drawer
 * was the whole of it.
 *
 * So what is pinned here is arithmetic, not appearance. The number of rows the
 * drawer shows is exactly the policy count `policyUnitCount` computes for the
 * same records — the figure the tabs and the server already agree on — and every
 * approved record is accounted for in exactly one row. A record whose policy the
 * queue could not lay out as a card is still named, by its own rule, rather than
 * falling through the gap between the two views. And the name shown is the
 * policy's, taken from its card, never a rule id.
 *
 * No number here measures any document. Each fixture states its own size and
 * every assertion is computed from the fixture, so growing one cannot turn a
 * count into a literal a later reader "corrects".
 */
import { describe, expect, it } from "vitest";
import type { AssembledPolicy, CandidateRule, CanonicalRule } from "./api";
import type { PolicyCard } from "./policyCards";
import { policyUnitCount } from "./policyRecordFacts";
import { approvedReadyPolicies, approvedReadyScale } from "./approvedReadyDrawer";

/** A canonical rule carrying only the title the drawer reads when it has no
 *  card to borrow one from. The rest is the shape the type demands. */
function rule(ruleId: string, title: string): CanonicalRule {
  return { rule_id: ruleId, title } as unknown as CanonicalRule;
}

/** One approved-but-unpublished record: the review status the queue has already
 *  filtered to, the provision it belongs to (or none), and its own rule. */
function approved(id: string, provisionId: string | null, title: string): CandidateRule {
  return {
    id,
    review_status: "approved",
    provision_id: provisionId,
    rule: rule(`rid-${id}`, title),
  } as unknown as CandidateRule;
}

/** A card for a policy: its provision, and the heading a reviewer reads it by.
 *  `policyTitle` returns the heading verbatim when one is present, so the empty
 *  passage list here is faithful — the title path the drawer uses never reaches
 *  for a passage while a heading is set. */
function card(provisionId: string, heading: string): PolicyCard {
  return {
    policy: {
      key: `key-${provisionId}`,
      heading,
      heading_path: [heading],
      provision_id: provisionId,
      passages: [],
      rules: [],
    } as unknown as AssembledPolicy,
    passages: [],
    rules: [],
    hiddenByFilter: 0,
    reviewableIds: [],
    allIds: [],
    reviewStatuses: [],
    policy_set_key: null,
  } as unknown as PolicyCard;
}

describe("the drawer counts the same policies the queue does", () => {
  it("shows one row per policy, however many approved rules each holds", () => {
    // Provision A holds three approved records, B holds one. The reviewer
    // decided two policies, not four rules, and the drawer says two.
    const records = [
      approved("1", "prov-A", "A"),
      approved("2", "prov-A", "A"),
      approved("3", "prov-A", "A"),
      approved("4", "prov-B", "B"),
    ];
    const rows = approvedReadyPolicies(records, [card("prov-A", "Leave of absence"), card("prov-B", "Overtime")]);

    expect(rows).toHaveLength(2);
    // The claim that makes it a grouping and not an accident: the row count is
    // the policy count, computed independently by the figure the tabs trust.
    expect(rows).toHaveLength(policyUnitCount(records));
  });

  it("accounts for every approved record in exactly one row", () => {
    // Fewer rows must never mean fewer records staged. The rules gather inside
    // their policy's row; none leaves the tally.
    const records = [
      approved("1", "prov-A", "A"),
      approved("2", "prov-A", "A"),
      approved("3", "prov-B", "B"),
    ];
    const rows = approvedReadyPolicies(records, [card("prov-A", "A heading"), card("prov-B", "B heading")]);
    const staged = rows.reduce((total, row) => total + row.ruleCount, 0);
    expect(staged).toBe(records.length);
    // Every row is a real policy, not a hole left by a dropped record: each has
    // a name to show and at least one rule behind it.
    for (const row of rows) {
      expect(row.title.length).toBeGreaterThan(0);
      expect(row.ruleCount).toBeGreaterThanOrEqual(1);
    }
  });

  it("counts a record attached to no provision as its own policy", () => {
    // The same arithmetic the count function draws: a record with no provision
    // groups with nothing, so it is its own unit. Dropping it would let the
    // drawer show fewer policies than the reviewer approved.
    const records = [
      approved("1", "prov-A", "A"),
      approved("2", null, "hand-authored"),
      approved("3", null, "another loose one"),
    ];
    const rows = approvedReadyPolicies(records, [card("prov-A", "A heading")]);
    expect(rows).toHaveLength(3);
    expect(rows).toHaveLength(policyUnitCount(records));
    // Named, not dropped: the loose records appear by their own titles rather
    // than being folded into the one policy that did have a provision.
    expect(rows.map((row) => row.title)).toContain("hand-authored");
    expect(rows.map((row) => row.title)).toContain("another loose one");
  });
});

describe("the drawer names policies, never ids", () => {
  it("titles each row by its card's heading", () => {
    const rows = approvedReadyPolicies(
      [approved("1", "prov-A", "unused rule title")],
      [card("prov-A", "Leave of absence")],
    );
    expect(rows[0].title).toBe("Leave of absence");
    // The regression this guards: a row titled by the record's id or rule id.
    expect(rows[0].title).not.toContain("rid-");
    expect(rows[0].title).not.toBe("prov-A");
  });

  it("falls back to the record's own rule title when no card carries the policy", () => {
    // A record whose policy could not be laid out as a card must still be named
    // and still appear — named by the reviewer's own words for the rule, which
    // is not an identifier. This is the reachability the drawer exists to keep:
    // nothing falls through the gap between the card view and this one.
    const rows = approvedReadyPolicies([approved("7", "prov-orphan", "Records retention")], []);
    expect(rows).toHaveLength(1);
    expect(rows[0].title).toBe("Records retention");
  });

  it("keeps the order the records first name each policy", () => {
    const rows = approvedReadyPolicies(
      [approved("1", "prov-C", "C"), approved("2", "prov-A", "A"), approved("3", "prov-C", "C")],
      [card("prov-A", "A heading"), card("prov-C", "C heading")],
    );
    expect(rows.map((row) => row.title)).toEqual(["C heading", "A heading"]);
  });
});

describe("empty is said, not vanished", () => {
  it("returns an empty list when nothing has been approved", () => {
    // The drawer renders its own "nothing approved yet" from this: an empty list
    // is a fact to state (constraint 5), and the caller can only state it if the
    // grouping hands back an empty list rather than throwing or guessing.
    expect(approvedReadyPolicies([], [card("prov-A", "A heading")])).toEqual([]);
    expect(approvedReadyPolicies([], [])).toEqual([]);
  });
});

describe("the ready-to-publish scale leads with the policy and keeps the rule (constraint 2)", () => {
  // The banner over the queue and the publish panel used to read the approved set
  // as "N approved rules" / "N approved candidate(s)" — the rule count alone. GMU's
  // real set is 4 rules in 1 policy, so that sized one decided policy as four
  // things to weigh. This pins the honest shape the drawer already uses: the
  // policy leads, the rule stays, and neither is dropped (constraint 11).
  it("says both units, policy first, for the real approved set", () => {
    expect(approvedReadyScale(1, 4)).toBe("1 policy · 4 rules");
  });

  it("keeps both nouns singular at one", () => {
    expect(approvedReadyScale(1, 1)).toBe("1 policy · 1 rule");
  });

  it("pluralises both when there are several", () => {
    expect(approvedReadyScale(2, 7)).toBe("2 policies · 7 rules");
  });

  it("falls back to the rule count, named as rules, when no policy was assembled (constraint 5)", () => {
    // Every approved rule belongs to a policy, so zero groups over a non-empty
    // rule set is not "no policies" — it is "not measured yet", the cards still
    // loading. Absent is not empty: it states the rules and names them as rules,
    // and never prints "0 policies", a figure nobody took.
    expect(approvedReadyScale(0, 4)).toBe("4 rules");
  });
});
