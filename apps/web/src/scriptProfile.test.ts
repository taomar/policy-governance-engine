/**
 * The script helper reads scripts, shares them by script and never by language.
 *
 * These tests hold the line the whole fix rests on: a label is withheld only
 * when it shares no script with its heading, "disjoint" is not "different", and
 * nothing here is special-cased to one language or one script. The samples are
 * written for this file — each is here for which script its characters are in,
 * not for what it says — except the one bilingual cell noted as read from the
 * corpus, which is what a real heading in two scripts looks like.
 */
import { describe, expect, it } from "vitest";
import { scriptsDisjoint, scriptsOf, sharesScript } from "./scriptProfile";

const LATIN = "Attendance";
const ARABIC = "\u0627\u0644\u062a\u0631\u062a\u064a\u0628"; // one Arabic-script word
const HAN = "\u653f\u7b56";
const HEBREW = "\u05de\u05d3\u05d9\u05e0\u05d9\u05d5\u05ea";
const GREEK = "\u0395\u03bb\u03bb\u03b7\u03bd\u03b9\u03ba\u03ac";
const CYRILLIC = "\u041f\u043e\u043b\u0438\u0442\u0438\u043a\u0430";

// Read from the bilingual employee handbook: one heading cell, two scripts.
const BILINGUAL = "Written Warning \u0625\u0646\u0630\u0627\u0631 \u0643\u062a\u0627\u0628\u064a";

describe("reading the scripts a string is written in", () => {
  it("names each script by its subtag, once, whatever the length", () => {
    expect(scriptsOf(LATIN).has("Latn")).toBe(true);
    expect(scriptsOf(LATIN).size).toBe(1);
    expect(scriptsOf(ARABIC).has("Arab")).toBe(true);
    expect(scriptsOf(ARABIC).size).toBe(1);
    expect(scriptsOf(HAN).has("Hani")).toBe(true);
  });

  it("collects every script a mixed string is written in", () => {
    const scripts = scriptsOf(BILINGUAL);
    expect(scripts.has("Latn")).toBe(true);
    expect(scripts.has("Arab")).toBe(true);
    expect(scripts.size).toBe(2);
  });

  it("reads digits, punctuation and spaces as no script at all", () => {
    // No letters, so nothing to withhold on: these are shared by everything.
    expect(scriptsOf("0123 .,:;-%/()").size).toBe(0);
  });
});

describe("deciding whether two strings share a script", () => {
  it("reads two strings in one script as not disjoint", () => {
    expect(scriptsDisjoint(LATIN, "Attendance policy")).toBe(false);
    expect(sharesScript(LATIN, "policy")).toBe(true);
  });

  it("reads a label and heading in different scripts as disjoint", () => {
    expect(scriptsDisjoint(ARABIC, LATIN)).toBe(true);
    expect(sharesScript(ARABIC, LATIN)).toBe(false);
  });

  it("keeps a label sharing one script with a heading written in two", () => {
    // The heart of it: disjoint is emptiness of overlap, not inequality of
    // sets. {Arab} is not equal to {Latn, Arab}, but the two are not disjoint,
    // because the label's one script is one of the heading's two.
    expect(scriptsDisjoint(ARABIC, BILINGUAL)).toBe(false);
    expect(scriptsDisjoint(LATIN, BILINGUAL)).toBe(false);
  });

  it("treats a string with no script as nothing to compare, never disjoint", () => {
    expect(scriptsDisjoint("2024 / 3.5%", ARABIC)).toBe(false);
    expect(scriptsDisjoint(ARABIC, "2024 / 3.5%")).toBe(false);
  });

  it("gives the same answer whichever string is named first", () => {
    const pairs: ReadonlyArray<readonly [string, string]> = [
      [ARABIC, LATIN],
      [ARABIC, BILINGUAL],
      [HAN, LATIN],
      [GREEK, CYRILLIC],
      ["2024", ARABIC],
    ];
    for (const [one, other] of pairs) {
      expect(scriptsDisjoint(one, other)).toBe(scriptsDisjoint(other, one));
    }
  });
});

describe("the decision privileges no language and no script", () => {
  it("withholds every cross-script pair alike, not one script only", () => {
    // The corpus case is an Arabic label on a Latin heading, but the rule is
    // about scripts sharing, not about Arabic. A label in any script the
    // heading lacks is disjoint from it, identically.
    expect(scriptsDisjoint(ARABIC, LATIN)).toBe(true);
    expect(scriptsDisjoint(HAN, LATIN)).toBe(true);
    expect(scriptsDisjoint(HEBREW, LATIN)).toBe(true);
    expect(scriptsDisjoint(GREEK, CYRILLIC)).toBe(true);
  });

  it("keys on script and not on language", () => {
    // Two languages in one script share it; one language could not be told from
    // another here, because a language is not what is being read.
    const persian = "\u0633\u06cc\u0627\u0633\u062a"; // Persian, written in Arabic script
    expect(scriptsDisjoint(ARABIC, persian)).toBe(false);

    const english = "policy";
    const french = "R\u00e8glement";
    const vietnamese = "Ch\u00ednh s\u00e1ch";
    expect(scriptsDisjoint(english, french)).toBe(false);
    expect(scriptsDisjoint(english, vietnamese)).toBe(false);
    expect(scriptsDisjoint(french, vietnamese)).toBe(false);
  });
});
