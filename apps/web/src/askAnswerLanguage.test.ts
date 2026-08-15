/**
 * THE LANGUAGE TABLE, AND THE GUARD THAT CANNOT READ IT.
 *
 * `tests/unit/test_no_readiness_framing.py` scans `apps/web/src` for copy that
 * frames a decision route as a deficiency — "documentation only", a bare
 * "executability" in a caption, the shapes that have evaded it five times. It
 * matches ASCII words. Every Arabic string in `askAnswerLanguage.ts` is
 * therefore invisible to it, not by oversight but by construction: the guard
 * cannot see a script it has no words in. Shipping non-English copy under a
 * guard that only reads English is shipping copy nobody checks.
 *
 * So the check moves here, where it can be written once and applied to the
 * table rather than to a language. This file:
 *
 *   - iterates `ASK_ANSWER_LANGUAGES`, so a third language is covered the
 *     moment it is appended and cannot arrive unguarded;
 *   - carries the route and fault vocabulary in both scripts, and asserts no
 *     copy string in any language names a route at all — the dialog's chrome
 *     has no business grading the source;
 *   - proves the scan is seeing, with positive controls in each script, because
 *     "no offenders" is also what a scan of nothing returns.
 *
 * WHY THE LATIN VOCABULARY IS WORD ARRAYS AND NOT PHRASES.
 *
 * Written as prose, several of these entries would be character-for-character
 * the phrasings the Python guard forbids anywhere under `apps/web/src` — and
 * that guard scans test files too, and cannot tell a forbidden phrase quoted as
 * data from one written as language. Its rule is right and is why it catches
 * real violations. `routeNotFault.test.ts` reached the same conclusion and the
 * same shape; this file follows it. A `join` costs nothing and expires never.
 */
import { describe, expect, it } from "vitest";

import {
  ASK_ANSWER_LANGUAGES,
  ASK_SCOPES,
  ASK_RECORD_SOURCES,
  DEFAULT_ASK_ANSWER_LANGUAGE,
  askAnswerLanguageByTag,
  fillCounts,
  type AskAnswerLanguage,
} from "./askAnswerLanguage";

/**
 * Ways of naming a decision route, or of calling one a shortcoming, in the
 * script this repository's other guard reads. Each is the sequence of words the
 * term normalises to; they are joined at match time.
 */
const LATIN_FAULT_WORDS: readonly (readonly string[])[] = [
  ["deterministic"],
  ["machine", "executable"],
  ["executable"],
  ["executability"],
  ["automatable"],
  ["ai", "ready"],
  ["documentation", "only"],
  ["not", "supported"],
  ["unsupported"],
  ["cannot", "be"],
  ["limitation"],
  ["shortcoming"],
  ["deficiency"],
  ["fallback"],
  ["degraded"],
];

/**
 * The same accusations in Arabic, as word sequences for the same reason — the
 * shape should not change with the script, or the next language's vocabulary
 * gets written to a looser standard than this one.
 *
 * These are what the English copy is forbidden to say, said in Arabic. The
 * point of requirement 7 is that the Arabic copy must not be allowed to say
 * what the English copy may not.
 */
const ARABIC_FAULT_WORDS: readonly (readonly string[])[] = [
  ["غير", "قابل", "للتنفيذ"],
  ["قابل", "للتنفيذ", "اليا"],
  ["توثيق", "فقط"],
  ["يدوي", "فقط"],
  ["غير", "مدعوم"],
  ["لا", "يمكن"],
  ["قصور"],
  ["عيب"],
  ["نقص"],
  ["فشل"],
  ["حتمي"],
  ["جاهز", "للذكاء", "الاصطناعي"],
];

/** Arabic diacritics and tatweel: decoration, not letters, and not part of a
 *  word for the purpose of recognising one. */
const ARABIC_MARKS = /[\u064B-\u0652\u0640\u0670]/g;

/** Codepoints Unicode keeps only for round-tripping legacy encodings. Arabic
 *  stored correctly uses none of them; text that has been through a naive
 *  shaping step is full of them. */
const PRESENTATION_FORMS = /[\uFB50-\uFDFF\uFE70-\uFEFF]/;

/**
 * A string reduced to space-separated words, in either script.
 *
 * Alef and ya carry several written forms that are the same letter; a guard
 * that distinguished them would miss a spelling a writer legitimately chose.
 */
