/**
 * What a reviewer has to read on a card, and what they can be spared.
 *
 * THE QUESTION THE CARD EXISTS TO ANSWER
 *
 * One: *does this faithfully and completely capture what the document says
 * here?* Everything on the card either serves that judgement or is in its way.
 *
 * The card was in its own way. A single-rule policy printed the same sentence
 * three times — as the quoted source, as the rule's statement, and a third time
 * split across `WHEN … → THEN …`:
 *
 *     • In order to process your Iqama, you will be needed to take a medical test.
 *     ① you will be needed to take a medical test
 *       WHEN In order to process your Iqama → THEN take a medical test
 *
 * A reviewer reads that three times and learns nothing on the second or third
 * pass. The document's words go once; what we made of them goes once; the
 * difference between those two *is* the review.
 *
 * MEASURED ON BOTH DOCUMENTS, 692 RULES
 *
 * Every reduction below is a measurement, not a preference:
 *
 *   - The outcome is already inside the statement for 240 of 279 AIS rules and
 *     375 of 413 GMU rules — 86% and 91%. `THEN take a medical test` after a
 *     statement reading "you will be needed to take a medical test" is the same
 *     words a third time. So the outcome is printed only when the statement
 *     does not already contain it.
 *   - 84 AIS rules and 174 GMU rules — 30% and 42% — narrow nothing, and used
 *     to render `WHEN Always`. That is a slot filled with the absence of a
 *     value. The claim still has to be visible, because a reviewer is checking
 *     whether we dropped a condition the document states, so it is said in
 *     words instead of keyed.
 *   - 112 AIS statements and 215 GMU statements — 40% and 52% — are an exact
 *     span of the passage they were read from, whitespace aside. Those can be
 *     shown *in* the source rather than beside it.
 *   - Where a statement is a span covering nearly the whole quotation, printing
 *     it again beneath is a straight duplicate: 32 AIS and 86 GMU rules repeat
 *     80% or more of their passage. Those name themselves by the sentence.
 *
 * WHY MARK THE SOURCE RATHER THAN QUOTE IT TWICE
 *
 * The reviewer's question has two halves. *Faithfully* is answered by reading
 * our statement against the source. *Completely* is answered by seeing which of
 * the document's words we took and which we left — and a mark on the source
 * answers that at a glance, where two blocks of similar prose do not.
 *
 * NOTHING HERE COMPOSES, SHORTENS OR REWRITES
 *
 * Marks are offsets into the stored text; the text is rendered whole and
 * unaltered, and every string returned is either the document's or a field the
 * extraction already produced. A statement is withheld from the rule row only
 * when the identical words are on screen immediately above it, marked as that
 * rule's — never when they are absent, and never behind a control.
 */
import type { CanonicalRule } from "./api";
import { ruleDecisionSummary } from "./ruleDisplay";

export interface Span {
  start: number;
  end: number;
}

/** A run of a quotation that became a rule, tied to that rule's number. */
export interface QuotationMark extends Span {
  ordinal: number;
}

export interface MarkedQuotation {
  text: string;
  marks: QuotationMark[];
}

export interface RuleReading {
  /** Position on the card, counted across the whole policy. */
  ordinal: number;
  /** What we made of the source. Always present; see `statementIsMarkedWhole`. */
  statement: string;
  /**
   * The statement is on screen already, marked inside the quotation above, and
   * is nearly all of it. The row says so rather than printing the sentence a
   * second time — the words are visible either way.
   */
  statementIsMarkedWhole: boolean;
  /** Which quotation carries this rule's words, when one does. */
  markedIn: number | null;
  /** What narrows the rule, in the source's words. Null when nothing does. */
  condition: string | null;
  /** True when `condition` is the source's wording rather than a compiled test. */
  conditionIsStatedOnly: boolean;
  /** The outcome, and only when the statement does not already say it. */
  outcome: string | null;
}

export interface PassageReading {
  quotations: MarkedQuotation[];
  rules: RuleReading[];
}

/** Letters and digits of any script, which is all that "the same words" needs. */
function words(text: string): string[] {
  return text.toLowerCase().match(/[\p{L}\p{N}]+/gu) ?? [];
}

