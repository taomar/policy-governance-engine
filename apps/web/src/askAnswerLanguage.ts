/**
 * The languages the Ask-AI dialog can answer in, and every word that dialog
 * says, keyed by language and by what is being asked about.
 *
 * WHY A TABLE AND NOT A PAIR
 *
 * The request was for English and Arabic. Written as `isArabic ? a : b` that
 * request becomes a shape: two branches per string, a third language a rewrite
 * of every component that renders one. So the language is a row here and the
 * component reads `language.copy.<name>` without ever knowing which row it
 * holds. Adding one is appending an entry below — no component, no test and no
 * server code changes for it, which is the property
 * `askAnswerLanguage.test.ts` holds this file to.
 *
 * WHAT IS IN THIS TABLE AND WHAT NEVER WILL BE
 *
 * Everything here is a sentence this app wrote about its own dialog. Not one
 * character of any document is in this file, and none can be: the dialog's
 * quoted material arrives from the server at read time, is rendered as it
 * arrives, and has no entry to be translated into. That is the whole boundary
 * this feature stands on — a reviewer approves a rule against the document's
 * own words, so those words must read the same whichever button is pressed.
 * `askAboutRuleLanguage.test.tsx` asserts the rendered quotation is character-
 * identical across every language in this table.
 *
 * DIRECTION IS NOT IN THIS TABLE EITHER
 *
 * There is no `dir` column. Direction is a property of each run of text, worked
 * out from the characters by `directionalText.ts`, because an answer written in
 * one language routinely carries a rule id, an identifier or a quoted clause
 * from another. A language that declared its own direction would let a caller
 * set it on the dialog and lay those runs out backwards.
 *
 * THE TAG IS THE ONLY THING THE SERVER IS TOLD
 *
 * `tag` is an IETF BCP-47 tag. It is what is sent with the question and what is
 * set as `lang` on the words this app wrote, so assistive technology announces
 * them correctly. The server names no language of its own — it is handed the
 * tag and asked to answer in it.
 *
 * TWO SCOPES, ARRANGED THE SAME WAY AS THE LANGUAGES
 *
 * The dialog is opened about one rule or about one whole policy. Those need
 * different headings, different openers and a different placeholder, and the
 * temptation is a second table or a boolean. Both are the mistake this file was
 * written to avoid, one step along: a scope becomes a branch, and a third —
 * a document, a comparison, a run — is a rewrite. So a scope is a key inside
 * each language's copy, `ASK_SCOPES` is the only place the set is decided, and
 * `askAnswerLanguage.test.ts` holds every language to the same scopes and every
 * scope to the same keys.
 */

/** What an Ask-AI dialog can be opened about.
 *
 *  A list rather than a union written by hand, so the type is derived from the
 *  data and the two cannot drift. */
export const ASK_SCOPES = ["rule", "policy"] as const;

export type AskScopeKind = (typeof ASK_SCOPES)[number];

/** Which of this app's tables a grounded answer's records were read out of.
 *
 *  The same discipline as `ASK_SCOPES`, one step further out: a published rule
 *  and the draft row that produced it carry the same `rule_id` and can say
 *  different things, so "which record" is a fact about an answer and not a fact
 *  about which screen asked. Listed rather than hand-written as a union so a
 *  third kind of record — an imported package, a comparison run — is a row in
 *  every language's table and a compile error until it has one, rather than a
 *  silent fall-through to whichever sentence was the default. The strings match
 *  `ai_chat.RECORDS_FROM_*`. */
export const ASK_RECORD_SOURCES = ["published_version", "draft_records"] as const;

export type AskRecordSource = (typeof ASK_RECORD_SOURCES)[number];

