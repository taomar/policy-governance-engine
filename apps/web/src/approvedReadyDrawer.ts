/**
 * The approved-but-not-yet-published policies the review queue stages for
 * publishing, said as a list the drawer can render.
 *
 * WHY THIS IS A GROUPING AND NOT A FILTER
 *
 * A reviewer's decision is recorded on a rule, but the queue's unit is the
 * policy (constraint 2). Approving clears a policy's rules, and the drawer's job
 * is to show *which policies* are now cleared and waiting to go live — by name,
 * so a reviewer reads what they decided rather than a list of record ids.
 *
 * So this groups the approved records into their policies rather than listing
 * them flat. The grouping is the same one `policyUnitCount` uses — a record's
 * `provision_id`, or the record itself where it has none — so the number of
 * groups this returns is exactly the policy count that function gives for the
 * same records. The drawer states one number and lists that many rows.
 *
 * WHY NOTHING IS DROPPED
 *
 * Every approved record falls into exactly one group: the ones with a provision
 * into their policy's group, the ones without into a group of their own. None is
 * filtered out, so the drawer can never show fewer policies than there are —
 * which is the whole point of a staging list (constraint 10: group and order,
 * never hide). A record whose policy could not be laid out as a card still
 * appears, named by its own rule, rather than falling silently through the gap
 * between the card view and this one.
 *
 * WHY THE TITLE IS THE CARD'S TITLE
 *
 * The name shown is the one `policyTitle` computes for the policy's card — the
 * document's heading, or its measured fallback — never the provision digest or a
 * rule id, and never a name re-implemented here. A record with no card to borrow
 * a title from is named by its own rule's title, which is the reviewer's own
 * words for it and not an identifier.
 *
 * This is a pure module holding no React, so the rule can be tested by argument
 * rather than by driving a live queue and reading the DOM.
 */

import type { CandidateRule } from "./api";
import { policyTitle, type PolicyCard } from "./policyCards";

/** One policy in the approved-ready drawer. */
export interface ApprovedReadyPolicy {
  /** Stable identity for a list key: the provision, or the record's own id
   *  where it has none. Never shown. */
  readonly key: string;
  /** What the policy is called — its card's title, or its own rule's title when
   *  no card carries it. Never a provision digest or a record id. */
  readonly title: string;
  /** How many approved-but-unpublished rules this policy carries. */
  readonly ruleCount: number;
}

/**
 * Group the approved-but-unpublished records into the policies that carry them,
 * in the order the records first name each policy.
 *
 * `approved` is the queue's `approvedUnpublished` — the records already decided
 * and not yet live — passed in rather than recomputed so the drawer and the
 * "Ready to publish" figure count the same set. `cards` is the queue's assembled
 * cards, read only to borrow each policy's title.
 */
export function approvedReadyPolicies(
  approved: readonly CandidateRule[],
  cards: readonly PolicyCard[],
): ApprovedReadyPolicy[] {
  const cardByProvision = new Map<string, PolicyCard>();
  for (const card of cards) {
    const provision = card.policy.provision_id;
    if (provision && !cardByProvision.has(provision)) {
      cardByProvision.set(provision, card);
    }
  }

  const order: string[] = [];
  const byKey = new Map<string, { key: string; title: string; ruleCount: number }>();
  for (const record of approved) {
    const key = record.provision_id ?? `rule:${record.id}`;
    let entry = byKey.get(key);
    if (!entry) {
      order.push(key);
      const card = record.provision_id ? cardByProvision.get(record.provision_id) : undefined;
      const title = card
        ? policyTitle(card.policy, card.passages).text || card.policy.heading || card.policy.key
        : record.rule.title || record.rule.rule_id;
      entry = { key, title, ruleCount: 0 };
      byKey.set(key, entry);
    }
    entry.ruleCount += 1;
  }

  return order.map((key) => byKey.get(key)!);
}
