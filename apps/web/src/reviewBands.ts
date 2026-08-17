import type { PolicyCard } from "./policyCards";
import { policyTitle } from "./policyCards";

/**
 * The three bands a reviewer sorts the queue into.
 *
 *  - `under_review` — still to decide. This is the working queue: the reviewer
 *    opening the page is here to move these forward, so it is what the list
 *    shows by default.
 *  - `approved` — cleared, not yet live. The next action on these is to publish.
 *  - `published` — already live in a numbered version. Reference, not work.
 *
 * The bands are a *partition*: every card falls in exactly one, and no card
 * falls in none. That is the whole point of computing them in one place — two
 * separately-built lists of the same policies drift apart, and this project has
 * lost hours to exactly that (handover §4.2). One source, derived each render
 * from the live cards, cannot disagree with itself.
 */
export type ReviewBandKey = "under_review" | "approved" | "published";

export interface ReviewBand {
  key: ReviewBandKey;
  /** How many policies (cards) are in this band. The unit a reviewer counts. */
  policies: number;
  /** How many rules those policies hold, in view. Named beside the policy count,
   *  never in place of it (constraint 2). */
  rules: number;
  /** The cards themselves, in the order they arrived. */
  cards: PolicyCard[];
}

export interface ReviewBands {
  under_review: ReviewBand;
  approved: ReviewBand;
  published: ReviewBand;
  /** The bands in the order they are shown, so a caller never re-hardcodes it. */
  order: ReviewBandKey[];
}

/** Rule states that mean the policy still has undecided work on it. */
const UNDER_REVIEW_STATES = new Set(["candidate", "changes_requested"]);

/**
 * Which band a single card belongs to.
 *
 * By precedence, not by majority: work wins. A policy with even one rule still
 * to decide stays in `under_review`, because a reviewer must not lose sight of
 * a rule that still needs them just because the rest of the policy is cleared.
 * Only once nothing is left to decide does a policy move on — to `approved` if
 * anything is waiting to publish, else to `published` if it is wholly live.
 *
 * A card that is none of these — rejected-only, or a state we do not recognise —
 * falls back to `under_review` rather than vanishing. A rejected policy can be
 * reopened, so it is still the reviewer's business; and an unknown state is a
 * reason to show a card, never to hide it (constraint 10).
 */
export function reviewBandOf(card: PolicyCard): ReviewBandKey {
  const statuses = card.reviewStatuses;
  if (statuses.some((s) => UNDER_REVIEW_STATES.has(s))) return "under_review";
  if (statuses.includes("approved")) return "approved";
  if (statuses.length > 0 && statuses.every((s) => s === "published")) return "published";
  return "under_review";
}

function bandRuleCount(cards: PolicyCard[]): number {
  return cards.reduce((sum, card) => sum + card.rules.length, 0);
}

function makeBand(key: ReviewBandKey, cards: PolicyCard[]): ReviewBand {
  return { key, policies: cards.length, rules: bandRuleCount(cards), cards };
}

/**
 * Sort the cards into the three bands.
 *
 * The result always carries all three bands, even the empty ones: a band with
 * no members is a fact a reviewer needs stated — "nothing is approved yet" —
 * not an absence to be silently dropped (constraint 5). The caller renders the
 * empty band's own words; this function makes sure it still exists to render.
 */
export function partitionReviewBands(cards: readonly PolicyCard[]): ReviewBands {
  const underReview: PolicyCard[] = [];
  const approved: PolicyCard[] = [];
  const published: PolicyCard[] = [];
  for (const card of cards) {
    const band = reviewBandOf(card);
    if (band === "approved") approved.push(card);
    else if (band === "published") published.push(card);
    else underReview.push(card);
  }
  return {
    under_review: makeBand("under_review", underReview),
    approved: makeBand("approved", approved),
    published: makeBand("published", published),
    order: ["under_review", "approved", "published"],
  };
}

/** A band's headline figure: policies over rules, policies null when unsayable. */
export interface BandScale {
  /** The policy count to lead with, or null when it cannot be said honestly. */
  policies: number | null;
  /** The rule count, always kept beside the policy figure, never in its place. */
  rules: number;
}

export interface BandScales {
  under_review: BandScale;
  approved: BandScale;
  published: BandScale;
}

/** Which review statuses each band's headline count is the sum of. */
const BAND_STATUS_KEYS: Record<ReviewBandKey, readonly string[]> = {
  under_review: ["candidate", "changes_requested"],
  approved: ["approved"],
  published: ["published"],
};

/**
 * The bands' headline counts, taken from the figures the status strip shows.
 *
 * A band and its tab sit on one screen, so their numbers must be one measurement,
 * not two. The card partition above fills each band's *list*, but it counts
 * cards, and a policy unit not yet placed in a passage has no card while still
 * being a policy under review — count the cards and the band reads one short of
 * its tab, which a reviewer reads as a policy gone missing. So the counts come
 * from the same resolved per-status figures the strip renders: rule counts always
 * present, policy counts only `when they can be said honestly` — null under a
 * scope that would make them a fabrication, and the band then leads with rules
 * exactly as the strip does (constraint 5). Rules hold one status each and sum
 * cleanly; the policy sum can overcount a unit straddling two open states, the
 * same latitude every per-status tab already takes, with the "All" tab left as
 * the honest total. Counts in policies, rules kept beside them (constraint 2).
 */
export function bandScalesFromTabCounts(
  ruleCounts: Record<string, number>,
  policyCounts: Record<string, number> | null,
): BandScales {
  const combine = (keys: readonly string[]): BandScale => ({
    policies: policyCounts
      ? keys.reduce((sum, key) => sum + (policyCounts[key] ?? 0), 0)
      : null,
    rules: keys.reduce((sum, key) => sum + (ruleCounts[key] ?? 0), 0),
  });
  return {
    under_review: combine(BAND_STATUS_KEYS.under_review),
    approved: combine(BAND_STATUS_KEYS.approved),
    published: combine(BAND_STATUS_KEYS.published),
  };
}

/**
 * A stable key for a band card, for React lists and de-duplication.
 *
 * A policy's provision is its identity where it has one. A pending candidate
 * with no provision yet is its own unit (the server counts it that way too), so
 * it is keyed by its first record id, which is stable for the life of the row.
 */
export function reviewBandCardKey(card: PolicyCard): string {
  return card.policy.provision_id ?? `rule:${card.allIds[0] ?? ""}`;
}

/**
 * What a band card is called, in one place so every band names a policy the
 * same way and none re-implements it.
 *
 * The policy's own title as `policyTitle` computes it — the document heading, or
 * its measured fallback — with the heading and then the card key behind it so a
 * row is never blank. The same order `approvedReadyPolicies` already uses, so a
 * policy reads identically whether it is in a band here or in the publish
 * banner's set. Never a provision digest or a record id.
 */
export function reviewBandCardTitle(card: PolicyCard): string {
  return policyTitle(card.policy, card.passages).text || card.policy.heading || card.policy.key;
}
