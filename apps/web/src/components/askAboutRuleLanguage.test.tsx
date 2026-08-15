/**
 * THE DOCUMENT'S WORDS DO NOT CHANGE LANGUAGE. OURS DO.
 *
 * The dialog answers in the language a reader picks. An answer arrives in two
 * halves — quoted source text, and this app's own reflection over it — and the
 * whole value of this product is that the first half is the document,
 * character for character. So the language control has to move exactly one of
 * them.
 *
 * The failure being guarded against is not a crash. It is a reviewer reading a
 * fluent Arabic rendering of an English clause, approving the rule against it,
 * and believing they had checked the source. Nothing on screen would look
 * wrong. The only thing that can catch it is an assertion that the quoted run
 * rendered in one language is the same string, character for character, as the
 * quoted run rendered in another — which is what
 * `renders quoted source text identically in every language` does, over every
 * language in the table rather than over a named pair.
 *
 * WHY SO MANY OF THESE TESTS ARE PAIRED
 *
 * "The English copy is gone after switching" also passes when the dialog
 * renders nothing at all, and "the quotation is unchanged" also passes when
 * there is no quotation. Every absence assertion below therefore sits beside a
 * presence assertion on the same run.
 */
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

import type { AskResponse, CandidateRule, CanonicalRule } from "../api";
import { ASK_ANSWER_LANGUAGES, askAnswerLanguageByTag } from "../askAnswerLanguage";
import { AskAboutRuleModal } from "./AskAboutRuleModal";
import { AskAiDrawer } from "./AskAiDrawer";

beforeAll(() => {
  // antd reads both on mount and jsdom implements neither.
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }));
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  );
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const ENGLISH = askAnswerLanguageByTag("en");
const ARABIC = askAnswerLanguageByTag("ar");

/** A clause as an English document wrote it. Quoted, so never rendered into
 *  another language whatever the reader picks. */
const ENGLISH_CLAUSE =
  "A staff member found in breach of clause 4.2 shall be given a written warning within five working days.";

/** The same, from a document written in Arabic. */
const ARABIC_CLAUSE = "يُمنح الموظف المخالف إنذارًا كتابيًا خلال خمسة أيام عمل من تاريخ الواقعة.";

/** This app's own words, in Arabic, carrying a Latin identifier and an English
 *  fragment of the clause it is discussing — the ordinary shape of a real
 *  answer, and the shape a dialog-level direction lays out backwards. */
const ARABIC_REFLECTION =
  'تشير هذه القاعدة إلى المُعرِّف any-employee-found-guilty وتقتبس عبارة "written warning" كما وردت في المستند.';

const ENGLISH_REFLECTION = "This rule fires once, and the exception in clause 4.3 is the only way past it.";

const RULE_ID = "AI-eb7e2e437d";

function canonical(): CanonicalRule {
  return {
    schema_version: "1.0",
    policy_set_id: "set",
    policy_version_id: "draft",
    rule_id: RULE_ID,
    rule_revision: 1,
    title: "Written warning on breach",
    description: ENGLISH_CLAUSE,
    rule_type: "obligation",
    authority: { level: "ai_drafted", owner: "formulator", rank: 0 },
    scope: { jurisdictions: [], organizational_units: [], personas: [], processes: [] },
    condition: { type: "all", all: [] },
    attributes: { applies: [], outcome: [] },
    effect: { type: "require_action", action: "warn" },
    required_facts: [],
    exceptions: [],
    priority: 0,
    effective_from: "2026-01-01",
    effective_to: null,
    machine_executable: false,
    ambiguity_status: "clear",
    review_status: "candidate",
    evidence: [],
    lineage: {
      extraction_run_id: "run",
      deployment_name: "model",
      prompt_version: "v1",
      parser_version: "v1",
      schema_version: "1.0",
    },
    category: "general",
    tags: [],
    group_label: "",
    related_rule_ids: [],
    is_explicit_override: false,
    supersedes_rule_ids: [],
    advice: [],
  } as CanonicalRule;
}

