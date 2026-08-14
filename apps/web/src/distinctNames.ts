/**
 * Shortening a set of names without making any two of them read the same.
 *
 * WHY THIS EXISTS
 *
 * Every clamped label in this interface was shortened by the browser, with
 * `text-overflow: ellipsis`. That drops characters from the end, which is the
 * one strategy guaranteed to fail on the names this product actually holds. A
 * project is an extraction of a document, and a re-extraction is another
 * project, so the names differ by an annotation that is appended:
 *
 *   Staff Handbook (Metro Group University) 2024 (full extraction)
 *   Staff Handbook (Metro Group University) 2024 (pilot subset)
 *   Staff Handbook (Metro Group University) 2024 (Phase 2 re-run)
 *
 * End-truncation keeps the part they share and discards the part that tells
 * them apart. An audit found five such rows in the navigation, of which two
 * rendered character-for-character identically -- so the list could not be
 * used to reach a specific project at all, and no amount of column width fixes
 * it, because the shared prefix grows with the document title.
 *
 * WHAT THIS DOES INSTEAD
 *
 * Three rules, in order, none of which knows anything about this product's
 * names:
 *
 *  1. A name that fits is left exactly as it is. Shortening what already fits
 *     would be damage, not density.
 *  2. A name that does not fit is elided in the MIDDLE, keeping a head and a
 *     tail. The head says what family the record belongs to and the tail
 *     carries whatever was appended to distinguish it, so both survive.
 *  3. If two labels still collide, the SPLIT MOVES for the colliding ones: the
 *     budget stays the same and is re-divided between head and tail until the
 *     labels differ. Every division of the budget is tried, most balanced
 *     first, so a difference at either end is reachable -- appended (an
 *     annotation) or prepended (a numbered variant).
 *  4. If no division of a two-part label reaches it, the second kept run is
 *     anchored where the names actually stop agreeing rather than at the end.
 *     That is what reaches "Standard v4" against "Standard v7" when the
 *     difference sits 30 characters into an otherwise identical 78-character
 *     name that also ends identically. It costs a second ellipsis, so it is
 *     tried only after rule 3 has been exhausted.
 *
 * Rule 3 is what makes the guarantee stateable: DISTINCT INPUTS PRODUCE
 * DISTINCT LABELS WHENEVER ANY DIVISION OF THE BUDGET CAN SHOW THE DIFFERENCE.
 * Two names that are genuinely identical are not made distinct here -- nothing
 * in a name can distinguish them -- and the caller is told so via
 * `hasCollisions`, which is how a surface knows it must show something else as
 * well, such as the project key it already holds. The same flag is raised when
 * a difference exists but no division of the budget reaches it, because the
 * consequence for the reader is identical: two rows they cannot tell apart.
 *
 * WHY A CHARACTER BUDGET AND NOT PIXELS
 *
 * Measuring text requires layout, so a pixel-exact answer means either
 * rendering twice or carrying a canvas around. A character budget is
 * deterministic, testable without a DOM, and stable across a resize. It is
 * paired with a CSS clamp on the same element, which stays as the last line of
 * defence: if a budget is ever set too generously the browser still cuts the
 * line, and this module's job of keeping the distinguishing part inside the
 * kept region is what makes that cut survivable.
 */

/** The character shown where text was removed. One glyph, so it costs one. */
export const ELLIPSIS = "…";

/**
 * Shortest label that still shows the shape of a name. Below this a head and a
 * tail cannot both be kept, and the result stops being readable as a name at
 * all -- so a budget under it is treated as this instead.
 */
const MIN_BUDGET = 8;

export interface DistinctLabels {
  /** Label for each input name, in the same order. */
  labels: string[];
  /**
   * True when two inputs were already identical, so no shortening could have
   * told them apart. The caller must show something else beside the label.
   */
  hasCollisions: boolean;
}

/**
 * Elide one name to a budget, keeping its head and its tail.
 *
 * `tailShare` moves the split: `null` divides the budget evenly, otherwise it
 * is the exact number of trailing characters to keep. Passing it is how rule 3
 * searches for a division that separates a colliding group without spending
 * more room than the budget allows.
 */
export function elideMiddle(name: string, budget: number, tailShare: number | null = null): string {
  const chars = Array.from(name); // by code point, so an emoji is not cut in half
  const limit = Math.max(MIN_BUDGET, Math.floor(budget));
  if (chars.length <= limit) return name;

  const keep = limit - 1; // one character is spent on the ellipsis
  const tail = Math.min(keep - 1, Math.max(1, tailShare ?? Math.floor(keep / 2)));
  const head = keep - tail;
  return chars.slice(0, head).join("") + ELLIPSIS + chars.slice(chars.length - tail).join("");
}

/**
 * Every division of a budget between head and tail, most balanced first.
 *
 * Ties are broken towards the tail, because an annotation is appended more
 * often than prepended in the material this product holds. That is a
 * preference between two equally valid answers, never a requirement: a
 * head-heavy division is reached one step later, not excluded.
 */
