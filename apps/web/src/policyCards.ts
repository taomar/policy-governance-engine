/**
 * The review queue's unit of decision: one passage, one card.
 *
 * THE DEFECT THIS CLOSES
 *
 * A passage stating three rules was drawn as a header over three rows. Each row
 * carried its own checkbox, its own approve, its own reject, its own record id
 * and its own JSON. The header said the three belonged together and the
 * interface then asked the reviewer to decide them one at a time — so the
 * grouping was an annotation on a list rather than a change to what is being
 * decided. A reviewer reads a passage and forms one judgement about it; that
 * judgement is what the card has to be.
 *
 * WHY THE GROUPING IS STILL NOT COMPUTED HERE
 *
 * `GET /policy-sets/{key}/policies` decides which rules belong together, on
 * `lineage.source_elements`, in `policy_assembly.py`. Everything below reads
 * that answer and pairs it with the flat candidate list the same fetch already
 * returns. No function here decides membership, order, or count — a second
 * opinion on grouping would be free to disagree with the first, silently, on
 * exactly the records where it matters. This repository already carries the
 * scar of two parsers.
 *
 * WHAT MUST SURVIVE CONTACT
 *
 * A policy of one rule is the ordinary case — 83 of the 155 passages in the
 * live corpus. It is built here by the same code path as a policy of seven and
 * renders as an ordinary card, never as a container with one thing in it.
 *
 * Route is a property of a rule. A card summarises the routes its rules take
 * for orientation and shows each rule's own route beside that rule; the summary
 * never replaces it, and neither route is a grade.
 *
 * A card must never present a fragment as a whole passage. The assembly is
 * unfiltered and the flat list is filtered, so the difference between them is
 * the number of rules the current filter is not showing — stated, not inferred.
 */

import type { AssembledPolicy, CandidateRule, CanonicalRule } from "./api";
import { candidateEditability } from "./candidateEditability";

/** One rule of a policy, as the current filter shows it. */
export interface PolicyCardRule {
  rule_id: string;
  /** The reviewable record behind the rule. The flat list is what a reviewer
   *  approves, edits and rejects; the assembly only says where it belongs. */
  candidate: CandidateRule;
  /** This rule's own route, from the assembly. Never summarised away. */
  evaluation_mode: string;
}

export interface PolicyCard {
  /** The server's policy, carried whole so nothing downstream has to
   *  reconstruct it. */
  policy: AssembledPolicy;
  /** Rules this filter is showing, in the order the passage states them. */
  rules: PolicyCardRule[];
  /** Rules the passage states that this filter is not showing. Zero for the
   *  ordinary case; anything else has to be said out loud on the card. */
  hiddenByFilter: number;
  /** Candidate ids on this card that are open to a review decision. One
   *  approve writes to all of them. */
  reviewableIds: string[];
  /** Every candidate id on the card, reviewable or already decided. */
  allIds: string[];
  /** Distinct review states present, in the order first seen. More than one
   *  means part of the passage has already been decided. */
  reviewStatuses: string[];
}

/**
 * Pair the server's policies with the candidate records currently in view.
 *
 * `candidates` is the filtered flat list, so a card carries only the rules the
 * reviewer can presently see — and reports how many it is therefore not
 * showing. A policy with none of its rules in view produces no card at all
 * rather than an empty one.
 */
export function buildPolicyCards(
  policies: readonly AssembledPolicy[],
  candidates: readonly CandidateRule[],
): PolicyCard[] {
  const byRuleId = new Map<string, CandidateRule>();
  for (const candidate of candidates) {
    if (!byRuleId.has(candidate.rule.rule_id)) byRuleId.set(candidate.rule.rule_id, candidate);
  }

  const cards: PolicyCard[] = [];
  for (const policy of policies) {
    const rules: PolicyCardRule[] = [];
    for (const rule of policy.rules) {
      const candidate = byRuleId.get(rule.rule_id);
      if (!candidate) continue;
      rules.push({
        rule_id: rule.rule_id,
        candidate,
        evaluation_mode: rule.evaluation_mode,
      });
    }
    if (rules.length === 0) continue;

    const reviewStatuses: string[] = [];
    for (const rule of rules) {
      if (!reviewStatuses.includes(rule.candidate.review_status)) {
        reviewStatuses.push(rule.candidate.review_status);
      }
    }

    cards.push({
      policy,
      rules,
      // Counted against the policy's own total rather than against the rules
      // it happens to list, so a filter, a page and a stale assembly all read
      // the same way: this is not all of it.
      hiddenByFilter: Math.max(0, policy.rule_count - rules.length),
      // What one approve on this card will write to. A rule already approved,
      // rejected or published is not re-decided by a later decision on its
      // neighbours: that would overwrite a judgement somebody already made.
      reviewableIds: rules
        .filter((rule) => candidateEditability(rule.candidate.review_status).canReview)
        .map((rule) => rule.candidate.id),
      allIds: rules.map((rule) => rule.candidate.id),
      reviewStatuses,
    });
  }
  return cards;
}

