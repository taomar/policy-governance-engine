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

/** Where a card's name came from. Always one of the document's own strings. */
export type PassageTitleSource =
  /** The passage's opening statement, quoted whole. */
  | "statement"
  /** The passage is a row of a table and states no sentence. Named by its own
   *  first cell, quoted whole, with the row left intact below it. */
  | "cell"
  /** The heading the passage sits under — used when the passage offers neither
   *  a statement nor a readable cell. */
  | "section"
  /** The document supplied neither. Named by its passage key, and said so. */
  | "unnamed";

export interface PassageTitle {
  source: PassageTitleSource;
  /** The name, verbatim. Empty only when the source is `unnamed`. */
  text: string;
  /** The passage minus whatever the title took from it. Rendered under the
   *  title, so title and remainder together are the passage, in order, once. */
  rest: string;
}

/**
 * A break between statements: after a full stop, or at a line end.
 *
 * `\u061F` is the Arabic question mark — both documents in the corpus are
 * bilingual, and a sentence that ends in Arabic ends just as much as one that
 * ends in English.
 */
const STATEMENT_BREAK = /(?<=[.!?\u061F])\s+|\n+/g;

/**
 * Split a passage at its first statement end.
 *
 * A break is only taken where what precedes it is a clause rather than a list
 * marker. "1. In keeping with the provisions of The Saudi Labor Law, employees
 * are entitled to 30 calendar days paid sick leave." has a full stop after the
 * enumerator, and a splitter that trusts it names the card "1." — which is how
 * the first measurement of this idea reported 7 unusable passages that were in
 * fact fine.
 */
function firstStatement(passage: string): [string, string] {
  const breaks = new RegExp(STATEMENT_BREAK.source, "g");
  let match: RegExpExecArray | null;
  while ((match = breaks.exec(passage)) !== null) {
    const left = passage.slice(0, match.index).trim();
    if (left.length >= 20 && left.split(/\s+/).length >= 4) {
      return [left, passage.slice(match.index + match[0].length).trim()];
    }
  }
  return [passage.trim(), ""];
}

/**
 * A marker the extraction wrote into the passage rather than read out of the
 * document: `(section: Table of Violations and Penalties) 10. | …`.
 *
 * Six AIS passages carry one and no GMU passage does. It is skipped when
 * choosing a name — a title has to be the document's words, and this is the
 * pipeline's. It is not removed from the passage text itself, because that text
 * is quoted as the record holds it and editing it here would make the quotation
 * a paraphrase.
 */
const PIPELINE_ANNOTATION = /^\(\s*section\s*:[^)]*\)\s*/i;

/** A row of an extracted table: cells separated by pipes, never a sentence. */
function looksLikeTableRow(text: string): boolean {
  return /\s\|\s/.test(text) || (text.match(/\|/g) ?? []).length >= 2;
}

/**
 * The first cell of a table row that says something.
 *
 * A row arrives as pipe-delimited cells, the first of which are often a row
 * number and blanks: `4. | | Failure to follow health regulations… | 50%
 * deduction | …`. The first cell carrying a clause is what the row is about —
 * the offence, the grade, the allowance — and it is unique per row where the
 * heading above it is not.
 *
 * The enumerator is stripped from the front of a cell but nothing else is
 * touched: what is returned is a substring of the document.
 */
function firstCell(passage: string): string | null {
  for (const raw of passage.split("|")) {
    const cell = raw.trim().replace(/^\d+[.)]\s*/, "").trim();
    if (cell.length >= 20 && cell.split(/\s+/).length >= 4) return cell;
  }
  return null;
}

