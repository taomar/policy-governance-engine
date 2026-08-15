/**
 * The review queue's unit of decision: one section, one card.
 *
 * THE DEFECT THIS CLOSES
 *
 * Twice over, one level apart. First, a passage stating three rules was drawn
 * as a header over three rows, each row carrying its own checkbox, approve,
 * reject, record id and JSON — the grouping was an annotation on a list rather
 * than a change to what is being decided. Then, once that was fixed, two
 * consecutive sentences of `7.2. WORK PERMIT (IQAMA) & TRANSFERRING ONES
 * SPONSORSHIP` still came back as two cards bearing the same name, because the
 * key was the passage and a policy stated across several sentences can never be
 * joined by it.
 *
 * So the card is the section. Its passages are how the document says it and its
 * rules are its logic, and a reviewer forms one judgement about the whole.
 *
 * WHY THE GROUPING IS STILL NOT COMPUTED HERE
 *
 * `GET /policy-sets/{key}/policies` decides which rules belong together, on the
 * heading their evidence records, in `policy_assembly.py`. Everything below
 * reads that answer — including the inner passage boundary, which arrives from
 * the same fetch — and pairs it with the flat candidate list. No function here
 * decides membership, order, or count; a second opinion on grouping would be
 * free to disagree with the first, silently, on exactly the records where it
 * matters. This repository already carries the scar of two parsers.
 *
 * WHAT MUST SURVIVE CONTACT
 *
 * A policy of one rule is the ordinary case. It is built here by the same code
 * path as a policy of seventy-two and renders as an ordinary card, never as a
 * container with one thing in it.
 *
 * A bigger card must not mean fewer rules. A section holding fourteen shows
 * fourteen, each with its own id, route, condition and outcome, and each still
 * shown under the passage that stated it — because a reviewer reading a long
 * card has to see which words a rule came from.
 *
 * Route is a property of a rule. A card summarises the routes its rules take
 * for orientation and shows each rule's own route beside that rule; the summary
 * never replaces it, and neither route is a grade.
 *
 * A card must never present a fragment as a whole policy. The assembly is
 * unfiltered and the flat list is filtered, so the difference between them is
 * the number of rules the current filter is not showing — stated, not inferred.
 */

import type {
  AssembledPassage,
  AssembledPolicy,
  CandidateRule,
  CanonicalRule,
} from "./api";
import { candidateEditability } from "./candidateEditability";

/** One rule of a policy, as a card holds it.
 *
 *  Deliberately says nothing about *which* table the record came from. A draft
 *  row under review and a published row carry the same rule, and both surfaces
 *  draw the same card from it. Naming a candidate here was the one thing
 *  stopping the published page calling this, and a second copy of the layout
 *  was written instead — which is how two surfaces showing the same rules start
 *  disagreeing about them. */
export interface PolicyCardRule {
  rule_id: string;
  /** The rule itself. Both a draft row and a published row carry one, and it is
   *  what everything reading a card actually wants. */
  rule: CanonicalRule;
  /** Where this record stands. Read through `candidateEditability`, which is
   *  what decides whether anything may be decided about it — including on a
   *  published record, where the answer is no. */
  reviewStatus: string;
  /** This record's own id: the draft row's where there is one, otherwise the
   *  rule's. What a decision, a copied id or a history lookup addresses.
   *
   *  Always present, so nothing downstream has to handle its absence and no
   *  record is ever keyed by an id that resolves to nothing. */
  recordId: string;
  /** The fuller draft row, where the record is one.
   *
   *  Optional, and no consumer may require it: a published record has none.
   *  The review surface still needs it for editing and bulk actions, which are
   *  paths that only exist where a draft row does. */
  candidate?: CandidateRule;
  /** This rule's own route, from the assembly. Never summarised away. */
  evaluation_mode: string;
}

/**
 * A record a card can be built from, said structurally rather than by name.
 *
 * `CandidateRule` satisfies this, and so does anything else carrying a rule —
 * which is the point: the published page hands over rows from a different table
 * and gets the same cards, rather than a transliteration of this file that
 * drifts from it a commit at a time.
 */
