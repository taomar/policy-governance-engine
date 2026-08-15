/**
 * A published version, arranged as the policies the document states.
 *
 * WHY THIS EXISTS SEPARATELY FROM `policyCards`
 *
 * It should not, and it is written to be deleted. `policyCards` already pairs
 * the server's assembly with the records in view, and every display helper it
 * exports that reads a *rule* rather than a *review record* is imported from
 * there by this module rather than restated. What it cannot presently do is
 * hold a rule that is not a `CandidateRule`: `PolicyCardRule.candidate` is a
 * reviewable draft row, and a published rule is not one and must not be dressed
 * as one. Synthesising a candidate to satisfy the type would put a record on
 * screen that no table holds, keyed by an id that resolves to nothing.
 *
 * So this module is the same pairing over the record a published version
 * actually has — the canonical rule — and nothing else. The moment
 * `PolicyCardRule` carries a canonical rule and a status instead of a candidate
 * row, every function here becomes a call into `policyCards` and this file goes
 * away. That change is written up for its owner; until it lands, the choice was
 * between one small module that will be deleted and a second copy of a card.
 *
 * WHAT IS NOT HERE
 *
 * No grouping. The server decides which rules are one policy, once, for the
 * queue and for the published version alike, and a second opinion computed here
 * would be free to disagree with the first.
 */
import { api, type AssembledPassage, type AssembledPolicy, type CanonicalRule } from "./api";
import type { PolicySightingView } from "./components/policyTabPanes";
import { passageTitle, policyJsonDocument, type PassageTitle, type PolicyCard } from "./policyCards";
import {
  policyComposition as sharedPolicyComposition,
  type PolicyComposition,
} from "./policyRecordFacts";

/**
 * The published version as policies, and this policy's history.
 *
 * Both are `api.ts` calls now. They lived here briefly, with a second copy of
 * the base URL beside them, only because that module was being edited
 * elsewhere; a second place for the base URL to be wrong is a second place to
 * fix it. Re-exported rather than repointed at every call site, so this module
 * can be deleted in one move once its callers reach `buildPolicyCards`.
 */
export const listVersionPolicies = (
  policySetKey: string,
  versionId: string,
): Promise<AssembledPolicy[]> => api.listVersionPolicies(policySetKey, versionId);

export const listProvisionHistory = (
  policySetKey: string,
  provisionKey: string,
): Promise<PolicySightingView[]> => api.listProvisionHistory(policySetKey, provisionKey);

export interface PublishedPolicyCardRule {
  rule_id: string;
  /** The published record itself. Immutable, and the whole of what there is:
   *  a published version holds no draft row behind the rule. */
  rule: CanonicalRule;
  /** This rule's own route, from the assembly. Never summarised away. */
  evaluation_mode: string;
}

export interface PublishedPolicyCardPassage {
  passage: AssembledPassage;
  rules: PublishedPolicyCardRule[];
}

export interface PublishedPolicyCard {
  policy: AssembledPolicy;
  passages: PublishedPolicyCardPassage[];
  /** Every rule on the card, flat, in document order. */
  rules: PublishedPolicyCardRule[];
  /** Rules this policy states that the current search or filter is not
   *  showing. Zero for the ordinary case; anything else is said out loud on
   *  the card, because a fragment presented as a whole policy is worse than no
   *  grouping at all. */
  hiddenByFilter: number;
}

interface Placement {
  cards: PublishedPolicyCard[];
  unplaced: CanonicalRule[];
}

function place(
  policies: readonly AssembledPolicy[],
  rules: readonly CanonicalRule[],
): Placement {
  const byRuleId = new Map<string, CanonicalRule>();
  for (const rule of rules) {
    if (!byRuleId.has(rule.rule_id)) byRuleId.set(rule.rule_id, rule);
  }

  const cards: PublishedPolicyCard[] = [];
  for (const policy of policies) {
    const passages: PublishedPolicyCardPassage[] = [];
    for (const passage of Array.isArray(policy.passages) ? policy.passages : []) {
      const placed: PublishedPolicyCardRule[] = [];
      for (const entry of Array.isArray(passage?.rules) ? passage.rules : []) {
        const rule = byRuleId.get(entry.rule_id);
        if (!rule) continue;
        placed.push({ rule_id: entry.rule_id, rule, evaluation_mode: entry.evaluation_mode });
      }
      if (placed.length > 0) passages.push({ passage, rules: placed });
    }
    const flat = passages.flatMap((passage) => passage.rules);
    if (flat.length === 0) continue;
    cards.push({
      policy,
      passages,
      rules: flat,
      // Counted against the policy's own total rather than against the rules it
      // happens to list, so a filter and a stale assembly read the same way:
      // this is not all of it.
      hiddenByFilter: Math.max(0, policy.rule_count - flat.length),
    });
  }

  // One definition of placed, read off what was actually built rather than off
  // a second walk of the same payload that could drift from the first.
  const placedIds = new Set<string>();
  for (const card of cards) for (const rule of card.rules) placedIds.add(rule.rule_id);

  return { cards, unplaced: rules.filter((rule) => !placedIds.has(rule.rule_id)) };
}

