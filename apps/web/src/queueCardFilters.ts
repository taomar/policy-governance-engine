/**
 * The filters that are properties of a rule, applied at the level of a policy.
 *
 * `queueCardSelection` established this for the search box. The same argument
 * decides every other filter in the queue, and this module finishes the job for
 * the ones that were still carving policies up: review status and delta status.
 *
 * WHY A RULE-LEVEL FILTER MUST NOT CHOOSE A CARD'S CONTENTS
 *
 * Review status and delta status are genuinely properties of a *rule*. One
 * policy holds rules in several states at once — a provision with two rules can
 * easily have one published and one still awaiting a decision. Filtering the
 * records and then assembling cards from what survives produces a card that
 * says `1 of 2 rules`, and offers one `Approve policy` button over it.
 *
 * That button is the problem. It is presented as a decision about the policy,
 * and a reviewer reads it as one, but it writes to the rules the filter left
 * behind. The card has become "the part of this policy that is still pending"
 * while keeping the name and the authority of the whole policy. Worse, the
 * reviewer cannot see what they are not deciding: the rest of the policy is
 * off the card, so the words they are approving are judged without the words
 * that sit beside them in the document.
 *
 * So the level moves, and only the level. The observation that a reviewer wants
 * to see what still needs review is correct and is kept. What changes is what
 * the answer selects: a filter now chooses **which policies are worth putting
 * on the screen**, and a policy that appears shows every rule it states.
 *
 * A policy appears when *any* of its rules answers the filter. Appearing under
 * more than one filter is honest — a policy really does contain both a
 * published rule and a pending one. Being shown as a fragment is not.
 *
 * The per-rule state stays legible because every rule row carries its own
 * status; the filter narrows the shelf, the row still says which book is which.
 *
 * Pure, and holding no React, so the rule can be tested by argument rather than
 * by rendering a queue and hoping.
 */

import type { CandidateRule } from "./api";
import type { PolicyCard } from "./policyCards";

/** The value every filter uses to mean "not filtering". */
const UNFILTERED = "all";

/** True when this filter is not narrowing anything. */
export function filterIsOff(value: string | null | undefined): boolean {
  return !value || value === UNFILTERED;
}

/**
 * True when this record's review status answers the status filter.
 *
 * Compared against the record's own `review_status` and nothing derived, so a
 * record never matches for a reason its own row does not show.
 */
export function candidateAnswersStatus(candidate: CandidateRule, statusFilter: string): boolean {
  if (filterIsOff(statusFilter)) return true;
  return candidate.review_status === statusFilter;
}

/**
 * True when this record's delta status answers the change filter.
 *
 * `delta_status` is nullable: a record extracted before deltas were tracked has
 * no answer to this question. Absent is not `baseline` — a record with no delta
 * recorded is not the same as one a run positively classified as unchanged — so
 * a null never matches a named delta rather than being folded into one.
 */
export function candidateAnswersDelta(candidate: CandidateRule, deltaFilter: string): boolean {
  if (filterIsOff(deltaFilter)) return true;
  return candidate.delta_status === deltaFilter;
}

/** True when this record answers every rule-level filter that is switched on. */
export function candidateAnswersRuleFilters(
  candidate: CandidateRule,
  filters: { status?: string; delta?: string },
): boolean {
  return (
    candidateAnswersStatus(candidate, filters.status ?? UNFILTERED) &&
    candidateAnswersDelta(candidate, filters.delta ?? UNFILTERED)
  );
}

/** The ids of the records that answered the rule-level filters. */
export function candidateIdsAnsweringRuleFilters(
  candidates: readonly CandidateRule[],
  filters: { status?: string; delta?: string },
): Set<string> {
  return new Set(
    candidates.filter((c) => candidateAnswersRuleFilters(c, filters)).map((c) => c.id),
  );
}

/**
 * The cards worth showing for these filters — each of them whole.
 *
 * A card is offered when any one of its rules answered. What comes back is the
 * card the assembly built, unaltered. Like `cardsAnsweringSearch`, this
 * function selects and has no way to subset: taking a rule out of a card is the
 * failure it exists to prevent, so the type it returns is the type it was
 * given, untouched.
 */
export function cardsAnsweringRuleFilters(
  cards: readonly PolicyCard[],
  filters: { status?: string; delta?: string },
  matched: ReadonlySet<string>,
): PolicyCard[] {
  if (filterIsOff(filters.status) && filterIsOff(filters.delta)) return [...cards];
  return cards.filter((card) => card.rules.some((entry) => matched.has(entry.candidate.id)));
}

/**
 * The sentence that reconciles the two numbers a filtered queue now shows.
 *
 * The status strip counts records, because a status is a property of a record
 * and "266 need review" is the true and actionable number. The list beneath it
 * counts policies, because a policy is what a reviewer decides. Those are two
 * different units and both are correct, so the screen has to say which is
 * which — a number whose unit is left to be guessed is worse than no number.
 *
 * It also answers the question the reviewer asks next. Choosing one status and
 * then seeing a policy list twelve rules, most of them in some other state,
 * looks like the filter is broken. It is not: the filter chose the policy, and
 * the policy supplied its rules. Saying so once, here, is cheaper than leaving
 * every card to look wrong.
 *
 * Returns null when there is nothing to reconcile — no filter, or nothing
 * shown, the latter already being described by the queue's empty state. Two
 * sentences saying "nothing here" is one more than a reader needs.
 */
export function policySelectionNote(
  shown: number,
  filterLabels: readonly string[],
): string | null {
  if (filterLabels.length === 0 || shown <= 0) return null;
  const names = filterLabels.map((l) => `“${l}”`).join(" and ");
  const unit = shown === 1 ? "policy" : "policies";
  return (
    `${shown} ${unit} ${shown === 1 ? "matches" : "match"} ${names}. ` +
    `Each lists every rule of the policy, including rules the filter did not select.`
  );
}