/** The words that change with what is being asked about. */
export interface AskScopeCopy {
  /** Dialog heading, with the subject's own identifier appended unchanged. */
  titlePrefix: string;
  /** What the dialog is grounded in. */
  groundingNote: string;
  /** The same, when the grounding reaches past the one thing in the title —
   *  a rule's variation group, or a policy stated across several passages. */
  groundingNoteWider: string;
  /** The openers offered before anything has been asked. Chosen for the scope:
   *  a question worth asking about one rule is not the question worth asking
   *  about the twenty rules a section was decomposed into. */
  suggestions: readonly string[];
  /** Placeholder in the follow-up box. */
  followUpPlaceholder: string;
  /** Said when the grounding could not carry everything asked about. Holds
   *  `{covered}` and `{total}`, filled by `fillCounts`, because the numbers are
   *  the same numbers in every language and only their setting differs.
   *
   *  Per scope rather than shared, because "the first 8 of this policy's 63
   *  rules" is a true and useful sentence and the same sentence about one rule
   *  is neither: it counts a policy that was not asked about and puts a plural
   *  on a single record. A caveat a reader can see is wrong is a caveat they
   *  learn to skip, and this is the one caveat that must not be skipped. */
  coverageNote: string;
  /** Said when the grounding carried *none* of what was asked about. Holds
   *  `{total}`.
   *
   *  A separate sentence from `coverageNote` rather than the same one with a
   *  zero in it, because they are different reports. "The first three of six"
   *  is an answer about the policy, bounded. Zero of six is not an answer about
   *  the policy at all — whatever came back rests on retrieved passages alone —
   *  and a reader who skims a number would read the two as the same kind of
   *  caveat. This is the failure mode the coverage report exists to prevent, so
   *  it gets its own words. */
  groundedNothingNote: string;
}

/** Every string the dialog renders, in one language. */
export interface AskAnswerCopy {
  /** Accessible name of the language control. Never just the two short labels. */
  languageChoiceLabel: string;
  /** Says out loud that the choice reaches nothing outside this dialog. */
  languageScopeNote: string;
  /** Heading over the quoted material. */
  quotedHeading: string;
  /** Says the quoted material is not translated, whichever language is chosen. */
  quotedStaysNote: string;
  /** Said when an answer came back carrying no quoted source text at all. An
   *  answer with nothing quoted and an answer quoting the document read the
   *  same once rendered — the quoted section is simply absent — and the whole
   *  job here is deciding whether a record matches its source. So the absence
   *  is stated rather than left as a gap the reader has to notice. */
  noQuotedTextNote: string;
  /** Marks the app's own writing, the way the generated subject label does. */
  writtenByAppLabel: string;
  /** Precedes the provenance chips. */
  retrievedFromLabel: string;
  /** Which record the answer was read out of, in the reader's language.
   *
   *  A table keyed by the server's own term rather than a pair of sentences
   *  chosen by a boolean, for the reason the language table itself is a table:
   *  a third kind of record is then a row here and no change to a component. */
  recordSourceNotes: Record<AskRecordSource, string>;
  /** The send button. */
  askLabel: string;
  /** Shown while a question is in flight. */
  thinkingLabel: string;
  /** Heading when the request itself did not complete. */
  failedHeading: string;
  /** Offer to send the same question again. */
  retryLabel: string;
  /** The request completed and carried nothing to show. Not a failure. */
  emptyAnswerNote: string;
  /** The words that depend on what is being asked about. */
  scopes: Record<AskScopeKind, AskScopeCopy>;
}

export interface AskAnswerLanguage {
  /** IETF BCP-47 tag. Sent to the server; set as `lang` on this app's words. */
  tag: string;
  /** What the control shows. Short by request — "En / Ar". */
  shortLabel: string;
  /** The language's name in itself, used as each option's accessible name so a
   *  screen reader announces a language rather than two letters. */
  endonym: string;
  copy: AskAnswerCopy;
}

