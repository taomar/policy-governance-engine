/**
 * THE QUEUE SORTS INTO THREE BANDS AND LOSES NO POLICY DOING IT.
 *
 * A reviewer opening the queue is there to decide things, so the working band —
 * the policies still under review — is what the list shows. The policies already
 * decided do not clutter that list; they wait in their own bands, Approved and
 * Published, where the next action (publish) or the record (already live) is.
 *
 * What is pinned here is that the bands are a *partition*, never a filter that
 * hides (constraint 10): every card falls in exactly one band, the three bands
 * together hold every card, and each band's counts are the policies it holds and
 * the rules those policies carry — policies first, rules kept beside them
 * (constraint 2). A band with no members is still a band with a count of zero,
 * so the caller can say "nothing approved yet" rather than letting the fact
 * vanish (constraint 5).
 *
 * No number here measures any document. Each fixture states its own size and
 * every assertion is computed from the fixture.
 */
import { describe, expect, it } from "vitest";
import type { AssembledPolicy } from "./api";
import type { PolicyCard, PolicyCardRule } from "./policyCards";
import { bandScalesFromTabCounts, partitionReviewBands, reviewBandOf } from "./reviewBands";

/** A card in a given set of review states, carrying `ruleCount` rules. The band
 *  logic reads only `reviewStatuses` and the length of `rules`; the rest is the
 *  shape the type demands. */
function card(provisionId: string | null, reviewStatuses: string[], ruleCount: number): PolicyCard {
  const rules = Array.from(
    { length: ruleCount },
    (_, i) => ({ id: `${provisionId ?? "loose"}-r${i}` }) as unknown as PolicyCardRule,
  );
  return {
    policy: { provision_id: provisionId, heading: `H-${provisionId}` } as unknown as AssembledPolicy,
    passages: [],
    rules,
    hiddenByFilter: 0,
    reviewableIds: [],
    allIds: rules.map((r) => (r as unknown as { id: string }).id),
    reviewStatuses,
    policy_set_key: null,
  } as unknown as PolicyCard;
}

describe("each policy lands in exactly one band, by what is left to do", () => {
  it("puts a policy still under review in the working band", () => {
    expect(reviewBandOf(card("a", ["candidate"], 1))).toBe("under_review");
    expect(reviewBandOf(card("a", ["changes_requested"], 1))).toBe("under_review");
  });

  it("puts a wholly-cleared policy in Approved, and a wholly-live one in Published", () => {
    expect(reviewBandOf(card("a", ["approved"], 1))).toBe("approved");
    expect(reviewBandOf(card("a", ["published"], 1))).toBe("published");
  });

  it("keeps a part-decided policy in the working band — work wins over tidiness", () => {
    // The regression this guards: a policy with one rule approved and one still
    // to decide sliding into Approved, taking its undecided rule out of the
    // reviewer's sight. As long as anything is still to decide, the policy stays
    // where the reviewer will act on it.
    expect(reviewBandOf(card("a", ["candidate", "approved"], 2))).toBe("under_review");
    expect(reviewBandOf(card("a", ["approved", "changes_requested"], 2))).toBe("under_review");
  });

  it("treats an approved-and-published policy as Approved — it still has something to publish", () => {
    expect(reviewBandOf(card("a", ["approved", "published"], 2))).toBe("approved");
  });

  it("keeps a rejected-only or unknown-state policy in the working band, never nowhere", () => {
    // Rejected is reopenable, so it is still the reviewer's business; an
    // unrecognised state is a reason to show a card, never to hide it. Either
    // way the card must land somewhere (constraint 10).
    expect(reviewBandOf(card("a", ["rejected"], 1))).toBe("under_review");
    expect(reviewBandOf(card("a", ["something_new"], 1))).toBe("under_review");
  });
});