/**
 * What to call this policy.
 *
 * MEASURED, NOT ASSUMED
 *
 * The heading was the obvious candidate and the data rules it out on its own:
 * 146 of 155 AIS passages and 175 of 187 GMU passages sit under a heading they
 * share with another passage — 94% on both. 50 passages share "Table of
 * Violations and Penalties". Titling by heading would have swapped one
 * uninformative label ("Stated together in one passage") for another.
 *
 * The passage's own opening statement is unique by construction and names the
 * topic in the document's words: 111 of 155 and 179 of 187 passages have one.
 *
 * The rest are rows of a table, which state no sentence. Naming those by their
 * heading was tried and measured badly: 50 AIS rows sit under "Table of
 * Violations and Penalties" and would all have carried it. Their own first cell
 * names them instead — "Late for work, 15 minutes or less without permission or
 * a valid reason, if it did not cause delay to other employees" — and every row
 * in the corpus has one: 45 of 45 on AIS (43 distinct) and 8 of 8 on GMU.
 * The heading stays above the title as the section the card sits under.
 *
 * NOTHING IS COMPOSED
 *
 * Every character of a title is a character the document has, in the document's
 * order. The title is not a summary of the passage — it is the passage's first
 * statement, with the remainder rendered directly beneath it. A reader who
 * reads the card top to bottom has read the passage, once, whole.
 *
 * A row is the exception to "once": its title is a cell of the row, and the row
 * is still rendered whole below, so that cell appears twice. Cutting the cell
 * out of the row to avoid that would leave a mangled row, and the row is the
 * evidence. Repetition is the lesser cost.
 */
export function passageTitle(rules: readonly CanonicalRule[]): PassageTitle {
  const passage = passageStatement(rules);
  const heading = passageHeading(rules);
  if (!passage) {
    return heading
      ? { source: "section", text: heading, rest: "" }
      : { source: "unnamed", text: "", rest: "" };
  }
  const [statement, rest] = firstStatement(passage.replace(PIPELINE_ANNOTATION, ""));
  const namesSomething = !looksLikeTableRow(statement) && statement.split(/\s+/).length >= 3;
  if (namesSomething) {
    // When the title is the head of the passage, the remainder is the rest of
    // it. When it is not — because an annotation stood in front — the whole
    // passage stays below, so that skipping the annotation for naming never
    // amounts to deleting text from the quotation.
    return {
      source: "statement",
      text: statement,
      rest: passage.startsWith(statement) ? rest : passage,
    };
  }
  // Nothing is taken from the passage, so the whole of it stays in view below
  // a title that is honest about where it came from.
  const cell = firstCell(passage.replace(PIPELINE_ANNOTATION, ""));
  if (cell) return { source: "cell", text: cell, rest: passage };
  return heading
    ? { source: "section", text: heading, rest: passage }
    : { source: "unnamed", text: "", rest: passage };
}

/**
 * What every rule of the card says the same way.
 *
 * A field is returned when all the rules agree on it and `null` when they do
 * not. The card states the agreed facts once, on the policy, and the differing
 * ones on the rule each belongs to — so a badge appearing beside a rule always
 * means "this rule, unlike its neighbours", and never "the third identical copy
 * of the card's only value".
 *
 * The split is not cosmetic. Across the corpus rule type differs within a
 * passage 65% of the time on AIS and 57% on GMU, and effect differs 44% and
 * 47%; review status and revision never differ today but can, the moment part
 * of a passage is decided. Route agrees 99% of the time — and the 1% is
 * precisely the case that must not be flattened, so it is reported here like
 * any other disagreement rather than being averaged into one badge.
 */
export interface SharedRuleFacets {
  ruleType: string | null;
  effectType: string | null;
  route: string | null;
  reviewStatus: string | null;
  revision: number | null;
}

function shared<T>(values: readonly T[]): T | null {
  if (values.length === 0) return null;
  const first = values[0];
  return values.every((value) => value === first) ? first : null;
}

export function sharedRuleFacets(card: PolicyCard): SharedRuleFacets {
  return {
    ruleType: shared(card.rules.map((rule) => rule.candidate.rule.rule_type)),
    effectType: shared(card.rules.map((rule) => rule.candidate.rule.effect?.type ?? "")),
    route: shared(card.rules.map((rule) => rule.evaluation_mode)),
    reviewStatus: shared(card.rules.map((rule) => rule.candidate.review_status)),
    revision: shared(card.rules.map((rule) => rule.candidate.rule.rule_revision)),
  };
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
  const title = passageTitle(rules);
  const document: Record<string, unknown> = {
    key: card.policy.key,
    source_elements: card.policy.source_elements,
    page: card.policy.page,
    heading: heading || null,
    title: title.text || null,
    // Said in the file as well as on screen: a reader opening this a year from
    // now should not have to guess whether the title is the document's
    // sentence, the heading above it, or something this app made up.
    title_from: title.source,
    passage: passageStatement(rules),
    rule_count: card.policy.rule_count,
    route: card.policy.route,
    rules,
  };
  if (card.hiddenByFilter > 0) document.rules_hidden_by_filter = card.hiddenByFilter;
  return document;
}