const ENGLISH: AskAnswerLanguage = {
  tag: "en",
  shortLabel: "En",
  endonym: "English",
  copy: {
    languageChoiceLabel: "Language of the answers in this dialog",
    languageScopeNote: "Applies to this dialog only.",
    quotedHeading: "The document's own words",
    quotedStaysNote:
      "Quoted text is shown as the document wrote it, in its own language, whichever language you choose here.",
    noQuotedTextNote:
      "This answer quoted no source text. What follows is this app's own reflection; read it against the rule before you rely on it.",
    writtenByAppLabel: "In plain words, by this app",
    retrievedFromLabel: "Retrieved from",
    recordSourceNotes: {
      published_version:
        "Read from the published version on screen — the sealed records, not the drafts under review.",
      draft_records:
        "Read from the draft records under review — what this app extracted, before publication.",
    },
    askLabel: "Ask",
    thinkingLabel: "Thinking…",
    failedHeading: "The request did not complete",
    retryLabel: "Ask again",
    emptyAnswerNote:
      "The question was answered and the answer held nothing to show. Asking it another way may get further.",
    scopes: {
      rule: {
        titlePrefix: "Ask AI about",
        groundingNote:
          "Grounded specifically in this rule — the document's own words, plus a separate reflection written by this app.",
        groundingNoteWider:
          "Grounded specifically in this rule and its variation group — the document's own words, plus a separate reflection written by this app.",
        suggestions: [
          "Explain this rule in plain English",
          "Does this conflict with any other rule?",
          "What happens if a required fact is missing?",
          "Summarize the exceptions in one sentence",
        ],
        followUpPlaceholder: "Ask a follow-up about this rule…",
        coverageNote:
          "This answer was grounded in {covered} of the {total} records asked for. The rest are on the card and are unchanged by this.",
        groundedNothingNote:
          "This rule's record was not read for this answer. Whatever follows rests on retrieved passages alone, so do not read it as a statement about the record on the card.",
      },
      policy: {
        titlePrefix: "Ask AI about",
        groundingNote:
          "Grounded in every rule this policy was decomposed into, together with the passage they were read from — the document's own words, plus a separate reflection written by this app.",
        groundingNoteWider:
          "Grounded in every rule this policy was decomposed into, together with the passages they were read from — the document's own words, plus a separate reflection written by this app.",
        suggestions: [
          "What does this policy require, taken as a whole?",
          "Do its rules agree with one another?",
          "Which of its rules apply only in some situations?",
          "Does the record here differ from the passage it was read from?",
        ],
        followUpPlaceholder: "Ask a follow-up about this policy…",
        coverageNote:
          "This answer was grounded in the first {covered} of this policy's {total} rules, in document order. The remaining rules are on the card and are unchanged by this.",
        groundedNothingNote:
          "None of this policy's {total} rules were read for this answer. Whatever follows rests on retrieved passages alone, so do not read it as a statement about the records on the card.",
      },
    },
  },
};

