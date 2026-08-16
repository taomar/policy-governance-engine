/**
 * Whether a record constrains anyone — the one question that sorts a policy's
 * rules without reading a word of them.
 *
 * ## Why this axis and not a topical one
 *
 * The obvious way to separate a policy's definitions from its rules is to ask
 * what each one is *about*: general statements, preambles, statements about the
 * document itself. That question cannot be answered without a vocabulary, and a
 * vocabulary is the one thing this project may not build. It would be a list of
 * words from one domain, in one language, and it would not survive Arabic or the
 * next customer's documents. This codebase has already refuted one content-based
 * signal by counterexample and abandoned it; this would be the second.
 *
 * So the axis is not what a record is about but what it *does*: a record either
 * decides what happens, or it supplies meaning. Prefaces, welcome messages,
 * copyright notices, definitions and classifications constrain nobody and fall
 * on the second side by construction — nobody has to decide what counts as
 * "general", and nothing here reads the words.
 *
 * ## Why the effect and not the rule type
 *
 * The extractor already made this judgement, once, per rule, with the document
 * in front of it. `effect.type` is that judgement. Re-deriving it in the client
 * would be a second opinion about a record the client cannot see the source of,
 * and two opinions is how the two surfaces of this app drifted apart in the
 * first place.
 *
 * Measured on the live corpus, `effect.type == "informational"` is a strict
 * superset of `rule_type == "definition"`: it also catches the calculation
 * records that likewise decide nothing. The older test was not merely less
 * principled, it was wrong on the data.
 *
 * ## Nothing here ranks anything
 *
 * A record that supplies meaning is not a lesser record, an incidental one, or
 * one that can be skipped. A wrong definition is a real defect and needs the
 * same review as a wrong prohibition. This module orders rules for scanning and
 * says nothing about their worth; no count, ordering or wording built on it may
 * imply otherwise.
 */

/**
 * What a record does, as three outcomes rather than two.
 *
 * `unstated` is not a default and not a bucket for awkward cases: it is the
 * honest answer when the record carries no effect to read. Folding it into
 * either side would put a record the app knows nothing about into a group that
 * claims to know something about it.
 */
export type RecordStance = "decides" | "supplies-meaning" | "unstated";

/** The effect value that means "this record settles what words mean". */
const SUPPLIES_MEANING = "informational";

/**
 * Anything with an effect this app has never met counts as constraining.
 *
 * The four effect kinds in the schema today are not treated as a closed set,
 * because a fifth would then land silently on whichever side the code happened
 * to fall through to. Asking "is this the one kind that constrains nobody" and
 * treating every other answer as constraining means an unfamiliar record
 * surfaces among the rules a reviewer reads, where it is visible and can be
 * questioned, rather than disappearing into the glossary where it is not.
 */
export function recordStance(
  record: { effect?: { type?: string | null } | null } | null | undefined,
): RecordStance {
  const type = record?.effect?.type;
  if (typeof type !== "string" || type.length === 0) return "unstated";
  return type === SUPPLIES_MEANING ? "supplies-meaning" : "decides";
}

/**
 * The order stances are read in.
 *
 * Records that bind someone come first because they are what an approval
 * decides; a reviewer who reads no further has still read the part that carries
 * consequences. `unstated` comes last so it reads as the open question it is,
 * rather than as a third category of record.
 */
export const STANCE_ORDER: readonly RecordStance[] = ["decides", "supplies-meaning", "unstated"];

/** A run of records that answer the constraining question the same way. */
export interface StanceGroup<T> {
  stance: RecordStance;
  items: T[];
}

/**
 * Group records by stance, keeping the order they arrived in within each group.
 *
 * The incoming order is the document's, and it is the only record of where a
 * rule sits in its source. Grouping re-orders across stances and never within
 * one, so the document's sequence survives inside each group and a caller that
 * renders positions computed beforehand still tells the truth about them.
 *
 * Groups that would be empty are absent rather than present and empty, for the
 * reason a count of zero is never printed on these cards: zero is the shape a
 * shortfall takes, and a policy that defines nothing has no shortfall.
 */
export function groupByStance<T>(
  items: readonly T[],
  stanceOf: (item: T) => RecordStance,
): StanceGroup<T>[] {
  const groups = new Map<RecordStance, T[]>();
  for (const item of items) {
    const stance = stanceOf(item);
    const existing = groups.get(stance);
    if (existing) existing.push(item);
    else groups.set(stance, [item]);
  }
  return STANCE_ORDER.filter((stance) => groups.has(stance)).map((stance) => ({
    stance,
    items: groups.get(stance) as T[],
  }));
}

/**
 * The stance of a group of records taken together.
 *
 * A group holding records of more than one stance has no single stance, and
 * says so rather than reporting its majority. This is what lets a passage that
 * both defines a term and states a rule stay where the document put it instead
 * of being filed under whichever kind it happens to hold more of.
 */
export function stanceOfMany(stances: readonly RecordStance[]): RecordStance | "mixed" | null {
  if (stances.length === 0) return null;
  const first = stances[0];
  return stances.every((stance) => stance === first) ? first : "mixed";
}

/**
 * How a group of records is introduced on screen.
 *
 * Phrased as what the records do, in the same words the composition count uses,
 * so a reviewer reading "3 decide what happens" at the head of a card meets the
 * same verb again over the group those three are in. Neither heading carries a
 * comparative: one is not the important group and the other the leftovers.
 *
 * WHY NOT "decides a case". That was the wording until a reader who governs a
 * business asked what a case was. "A case" is what this app calls a situation
 * put to a rule; it is the vocabulary of the thing doing the deciding, not of
 * the person reading the answer, and it appeared on a tab written for that
 * person. What the reader wants to know is whether the rule settles an outcome
 * or explains a word, and that can be said without a term of art.
 */