/**
 * Candidates the assembly did not place.
 *
 * The two fetches do not always cover the same population: the flat list can
 * ask for superseded rows when a historical run is open, and the assembly does
 * not. A rule in that gap has to be shown — dropping a decision from the review
 * queue is the one failure worse than showing it ungrouped — and it has to be
 * shown as what it is rather than promoted to a passage of its own, because
 * "the server did not place this" and "the source stated this alone" are
 * different facts.
 */
export function unplacedCandidates(
  policies: readonly AssembledPolicy[],
  candidates: readonly CandidateRule[],
): CandidateRule[] {
  const placed = new Set<string>();
  for (const policy of policies) {
    for (const rule of policy.rules) placed.add(rule.rule_id);
  }
  return candidates.filter((candidate) => !placed.has(candidate.rule.rule_id));
}

/** The verbatim sentence a rule was formulated from. */
function sourceSentence(rule: CanonicalRule): string {
  const stated = rule.formulation?.canonical?.source_text?.trim();
  if (stated) return stated;
  return rule.description.trim();
}

/**
 * The passage, quoted once.
 *
 * Each rule of a passage records the source text it was formulated from, and
 * those texts overlap heavily: of the three rules of `p9-E000072`, the second
 * records the first's whole sentence ahead of its own. Rendered per rule that
 * reads as the document repeating itself, which is exactly the noise a reviewer
 * has to see past to find what actually differs between the rules.
 *
 * So: exact duplicates collapse, and a text wholly contained in a longer one is
 * dropped in favour of the longer. What remains is joined in the order the
 * passage states it. Nothing is reworded, shortened or summarised — every
 * character shown is a character the document has.
 *
 * This is not a second opinion on grouping. It arranges the text of a group the
 * server has already decided.
 */
export function passageStatement(rules: readonly CanonicalRule[]): string {
  const seen = new Set<string>();
  const texts: string[] = [];
  for (const rule of rules) {
    const text = sourceSentence(rule);
    if (!text || seen.has(text)) continue;
    seen.add(text);
    texts.push(text);
  }
  const kept = texts.filter(
    (text, index) => !texts.some((other, position) => position !== index && other.includes(text)),
  );
  return kept.join(" ");
}

/**
 * What the document calls this passage.
 *
 * Taken from the citations' `section`, exactly as recorded. A passage whose
 * rules cite more than one heading keeps both rather than picking one, because
 * choosing silently would attribute the passage to a heading it may not sit
 * under. An empty result means no citation recorded a heading, which is a fact
 * about how the document was read and is stated as such rather than filled in.
 */
export function passageHeading(rules: readonly CanonicalRule[]): string {
  const headings: string[] = [];
  for (const rule of rules) {
    for (const reference of rule.evidence) {
      const heading = (reference.section ?? "").trim();
      if (heading && !headings.includes(heading)) headings.push(heading);
    }
  }
  return headings.join(" · ");
}

/** The page a passage sits on, when the assembly recorded one. */
export function passagePageLabel(page: number | null): string | null {
  return page === null ? null : `page ${page}`;
}

/**
 * The card as one document.
 *
 * The policy is the object and its rules are nested inside it, so what a
 * reviewer downloads has the same shape as what they decided on — one record,
 * not three that happen to have been listed together.
 *
 * `rules_hidden_by_filter` is present only when there are some. A JSON claiming
 * to be a whole passage while holding part of one is the same fragment-as-whole
 * failure as on screen, and harder to notice once the file has left the app.
 */
export function policyJsonDocument(card: PolicyCard): Record<string, unknown> {
  const rules = card.rules.map((rule) => rule.candidate.rule);
  const heading = passageHeading(rules);
  const document: Record<string, unknown> = {
    key: card.policy.key,
    source_elements: card.policy.source_elements,
    page: card.policy.page,
    heading: heading || null,
    passage: passageStatement(rules),
    rule_count: card.policy.rule_count,
    route: card.policy.route,
    rules,
  };
  if (card.hiddenByFilter > 0) document.rules_hidden_by_filter = card.hiddenByFilter;
  return document;
}