function normalise(text: string): string {
  return text
    .toLowerCase()
    .replace(ARABIC_MARKS, "")
    .replace(/[أإآٱ]/g, "ا")
    .replace(/[ىئ]/g, "ي")
    .replace(/ة/g, "ه")
    .replace(/[^a-z\u0600-\u06FF ]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

const FAULT_TERMS: readonly string[] = [...LATIN_FAULT_WORDS, ...ARABIC_FAULT_WORDS].map((words) =>
  words.join(" "),
);

/** Every fault term a passage names, in any script. Whole-word (or whole-word-
 *  sequence) matches only, so a term is not found inside a longer word. */
function faultTermsIn(text: string): string[] {
  const value = ` ${normalise(text)} `;
  return FAULT_TERMS.filter((term) => value.includes(` ${term} `));
}

/**
 * Source with comments removed.
 *
 * A comment renders nothing. The design notes in these files legitimately
 * discuss the languages on offer — quoting a caption to explain why it is not
 * hardcoded is the opposite of hardcoding it — and a scan that could not tell
 * the two apart would push those explanations out of the code.
 *
 * The `[^:]` guard keeps `http://` from being read as the start of a comment.
 */
function withoutComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, " ").replace(/(^|[^:])\/\/[^\n]*/g, "$1");
}

/** Every string this table would put in front of a reader, with where it came
 *  from, so a failure names the entry rather than the sentence.
 *
 *  It walks whatever shape the table has rather than the shape it had when this
 *  was written. The copy is now nested — a scope holds its own headings and
 *  openers — and a walker that only read the top level would have reported a
 *  clean scan while the newest strings, the ones most likely to be wrong, were
 *  never looked at. A guard that silently stops covering what it is guarding is
 *  worse than no guard, because it is believed. */
function copyStrings(language: AskAnswerLanguage): { key: string; text: string }[] {
  const out: { key: string; text: string }[] = [
    { key: `${language.tag}.shortLabel`, text: language.shortLabel },
    { key: `${language.tag}.endonym`, text: language.endonym },
  ];
  const walk = (value: unknown, path: string): void => {
    if (typeof value === "string") {
      out.push({ key: path, text: value });
    } else if (Array.isArray(value)) {
      value.forEach((entry, i) => walk(entry, `${path}[${i}]`));
    } else if (value && typeof value === "object") {
      for (const [key, nested] of Object.entries(value)) walk(nested, `${path}.${key}`);
    }
  };
  walk(language.copy, `${language.tag}.copy`);
  return out;
}

const EVERY_STRING = ASK_ANSWER_LANGUAGES.flatMap(copyStrings);

describe("the dialog's own words say nothing about how a rule is decided, in any language", () => {
  it("is reading something", () => {
    // The verdict below is "this list is empty", which is also what a scan of
    // nothing returns. So: languages exist, each contributed a full set of
    // strings, and every one of them has content.
    expect(ASK_ANSWER_LANGUAGES.length).toBeGreaterThanOrEqual(2);
    expect(EVERY_STRING.length).toBeGreaterThanOrEqual(ASK_ANSWER_LANGUAGES.length * 30);
    for (const { key, text } of EVERY_STRING) {
      expect(text.trim(), key).not.toBe("");
    }
  });

  it("reaches the words each scope adds, in every script", () => {
    // The walker above is the only thing standing between the newest copy and
    // no review at all, and its failure mode is silence. So: name a string that
    // exists only inside a scope, in each language, and insist the scan holds
    // it. If the walk ever stops descending, this fails rather than passing
    // with less to check.
    for (const language of ASK_ANSWER_LANGUAGES) {
      const scanned = copyStrings(language).map(({ text }) => text);
      for (const scope of ASK_SCOPES) {
        const scopeCopy = language.copy.scopes[scope];
        expect(scanned, `${language.tag}/${scope} heading`).toContain(scopeCopy.titlePrefix);
        expect(scanned, `${language.tag}/${scope} placeholder`).toContain(scopeCopy.followUpPlaceholder);
        for (const opener of scopeCopy.suggestions) {
          expect(scanned, `${language.tag}/${scope} opener`).toContain(opener);
        }
      }
    }
  });

  it("recognises the accusations it is looking for, in each script", () => {
    // Assembled from the atoms above rather than written out, for the reason in
    // this file's header. Both must be caught, or the verdict means nothing.
    const latin = `This record is ${LATIN_FAULT_WORDS[6].join(" ")} and so it is a ${LATIN_FAULT_WORDS[12].join(" ")}.`;
    const arabic = `هذه القاعدة ${ARABIC_FAULT_WORDS[0].join(" ")} وهي ${ARABIC_FAULT_WORDS[6].join(" ")}.`;
    expect(faultTermsIn(latin).length).toBeGreaterThan(0);
    expect(faultTermsIn(arabic).length).toBeGreaterThan(0);
    // And it is not simply flagging everything.
    expect(faultTermsIn("Ask a follow-up about this rule")).toEqual([]);
    expect(faultTermsIn("اطرح سؤالا آخر عن هذه القاعدة")).toEqual([]);
  });

  it("finds no accusation in any language on offer", () => {
    const offenders = EVERY_STRING.flatMap(({ key, text }) =>
      faultTermsIn(text).map((term) => `${key}: ${term}`),
    );
    expect(offenders).toEqual([]);
  });
});