function candidate(): CandidateRule {
  return {
    id: "candidate-1",
    policy_set_id: "set",
    extraction_run_id: "run",
    rule_type: "obligation",
    revision: 1,
    review_status: "candidate",
    reviewed_by: null,
    reviewed_at: null,
    review_notes: null,
    published_version_id: null,
    created_at: "2026-01-01T00:00:00Z",
    delta_status: null,
    reworded: false,
    baseline_candidate_id: null,
    superseded_by_candidate_id: null,
    superseded_at: null,
    rule: canonical(),
  };
}

function answer(overrides: Partial<AskResponse> = {}): AskResponse {
  return {
    groups: [
      {
        heading: "Warnings",
        facts: [{ text: ENGLISH_CLAUSE, source_label: "Staff Handbook — p12-para-3" }],
      },
    ],
    reflection: ENGLISH_REFLECTION,
    sources: [{ heading: "Staff Handbook", section: "4.2", clause_id: "c1", document_id: "d1" }],
    ...overrides,
  };
}

/** The bodies of every request the component made, parsed. */
function requestBodies(fetchMock: ReturnType<typeof vi.fn>): Record<string, unknown>[] {
  return fetchMock.mock.calls.map(([, init]) => JSON.parse(String((init as RequestInit).body)));
}

function serve(result: AskResponse) {
  const fetchMock = vi.fn(async () => ({ ok: true, status: 200, json: async () => result }) as unknown as Response);
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

/** Pick a language on the control. Named by the language's own name for itself,
 *  which is what a screen reader is given. */
function choose(endonym: string) {
  fireEvent.click(screen.getByRole("radio", { name: endonym }));
}

/** Send one of the offered openers. */
function clickSuggestion(label: string) {
  const tag = screen.getByText(label).closest(".ask-rule-suggestion");
  expect(tag).not.toBeNull();
  fireEvent.click(tag as Element);
}

describe("the dialog speaks the reader's language and quotes the document's", () => {
  it("opens in the first language of the table, with that language's openers", () => {
    serve(answer());
    render(<AskAboutRuleModal candidate={candidate()} onClose={() => {}} />);

    for (const opener of ENGLISH.copy.scopes.rule.suggestions) {
      expect(screen.getByText(opener)).toBeTruthy();
    }
    expect(screen.getByText(ENGLISH.copy.scopes.rule.groundingNote)).toBeTruthy();
    expect(screen.getByPlaceholderText(ENGLISH.copy.scopes.rule.followUpPlaceholder)).toBeTruthy();
    expect(document.querySelector(".ask-rule-header")?.textContent).toContain(
      `${ENGLISH.copy.scopes.rule.titlePrefix} ${RULE_ID}`,
    );
  });

  it("moves every opener, the heading, the note and the placeholder to the chosen language", () => {
    serve(answer());
    render(<AskAboutRuleModal candidate={candidate()} onClose={() => {}} />);

    choose(ARABIC.endonym);

    for (const opener of ARABIC.copy.scopes.rule.suggestions) {
      expect(screen.getByText(opener)).toBeTruthy();
    }
    expect(screen.getByText(ARABIC.copy.scopes.rule.groundingNote)).toBeTruthy();
    expect(screen.getByPlaceholderText(ARABIC.copy.scopes.rule.followUpPlaceholder)).toBeTruthy();
    // The rule's own id is not language and is not translated; it is still
    // there, beside a heading that now is, and each is laid out as its own run
    // rather than as one string in one direction.
    const header = document.querySelector(".ask-rule-header");
    expect(header?.textContent).toContain(ARABIC.copy.scopes.rule.titlePrefix);
    expect(header?.textContent).toContain(RULE_ID);
    expect([...(header?.querySelectorAll("bdi") ?? [])].some((run) => run.getAttribute("dir") === "rtl")).toBe(
      true,
    );

    // Paired with the presence assertions above: the English copy is gone
    // rather than merely joined.
    for (const opener of ENGLISH.copy.scopes.rule.suggestions) {
      expect(screen.queryByText(opener)).toBeNull();
    }
    expect(screen.queryByText(ENGLISH.copy.scopes.rule.groundingNote)).toBeNull();
  });

  it("asks the server for the answer in the chosen language, and changes nothing else about the request", async () => {
    const fetchMock = serve(answer());
    render(<AskAboutRuleModal candidate={candidate()} onClose={() => {}} />);

    choose(ARABIC.endonym);
    clickSuggestion(ARABIC.copy.scopes.rule.suggestions[0]);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [body] = requestBodies(fetchMock);
    expect(body.answer_language).toBe(ARABIC.tag);
    // The opener that was sent is the one the reader saw, not its English twin.
    expect(body.question).toBe(ARABIC.copy.scopes.rule.suggestions[0]);
    expect(body.focus_candidate_rule_id).toBe("candidate-1");
    // A rule ask grounds on the rule and on nothing wider. If this ever carried
    // a list, the dialog would be answering about a policy under a rule's
    // heading, and the reader would have no way of telling.
    expect(body.focus_rule_ids).toBeNull();
    expect(Object.keys(body).sort()).toEqual(
      [
        "answer_language",
        "focus_candidate_rule_id",
        "focus_rule_ids",
        "history",
        "policy_set_key",
        "question",
      ].sort(),
    );
  });

  it("renders quoted source text identically in every language the table offers", async () => {
    const rendered: string[] = [];

    for (const language of ASK_ANSWER_LANGUAGES) {
      serve(answer());
      render(<AskAboutRuleModal candidate={candidate()} onClose={() => {}} />);
      choose(language.endonym);
      clickSuggestion(language.copy.scopes.rule.suggestions[0]);

      const fact = await screen.findByTestId("ask-rule-fact");
      rendered.push(fact.textContent ?? "");
      cleanup();
    }

    // Present: something was rendered at all, in every language.
    expect(rendered).toHaveLength(ASK_ANSWER_LANGUAGES.length);
    for (const text of rendered) {
      expect(text).toBe(ENGLISH_CLAUSE);
    }
    // Identical: not merely each equal to a constant, but equal to each other,
    // so this still means something if the clause above is ever changed.
    expect(new Set(rendered).size).toBe(1);
  });

  it("keeps an English clause in English inside an Arabic answer, and an Arabic clause in Arabic inside an English one", async () => {
    serve(
      answer({
        groups: [{ heading: "تحذيرات", facts: [{ text: ENGLISH_CLAUSE, source_label: null }] }],
        reflection: ARABIC_REFLECTION,
      }),
    );
    render(<AskAboutRuleModal candidate={candidate()} onClose={() => {}} />);
    choose(ARABIC.endonym);
    clickSuggestion(ARABIC.copy.scopes.rule.suggestions[0]);

    expect((await screen.findByTestId("ask-rule-fact")).textContent).toBe(ENGLISH_CLAUSE);
    expect((await screen.findByTestId("ask-rule-reflection")).textContent).toContain(ARABIC_REFLECTION);
    cleanup();

    serve(
      answer({
        groups: [{ heading: "Warnings", facts: [{ text: ARABIC_CLAUSE, source_label: null }] }],
        reflection: ENGLISH_REFLECTION,
      }),
    );
    render(<AskAboutRuleModal candidate={candidate()} onClose={() => {}} />);
    clickSuggestion(ENGLISH.copy.scopes.rule.suggestions[0]);

    expect((await screen.findByTestId("ask-rule-fact")).textContent).toBe(ARABIC_CLAUSE);
    expect((await screen.findByTestId("ask-rule-reflection")).textContent).toContain(ENGLISH_REFLECTION);
  });

  it("says which words are the document's and which are its own", async () => {
    serve(answer({ reflection: ARABIC_REFLECTION }));
    render(<AskAboutRuleModal candidate={candidate()} onClose={() => {}} />);
    choose(ARABIC.endonym);
    clickSuggestion(ARABIC.copy.scopes.rule.suggestions[0]);

    const quoted = await screen.findByTestId("ask-rule-quoted");
    expect(quoted.textContent).toContain(ARABIC.copy.quotedHeading);
    // The promise the toggle makes, said where the quotation is, in the
    // language the reader chose.
    expect(quoted.textContent).toContain(ARABIC.copy.quotedStaysNote);

    const reflection = await screen.findByTestId("ask-rule-reflection");
    expect(reflection.getAttribute("data-generated")).toBe("true");
    expect(reflection.textContent).toContain("✦");
    expect(reflection.textContent).toContain(ARABIC.copy.writtenByAppLabel);
  });

  it("claims a language for its own words and claims none for the document's", async () => {
    serve(answer({ reflection: ARABIC_REFLECTION }));
    render(<AskAboutRuleModal candidate={candidate()} onClose={() => {}} />);
    choose(ARABIC.endonym);
    clickSuggestion(ARABIC.copy.scopes.rule.suggestions[0]);

    const reflection = await screen.findByTestId("ask-rule-reflection");
    expect(reflection.getAttribute("lang")).toBe(ARABIC.tag);

    // The quotation's language is the document's, which this app does not know.
    // Nothing between the quoted run and the dialog may assert one.
    const fact = await screen.findByTestId("ask-rule-fact");
    const claimed = fact.closest("[lang]");
    expect(claimed).toBeNull();
  });

  it("sets no direction on the dialog, and lays each run of a mixed answer out in its own", async () => {
    serve(answer({ reflection: ARABIC_REFLECTION }));
    render(<AskAboutRuleModal candidate={candidate()} onClose={() => {}} />);
    choose(ARABIC.endonym);
    clickSuggestion(ARABIC.copy.scopes.rule.suggestions[0]);

    const reflection = await screen.findByTestId("ask-rule-reflection");
    const dialog = reflection.closest("[role='dialog']");
    expect(dialog).not.toBeNull();
    expect((dialog as Element).getAttribute("dir")).toBeNull();
    expect(document.documentElement.getAttribute("dir")).toBeNull();

    const runs = [...reflection.querySelectorAll("bdi")];
    expect(runs.some((run) => run.getAttribute("dir") === "rtl")).toBe(true);
    // The Latin identifier and the quoted English fragment inside an Arabic
    // sentence each keep their own direction.
    expect(runs.some((run) => run.getAttribute("dir") === "ltr")).toBe(true);
    // And nothing was reordered or dropped on the way.
    expect(reflection.textContent).toContain(ARABIC_REFLECTION);
  });

  it("reaches nothing outside this dialog", async () => {
    const stored = vi.spyOn(Storage.prototype, "setItem");
    const documentLanguage = document.documentElement.getAttribute("lang");
    serve(answer());
    render(
      <>
        <AskAboutRuleModal candidate={candidate()} onClose={() => {}} />
        <AskAiDrawer open onClose={() => {}} policySets={[]} />
      </>,
    );

    choose(ARABIC.endonym);

    // The sibling surface that shares this request path is untouched.
    expect(screen.getByPlaceholderText("Ask about a policy…")).toBeTruthy();
    expect(document.documentElement.getAttribute("lang")).toBe(documentLanguage);
    expect(document.documentElement.getAttribute("dir")).toBeNull();
    expect(stored).not.toHaveBeenCalled();
  });

  it("opens in the default language again next time, having stored nothing", () => {
    serve(answer());
    const first = render(<AskAboutRuleModal candidate={candidate()} onClose={() => {}} />);
    choose(ARABIC.endonym);
    expect(screen.getByText(ARABIC.copy.scopes.rule.groundingNote)).toBeTruthy();
    first.unmount();
    cleanup();

    render(<AskAboutRuleModal candidate={candidate()} onClose={() => {}} />);
    expect(screen.getByText(ENGLISH.copy.scopes.rule.groundingNote)).toBeTruthy();
    expect(screen.queryByText(ARABIC.copy.scopes.rule.groundingNote)).toBeNull();
  });

  it("leaves an answer already on screen in the language it was asked in", async () => {
    serve(answer());
    render(<AskAboutRuleModal candidate={candidate()} onClose={() => {}} />);
    clickSuggestion(ENGLISH.copy.scopes.rule.suggestions[0]);

    const reflection = await screen.findByTestId("ask-rule-reflection");
    expect(reflection.getAttribute("lang")).toBe(ENGLISH.tag);

    choose(ARABIC.endonym);

    // Not relabelled, and — the point — not rewritten.
    expect(screen.getByTestId("ask-rule-reflection").getAttribute("lang")).toBe(ENGLISH.tag);
    expect(screen.getByTestId("ask-rule-reflection").textContent).toContain(ENGLISH_REFLECTION);
    expect(screen.getByTestId("ask-rule-fact").textContent).toBe(ENGLISH_CLAUSE);
  });
});

describe("nothing asked, waiting, refused and failed stay four different things", () => {
  it("offers openers and says nothing else before anything is asked", () => {
    serve(answer());
    render(<AskAboutRuleModal candidate={candidate()} onClose={() => {}} />);

    expect(screen.getByTestId("ask-rule-suggestions")).toBeTruthy();
    expect(screen.queryByTestId("ask-rule-thinking")).toBeNull();
    expect(screen.queryByTestId("ask-rule-quoted")).toBeNull();
    expect(screen.queryByTestId("ask-rule-empty")).toBeNull();
    expect(screen.queryByTestId("ask-rule-failed")).toBeNull();
  });

  it("says it is waiting, in the chosen language, while the question is in flight", async () => {
    let release: (value: Response) => void = () => {};
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise<Response>((resolve) => (release = resolve))),
    );
    render(<AskAboutRuleModal candidate={candidate()} onClose={() => {}} />);
    choose(ARABIC.endonym);
    clickSuggestion(ARABIC.copy.scopes.rule.suggestions[0]);

    const waiting = await screen.findByTestId("ask-rule-thinking");
    expect(waiting.textContent).toContain(ARABIC.copy.thinkingLabel);
    expect(screen.queryByTestId("ask-rule-failed")).toBeNull();
    expect(screen.queryByTestId("ask-rule-empty")).toBeNull();

    release({ ok: true, status: 200, json: async () => answer() } as unknown as Response);
    await screen.findByTestId("ask-rule-quoted");
  });

  it("tells a request that never completed apart from an answer that held nothing", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("Failed to fetch");
      }),
    );
    render(<AskAboutRuleModal candidate={candidate()} onClose={() => {}} />);
    choose(ARABIC.endonym);
    clickSuggestion(ARABIC.copy.scopes.rule.suggestions[0]);

    const failed = await screen.findByTestId("ask-rule-failed");
    expect(failed.textContent).toContain(ARABIC.copy.failedHeading);
    expect(failed.textContent).toContain(ARABIC.copy.retryLabel);
    // The exception name never reaches a reviewer.
    expect(failed.textContent).not.toContain("TypeError");
    expect(screen.queryByTestId("ask-rule-empty")).toBeNull();
    cleanup();

    serve({ groups: [], reflection: "", sources: [] });
    render(<AskAboutRuleModal candidate={candidate()} onClose={() => {}} />);
    choose(ARABIC.endonym);
    clickSuggestion(ARABIC.copy.scopes.rule.suggestions[0]);

    const empty = await screen.findByTestId("ask-rule-empty");
    expect(empty.textContent).toContain(ARABIC.copy.emptyAnswerNote);
    expect(screen.queryByTestId("ask-rule-failed")).toBeNull();
  });

  it("sends the same question again when asked to, in the language it was asked in", async () => {
    const fetchMock = vi.fn(async () => {
      throw new TypeError("Failed to fetch");
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<AskAboutRuleModal candidate={candidate()} onClose={() => {}} />);
    choose(ARABIC.endonym);
    clickSuggestion(ARABIC.copy.scopes.rule.suggestions[0]);

    fireEvent.click(await screen.findByText(ARABIC.copy.retryLabel));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const bodies = requestBodies(fetchMock as unknown as ReturnType<typeof vi.fn>);
    expect(bodies[1].question).toBe(ARABIC.copy.scopes.rule.suggestions[0]);
    expect(bodies[1].answer_language).toBe(ARABIC.tag);
  });
});

