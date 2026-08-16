/**
 * Which Unicode scripts a string is written in, and whether two strings share
 * one.
 *
 * WHY THIS EXISTS
 *
 * A generated label sits above a document's own heading, to be read beside it.
 * A label written in a script the heading shares none of cannot be read as
 * naming that heading — see `policyTopicLabel`, which withholds it. Deciding
 * that needs one thing and one thing only: do these two runs have a script in
 * common. Not what language either is in, not which direction either runs, not
 * whether one contains the other — only whether the sets of scripts they are
 * written in touch at all.
 *
 * SCRIPT, NOT LANGUAGE
 *
 * A script is a property of characters, which is observable, where a language
 * is a property of meaning, which is not. Arabic script carries Arabic, Farsi,
 * Urdu and Pashto; Latin carries English, French, Vietnamese and a hundred
 * more. This module reads the script, because the script is what the characters
 * actually are. Nothing here keys on a language or a locale, and the decision
 * below (`scriptsDisjoint`, `sharesScript`) never names a script either — it is
 * set arithmetic over opaque subtags. The only place a script is named at all
 * is the table of Unicode data, which is an enumeration of what Unicode defines
 * rather than a list of anything this product privileges. This mirrors
 * `directionalText.ts`, which states its right-to-left scripts the same way and
 * for the same reason.
 *
 * WHAT IS IGNORED
 *
 * Digits, punctuation, spaces, currency, maths and every other character that
 * belongs to no one script — Unicode's `Common` and `Inherited` — carry no
 * script and are skipped. They are shared by everything, so counting them would
 * make every pair of strings overlap and no label would ever be withheld. A
 * string of only such characters therefore has an empty script set, which the
 * decision treats as "cannot tell", never as "disjoint".
 */

/**
 * The scripts, each with the ISO 15924 subtag it is recorded under.
 *
 * An enumeration of Unicode data. The living scripts in wide use are here so a
 * label and a heading in any of them can be told apart or matched; a handful of
 * others sit alongside them on exactly the same footing. A script earns its
 * place because Unicode defines it, not because the product cares about the
 * language it happens to carry — and none of these subtags is referenced
 * anywhere in the decision that uses them.
 */
const SCRIPTS: ReadonlyArray<readonly [string, string]> = [
  ["Latin", "Latn"],
  ["Arabic", "Arab"],
  ["Han", "Hani"],
  ["Hebrew", "Hebr"],
  ["Cyrillic", "Cyrl"],
  ["Greek", "Grek"],
  ["Hiragana", "Hira"],
  ["Katakana", "Kana"],
  ["Hangul", "Hang"],
  ["Devanagari", "Deva"],
  ["Bengali", "Beng"],
  ["Gurmukhi", "Guru"],
  ["Gujarati", "Gujr"],
  ["Oriya", "Orya"],
  ["Tamil", "Taml"],
  ["Telugu", "Telu"],
  ["Kannada", "Knda"],
  ["Malayalam", "Mlym"],
  ["Sinhala", "Sinh"],
  ["Thai", "Thai"],
  ["Lao", "Laoo"],
  ["Tibetan", "Tibt"],
  ["Myanmar", "Mymr"],
  ["Georgian", "Geor"],
  ["Armenian", "Armn"],
  ["Ethiopic", "Ethi"],
  ["Cherokee", "Cher"],
  ["Khmer", "Khmr"],
  ["Mongolian", "Mong"],
  ["Bopomofo", "Bopo"],
  ["Yi", "Yiii"],
  ["Syriac", "Syrc"],
  ["Thaana", "Thaa"],
  ["Nko", "Nkoo"],
  ["Samaritan", "Samr"],
  ["Mandaic", "Mand"],
  ["Adlam", "Adlm"],
  ["Vai", "Vaii"],
  ["Tifinagh", "Tfng"],
  ["Javanese", "Java"],
  ["Sundanese", "Sund"],
  ["Balinese", "Bali"],
  ["Batak", "Batk"],
  ["Tagalog", "Tglg"],
  ["Coptic", "Copt"],
];

/**
 * A subtag for a character that is written in some script none of the table
 * above recognises — ISO 15924's own code for an uncoded script. Two such
 * characters from genuinely different scripts collapse to this one bucket and
 * so read as sharing it, which can only keep a label that would otherwise be
 * withheld. Erring toward keeping is the safe direction: it never hides a name
 * a reader could have used.
 */
const UNKNOWN_SCRIPT = "Zzzz";

/**
 * Compile a script test, skipping any script this engine's Unicode tables do
 * not know about. Property escapes throw at construction for an unrecognised
 * script name and engines ship different Unicode versions, so probing each one
 * keeps a newer script harmless on an older engine rather than taking the
 * module down at import. Mirrors `directionalText.ts`.
 */
function compileScript(script: string): RegExp | null {
  try {
    return new RegExp(`\\p{Script=${script}}`, "u");
  } catch {
    return null;
  }
}

const SCRIPT_MATCHERS: ReadonlyArray<readonly [RegExp, string]> = SCRIPTS.map(
  ([script, subtag]) => [compileScript(script), subtag] as const,
).filter((entry): entry is readonly [RegExp, string] => entry[0] !== null);

/**
 * Characters that carry no script of their own: digits, punctuation, spaces,
 * symbols (`Common`) and combining marks that take the script of what they
 * attach to (`Inherited`). Skipped so that shared punctuation cannot make two
 * otherwise-disjoint strings look as though they overlap.
 */
const SCRIPTLESS = [compileScript("Common"), compileScript("Inherited")].filter(
  (matcher): matcher is RegExp => matcher !== null,
);

/**
 * The set of scripts a string is written in, as ISO 15924 subtags.
 *
 * Iterated by code point, so characters outside the basic plane are read whole.
 * Scriptless characters contribute nothing; a script-bearing character the
 * table does not recognise contributes the uncoded-script bucket. The result is
 * a set: how many characters were in a script, and in what order, does not
 * matter to the question this answers.
 */
export function scriptsOf(text: string): Set<string> {
  const scripts = new Set<string>();
  for (const character of text) {
    if (SCRIPTLESS.some((matcher) => matcher.test(character))) continue;
    const matched = SCRIPT_MATCHERS.find(([matcher]) => matcher.test(character));
    scripts.add(matched ? matched[1] : UNKNOWN_SCRIPT);
  }
  return scripts;
}

/** Whether two strings are written in at least one script in common. */
export function sharesScript(one: string, other: string): boolean {
  const scripts = scriptsOf(one);
  for (const script of scriptsOf(other)) {
    if (scripts.has(script)) return true;
  }
  return false;
}

/**
 * Whether two strings share no script at all — the test a label is withheld on.
 *
 * True only when both strings are written in some script and no script is
 * common to them. This is disjointness, not inequality: a heading written in
 * two scripts is not disjoint from a label in either one of them, because they
 * still share that one. A string with no script of its own — all digits and
 * punctuation, say — yields "cannot tell" rather than "disjoint", so a label is
 * never withheld from a heading there was nothing to compare it against.
 */
export function scriptsDisjoint(one: string, other: string): boolean {
  const first = scriptsOf(one);
  const second = scriptsOf(other);
  if (first.size === 0 || second.size === 0) return false;
  for (const script of first) {
    if (second.has(script)) return false;
  }
  return true;
}