export interface PolicyRecordInput {
  rule: CanonicalRule;
  /** Absent on records that were never under review. Treated as published,
   *  because a record with no review state is not one awaiting a decision. */
  review_status?: string;
  /** Absent on records identified by their rule alone. */
  id?: string;
}

/**
 * The card-rule fields a draft row supplies.
 *
 * One statement of how a row under review becomes a rule on a card, so the
 * mapping is written once rather than at every place that builds one. Spread
 * beside `rule_id` and `evaluation_mode`.
 */
export function fromDraftRow(
  candidate: CandidateRule,
): Pick<PolicyCardRule, "rule" | "reviewStatus" | "recordId" | "candidate"> {
  return {
    rule: candidate.rule,
    reviewStatus: candidate.review_status,
    recordId: candidate.id,
    candidate,
  };
}

/** One passage of a card: the sentence, and the rules stated in it.
 *
 *  Kept because the section is now the card. Fourteen rules run together would
 *  answer the owner's complaint by making a smaller version of it — the
 *  reviewer would see one policy and lose which of its words each obligation
 *  came from. */
export interface PolicyCardPassage {
  /** The server's passage, carried whole. */
  passage: AssembledPassage;
  /** Its rules that this filter is showing, in the order it states them. */
  rules: PolicyCardRule[];
}

export interface PolicyCard {
  /** The server's policy, carried whole so nothing downstream has to
   *  reconstruct it. */
  policy: AssembledPolicy;
  /** The passages of this section that have at least one rule in view. */
  passages: PolicyCardPassage[];
  /** Every rule on the card, flat, in document order — the same rules the
   *  passages hold, once each. What one decision writes to. */
  rules: PolicyCardRule[];
  /** Rules the policy states that this filter is not showing. Zero for the
   *  ordinary case; anything else has to be said out loud on the card. */
  hiddenByFilter: number;
  /** Candidate ids on this card that are open to a review decision. One
   *  approve writes to all of them. */
  reviewableIds: string[];
  /** Every candidate id on the card, reviewable or already decided. */
  allIds: string[];
  /** Distinct review states present, in the order first seen. More than one
   *  means part of the policy has already been decided. */
  reviewStatuses: string[];
}

/**
 * Pair the server's policies with the candidate records currently in view.
 *
 * `candidates` is the filtered flat list, so a card carries only the rules the
 * reviewer can presently see — and reports how many it is therefore not
 * showing. A policy with none of its rules in view produces no card at all
 * rather than an empty one, and a passage with none in view produces no block.
 *
 * WHY THIS AND `unplacedRules` SHARE ONE PASS
 *
 * They used to answer "is this rule placed?" from different fields. This one
 * walked `policy.passages`; that one walked `policy.rules`. When a policy
 * arrived carrying rules but no passages the two disagreed completely: this
 * built no card and dropped the policy, while that read every one of its rules
 * as placed and returned none of them. The result was a queue showing nothing
 * at all, over a payload holding hundreds of rules, with no line on screen
 * saying why — the rules had fallen through the gap between two views that each
 * believed the other was showing them.
 *
 * So there is now one pass and one definition, and the definition is *rendered*
 * rather than *listed*: a rule is placed when it came out on a card. A policy
 * that cannot be laid out therefore places nothing, and everything it holds
 * falls through to `unplacedRules`, which is a view that exists precisely
 * to keep rules on screen when the arrangement around them is missing.
 */
export function buildPolicyCards(
  policies: readonly AssembledPolicy[],
  candidates: readonly PolicyRecordInput[],
): PolicyCard[] {
  return placement(policies, candidates).cards;
}

/**
 * Records the assembly did not place.
 *
 * The two fetches do not always cover the same population: the flat list can
 * ask for superseded rows when a historical run is open, and the assembly does
 * not. A rule in that gap has to be shown — dropping a decision from the review
 * queue is the one failure worse than showing it ungrouped — and it has to be
 * shown as what it is rather than promoted to a passage of its own, because
 * "the server did not place this" and "the source stated this alone" are
 * different facts.
 *
 * A policy the queue could not lay out lands here too, for the same reason and
 * by the same test: nothing of it was drawn, so nothing of it is placed. That
 * is deliberately not repaired by inventing a passage to hold the rules. A
 * passage is a claim that the document stated these rules together in one run
 * of text, and manufacturing one to satisfy a layout would put a claim about
 * the source on screen that no reading of the source produced.
 *
 * Returns what it was given, so a caller gets its own row type back rather than
 * this file's idea of one.
 */