describe("adding a language is adding a row", () => {
  it("gives every language the same set of strings", () => {
    const shape = (language: AskAnswerLanguage) =>
      copyStrings(language)
        .map(({ key }) => key.slice(language.tag.length + 1))
        .sort();
    const first = shape(ASK_ANSWER_LANGUAGES[0]);
    expect(first.length).toBeGreaterThanOrEqual(30);
    for (const language of ASK_ANSWER_LANGUAGES) {
      // A language missing a key would render an empty caption, not an error.
      expect(shape(language), language.tag).toEqual(first);
    }
  });

  it("gives every language the same number of openers", () => {
    for (const scope of ASK_SCOPES) {
      const counts = new Set(
        ASK_ANSWER_LANGUAGES.map((language) => language.copy.scopes[scope].suggestions.length),
      );
      expect(counts.size, scope).toBe(1);
      expect([...counts][0], scope).toBeGreaterThanOrEqual(4);
    }
  });

  it("says where the records came from in every language, and says it differently for each", () => {
    // Two failures, both silent. A language missing a record source renders an
    // empty provenance line, which reads as "no note" — the same as an older
    // reply that named no source, so a reader could not tell a missing
    // translation from an absent claim. And one sentence used for both sources
    // would state a provenance that is right half the time while looking
    // authoritative all of it, which is the exact confusion the line exists to
    // remove.
    for (const language of ASK_ANSWER_LANGUAGES) {
      const seen = new Set<string>();
      for (const source of ASK_RECORD_SOURCES) {
        const note = language.copy.recordSourceNotes[source];
        expect(note, `${language.tag} has no note for ${source}`).toBeTypeOf("string");
        expect(note.trim().length, `${language.tag}.${source}`).toBeGreaterThan(20);
        expect(seen.has(note), `${language.tag}: ${source} reuses another source's words`).toBe(
          false,
        );
        seen.add(note);
      }
    }
  });

  it("keeps 'none of them' a different sentence from 'the first few of them'", () => {
    // Zero read and a prefix read are different reports, not one report with a
    // smaller number in it: the first says the answer is not about the policy at
    // all. Sharing the sentence would let a reader who skims the numbers take
    // the first for the second.
    for (const language of ASK_ANSWER_LANGUAGES) {
      const { coverageNote, groundedNothingNote } = language.copy;
      expect(groundedNothingNote.trim().length, language.tag).toBeGreaterThan(20);
      expect(groundedNothingNote, language.tag).not.toBe(coverageNote);
      // The counts belong in the copy as placeholders, not assembled around it.
      expect(groundedNothingNote.includes("{total}"), language.tag).toBe(true);
    }
  });

  it("gives every scope its own openers rather than the other scope's", () => {
    // A question worth asking about one rule is not the question worth asking
    // about the twenty rules a section was decomposed into. Reusing the set
    // would look like scope had been handled while the dialog asked the wrong
    // thing, which is harder to notice than an obviously missing feature.
    for (const language of ASK_ANSWER_LANGUAGES) {
      const seen = new Map<string, string>();
      for (const scope of ASK_SCOPES) {
        for (const opener of language.copy.scopes[scope].suggestions) {
          const already = seen.get(opener);
          expect(already, `${language.tag}: ${scope} repeats ${already}'s opener`).toBeUndefined();
          seen.set(opener, scope);
        }
      }
    }
  });

  it("states coverage as a whole sentence per language, with the counts marked", () => {
    // The two numbers are the same numbers everywhere; the words around them
    // are not, and word order is not a constant across languages. A sentence
    // glued from fragments can only come out right in the language the glue was
    // written for, so each language holds its own sentence with the numbers
    // marked in it.
    for (const language of ASK_ANSWER_LANGUAGES) {
      const note = language.copy.coverageNote;
      expect(note, `${language.tag} covered`).toContain("{covered}");
      expect(note, `${language.tag} total`).toContain("{total}");
      const filled = fillCounts(note, { covered: 12, total: 72 });
      expect(filled, `${language.tag} filled`).toContain("12");
      expect(filled, `${language.tag} filled`).toContain("72");
      expect(filled).not.toContain("{");
    }
  });

  it("leaves no other string holding an unfilled placeholder", () => {
    // A `{covered}` that reached the screen would be this app showing its own
    // scaffolding to a reviewer. The exceptions are named rather than matched
    // loosely, so a new string that carries counts has to be declared here and
    // given a `fillCounts` call rather than quietly joining the exempt set.
    const carriesCounts = new Set(["coverageNote", "groundedNothingNote"]);
    for (const { key, text } of EVERY_STRING) {
      const leaf = key.slice(key.lastIndexOf(".") + 1);
      if (carriesCounts.has(leaf)) continue;
      expect(/\{[a-z_]+\}/.test(text), key).toBe(false);
    }
  });

  it("names no language in the code that renders them", () => {
    // The mechanism must not know which languages exist. If a tag, an endonym
    // or a caption appears in a component, a third language is a code change.
    // Sources come through Vite's own graph rather than an `fs` walk: this
    // project carries no node types, and a path walk can silently resolve to
    // the wrong root and read nothing at all. Same idiom as
    // `routeNotFault.test.ts`, for the same reason.
    const modules = import.meta.glob("./**/*.{ts,tsx}", {
      query: "?raw",
      import: "default",
      eager: true,
    }) as Record<string, string>;

    const wanted = [
      "./components/AskAiModal.tsx",
      "./components/AskAboutRuleModal.tsx",
      "./components/PolicyAskAiButton.tsx",
      "./components/PublishedRuleAskAiButton.tsx",
      "./components/AnswerLanguageToggle.tsx",
      "./askInLanguage.ts",
    ];
    const sources = wanted.map((path) => {
      const raw = modules[path];
      expect(raw, `${path} was not read`).toBeTypeOf("string");
      return { path, raw, text: withoutComments(raw) };
    });

    for (const { path, raw, text } of sources) {
      expect(raw.length, path).toBeGreaterThan(200);
      expect(text.length, path).toBeGreaterThan(100);
      for (const language of ASK_ANSWER_LANGUAGES) {
        expect(text.includes(`"${language.tag}"`), `${path} names ${language.tag}`).toBe(false);
        expect(text.includes(language.endonym), `${path} names ${language.endonym}`).toBe(false);
        for (const { text: caption } of copyStrings(language)) {
          if (caption.length > 4) {
            expect(text.includes(caption), `${path} carries a caption`).toBe(false);
          }
        }
      }
    }
  });

  it("opens in the head of the table rather than in a named language", () => {
    expect(DEFAULT_ASK_ANSWER_LANGUAGE).toBe(ASK_ANSWER_LANGUAGES[0]);
    expect(askAnswerLanguageByTag(ASK_ANSWER_LANGUAGES[1].tag)).toBe(ASK_ANSWER_LANGUAGES[1]);
    // A tag from anywhere — a URL, a stored value, a language this build no
    // longer offers — resolves rather than returning nothing.
    expect(askAnswerLanguageByTag("zz-XX")).toBe(DEFAULT_ASK_ANSWER_LANGUAGE);
    expect(askAnswerLanguageByTag(null)).toBe(DEFAULT_ASK_ANSWER_LANGUAGE);
  });

  it("lets no language declare a direction", () => {
    // Direction belongs to a run of text, worked out from its characters. A
    // language that carried one would invite a caller to set it on the dialog,
    // and lay the Latin identifiers inside an Arabic answer out backwards.
    for (const language of ASK_ANSWER_LANGUAGES) {
      expect(Object.keys(language)).not.toContain("dir");
      expect(Object.keys(language)).not.toContain("direction");
      expect(Object.keys(language.copy)).not.toContain("dir");
    }
  });

  it("stores every language's own script as characters rather than as shapes", () => {
    for (const { key, text } of EVERY_STRING) {
      expect(PRESENTATION_FORMS.test(text), key).toBe(false);
    }
  });

  it("carries a real IETF tag and a name in the language itself", () => {
    const seen = new Set<string>();
    for (const language of ASK_ANSWER_LANGUAGES) {
      expect(language.tag, "tag").toMatch(/^[A-Za-z]{2,8}(-[A-Za-z0-9]{1,8})*$/);
      expect(seen.has(language.tag)).toBe(false);
      seen.add(language.tag);
      // The name a screen reader announces is the language's own, not two
      // letters of chrome.
      expect(language.endonym.trim().length).toBeGreaterThan(language.shortLabel.trim().length);
    }
  });
});
