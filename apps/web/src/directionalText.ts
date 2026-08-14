/**
 * Split text into directional runs so the browser can lay each one out in its
 * own right.
 *
 * The stored text is already in logical order — the ingestion side recovers it
 * from paint order and normalises presentation forms before anything is
 * persisted. Nothing here repairs, reorders or rewrites that text. The only
 * thing HTML cannot work out for itself is the *base direction* of a run when
 * runs of opposite direction sit next to each other, and supplying that is the
 * whole job of this module.
 *
 * Why it is needed at all: a run of right-to-left text placed in a left-to-right
 * container does not simply sit there. The Unicode Bidirectional Algorithm
 * resolves the neutral characters around it — digits, per-cent signs, brackets,
 * commas — against the *container's* direction rather than the run's. So a
 * deduction written `خصم 10%` is laid out with the number on the wrong side of
 * the phrase, and a reviewer reads a different figure from the one the document
 * states. Marking the run and isolating it from its neighbours is what stops
 * that, and it is a statement about the text, not a transformation of it.
 *
 * Two invariants hold and both are asserted in the tests:
 *
 * 1. Concatenating the runs in order reproduces the input exactly, character
 *    for character. No run is reversed, dropped, merged or re-cased. If this
 *    ever fails, this module has started editing text and must be treated as a
 *    defect rather than a fix.
 * 2. Direction is a property of a *run*, never of a document, a page, a record
 *    or a field. A single foreign term quoted inside a sentence gets its own
 *    run and nothing else moves.
 *
 * Nothing keys on a language, a locale or a particular script. The strong
 * classes below mirror `reading_order.py` on the ingestion side, which reads
 * them from `unicodedata.bidirectional`; JavaScript's regular expressions do
 * not expose `Bidi_Class`, so the equivalent is stated as the set of
 * right-to-left *scripts*, which is itself Unicode data rather than a choice.
 */

/** How a run should be laid out. `auto` means "we could not tell — let the
 *  browser decide from the first strong character and do not pretend to know". */
export type RunDirection = "rtl" | "ltr" | "auto";

export interface TextRun {
  /** The exact characters of this run, unmodified. */
  text: string;
  /** Base direction to lay this run out in. */
  direction: RunDirection;
  /**
   * BCP-47 script subtag for the run, e.g. `und-Arab` — "undetermined
   * language, this script". Deliberately not a language tag: Arabic script
   * carries Arabic, Farsi, Urdu, Pashto and more, and claiming `lang="ar"` for
   * all of them would tell a screen reader to pronounce Urdu as Arabic. The
   * script is what we actually observed, so the script is what we state.
   */
  lang?: string;
  /**
   * True when this run's characters alternate direction faster than they form
   * words — the signature of text that was shredded glyph-by-glyph upstream
   * rather than written. Such a run is *not* clean bilingual text and must not
   * be presented as though it were.
   */
  interleaved: boolean;
}

/**
 * The right-to-left scripts, with the ISO 15924 subtag each is written with.
 *
 * This is an enumeration of Unicode data, not a list of languages the product
 * cares about: Hebrew, Thaana, Syriac, N'Ko, Samaritan and Adlam are all here
 * on the same footing as Arabic, and none of them is referenced anywhere else
 * in the codebase. A script is included because Unicode says it runs
 * right-to-left, and for no other reason.
 */
const RTL_SCRIPTS: ReadonlyArray<readonly [string, string]> = [
  ["Adlam", "Adlm"],
  ["Arabic", "Arab"],
  ["Hebrew", "Hebr"],
  ["Syriac", "Syrc"],
  ["Thaana", "Thaa"],
  ["Nko", "Nkoo"],
  ["Samaritan", "Samr"],
  ["Mandaic", "Mand"],
  ["Mende_Kikakui", "Mend"],
  ["Cypriot", "Cprt"],
  ["Kharoshthi", "Khar"],
  ["Lydian", "Lydi"],
  ["Manichaean", "Mani"],
  ["Nabataean", "Nbat"],
  ["Old_Hungarian", "Hung"],
  ["Old_Turkic", "Orkh"],
  ["Palmyrene", "Palm"],
  ["Phoenician", "Phnx"],
  ["Imperial_Aramaic", "Armi"],
  ["Inscriptional_Pahlavi", "Phli"],
  ["Inscriptional_Parthian", "Prti"],
  ["Psalter_Pahlavi", "Phlp"],
  ["Hatran", "Hatr"],
  ["Meroitic_Cursive", "Merc"],
  ["Meroitic_Hieroglyphs", "Mero"],
  ["Old_North_Arabian", "Narb"],
  ["Old_South_Arabian", "Sarb"],
  ["Yezidi", "Yezi"],
];

/**
 * Compile a script test, skipping any script this engine's Unicode tables do
 * not know about.
 *
 * Property escapes throw at construction time for an unrecognised script name,
 * and engines ship different Unicode versions. Probing each one keeps a newer
 * script in the list harmless on an older engine instead of taking the whole
 * module down at import.
 */
function compileScript(script: string): RegExp | null {
  try {
    return new RegExp(`\\p{Script=${script}}`, "u");
  } catch {
    return null;
  }
}