export function unplacedRules<T extends PolicyRecordInput>(
  policies: readonly AssembledPolicy[],
  candidates: readonly T[],
): T[] {
  return placement(policies, candidates).unplaced as T[];
}

interface Placement {
  cards: PolicyCard[];
  unplaced: PolicyRecordInput[];
}

/**
 * The last answer, kept so asking both questions costs one pass.
 *
 * The two exported views are read from separate `useMemo`s with the same two
 * arrays, so without this the work happens twice per render of a queue that can
 * run to hundreds of rules. Keyed on the identity of both inputs, never on
 * their contents: a caller that replaces an array gets a fresh answer, which is
 * how React state arrives. A caller that mutates one in place would not, and
 * nothing in this app does that — the arrays come from `setState`.
 */
let lastPlacement: {
  policies: readonly AssembledPolicy[];
  candidates: readonly PolicyRecordInput[];
  result: Placement;
} | null = null;

function placement(
  policies: readonly AssembledPolicy[],
  candidates: readonly PolicyRecordInput[],
): Placement {
  if (lastPlacement && lastPlacement.policies === policies && lastPlacement.candidates === candidates) {
    return lastPlacement.result;
  }
  const result = place(policies, candidates);
  lastPlacement = { policies, candidates, result };
  return result;
}

function place(
  policies: readonly AssembledPolicy[],
  candidates: readonly PolicyRecordInput[],
): Placement {
  const byRuleId = new Map<string, PolicyRecordInput>();
  for (const candidate of candidates) {
    if (!byRuleId.has(candidate.rule.rule_id)) byRuleId.set(candidate.rule.rule_id, candidate);
  }

  const cards: PolicyCard[] = [];
  for (const policy of policies) {
    const passages: PolicyCardPassage[] = [];
    // Absent and empty are the same thing to *this* loop — either way nothing
    // is drawn — but they must not be the same thing to the reader, and they
    // are not: what is not drawn here is not placed, and what is not placed is
    // shown by the other view with the reason attached.
    for (const passage of Array.isArray(policy.passages) ? policy.passages : []) {
      const rules: PolicyCardRule[] = [];
      for (const rule of Array.isArray(passage?.rules) ? passage.rules : []) {
        const candidate = byRuleId.get(rule.rule_id);
        if (!candidate) continue;
        rules.push({
          rule_id: rule.rule_id,
          rule: candidate.rule,
          // A record carrying no review state is not one awaiting a decision.
          // Read as published rather than as unrecognised, so the interface
          // explains it as an immutable snapshot instead of as a build that
          // does not know what it is looking at.
          reviewStatus: candidate.review_status ?? "published",
          recordId: candidate.id ?? rule.rule_id,
          // The wider input narrowed back, in the one place it happens. A
          // record carrying a draft row's id and its review state is a draft
          // row; a published row carries neither and stays undefined, so
          // nothing downstream can reach for a row that does not exist.
          candidate:
            candidate.id !== undefined && candidate.review_status !== undefined
              ? (candidate as CandidateRule)
              : undefined,
          evaluation_mode: rule.evaluation_mode,
        });
      }
      if (rules.length > 0) passages.push({ passage, rules });
    }
    const rules = passages.flatMap((passage) => passage.rules);
    if (rules.length === 0) continue;

    const reviewStatuses: string[] = [];
    for (const rule of rules) {
      if (!reviewStatuses.includes(rule.reviewStatus)) {
        reviewStatuses.push(rule.reviewStatus);
      }
    }

    cards.push({
      policy,
      passages,
      rules,
      // Counted against the policy's own total rather than against the rules
      // it happens to list, so a filter, a page and a stale assembly all read
      // the same way: this is not all of it.
      hiddenByFilter: Math.max(0, policy.rule_count - rules.length),
      // What one approve on this card will write to. A rule already approved,
      // rejected or published is not re-decided by a later decision on its
      // neighbours: that would overwrite a judgement somebody already made.
      // Read off the record's own state, never off whether a handler was
      // wired: a sealed record must stay sealed however it is drawn.
      reviewableIds: rules
        .filter((rule) => candidateEditability(rule.reviewStatus).canReview)
        .map((rule) => rule.recordId),
      allIds: rules.map((rule) => rule.recordId),
      reviewStatuses,
    });
  }

  // The one definition of placed, read off what was actually built. Not a
  // second walk of the policies that could drift from the first.
  const placed = new Set<string>();
  for (const card of cards) {
    for (const rule of card.rules) placed.add(rule.rule_id);
  }

  return {
    cards,
    unplaced: candidates.filter((candidate) => !placed.has(candidate.rule.rule_id)),
  };
}

