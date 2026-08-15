/**
 * What a search is allowed to decide, and what it is not.
 *
 * A queue of policies has two different questions in it that look like one:
 *
 *   1. Which policies are worth putting on the screen right now?
 *   2. What is in a policy?
 *
 * A search answers the first. It cannot answer the second, because the second
 * has already been answered — by the document, and then by the assembly that
 * read it. When the two are collapsed into a single filter over records, the
 * card stops being the policy and becomes "the part of the policy that matched
 * what I typed", while still carrying one Approve button that decides all of
 * it. A reviewer approving three visible rules approves nine.
 *
 * So the two are kept apart here, as two functions, and the split is the point:
 * `matchedCandidateIds` says which records answered the search, and
 * `cardsAnsweringSearch` uses that only to choose *cards*, never to choose what
 * is inside one. Every card that comes back holds every rule the assembly put
 * in it.
 *
 * This module is pure and holds no React, so the rule can be tested by argument
 * rather than by rendering a queue and hoping the right thing happened.
 */

import type { CandidateRule } from "./api";
import type { PolicyCard } from "./policyCards";

/**
 * The records a policy can be built from.
 *
 * Superseded readings are dropped: a later extraction run records the reading
 * it replaces, both stay in the payload, and placing both leaves two cards for
 * one policy with nothing to order them. The predecessor stays reachable from
 * the card that replaced it.
 */
export function placeableCandidates(candidates: readonly CandidateRule[]): CandidateRule[] {
  return candidates.filter((c) => !c.superseded_by_candidate_id);
}

/**
 * True when this record's own words answer the search.
 *
 * Every field compared here is one the reviewer can see. Nothing is matched on
 * a derived or generated value, so a record never appears for a reason its own
 * text does not show.
 */
export function candidateAnswersSearch(candidate: CandidateRule, searchText: string): boolean {
  const q = searchText.trim().toLowerCase();
  if (!q) return true;
  const r = candidate.rule;
  return (
    r.title.toLowerCase().includes(q) ||
    r.description.toLowerCase().includes(q) ||
    r.rule_id.toLowerCase().includes(q) ||
    r.effect.action.toLowerCase().includes(q) ||
    (r.category ?? "").toLowerCase().includes(q) ||
    (r.tags ?? []).some((t) => t.toLowerCase().includes(q)) ||
    (r.group_label ?? "").toLowerCase().includes(q)
  );
}

/** The ids of the records that answered the search. */
export function matchedCandidateIds(
  candidates: readonly CandidateRule[],
  searchText: string,
): Set<string> {
  return new Set(
    candidates.filter((c) => candidateAnswersSearch(c, searchText)).map((c) => c.id),
  );
}

/**
 * The cards worth showing for this search — each of them whole.
 *
 * A card is offered when any one of its rules answered the search. What comes
 * back is the card the assembly built, unaltered: this function selects, and
 * has no way to subset, because taking a rule out of a card is the failure it
 * exists to prevent.
 */
export function cardsAnsweringSearch(
  cards: readonly PolicyCard[],
  searchText: string,
  matched: ReadonlySet<string>,
): PolicyCard[] {
  if (!searchText.trim()) return [...cards];
  return cards.filter((card) => card.rules.some((entry) => matched.has(entry.recordId)));
}
