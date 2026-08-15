/**
 * What a policy holds that the surface is not showing, said in terms a reviewer
 * can act on.
 *
 * A card that shows three of a policy's eighteen rules has to say so, or a
 * reviewer approves believing they judged the whole policy. That warning was
 * already there. What it did not say was *what* the other fifteen are or
 * *where* they went — so a reviewer reading "outside the current filter" had to
 * ask what it meant, which is the message failing.
 *
 * Both facts are already in the client. Every record carries its own kind, and
 * the surface knows the filters it is offering. This module joins the two and
 * builds one sentence from them, so the three surfaces that state this do not
 * each grow their own wording.
 *
 * Two rules govern everything here:
 *
 *  - Nothing is guessed. A kind is named only for a record this client actually
 *    received. Records whose kind was never loaded are counted separately and
 *    said out loud, because "fifteen definitions" when four of them are
 *    something else is worse than "fifteen rules".
 *  - No kind is ranked. A definition is a record like any other and the copy
 *    says what it is, never what it is worth. `recordsNotShownIsNeutral.test.ts`
 *    fails on any wording that implies otherwise.
 */
import { ruleTypeLabel } from "./ruleTypes";

/** One kind of record, as many as this policy holds of it, out of view. */
export interface NotShownGroup {
  /** The kind exactly as the record states it, e.g. `definition`. */
  kind: string;
  /** The same kind in running text, e.g. `definitions`. Derived, never listed. */
  phrase: string;
  count: number;
}

/** Somewhere a reviewer could go to read the records this surface is not
 *  showing. Supplied by the surface, because the name has to be the one the
 *  reviewer can see, and this module cannot know it. */
export interface RecordDestination {
  /** Exactly as it reads on screen, counts and all. */
  label: string;
  /** Whether records of this kind are found there. A predicate rather than a
   *  list of kinds, and a list rather than a pair, so that adding a third
   *  filter needs no change here. */
  holds: (recordKind: string) => boolean;
  /** True for the filter the reviewer is already on. That one is never offered
   *  as somewhere to go. */
  isCurrent?: boolean;
  /** Go there. Optional: a surface that cannot navigate still contributes its
   *  name, which is the part the reviewer needs to find the records. */
  go?: () => void;
}

export interface RecordsNotShown {
  /** How many records of this policy are out of view. Taken from the card's own
   *  count rather than from anything derived here, so this number and the
   *  card's header can never disagree. */
  count: number;
  /** The kinds, most numerous first. */
  groups: NotShownGroup[];
  /** Out-of-view records whose kind this client has not loaded. Never folded
   *  into `groups`: a kind nobody has seen is not a kind of zero. */
  unnamed: number;
  /** Where the reviewer can read them, by the name on screen. Empty when no
   *  surface has said what it is offering. */
  destinations: RecordDestination[];
}

const kindByRuleId = new Map<string, string>();

let destinations: RecordDestination[] = [];

/**
 * Remember what kind each record states itself to be.
 *
 * Called as records arrive rather than asked for later, because the records a
 * surface is *not* showing are exactly the ones it no longer holds. What was
 * once received is enough to name them; nothing is fetched to do it.
 */
export function noteRecordKinds(
  records: readonly { rule_type?: string | null; rule?: { rule_id?: string | null } | null }[],
): void {
  for (const record of records) {
    const id = record?.rule?.rule_id;
    const kind = record?.rule_type;
    if (typeof id === "string" && id && typeof kind === "string" && kind) {
      kindByRuleId.set(id, kind);
    }
  }
}

/**
 * Say which filters this surface is offering and which one is showing.
 *
 * Replaces the whole set on every call, so a surface that changes tabs simply
 * says so again and no stale destination survives.
 */
export function registerRecordDestinations(next: readonly RecordDestination[]): void {
  destinations = [...next];
}

/** Test seam. Nothing in the app calls this. */
export function forgetRecordKinds(): void {
  kindByRuleId.clear();
  destinations = [];
}

/** English plural of one kind's label.
 *
 *  Written for a kind extraction has not learned yet, not for the ones in
 *  `RULE_TYPES` today. `eligibility` and `delegation of authority` both end in a
 *  consonant and a `y`, and a bare `s` makes nonsense of them. A word that
 *  already ends in `s` is left alone rather than doubled. */
function plural(one: string): string {
  if (/[^aeiou]y$/i.test(one)) return `${one.slice(0, -1)}ies`;
  if (/(ss|x|z|ch|sh)$/i.test(one)) return `${one}es`;
  if (/s$/i.test(one)) return one;
  return `${one}s`;
}

/** The record kind in running text.
 *
 *  Built on the house label function so there is one place that turns a
 *  `rule_type` into words; this only lowercases it for mid-sentence use and
 *  pluralises it. Naming kinds again here would be a second taxonomy, and the
 *  two would drift the first time extraction learns a new one. */