const ARABIC: AskAnswerLanguage = {
  tag: "ar",
  shortLabel: "Ar",
  endonym: "العربية",
  copy: {
    languageChoiceLabel: "لغة الإجابات في هذه النافذة",
    languageScopeNote: "ينطبق على هذه النافذة وحدها.",
    quotedHeading: "كلمات المستند نفسها",
    quotedStaysNote:
      "النص المقتبس يظهر كما كتبه المستند، بلغته هو، مهما كانت اللغة التي تختارها هنا.",
    noQuotedTextNote:
      "لم تقتبس هذه الإجابة أي نص من المستند. ما يلي هو تأمل هذا التطبيق وحده؛ اقرأه مقابل القاعدة قبل الاعتماد عليه.",
    writtenByAppLabel: "بكلمات مبسطة، من هذا التطبيق",
    retrievedFromLabel: "مأخوذ من",
    recordSourceNotes: {
      published_version:
        "مقروء من النسخة المنشورة المعروضة — السجلات المختومة، لا المسودات قيد المراجعة.",
      draft_records:
        "مقروء من سجلات المسودة قيد المراجعة — ما استخرجه هذا التطبيق، قبل النشر.",
    },
    askLabel: "اسأل",
    thinkingLabel: "جارٍ التفكير…",
    failedHeading: "لم يكتمل الطلب",
    retryLabel: "اسأل مرة أخرى",
    emptyAnswerNote:
      "تمت الإجابة على السؤال ولم تحمل الإجابة شيئًا يُعرض. قد تصل صياغة أخرى للسؤال إلى نتيجة.",
    scopes: {
      rule: {
        titlePrefix: "اسأل الذكاء الاصطناعي عن",
        groundingNote:
          "مبني تحديدًا على هذه القاعدة — كلمات المستند نفسها، مع تأمل منفصل كتبه هذا التطبيق.",
        groundingNoteWider:
          "مبني تحديدًا على هذه القاعدة ومجموعة تنويعاتها — كلمات المستند نفسها، مع تأمل منفصل كتبه هذا التطبيق.",
        suggestions: [
          "اشرح هذه القاعدة بكلمات مبسطة",
          "هل تتعارض هذه القاعدة مع قاعدة أخرى؟",
          "ماذا يحدث إذا غابت إحدى الحقائق المطلوبة؟",
          "لخّص الاستثناءات في جملة واحدة",
        ],
        followUpPlaceholder: "اطرح سؤالًا آخر عن هذه القاعدة…",
        coverageNote:
          "بُنيت هذه الإجابة على {covered} من أصل {total} من السجلات المطلوبة. وما تبقّى معروض على البطاقة ولم يمسّه شيء.",
        groundedNothingNote:
          "لم يُقرأ سجل هذه القاعدة من أجل هذه الإجابة. وما يلي يستند إلى المقاطع المسترجَعة وحدها، فلا تقرأه على أنه قول عن السجل المعروض على البطاقة.",
      },
      policy: {
        titlePrefix: "اسأل الذكاء الاصطناعي عن",
        groundingNote:
          "مبني على كل قاعدة استُخرجت من هذه السياسة، مع المقطع الذي قُرئت منه — كلمات المستند نفسها، مع تأمل منفصل كتبه هذا التطبيق.",
        groundingNoteWider:
          "مبني على كل قاعدة استُخرجت من هذه السياسة، مع المقاطع التي قُرئت منها — كلمات المستند نفسها، مع تأمل منفصل كتبه هذا التطبيق.",
        suggestions: [
          "ماذا تشترط هذه السياسة في مجملها؟",
          "هل تتفق قواعدها مع بعضها؟",
          "أي من قواعدها ينطبق في حالات بعينها فقط؟",
          "هل يختلف السجل هنا عن المقطع الذي قُرئ منه؟",
        ],
        followUpPlaceholder: "اطرح سؤالًا آخر عن هذه السياسة…",
        coverageNote:
          "بُنيت هذه الإجابة على أول {covered} من قواعد هذه السياسة البالغ عددها {total}، بترتيب المستند. وبقية القواعد معروضة على البطاقة ولم يمسّها شيء.",
        groundedNothingNote:
          "لم تُقرأ أي قاعدة من قواعد هذه السياسة البالغ عددها {total} من أجل هذه الإجابة. وما يلي يستند إلى المقاطع المسترجَعة وحدها، فلا تقرأه على أنه قول عن السجلات المعروضة على البطاقة.",
      },
    },
  },
};

/**
 * The languages on offer, in the order the control shows them.
 *
 * The first entry is what a freshly opened dialog answers in.
 */
export const ASK_ANSWER_LANGUAGES: readonly AskAnswerLanguage[] = [ENGLISH, ARABIC];

/** What the dialog opens in. Deliberately read from the table's head rather
 *  than named, so the table stays the only place the set is decided. */
export const DEFAULT_ASK_ANSWER_LANGUAGE = ASK_ANSWER_LANGUAGES[0];

/**
 * The entry for a tag, or the default when the tag is not one this build
 * offers. A caller can therefore hold a tag from anywhere — a URL, a stored
 * value, a future column — without a lookup that can return nothing.
 */
export function askAnswerLanguageByTag(tag: string | null | undefined): AskAnswerLanguage {
  return (
    ASK_ANSWER_LANGUAGES.find((language) => language.tag === tag) ?? DEFAULT_ASK_ANSWER_LANGUAGE
  );
}

/**
 * Puts the two counts into a coverage sentence.
 *
 * The counts sit in the copy as `{covered}` and `{total}` rather than the
 * sentence being assembled from fragments, because word order is not a constant
 * across languages and a sentence glued together from pieces can only be
 * correct in the language whose order the glue was written for. A whole
 * sentence per language with the numbers marked is translatable; "the first",
 * covered, "of", total, "rules" is not.
 */
export function fillCounts(
  template: string,
  counts: { covered: number; total: number },
): string {
  return template
    .replace("{covered}", String(counts.covered))
    .replace("{total}", String(counts.total));
}