describe("the partition counts in policies and rules, and drops nothing", () => {
  it("counts each band in policies with its rules kept beside", () => {
    const bands = partitionReviewBands([
      card("u1", ["candidate"], 5),
      card("u2", ["candidate"], 3),
      card("ap", ["approved"], 4),
      card("pb1", ["published"], 10),
      card("pb2", ["published"], 18),
    ]);
    expect(bands.under_review.policies).toBe(2);
    expect(bands.under_review.rules).toBe(8);
    expect(bands.approved.policies).toBe(1);
    expect(bands.approved.rules).toBe(4);
    expect(bands.published.policies).toBe(2);
    expect(bands.published.rules).toBe(28);
  });

  it("accounts for every card in exactly one band (constraint 10 — no wall)", () => {
    const cards = [
      card("u1", ["candidate"], 1),
      card("mix", ["candidate", "approved"], 2),
      card("ap", ["approved"], 4),
      card("pb", ["published"], 10),
      card("rj", ["rejected"], 1),
    ];
    const bands = partitionReviewBands(cards);
    const placed = bands.under_review.policies + bands.approved.policies + bands.published.policies;
    // Every card is somewhere, and no card is in two places: the placed count is
    // the input count exactly.
    expect(placed).toBe(cards.length);
    const placedRules =
      bands.under_review.rules + bands.approved.rules + bands.published.rules;
    expect(placedRules).toBe(cards.reduce((sum, c) => sum + c.rules.length, 0));
  });

  it("leaves the working band free of anything already decided — the default view is the work", () => {
    // This is the whole point of the default: a reviewer landing on the queue
    // sees what still needs them, not the approved and published policies that
    // were making the list hard to read.
    const bands = partitionReviewBands([
      card("u1", ["candidate"], 1),
      card("ap", ["approved"], 4),
      card("pb", ["published"], 10),
    ]);
    const workingStates = bands.under_review.cards.flatMap((c) => c.reviewStatuses);
    expect(workingStates).not.toContain("approved");
    // ...unless the policy also still has undecided rules, which the previous
    // block already pins. A purely-approved or purely-published policy is not in
    // the working band.
    expect(bands.under_review.policies).toBe(1);
  });
});

describe("an empty band is stated, not dropped (constraint 5)", () => {
  it("returns all three bands even when some hold nothing", () => {
    const bands = partitionReviewBands([card("u1", ["candidate"], 2)]);
    // The approved and published bands exist and say zero, so the caller can
    // render "nothing approved yet" / "nothing published yet" rather than
    // letting a reviewer conclude those categories are gone.
    expect(bands.approved.policies).toBe(0);
    expect(bands.approved.rules).toBe(0);
    expect(bands.approved.cards).toEqual([]);
    expect(bands.published.policies).toBe(0);
    expect(bands.published.cards).toEqual([]);
    expect(bands.order).toEqual(["under_review", "approved", "published"]);
  });

  it("returns three empty bands for an empty queue, never undefined", () => {
    const bands = partitionReviewBands([]);
    for (const key of bands.order) {
      expect(bands[key].policies).toBe(0);
      expect(bands[key].rules).toBe(0);
    }
  });
});

describe("a band's headline count is the strip's figure, so the two never disagree", () => {
  it("leads the under-review band with the tab's policy unit, not the count of cards", () => {
    // The defect this guards: the list's card partition counts cards, but a
    // policy unit not yet placed in a passage has no card. Count the cards and
    // the band reads one short of its "Needs review" tab — a policy a reviewer
    // then believes went missing. The headline count comes from the strip's own
    // resolved figure, so band and tab are one measurement, not two.
    const scales = bandScalesFromTabCounts(
      { candidate: 367, approved: 4, published: 28 },
      { candidate: 30, approved: 1, published: 2 },
    );
    expect(scales.under_review).toEqual({ policies: 30, rules: 367 });
    expect(scales.approved).toEqual({ policies: 1, rules: 4 });
    expect(scales.published).toEqual({ policies: 2, rules: 28 });
  });

  it("folds changes-requested into the under-review band, summing rules and policies", () => {
    // Both open states are still under review, so the band's figures are the sum
    // of the two, computed from the fixture: rules 10 + 3, policies 2 + 1.
    const scales = bandScalesFromTabCounts(
      { candidate: 10, changes_requested: 3 },
      { candidate: 2, changes_requested: 1 },
    );
    expect(scales.under_review).toEqual({ policies: 13 - 10, rules: 10 + 3 });
  });

  it("leads with rules alone when the policy figure cannot be said honestly (constraint 5)", () => {
    // Under a scope where the whole-set tally counts a different population, the
    // strip shows no policy figure rather than a fabricated one, and the band
    // follows it: rules kept, policies null — not zero, which would be a
    // measurement nobody took.
    const scales = bandScalesFromTabCounts(
      { candidate: 367, approved: 4, published: 28 },
      null,
    );
    expect(scales.under_review).toEqual({ policies: null, rules: 367 });
    expect(scales.approved).toEqual({ policies: null, rules: 4 });
    expect(scales.published).toEqual({ policies: null, rules: 28 });
  });

  it("reads an absent status as zero, never undefined", () => {
    const scales = bandScalesFromTabCounts({}, {});
    expect(scales.under_review).toEqual({ policies: 0, rules: 0 });
    expect(scales.approved).toEqual({ policies: 0, rules: 0 });
    expect(scales.published).toEqual({ policies: 0, rules: 0 });
  });
});