export function phraseForKind(kind: string, count: number): string {
  const spaced = ruleTypeLabel(kind.trim()).toLowerCase();
  if (!spaced) return count === 1 ? "record" : "records";
  return count === 1 ? spaced : plural(spaced);
}

function articleFor(phrase: string): string {
  return /^[aeiou]/i.test(phrase) ? "an" : "a";
}

/** The shape both the review card and the published card already have. Taken
 *  structurally so this module needs no import from either, and so a third
 *  surface can adopt it without one. */
export interface PolicyLikeCard {
  hiddenByFilter: number;
  rules: readonly { rule_id: string }[];
  policy: {
    passages?: readonly { rules?: readonly { rule_id: string }[] | null }[] | null;
  };
}

/**
 * Which of a policy's records this card is not showing, and what they are.
 *
 * The out-of-view records are the assembly's, minus the ones on the card. The
 * assembly is the whole policy by construction, so this is a subtraction and
 * not a second opinion about what the policy holds.
 */
export function recordsNotShown(card: PolicyLikeCard): RecordsNotShown {
  const count = Math.max(0, card.hiddenByFilter);
  if (count === 0) return { count: 0, groups: [], unnamed: 0, destinations: [] };

  const shown = new Set(card.rules.map((rule) => rule.rule_id));
  const counts = new Map<string, number>();
  let derived = 0;
  let unnamed = 0;

  for (const passage of card.policy.passages ?? []) {
    for (const rule of passage?.rules ?? []) {
      if (!rule?.rule_id || shown.has(rule.rule_id)) continue;
      derived += 1;
      const kind = kindByRuleId.get(rule.rule_id);
      if (!kind) {
        unnamed += 1;
        continue;
      }
      counts.set(kind, (counts.get(kind) ?? 0) + 1);
    }
  }

  // The card's own count is the one on screen and the one that governs. Where
  // the assembly accounts for fewer, the difference is records this view cannot
  // describe — which is said, not absorbed into a kind that would then be wrong.
  if (derived < count) unnamed += count - derived;

  const groups = [...counts.entries()]
    .map(([kind, kindCount]) => ({ kind, phrase: phraseForKind(kind, kindCount), count: kindCount }))
    .sort((left, right) => right.count - left.count || left.kind.localeCompare(right.kind));

  const kinds = new Set(groups.map((group) => group.kind));
  const where = destinations.filter(
    (destination) =>
      !destination.isCurrent && [...kinds].some((kind) => destination.holds(kind)),
  );

  return { count, groups, unnamed, destinations: where };
}

function listed(parts: readonly string[]): string {
  if (parts.length === 0) return "";
  if (parts.length === 1) return parts[0];
  return `${parts.slice(0, -1).join(", ")} and ${parts[parts.length - 1]}`;
}

/**
 * The sentence that says what is out of view.
 *
 * Kept apart from the consequence sentence, which every surface states in its
 * own terms because approving, comparing and reading have different
 * consequences.
 */
export function notShownSentence(shown: RecordsNotShown): string {
  if (shown.count === 0) return "";
  const subject =
    shown.count === 1
      ? "1 more rule of this policy is"
      : `${shown.count} more rules of this policy are`;

  // Not one of them could be named, so there is no mixture to describe and the
  // count in the subject already says how many are unaccounted for. The reviewer
  // still learns the number and the consequence, which is what the sentence is
  // for. Saying "3, and this view has not loaded 3" would only repeat it.
  if (shown.groups.length === 0) return `${subject} not shown by the current filters.`;

  // One kind and nothing unaccounted for: the subject already carries the
  // count, so repeating it would read "15 more rules ... are 15 definitions".
  const single = shown.groups.length === 1 && shown.unnamed === 0;
  const parts = shown.groups.map((group) => {
    if (!single) return `${group.count} ${group.phrase}`;
    return group.count === 1 ? `${articleFor(group.phrase)} ${group.phrase}` : group.phrase;
  });
  if (shown.unnamed > 0) {
    parts.push(
      shown.unnamed === 1
        ? "1 whose kind this view has not loaded"
        : `${shown.unnamed} whose kind this view has not loaded`,
    );
  }

    const named = `${subject} ${listed(parts)}`;

  if (shown.destinations.length === 0) {
    // No surface has said what filters it is offering, so no name can be given
    // without inventing one — and a filter named wrongly sends the reviewer
    // somewhere the records are not. The control is still pointed at, because
    // a record out of view by a filter is in view under another one.
    return `${named}. A different filter on this page shows them.`;
  }
  const where = listed(shown.destinations.map((destination) => destination.label));
  return `${named}. Read them under ${where}.`;
}