/** The verbatim sentence a rule was formulated from. */
function sourceSentence(rule: CanonicalRule): string {
  const stated = rule.formulation?.canonical?.source_text?.trim();
  if (stated) return stated;
  return rule.description.trim();
}

/**
 * The passage, quoted — one entry per distinct statement, never joined.
 *
 * Each rule of a passage records the source text it was formulated from, and
 * those texts overlap heavily: of the three rules of `p9-E000072`, the second
 * records the first's whole sentence ahead of its own. Rendered per rule that
 * reads as the document repeating itself, which is exactly the noise a reviewer
 * has to see past to find what actually differs between the rules.
 *
 * So: exact duplicates collapse, and a text wholly contained in a longer one is
 * dropped in favour of the longer. What remains is returned in the order the
 * passage states it.
 *
 * WHY A LIST AND NOT A STRING
 *
 * This used to join what remained with a space and return one string. Every
 * character was the document's, but their *adjacency* was not: two texts the
 * document states as separate records came back as one run of prose, and a
 * reader had no way to see where one ended. That is composition — the smallest
 * possible amount of it, which is how it survived review twice — and this
 * product exists to not do it. A list cannot be joined by accident; a joined
 * string cannot be unjoined at all.
 *
 * This is not a second opinion on grouping. It arranges the text of a group the
 * server has already decided.
 */