describe("an answer that quoted nothing says so", () => {
  // Under this dialog's licence to help the reviewer: a reply carrying a
  // reflection and no facts rendered exactly like a grounded one, because the
  // quoted section is simply absent when there is nothing to put in it. The
  // reviewer's whole job is deciding whether a record matches its source, and
  // "the model wrote prose and quoted no source" is the one thing they most
  // need told. Absent is not empty here either: this is a fifth condition
  // stated out loud, and it collapses none of the four.
  it("marks an ungrounded answer in whichever language it was asked in", async () => {
    for (const language of ASK_ANSWER_LANGUAGES) {
      serve(answer({ groups: [], reflection: ENGLISH_REFLECTION }));
      render(<AskAboutRuleModal candidate={candidate()} onClose={() => {}} />);
      choose(language.endonym);
      clickSuggestion(language.copy.scopes.rule.suggestions[0]);

      const note = await screen.findByTestId("ask-rule-unquoted");
      expect(note.textContent, language.tag).toContain(language.copy.noQuotedTextNote);
      // Said in the reader's language, and announced as such.
      expect(note.querySelector(`[lang="${language.tag}"]`), language.tag).not.toBeNull();
      // The four states it must not be mistaken for. An answer arrived, so this
      // is neither absence nor failure, and the reflection is still shown.
      expect(screen.queryByTestId("ask-rule-empty"), language.tag).toBeNull();
      expect(screen.queryByTestId("ask-rule-failed"), language.tag).toBeNull();
      expect(screen.queryByTestId("ask-rule-thinking"), language.tag).toBeNull();
      expect(screen.queryByTestId("ask-rule-reflection"), language.tag).not.toBeNull();
      cleanup();
    }
  });

  it("says nothing of the kind when the document was quoted", async () => {
    serve(answer());
    render(<AskAboutRuleModal candidate={candidate()} onClose={() => {}} />);
    clickSuggestion(ENGLISH.copy.scopes.rule.suggestions[0]);

    await screen.findByTestId("ask-rule-quoted");
    expect(screen.queryByTestId("ask-rule-unquoted")).toBeNull();
  });
});

describe("the control is a control", () => {
  it("is a named group of radios carrying each language's own name", () => {
    serve(answer());
    render(<AskAboutRuleModal candidate={candidate()} onClose={() => {}} />);

    const group = screen.getByRole("radiogroup");
    const name = group.getAttribute("aria-label") ?? "";
    expect(name).toContain(ENGLISH.copy.languageChoiceLabel);
    expect(name).toContain(ENGLISH.copy.languageScopeNote);
    // Not two letters to a screen reader.
    expect(name.trim().length).toBeGreaterThan(ENGLISH.shortLabel.length + ARABIC.shortLabel.length);

    for (const language of ASK_ANSWER_LANGUAGES) {
      const option = screen.getByRole("radio", { name: language.endonym }) as HTMLInputElement;
      expect(option.checked).toBe(language.tag === ENGLISH.tag);
    }

    choose(ARABIC.endonym);
    expect((screen.getByRole("radio", { name: ARABIC.endonym }) as HTMLInputElement).checked).toBe(true);
    expect((screen.getByRole("radio", { name: ENGLISH.endonym }) as HTMLInputElement).checked).toBe(false);
  });
});