function tailShares(budget: number): number[] {
  const keep = Math.max(MIN_BUDGET, Math.floor(budget)) - 1;
  const balanced = Math.floor(keep / 2);
  const order: number[] = [balanced];
  for (let step = 1; step < keep; step += 1) {
    for (const candidate of [balanced + step, balanced - step]) {
      if (candidate >= 1 && candidate <= keep - 1) order.push(candidate);
    }
  }
  return order;
}

/**
 * A label that keeps a head and a run taken from anywhere in the name.
 *
 * A head-and-tail label can only show the two ends, so a difference sitting in
 * the middle is unreachable however the budget is divided -- "Standard v4" and
 * "Standard v7", 30 characters into a 78-character name that ends identically,
 * are the case that proves it. Anchoring the second run at the difference
 * instead of at the end reaches it, at the cost of one more ellipsis when the
 * run does not happen to end the name.
 */
function elideAround(name: string, budget: number, headLength: number, runStart: number): string {
  const chars = Array.from(name);
  const limit = Math.max(MIN_BUDGET, Math.floor(budget));
  if (chars.length <= limit) return name;

  const head = Math.max(1, Math.min(headLength, limit - 3));
  // Two ellipses unless the run reaches the end of the name, in which case the
  // trailing one would claim text was removed that was not.
  const runLength = Math.max(1, limit - head - 2);
  const start = Math.min(Math.max(runStart, head + 1), chars.length - runLength);
  const reachesEnd = start + runLength >= chars.length;
  const run = chars.slice(start, start + runLength).join("");
  const withoutTrailing = chars.slice(0, head).join("") + ELLIPSIS + run;
  return reachesEnd ? withoutTrailing : withoutTrailing + ELLIPSIS;
}

/** The first position at which the names in a group stop agreeing. */
function firstDivergence(names: readonly string[]): number {
  const rows = names.map((name) => Array.from(name));
  const shortest = Math.min(...rows.map((row) => row.length));
  for (let i = 0; i < shortest; i += 1) {
    const first = rows[0][i];
    if (rows.some((row) => row[i] !== first)) return i;
  }
  return shortest;
}

/**
 * Shorten a set of names to a budget so that no two distinct names collide.
 *
 * The set matters: the same name shortens differently depending on what it is
 * shown beside, which is the whole point. A name displayed alone needs no
 * disambiguation; the same name in a list of near-twins does.
 */
export function distinctLabels(names: readonly string[], budget: number): DistinctLabels {
  const labels = names.map((name) => elideMiddle(name, budget));

  // Only names that are themselves distinct can be pulled apart. Group by the
  // label produced, and work on each colliding group.
  const byLabel = new Map<string, number[]>();
  labels.forEach((label, index) => {
    const existing = byLabel.get(label);
    if (existing) existing.push(index);
    else byLabel.set(label, [index]);
  });

  let hasCollisions = false;

  for (const indices of byLabel.values()) {
    if (indices.length < 2) continue;
    const distinctNames = new Set(indices.map((i) => names[i]));
    if (distinctNames.size < indices.length) {
      // At least two inputs are the same string. Note it and still separate the
      // ones that can be separated.
      hasCollisions = true;
    }
    if (distinctNames.size < 2) continue;

    const apply = (attempt: string[]): boolean => {
      if (new Set(attempt).size !== distinctNames.size) return false;
      indices.forEach((index, position) => {
        labels[index] = attempt[position];
      });
      return true;
    };

    // First re-divide the same budget between head and tail. A two-part label
    // reads better than a three-part one, so it is tried exhaustively before
    // the second ellipsis is spent.
    let separated = tailShares(budget).some((tailShare) =>
      apply(indices.map((i) => elideMiddle(names[i], budget, tailShare))),
    );

    if (!separated) {
      // Anchor the second run where these names actually stop agreeing, and
      // vary how much head is kept in front of it.
      const divergence = firstDivergence(indices.map((i) => names[i]));
      const runStart = Math.max(0, divergence - 1);
      for (let head = Math.max(1, Math.floor(budget / 2)); head >= 1 && !separated; head -= 1) {
        separated = apply(indices.map((i) => elideAround(names[i], budget, head, runStart)));
      }
    }

    // Nothing this budget can show reaches the difference. Say so rather than
    // let the caller believe the rows are distinguishable.
    if (!separated) hasCollisions = true;
  }

  return { labels, hasCollisions };
}

/**
 * The labels for one keyed collection, as a lookup.
 *
 * Surfaces hold records rather than bare strings, and reading a label by key is
 * what a render loop wants. Keys are assumed unique, which every caller's key
 * already is -- a project key is unique by database constraint.
 */
export function distinctLabelsByKey<T>(
  items: readonly T[],
  keyOf: (item: T) => string,
  nameOf: (item: T) => string,
  budget: number,
): { labelFor: (key: string) => string; hasCollisions: boolean } {
  const { labels, hasCollisions } = distinctLabels(items.map(nameOf), budget);
  const lookup = new Map<string, string>();
  items.forEach((item, index) => lookup.set(keyOf(item), labels[index]));
  return {
    // A key that was not in `items` has no computed label. Returning the key
    // is the honest answer: it is real, unique data, and it makes the gap
    // visible instead of rendering an empty cell.
    labelFor: (key: string) => lookup.get(key) ?? key,
    hasCollisions,
  };
}