export function passageQuotations(rules: readonly CanonicalRule[]): string[] {
  const seen = new Set<string>();
  const texts: string[] = [];
  for (const rule of rules) {
    const text = sourceSentence(rule);
    if (!text || seen.has(text)) continue;
    seen.add(text);
    texts.push(text);
  }
  return texts.filter(
    (text, index) => !texts.some((other, position) => position !== index && other.includes(text)),
  );
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
  /** The heading the policy is assembled under, quoted whole. The ordinary
   *  case for a card, and unique per card by construction. */
  | "heading"
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
  /** The passage minus whatever the title took from it, one entry per
   *  quotation. Rendered under the title as separate blocks, so title and
   *  remainder together are the passage, in order, once — and two quotations
   *  never arrive as one run of prose. */
  rest: string[];
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
 * What to call this passage, inside the card its section makes.
 *
 * MEASURED, NOT ASSUMED
 *
 * The heading names the card, and cannot also name the passages within it —
 * they all share it. So a passage block is named by its own words: 111 of 155
 * AIS passages and 179 of 187 GMU passages open with a statement, which is
 * unique by construction and names the topic in the document's language.
 *
 * The rest are rows of a table, which state no sentence. Naming those by their
 * heading was tried and measured badly: 50 AIS rows sit under "Table of
 * Violations and Penalties" and would all have carried it. Their own first cell
 * names them instead — "Late for work, 15 minutes or less without permission or
 * a valid reason, if it did not cause delay to other employees" — and every row
 * in the corpus has one: 45 of 45 on AIS (43 distinct) and 8 of 8 on GMU.
 *
 * NOTHING IS COMPOSED
 *
 * Every character of a title is a character the document has, in the document's
 * order. The title is not a summary of the passage — it is the passage's first
 * statement, with the remainder rendered directly beneath it. A reader who
 * reads the block top to bottom has read the passage, once, whole.
 *
 * A row is the exception to "once": its title is a cell of the row, and the row
 * is still rendered whole below, so that cell appears twice. Cutting the cell
 * out of the row to avoid that would leave a mangled row, and the row is the
 * evidence. Repetition is the lesser cost.
 *
 * The title is drawn from the passage's *first* quotation only. The others are
 * carried into `rest` unchanged, as separate blocks — a title that spanned two
 * quotations would be the joined string this function no longer builds.
 */
export function passageTitle(rules: readonly CanonicalRule[]): PassageTitle {
  const quotations = passageQuotations(rules);
  const passage = quotations[0] ?? "";
  const others = quotations.slice(1);
  const heading = passageHeading(rules);
  if (!passage) {
    return heading
      ? { source: "section", text: heading, rest: others }
      : { source: "unnamed", text: "", rest: others };
  }
  const [statement, rest] = firstStatement(passage.replace(PIPELINE_ANNOTATION, ""));
  const namesSomething = !looksLikeTableRow(statement) && statement.split(/\s+/).length >= 3;
  if (namesSomething) {
    // When the title is the head of the passage, the remainder is the rest of
    // it. When it is not — because an annotation stood in front — the whole
    // passage stays below, so that skipping the annotation for naming never
    // amounts to deleting text from the quotation.
    const head = passage.startsWith(statement) ? rest : passage;
    return {
      source: "statement",
      text: statement,
      rest: head ? [head, ...others] : others,
    };
  }
  // Nothing is taken from the passage, so the whole of it stays in view below
  // a title that is honest about where it came from.
  const cell = firstCell(passage.replace(PIPELINE_ANNOTATION, ""));
  if (cell) return { source: "cell", text: cell, rest: quotations };
  return heading
    ? { source: "section", text: heading, rest: quotations }
    : { source: "unnamed", text: "", rest: quotations };
}

/**
 * What to call this policy.
 *
 * The heading, exactly as the document wrote it — `7.1. THE EMPLOYMENT
 * CONTRACT`. The card *is* the section now, so the heading names the whole card
 * and no two cards share it: the collision that ruled the heading out as a
 * *passage* title is gone, because a heading is no longer above several cards.
 *
 * WHY THE HEADING IS READ AND NOT THE KEY
 *
 * It used to be both: the assembly keyed a policy by its heading text, so the
 * key could be shown. A persisted provision is keyed by a digest instead —
 * because two sections can be written under the same words and only their
 * position in the document tells them apart — and a digest is not a name. So
 * the heading arrives as its own field and is read from there. A card titled
 * `a7b3cc4423…` would be the `p9-E000074` failure again in a new alphabet.
 *
 * The card used to be titled "Stated together in one passage", which describes
 * why the rules were grouped rather than what they are about — a reviewer
 * scanning a queue of these learns nothing from being told each time that a
 * passage is a passage.
 *
 * A policy assembled without a heading falls back to its single passage's own
 * title, and says which it used. It exists so that a document read without
 * headings degrades to the previous behaviour rather than to a card called by
 * its element id or its digest. The server reports that case by sending no
 * heading rather than by sending the key it fell back to, so what is read here
 * is an absence — this never has to guess whether a string is a name.
 */
export function policyTitle(
  policy: Pick<AssembledPolicy, "key" | "heading" | "heading_path">,
  passages: readonly PolicyCardPassage[],
): PassageTitle {
  const heading = policy.heading?.trim() ?? "";
  const first = passages[0];
  if (heading) {
    return { source: "heading", text: heading, rest: [] };
  }
  if (!first) return { source: "unnamed", text: "", rest: [] };
  return passageTitle(first.rules.map((rule) => rule.rule));
}

/**
 * What the card knows about the generated subject name, as four distinct states.
 *
 * A discriminated union rather than a nullable string, because the cases a
 * reader must be able to tell apart are not "a string or not a string":
 *
 * - `named` — a label was generated and it says something the heading did not,
 * - `redundant` — a label was generated and it only repeats the heading,
 * - `unavailable` — one was asked for and nothing usable came back,
 * - `absent` — nobody has asked.
 *
 * Collapsing `unavailable` into `absent` would tell a reviewer "not generated
 * yet" about a policy the system has already failed on, and they would wait for
 * something that is not coming. The distinction is the same one `loadState.ts`
 * draws between a value that is missing and a value that is empty, and it is
 * drawn here for the same reason.
 *
 * `redundant` is separate from `absent` for the mirror of that reason. Both
 * render as nothing on the card, but they are opposite facts — one is "there is
 * no name", the other is "the name is already on the screen, in the document's
 * own words, directly below". Naming it keeps the export honest and keeps the
 * rule testable; conflating it would make "no eyebrow" mean two things and
 * quietly turn a display decision into a claim about the data.
 *
 * The empty-label case is deliberately absent from this union. An empty reply
 * is refused at generation and stored as an unavailable outcome, so no state
 * downstream ever has to render nothing as if it were a name.
 */
export type PolicyTopicLabelState =
  | { readonly state: "named"; readonly text: string; readonly provenance: string }
  | { readonly state: "redundant"; readonly text: string }
  | { readonly state: "unavailable" }
  | { readonly state: "absent" };

/** The words of a string, for comparing one string's content against another's.
 *
 *  Maximal runs of letters and digits, case-folded. Unicode-aware through the
 *  `u` flag, so an Arabic label tokenises the same way a Latin one does and
 *  neither is privileged. Nothing here knows what a word means, only where one
 *  ends — there is no stopword list, because a stopword list is a list of one
 *  language's words and this must work on a document in any language.
 */
function words(text: string): string[] {
  return (text.toLowerCase().match(/[\p{L}\p{N}]+/gu) ?? []);
}

/**
 * Does the label tell the reader anything the heading did not?
 *
 * The label exists to answer "what is this about?" when the heading does not.
 * Where the heading already answers it, a label repeating it is a second copy
 * of a fact the reader has, costing a line and teaching nothing — and worse,
 * training them to skip a line that elsewhere carries the whole value.
 *
 * Judged as a relation between two strings, never as a property of either, and
 * asked in one direction only: is the label's content already in the heading.
 * Not whether the two resemble each other — a heading may say a great deal the
 * label does not and still leave the label adding nothing.
 *
 * Two things stop a word-for-word membership test from answering that honestly,
 * and both are about the same word being written two ways rather than about two
 * different words.
 *
 * INFLECTION. `probationary` against `Probation`, `employee` against
 * `EMPLOYEES`, `confidential` against `CONFIDENTIALITY`. One is the other with
 * a tail. Matching a shared prefix catches this without a stemmer and without
 * knowing a language, but a bare prefix test would also let `a` match
 * `absence`. The guard is the shape of an inflection rather than a length
 * picked to fit: a tail hangs off a stem, so it is shorter than the stem it
 * hangs off. `probation` + `ary` passes; `a` + `bsence` does not.
 *
 * CONNECTIVES WRITTEN AS SYMBOLS. `ABSENCE, LATENESS, TARDINESS & LEAVE`
 * against `Absence and leave`. The heading joined its terms with a symbol and
 * the label joined them with a word, so a membership test reads the label's
 * conjunction as new content when it is the same connective in the other
 * notation. Each joining symbol standing between two words in the heading
 * therefore accounts for one label word that is otherwise unmatched. This is a
 * token-for-token exchange, not an allowance: a heading with no such symbol
 * grants nothing, and a label whose unmatched words outnumber them still adds
 * something. Deliberately not a stopword list — that would be one language's
 * words, and the corpus is not in one language.
 *
 * Digits are dropped before comparing, because a heading's ordinal numbers the
 * section rather than naming it, and the instruction forbids the label to carry
 * a number at all.
 *
 * THE DOCUMENT'S OWN NAME IS A GOVERNING NAME TOO.
 *
 * The heading chain is not the whole of what already names a card. One level
 * further out sits the document, and every policy in a document is part of it —
 * so a label repeating the document's name distinguishes nothing, for exactly
 * the reason a label repeating the heading distinguishes nothing. It is the
 * worse of the two failures, because it occupies the card's most prominent line
 * to restate the one fact a reviewer cannot be unaware of.
 *
 * Passed in rather than read here, and optional: a surface that does not know
 * which document a policy came from asks the narrower question and gets the
 * answer it had before. It joins the front of the chain because it governs
 * everything under it, and it goes through the same comparison as any heading —
 * there is no separate rule for it, and nothing here knows a document from a
 * section beyond where it sits in the chain.
 *
 * Widening it can only withhold more, never less: another governing name can
 * only match more of the label's words, and the connective allowance is counted
 * over the same text that is matched against.
 *
 * There is no threshold, no list of headings, no vocabulary, and nothing that
 * knows what a subject is. Compared against the whole chain rather than the
 * innermost heading because the card shows the whole chain, and a label
 * repeating an outer heading is as redundant as one repeating the inner.
 *
 * The decision is made here, at display, and never stored. It is a function of
 * two strings that can each change — a heading corrected, a label regenerated —
 * and a stored answer would go stale silently against both.
 */
export function labelAddsNothing(
  text: string,
  headingPath: readonly string[],
  documentName?: string | null,
): boolean {
  const governing = [documentName?.trim() || null, ...headingPath].filter(
    (name): name is string => Boolean(name),
  );
  const heading = governing.join(" ");
  const headingWords = words(heading).filter(isNotJustDigits);
  const labelWords = words(text).filter(isNotJustDigits);
  if (labelWords.length === 0) return true;

  const unmatched = labelWords.filter(
    (word) => !headingWords.some((candidate) => sameWordAllowingInflection(word, candidate)),
  );
  return unmatched.length <= joiningSymbolCount(heading);
}

/** Ordinals number a section; they never name its subject. */
function isNotJustDigits(word: string): boolean {
  return !/^\p{N}+$/u.test(word);
}

/** One word being the other plus a tail shorter than the stem it hangs off. */
function sameWordAllowingInflection(one: string, other: string): boolean {
  if (one === other) return true;
  const [shorter, longer] = one.length < other.length ? [one, other] : [other, one];
  if (!longer.startsWith(shorter)) return false;
  return longer.length - shorter.length < shorter.length;
}

/**
 * Symbols the heading used to join two words, each standing in for a connective
 * the label may have written out. Counted only between two word characters, so
 * a symbol used as anything else is not mistaken for a conjunction.
 */
function joiningSymbolCount(heading: string): number {
  return (heading.match(/[\p{L}\p{N}]\s*[&+/]\s*[\p{L}\p{N}]/gu) ?? []).length;
}

/**
 * Read the generated subject name off a policy.
 *
 * This never composes a label and never falls back to one. A fallback would be
 * this app naming a document's subject out of its own vocabulary — which is the
 * single thing the product exists not to do — so an absent label stays absent
 * all the way to the screen, where it is stated rather than filled in.
 *
 * `generated` is required to be true on the payload before the text is used. It
 * is the server's assertion that these words are ours, and a payload arriving
 * without it is not something this may present as a label.
 *
 * `documentName` is the name of the document the policy was read out of, where
 * the surface knows it. Omitting it asks the narrower redundancy question and
 * is always safe; supplying it lets the answer account for the outermost name
 * governing the card.
 */
export function policyTopicLabel(
  policy: Pick<AssembledPolicy, "topic_label" | "heading_path">,
  documentName?: string | null,
): PolicyTopicLabelState {
  const label = policy.topic_label;
  if (!label || label.generated !== true) return { state: "absent" };
  const text = label.text?.trim() ?? "";
  if (!text) return { state: "unavailable" };
  if (labelAddsNothing(text, policy.heading_path ?? [], documentName)) {
    return { state: "redundant", text };
  }
  // Provenance travels with the words, not in a lookup somewhere else. A reader
  // asking "where did this come from" is asking about the string in front of
  // them, and the answer has to be reachable from it.
  const parts = [label.model_deployment, label.generated_at, label.prompt_version];
  return {
    state: "named",
    text,
    provenance: parts.filter((part): part is string => Boolean(part)).join(" · "),
  };
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
    ruleType: shared(card.rules.map((rule) => rule.rule.rule_type)),
    effectType: shared(card.rules.map((rule) => rule.rule.effect?.type ?? "")),
    route: shared(card.rules.map((rule) => rule.evaluation_mode)),
    reviewStatus: shared(card.rules.map((rule) => rule.reviewStatus)),
    revision: shared(card.rules.map((rule) => rule.rule.rule_revision)),
  };
}

