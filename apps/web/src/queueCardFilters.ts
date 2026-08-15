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
import { recordStance } from "./recordStance";

/**
 * The content lenses, and why this is one selectable lens rather than two tabs.
 *
 * A two-lane split — enforceable rules on one side, glossary on the other —
 * partitions honestly only if a policy falls on one side. Measured across the
 * whole live corpus at policy level:
 *
 *   ais-employee-handbook   38 policies   0 purely meaning-supplying   11 mixed
 *   gmu-staff-handbook-2024 32 policies   0 purely meaning-supplying   16 mixed
 *
 * Not one policy in either document is made only of records that define. Every
 * policy holds something that constrains someone, so a "rules" lane would hold
 * 38 of 38 and 32 of 32 — every card, twice over — while the glossary lane held
 * a subset the reviewer had already seen. A partition whose larger half is
 * everything is not a partition, and the wall would earn nothing.
 *
 * What is real is the smaller set: 11 and 16 policies do state meanings, and a
 * reviewer working the glossary wants exactly those. So it is offered as a lens
 * over the queue, in the same shape as status and delta, and the default is the
 * whole queue rather than a lane pretending to be one side of a split.
 */
export const STANCE_LENSES = [
  { value: "all", label: "Every policy" },
  { value: "supplies-meaning", label: "Policies that state meanings" },
] as const;


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

/**
 * True when this record's stance answers the content filter.
 *
 * The stance is read from `recordStance`, which asks the extractor's own
 * `effect.type` whether the record constrains anyone. It is deliberately not
 * re-derived here: the extractor made that judgement once with the document in
 * front of it, and a second opinion formed in the client — from `rule_type`, or
 * worse from the words — is how two renderings of one record drift apart.
 *
 * It is also why this filter is not built on a topic. "General statements" and
 * "things about the document itself" cannot be recognised without a vocabulary,
 * and a vocabulary belongs to one domain and one language. Asking what a record
 * *does* needs no words at all, so it survives Arabic and the next corpus.
 *
 * `unstated` answers neither lens. A record whose effect was never recorded has
 * not been shown to define anything, and saying it constrains someone would be
 * a claim the app cannot support; it stays visible in the unfiltered queue,
 * which is where a record the app knows least about most needs to be.
 */
export function candidateAnswersStance(candidate: CandidateRule, stanceFilter: string): boolean {
  if (filterIsOff(stanceFilter)) return true;
  return recordStance(candidate.rule) === stanceFilter;
}

/** True when this record answers every rule-level filter that is switched on. */
export function candidateAnswersRuleFilters(
  candidate: CandidateRule,
  filters: { status?: string; delta?: string; stance?: string },
): boolean {
  return (
    candidateAnswersStatus(candidate, filters.status ?? UNFILTERED) &&
    candidateAnswersDelta(candidate, filters.delta ?? UNFILTERED) &&
    candidateAnswersStance(candidate, filters.stance ?? UNFILTERED)
  );
}

/** The ids of the records that answered the rule-level filters. */
export function candidateIdsAnsweringRuleFilters(
  candidates: readonly CandidateRule[],
  filters: { status?: string; delta?: string; stance?: string },
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
  filters: { status?: string; delta?: string; stance?: string },
  matched: ReadonlySet<string>,
): PolicyCard[] {
  if (
    filterIsOff(filters.status) &&
    filterIsOff(filters.delta) &&
    filterIsOff(filters.stance)
  ) {
    return [...cards];
  }
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