let lastPlacement: {
  policies: readonly AssembledPolicy[];
  rules: readonly CanonicalRule[];
  result: Placement;
} | null = null;

function placement(
  policies: readonly AssembledPolicy[],
  rules: readonly CanonicalRule[],
): Placement {
  if (lastPlacement && lastPlacement.policies === policies && lastPlacement.rules === rules) {
    return lastPlacement.result;
  }
  const result = place(policies, rules);
  lastPlacement = { policies, rules, result };
  return result;
}

/** Pair the server's policies with the published rules currently in view. */
export function buildPublishedPolicyCards(
  policies: readonly AssembledPolicy[],
  rules: readonly CanonicalRule[],
): PublishedPolicyCard[] {
  return placement(policies, rules).cards;
}

/**
 * Published rules the assembly did not place.
 *
 * Shown rather than dropped, for the reason the queue's equivalent gives: a
 * record missing from the arrangement is still a record, and a version that
 * quietly showed fewer rules than it holds would be lying about what was
 * published. Not repaired by inventing a passage to hold them — a passage is a
 * claim about the source, and one manufactured to satisfy a layout is a claim
 * no reading of the source produced.
 */
export function unplacedPublishedRules(
  policies: readonly AssembledPolicy[],
  rules: readonly CanonicalRule[],
): CanonicalRule[] {
  return placement(policies, rules).unplaced;
}

/**
 * What names this card.
 *
 * The heading the policy is assembled under, verbatim, and where the document
 * recorded none, whatever `passageTitle` finds in the first passage's own
 * words. The same order of preference the queue's card uses; it is written here
 * rather than called because the queue's version reaches through a review
 * record to reach the rules, and there is no review record on this side.
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
 * the same two kinds of statement wherever it is drawn. This is the adapter
 * from a card's paired rules to that, and nothing more.
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
 * The rule this encodes: a search or a facet filter selects *policies*. It
 * never selects some of a policy's rules and leaves the rest out, because the
 * result is a card that looks exactly like a whole policy and is not one — and
 * a reader has no way to tell the difference, since a policy with three rules
 * and a nine-rule policy showing three render identically.
 *
 * The card objects are returned by identity, not rebuilt, so there is no path
 * by which a narrowing could alter what a card contains even by accident.
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
 * This is an adapter and not a serialiser. There is one serialiser —
 * `policyJsonDocument` — and it already answers the only question this tab
 * asks: what did the document state here, as one file. Writing a second one
 * for published records would mean two files claiming to be the same policy,
 * free to disagree the first time either is changed, which is exactly the
 * drift the shared panes exist to close.
 *
 * What the serialiser wants from each rule is the canonical record; a queue
 * card reaches it through the candidate that proposes it, a published version
 * holds it directly. Only that one hop differs, so only that one hop is
 * bridged here.
 *
 * The coupling is real and worth naming: if the serialiser ever reads a field
 * of the candidate other than its rule, this bridge will hand it nothing.
 * `publishedPolicyDocumentHoldsEveryRule` in the tests fails the moment that
 * stops being true for the rules, and the standing request to give the
 * serialiser a record-shaped parameter would remove the bridge entirely.
 */
export function publishedPolicyJsonDocument(
  card: PublishedPolicyCard,
): Record<string, unknown> {
  return policyJsonDocument({
    policy: card.policy,
    passages: card.passages.map((block) => ({
      passage: block.passage,
      rules: block.rules.map((entry) => ({
        rule_id: entry.rule_id,
        candidate: { rule: entry.rule },
        evaluation_mode: entry.evaluation_mode,
      })),
    })),
    rules: card.rules.map((entry) => ({
      rule_id: entry.rule_id,
      candidate: { rule: entry.rule },
      evaluation_mode: entry.evaluation_mode,
    })),
    hiddenByFilter: card.hiddenByFilter,
    reviewableIds: [],
    allIds: card.rules.map((entry) => entry.rule_id),
  } as unknown as PolicyCard);
}