/**
 * The card as one document.
 *
 * The policy is the object, its passages are nested inside it and its rules
 * inside those, so what a reviewer downloads has the same shape as what they
 * decided on — one record, not three that happen to have been listed together,
 * and not one that has forgotten which sentence each rule came from.
 *
 * `rules_hidden_by_filter` is present only when there are some. A JSON claiming
 * to be a whole policy while holding part of one is the same fragment-as-whole
 * failure as on screen, and harder to notice once the file has left the app.
 */
export function policyJsonDocument(
  card: PolicyCard,
  documentName?: string | null,
): Record<string, unknown> {
  const title = policyTitle(card.policy, card.passages);
  const document: Record<string, unknown> = {
    key: card.policy.key,
    // Null rather than absent, and null rather than the key: a policy the
    // assembly could not file under a heading has no heading, and saying so is
    // different from silently repeating its element id or its digest as one.
    heading: title.source === "heading" ? card.policy.heading : null,
    // The chain of headings that governs this section, outermost first, each
    // verbatim. An array and not a path string: a separator would be a
    // character the document never wrote between two of its own headings.
    heading_path: card.policy.heading_path,
    title: title.text || null,
    // Said in the file as well as on screen: a reader opening this a year from
    // now should not have to guess whether the title is the document's
    // heading, a sentence of the passage, or something this app made up.
    title_from: title.source,
    // Ours, and filed apart from every key above that holds the document's
    // characters. Under its own object with its own provenance so that a
    // consumer reading `heading`, `heading_path`, `title` or `quotations` never
    // picks this up by accident, and so that a reader opening the file a year
    // from now can see it was generated, by what, and when.
    generated_topic_label:
      card.policy.topic_label && card.policy.topic_label.generated === true
        ? {
            generated: true as const,
            text: card.policy.topic_label.text,
            unavailable_code: card.policy.topic_label.unavailable_code,
            model_deployment: card.policy.topic_label.model_deployment,
            prompt_version: card.policy.topic_label.prompt_version,
            generated_at: card.policy.topic_label.generated_at,
            // Whether the card showed it. A label that only repeats the
            // heading, or the document's own name, is withheld on screen but
            // kept here: the file records what was generated, and separately
            // what a reader was shown, so neither can be inferred wrongly from
            // the other. Asked with the same document name the card had, so the
            // two answers cannot disagree.
            shown_on_card: policyTopicLabel(card.policy, documentName).state === "named",
          }
        : null,
    source_elements: card.policy.source_elements,
    page: card.policy.page,
    rule_count: card.policy.rule_count,
    passage_count: card.policy.passage_count,
    route: card.policy.route,
    // Whether the pipeline recorded this grouping or the reader's request
    // derived it. A file that does not say cannot be told apart later from one
    // that does.
    persisted: card.policy.persisted,
    // Which persisted provision this policy is, when it is one. The same
    // identity the flat candidate list carries, so an exported file can be
    // rejoined to the queue it came from without matching headings.
    provision_id: card.policy.provision_id ?? null,
    passages: card.passages.map((block) => {
      const rules = block.rules.map((rule) => rule.rule);
      const passageName = passageTitle(rules);
      return {
        key: block.passage.key,
        source_elements: block.passage.source_elements,
        page: block.passage.page,
        title: passageName.text || null,
        title_from: passageName.source,
        // A list, one entry per distinct statement. It was a single joined
        // string; two texts the document states apart came out of the file as
        // one run of prose, and nothing downstream could separate them again.
        quotations: passageQuotations(rules),
        rules,
      };
    }),
  };
  if (card.hiddenByFilter > 0) document.rules_hidden_by_filter = card.hiddenByFilter;
  return document;
}
