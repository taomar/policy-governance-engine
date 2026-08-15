/**
 * A published version, arranged as the policies the document states.
 *
 * WHAT IS LEFT OF THIS MODULE, AND WHY
 *
 * It used to hold a second placement, a second card model and a second
 * serialiser, because `PolicyCardRule` named a reviewable draft row and a
 * published rule is not one. Dressing a published record as a candidate would
 * have put a row on screen that no table holds, keyed by an id that resolves to
 * nothing, so the duplicate was written with its own deletion condition
 * attached: the moment a card rule carried a canonical rule and a status rather
 * than a draft row, every function here became a call into `policyCards`.
 *
 * That has happened. There is now one placement, one card model and one
 * serialiser, and what remains here is the adapter into them plus the few
 * helpers that read a *published* card specifically. Nothing below computes a
 * grouping, a title or a document; each hands the shared implementation the same
 * facts a queue card hands it.
 *
 * WHY THE READ-ONLY BEHAVIOUR IS NOT WRITTEN HERE EITHER
 *
 * `PolicyCard.reviewableIds` is what a decision would write to, and the shared
 * builder derives it from each record's own status through `candidateEditability`.
 * A published record answers no, so these cards come back with an empty list
 * without this file saying anything about publishing. That is the property the
 * page depends on, and it is a consequence of the record rather than of a flag
 * set here.
 *
 * WHAT IS NOT HERE
 *
 * No grouping. The server decides which rules are one policy, once, for the
 * queue and for the published version alike, and a second opinion computed here
 * would be free to disagree with the first.
 */
import { api, type AssembledPolicy, type CanonicalRule } from "./api";
import type { PolicySightingView } from "./components/policyTabPanes";
import {
  buildPolicyCards,
  passageTitle,
  policyJsonDocument,
  unplacedRules,
  type PassageTitle,
  type PolicyCard,
  type PolicyCardPassage,
  type PolicyCardRule,
  type PolicyRecordInput,
} from "./policyCards";
import {
  policyComposition as sharedPolicyComposition,
  type PolicyComposition,
} from "./policyRecordFacts";

/**
 * The published version as policies, and this policy's history.
 *
 * Both are `api.ts` calls. They lived here briefly, with a second copy of the
 * base URL beside them, only because that module was being edited elsewhere; a
 * second place for the base URL to be wrong is a second place to fix it.
 * Re-exported rather than repointed at every call site, so this module can be
 * deleted in one move once its callers reach `api` directly.
 */
export const listVersionPolicies = (
  policySetKey: string,
  versionId: string,
): Promise<AssembledPolicy[]> => api.listVersionPolicies(policySetKey, versionId);

export const listProvisionHistory = (
  policySetKey: string,
  provisionKey: string,
): Promise<PolicySightingView[]> => api.listProvisionHistory(policySetKey, provisionKey);

/** The one card model, under the names this surface already calls it by.
 *  Duplicated names, and deliberately not duplicated types: a published card and
 *  a queue card are the same object, differing only in what the records on them
 *  say about themselves. */
export type PublishedPolicyCardRule = PolicyCardRule;
export type PublishedPolicyCardPassage = PolicyCardPassage;
export type PublishedPolicyCard = PolicyCard;

/**
 * What a published version supplies about each of its rules.
 *
 * The rule, and nothing else: a published row carries no draft id and no review
 * state, and the shared builder reads that absence as published rather than as
 * unrecognised. Nothing is invented to fill either field, which is what stops a
 * sealed record acquiring a draft row's identity on the way to a card.
 */
function asRecords(rules: readonly CanonicalRule[]): PolicyRecordInput[] {
  return rules.map((rule) => ({ rule }));
}

/** Pair the server's policies with the published rules currently in view. */
export function buildPublishedPolicyCards(
  policies: readonly AssembledPolicy[],
  rules: readonly CanonicalRule[],
): PublishedPolicyCard[] {
  return buildPolicyCards(policies, asRecords(rules));
}

/**
 * Published rules the assembly did not place.
 *
 * Shown rather than dropped, for the reason the queue's equivalent gives: a
 * record missing from the arrangement is still a record, and a version that
 * quietly showed fewer rules than it holds would be lying about what was
 * published. Not repaired by inventing a passage to hold them — a passage is a
 * claim about the source, and one manufactured to satisfy a layout is a claim no
 * reading of the source produced.
 */