const RTL_MATCHERS: ReadonlyArray<readonly [RegExp, string]> = RTL_SCRIPTS.map(
  ([script, subtag]) => [compileScript(script), subtag] as const,
).filter((entry): entry is readonly [RegExp, string] => entry[0] !== null);

/** Characters with a strong left-to-right class. Cased letters are the bulk of
 *  it; the property escape covers every alphabet Unicode calls left-to-right. */
const STRONG_LTR = /\p{Letter}/u;

/** Which direction a single character is strong in, or null when it is
 *  neutral — a digit, a space, a bracket, a per-cent sign, a full stop. */
function strongDirectionOf(char: string): "rtl" | "ltr" | null {
  for (const [matcher] of RTL_MATCHERS) {
    if (matcher.test(char)) return "rtl";
  }
  return STRONG_LTR.test(char) ? "ltr" : null;
}

/** The script subtag for a right-to-left character, for `lang`. */
function scriptSubtagOf(char: string): string | undefined {
  for (const [matcher, subtag] of RTL_MATCHERS) {
    if (matcher.test(char)) return `und-${subtag}`;
  }
  return undefined;
}

/** True when the text contains any strongly right-to-left character. */
export function hasRtl(text: string): boolean {
  for (const char of text) {
    if (strongDirectionOf(char) === "rtl") return true;
  }
  return false;
}

/**
 * The base direction of a whole passage, for aligning the block that holds it.
 *
 * Taken from the first strong character, which is what `dir="auto"` does. A
 * block is aligned to the side its reader starts from, and that is decided by
 * where the passage begins, not by counting which script has more characters —
 * a rule quoted in English with one Arabic term is an English rule.
 */
export function baseDirection(text: string): RunDirection {
  for (const char of text) {
    const strong = strongDirectionOf(char);
    if (strong) return strong;
  }
  return "auto";
}

/**
 * Fewer than this many same-direction characters in a row, on average, within a
 * single word means the word's scripts are interleaved rather than adjacent.
 *
 * Two is not a tuned figure, it is the smallest run that is a fragment of a
 * word at all: below it, no script manages even a pair of consecutive letters,
 * which does not happen in written text and does happen when glyphs from two
 * columns are collected in paint order.
 */
const MIN_MEAN_RUN_IN_A_WORD = 2;

/**
 * Whether one whitespace-delimited token has its scripts shredded together.
 *
 * Written bilingual text puts a word in one script and the next word in
 * another. Text that was mis-assembled upstream puts single letters of one
 * script between the letters of another, so the test is structural: does this
 * token contain both directions, and do its same-direction stretches average
 * less than a word fragment?
 */
function isInterleaved(token: string): boolean {
  const strongs: Array<"rtl" | "ltr"> = [];
  for (const char of token) {
    const strong = strongDirectionOf(char);
    if (strong) strongs.push(strong);
  }
  if (strongs.length < 2) return false;

  let runs = 1;
  for (let i = 1; i < strongs.length; i += 1) {
    if (strongs[i] !== strongs[i - 1]) runs += 1;
  }
  if (runs < 2) return false;

  return strongs.length / runs < MIN_MEAN_RUN_IN_A_WORD;
}

/** Split on whitespace, keeping the whitespace so the text can be rebuilt
 *  exactly. */
function tokenise(text: string): string[] {
  return text.split(/(\s+)/u).filter((part) => part !== "");
}

/**
 * Split text into runs, each carrying the direction it should be laid out in.
 *
 * Neutral characters attach to the run they follow. That is a choice about
 * *grouping* only — the characters stay exactly where they are, and because
 * each run is rendered isolated, the browser resolves the neutrals inside it
 * against that run's own direction, which is the correct answer and the one
 * that was previously being got wrong. A per-cent sign after an Arabic phrase
 * belongs to the Arabic phrase; a bracketed article number inside it stays a
 * left-to-right island within it.
 */
export function splitDirectionalRuns(text: string): TextRun[] {
  if (!text) return [];

  const runs: TextRun[] = [];
  let current: RunDirection | null = null;
  let buffer = "";
  let lang: string | undefined;

  const flush = () => {
    if (!buffer) return;
    runs.push({ text: buffer, direction: current ?? "auto", lang, interleaved: false });
    buffer = "";
    lang = undefined;
  };

  for (const token of tokenise(text)) {
    if (isInterleaved(token)) {
      flush();
      // Not presented as either language: it is neither, and saying so is the
      // point. `auto` lets the browser do something sane without this code
      // asserting a direction it has no grounds for.
      runs.push({ text: token, direction: "auto", lang: undefined, interleaved: true });
      current = null;
      continue;
    }

    for (const char of token) {
      const strong = strongDirectionOf(char);
      if (strong && strong !== current) {
        // A strong character of the other direction ends the run in force.
        // Everything neutral since the last strong character — the space, the
        // digits, the per-cent sign — has already been buffered into that run,
        // which is what keeps a quantity attached to the phrase it qualifies.
        //
        // Before the first strong character there is no run to attach to, so
        // the neutrals wait and join the one that arrives. That keeps `10%
        // deduction` whole rather than stranding the figure in a run of its
        // own, which is the same principle applied at the other edge.
        if (current !== null) flush();
        current = strong;
      }
      if (strong === "rtl" && !lang) lang = scriptSubtagOf(char);
      buffer += char;
    }
  }
  flush();

  return runs;
}