export function stanceHeading(stance: RecordStance, count: number): string {
  if (stance === "decides") {
    return count === 1 ? "Decides what happens" : "Decide what happens";
  }
  if (stance === "supplies-meaning") {
    return count === 1 ? "Supplies a meaning" : "Supply meanings";
  }
  return count === 1
    ? "Does not state whether it decides or defines"
    : "Do not state whether they decide or define";
}

/**
 * What the grouping is, said once, for a reader who wonders why the order
 * changed. Names the source of the answer, because a reviewer who disagrees
 * with a placement needs to know the record decided it and not this screen.
 */
export const STANCE_GROUPING_NOTE =
  "Grouped by what each rule does, as its own effect states it. Numbers keep each rule's place in the document.";

/** How many records take one stance. Only stances actually present appear. */
export interface StanceTally {
  stance: RecordStance;
  count: number;
}

/**
 * What a policy is made of, as one count per stance actually present.
 *
 * Every record lands in exactly one tally, so the counts sum to the number of
 * records passed and a reader can check the arithmetic against the head count.
 * That is the whole point of returning tallies rather than a pair of numbers:
 * a shape with a fixed number of slots cannot represent a record whose effect
 * it did not expect, so it has to put that record somewhere it does not belong
 * — and the sum still adds up, which is what makes the error invisible.
 *
 * Stances with no records are absent rather than present as zero. Zero is the
 * shape a shortfall takes, and a policy that defines nothing is not short of
 * definitions.
 */
export function stanceComposition<T>(
  items: readonly T[],
  stanceOf: (item: T) => RecordStance,
): StanceTally[] {
  const counts = new Map<RecordStance, number>();
  for (const item of items) {
    const stance = stanceOf(item);
    counts.set(stance, (counts.get(stance) ?? 0) + 1);
  }
  return STANCE_ORDER.filter((stance) => counts.has(stance)).map((stance) => ({
    stance,
    count: counts.get(stance) as number,
  }));
}

/**
 * One tally as a phrase, in the same verbs the group headings use.
 *
 * Kept beside `stanceHeading` on purpose: a reviewer who reads "3 decide what
 * happens" at the head of a card meets "Decide what happens" again over the
 * group those three are in, and does not have to work out that they refer to
 * the same rules.
 */
export function stanceTallyPhrase({ stance, count }: StanceTally): string {
  if (stance === "decides") {
    return count === 1 ? "1 decides what happens" : `${count} decide what happens`;
  }
  if (stance === "supplies-meaning") {
    return count === 1 ? "1 supplies a meaning" : `${count} supply meanings`;
  }
  return count === 1 ? "1 does not state which" : `${count} do not state which`;
}

/**
 * The composition as a phrase, or null when there is nothing to contrast.
 *
 * Built from whatever stances are present rather than from a fixed pair of
 * slots. A policy holding rules of one kind returns null: the head already
 * carries the total, so the only thing this could add is a zero for the kind
 * the policy does not hold, and "12 decide what happens · 0 supply meanings" invites
 * the reader to look for twelve missing definitions that were never missing.
 * A policy whose records carry an effect this app has not met says so here
 * instead of being quietly counted as something it is not.
 */
export function compositionPhrase(tally: readonly StanceTally[]): string | null {
  if (tally.length <= 1) return null;
  return tally.map(stanceTallyPhrase).join(" · ");
}

/**
 * Which of a policy's rules a reviewer is looking at, and what they may choose.
 *
 * ## Why the shown records and the chip counts come from one call
 *
 * A control that narrows a list is two derivations if it is built the obvious
 * way: one deciding what the buttons say, another deciding what the list holds.
 * They agree until they do not, and the failure is silent — a chip reading
 * "15 supply meanings" over a list of fourteen. Both come from here, from one
 * pass over one set of records, so they cannot disagree.
 *
 * ## Why an unrecognised focus is not an error
 *
 * `requested` is view state held by whoever renders this, and view state
 * outlives the thing it describes: a reviewer focuses the definitions of one
 * policy and opens another that has none. Answering with everything, and
 * reporting the focus as cleared, is the only behaviour that cannot hide a
 * record. The caller is told what the effective focus is rather than what it
 * asked for, so the buttons it draws describe the list it actually has.
 *
 * ## What this deliberately does not do
 *
 * Narrowing here is a reading aid over one policy the reviewer already has
 * open. It changes what is on screen and nothing else — no record is removed
 * from the policy, and no action taken on the policy is scoped by it. Anything
 * that decides, approves, exports or publishes reads the policy's rules, never
 * this. That distinction is the whole reason this is safe where an earlier
 * filter across policies was not: that one made a card a fragment while its
 * Approve still called itself policy-level.
 */
export interface StanceFocus<T> {
  /** One entry per stance the policy actually holds, in reading order. */
  tally: StanceTally[];
  /** The focus in force — `null` when every record is shown. */
  focus: RecordStance | null;
  /** The records to render under that focus. */
  shown: readonly T[];
  /** Every record the policy holds, whatever the focus. */
  total: number;
  /** True when the reviewer could meaningfully choose, i.e. more than one stance. */
  choosable: boolean;
}

export function composeFocus<T>(
  items: readonly T[],
  stanceOf: (item: T) => RecordStance,
  requested: RecordStance | null,
): StanceFocus<T> {
  const tally = stanceComposition(items, stanceOf);
  const focus =
    requested !== null && tally.some((entry) => entry.stance === requested) ? requested : null;
  return {
    tally,
    focus,
    shown: focus === null ? items : items.filter((item) => stanceOf(item) === focus),
    total: items.length,
    choosable: tally.length > 1,
  };
}