export function unplacedPublishedRules(
  policies: readonly AssembledPolicy[],
  rules: readonly CanonicalRule[],
): CanonicalRule[] {
  return unplacedRules(policies, asRecords(rules)).map((record) => record.rule);
}

/**
 * What names this card.
 *
 * The heading the policy is assembled under, verbatim, and where the document
 * recorded none, whatever `passageTitle` finds in the first passage's own words.
 */
export function publishedPolicyTitle(
  policy: Pick<AssembledPolicy, "key" | "heading" | "heading_path">,
  passages: readonly PublishedPolicyCardPassage[],
): PassageTitle {
  const heading = policy.heading?.trim() ?? "";
  if (heading) return { source: "heading", text: heading, rest: [] };
  const first = passages[0];
  if (!first) return { source: "unnamed", text: "", rest: [] };
  return passageTitle(first.rules.map((rule) => rule.rule));
}

export interface PublishedSharedFacets {
  ruleType: string | null;
  effectType: string | null;
  route: string | null;
}

function shared<T>(values: readonly T[]): T | null {
  if (values.length === 0) return null;
  const first = values[0];
  if (first === null || first === undefined || first === ("" as unknown as T)) return null;
  return values.every((value) => value === first) ? first : null;
}

/**
 * What every rule of the card agrees on, so the head can state it once.
 *
 * Null for anything they do not all share, which is what tells the card to show
 * that facet per rule instead. There is no review status here: every rule of a
 * published version is published, so a status badge on this card would repeat
 * the name of the page on every row.
 */
export function publishedSharedFacets(card: PublishedPolicyCard): PublishedSharedFacets {
  return {
    ruleType: shared(card.rules.map((rule) => rule.rule.rule_type)),
    effectType: shared(card.rules.map((rule) => rule.rule.effect?.type ?? "")),
    route: shared(card.rules.map((rule) => rule.evaluation_mode)),
  };
}

/**
 * How a policy is made up: what settles cases, and what supplies meaning.
 *
 * The count itself lives in `policyRecordFacts`, over canonical rules, because
 * the policy panel and the published card both need it and a policy is made of
 * the same two kinds of statement wherever it is drawn. This is the adapter from
 * a card's paired rules to that, and nothing more.
 */
export function policyComposition(
  rules: readonly PublishedPolicyCardRule[],
): PolicyComposition {
  return sharedPolicyComposition(rules.map((entry) => entry.rule));
}

export { policyCompositionLabel } from "./policyRecordFacts";
export type { PolicyComposition } from "./policyRecordFacts";

/**
 * The policies a narrowing answers, each still whole.
 *
 * The rule this encodes: a search or a facet filter selects *policies*. It never
 * selects some of a policy's rules and leaves the rest out, because the result
 * is a card that looks exactly like a whole policy and is not one — and a reader
 * has no way to tell the difference, since a policy with three rules and a
 * nine-rule policy showing three render identically.
 *
 * The card objects are returned by identity, not rebuilt, so there is no path by
 * which a narrowing could alter what a card contains even by accident.
 */
export function publishedCardsAnsweringNarrowing(
  cards: readonly PublishedPolicyCard[],
  matchedRuleIds: ReadonlySet<string>,
): PublishedPolicyCard[] {
  return cards.filter((card) => card.rules.some((entry) => matchedRuleIds.has(entry.rule_id)));
}

/**
 * The published policy as one document, with its rules nested inside it.
 *
 * There is one serialiser and this is it, reached directly. It used to be
 * reached through a bridge that rewrapped every rule as a draft row, because the
 * serialiser read the record through one — and that bridge ended in a cast,
 * which is the part that mattered. When the serialiser stopped reading rules
 * that way, the cast kept the rewrapping compiling while it handed the
 * serialiser nothing, and the JSON tab threw at runtime on a field of a rule
 * that was no longer there. A named re-export cannot go stale that way: a change
 * of shape now fails the build instead of the page.
 */
export const publishedPolicyJsonDocument = policyJsonDocument;