/**
 * `needle`'s words appear in `haystack`, in order and adjacent.
 *
 * Compared as whole words with the punctuation and casing dropped, so "take a
 * medical test" is found inside "you will be needed to take a medical test."
 * Padded on both sides so "test" is not found inside "testimony".
 */
export function containsPhrase(haystack: string, needle: string): boolean {
  const straw = words(haystack).join(" ");
  const pin = words(needle).join(" ");
  if (!pin) return false;
  return ` ${straw} `.includes(` ${pin} `);
}

function escapeRegExp(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/**
 * Where `needle` sits inside `text`, exactly.
 *
 * Character offsets into the stored string, so what gets marked is the
 * document's own run and nothing adjacent. Whitespace is allowed to differ,
 * because a passage keeps the line breaks of the page it came off and a title
 * does not: four AIS statements match on words and not on characters, and they
 * are the same words.
 *
 * Nothing is matched loosely beyond that. A statement that is a paraphrase gets
 * no mark, which is correct — it is not the document's run, and saying it was
 * would be the one lie this screen cannot tell.
 */
export function findSpan(text: string, needle: string): Span | null {
  const trimmed = needle.trim();
  // Too short to be a statement, and short strings collide: "AIS" would mark
  // the first three letters of every mention in the passage.
  if (trimmed.length < 8) return null;
  const direct = text.indexOf(trimmed);
  if (direct >= 0) return { start: direct, end: direct + trimmed.length };
  const spaced = new RegExp(escapeRegExp(trimmed).replace(/\s+/g, "\\s+"));
  const match = spaced.exec(text);
  return match ? { start: match.index, end: match.index + match[0].length } : null;
}

/** The share of a quotation's words a span covers. */
function coverage(quotation: string, span: Span): number {
  const whole = words(quotation).length;
  if (whole === 0) return 0;
  return words(quotation.slice(span.start, span.end)).length / whole;
}

/**
 * A statement that is essentially the whole quotation.
 *
 * The threshold is four fifths, which separates "the sentence, with the
 * enumerator or a trailing clause left off" from "one obligation out of a
 * sentence that states three". Below it the statement is printed in its own
 * right, because the reviewer would otherwise have to work out which part of a
 * long sentence the rule is.
 */
const WHOLE = 0.8;

/**
 * Read one passage: its quotations with the runs each rule was taken from, and
 * the rules with what is left to say about them.
 *
 * `firstOrdinal` is where this passage's rules start in the card's numbering.
 * Rules are numbered across the whole policy, so "rule 9" means the same thing
 * on the card, in the detail panel and out loud.
 */
export function readPassage(
  quotations: readonly string[],
  rules: readonly CanonicalRule[],
  firstOrdinal: number,
): PassageReading {
  const marked: MarkedQuotation[] = quotations.map((text) => ({ text, marks: [] }));
  const readings: RuleReading[] = [];

  rules.forEach((rule, index) => {
    const ordinal = firstOrdinal + index;
    const statement = (rule.title ?? "").trim();
    const decision = ruleDecisionSummary(rule);
    const outcome = decision.action?.trim() ?? "";

    let markedIn: number | null = null;
    let statementIsMarkedWhole = false;
    for (let i = 0; i < marked.length; i += 1) {
      const span = findSpan(marked[i].text, statement);
      if (!span) continue;
      // Two rules whose runs overlap cannot both be marked without one of them
      // claiming words that became the other. The first keeps the mark; the
      // second prints its statement, which is where it would have been anyway.
      const clash = marked[i].marks.some((mark) => span.start < mark.end && mark.start < span.end);
      if (!clash) {
        marked[i].marks.push({ ...span, ordinal });
        markedIn = i;
        statementIsMarkedWhole = coverage(marked[i].text, span) >= WHOLE;
      }
      break;
    }

    readings.push({
      ordinal,
      statement,
      statementIsMarkedWhole,
      markedIn,
      condition: decision.unconditional ? null : decision.condition,
      conditionIsStatedOnly: decision.conditionIsStatedOnly,
      outcome: !outcome || containsPhrase(statement, outcome) ? null : outcome,
    });
  });

  for (const quotation of marked) quotation.marks.sort((a, b) => a.start - b.start);
  return { quotations: marked, rules: readings };
}
