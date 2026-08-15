/**
 * ASKING ABOUT A WHOLE POLICY, WITHOUT TRANSLATING IT.
 *
 * The scope changed and the constraint did not. A policy-wide answer quotes more
 * of the document than a rule-wide one, so the failure the rule-scope tests
 * guard against — a reviewer reading a fluent rendering of a clause, approving
 * against it, and believing they had checked the source — has more surface here,
 * not less. The assertions that matter most in this file are the ones that
 * compare a quoted run rendered in one language against the same run rendered in
 * another, character for character, over every language in the table rather than
 * over a named pair.
 *
 * The second thing held here is coverage. A policy can hold more rules than one
 * request carries. An answer grounded in part of a policy and an answer grounded
 * in all of it look identical on screen unless something says otherwise, so the
 * dialog says it — before the answer, in the reader's language, with the counts.
 *
 * WHY SO MANY OF THESE TESTS ARE PAIRED
 *
 * "The English copy is gone after switching" also passes when the dialog renders
 * nothing at all, and "the quotation is unchanged" also passes when there is no
 * quotation. Every absence assertion below sits beside a presence assertion on
 * the same run.
 */
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

import type { AskResponse, AssembledPolicy } from "../api";
import { ASK_ANSWER_LANGUAGES, askAnswerLanguageByTag, fillCounts } from "../askAnswerLanguage";
import { AskAboutRuleModal } from "./AskAboutRuleModal";
import { PolicyAskAiButton } from "./PolicyAskAiButton";

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
  "No employee may participate in a hiring decision concerning a relative, and any such involvement must be declared in writing.";

/** The same, from a document written in Arabic. */
const ARABIC_CLAUSE = "لا يجوز لأي موظف المشاركة في قرار توظيف يخص أحد أقاربه، ويجب الإفصاح عن ذلك كتابيًا.";

/** This app's own words, in Arabic, carrying a Latin identifier and an English
 *  fragment of the clause it is discussing — the ordinary shape of a real
 *  answer, and the shape a dialog-level direction lays out backwards. */
const ARABIC_REFLECTION =
  'تتفق قواعد هذه السياسة فيما بينها: يشير المُعرِّف any-employee-found-guilty إلى عبارة "declared in writing" كما وردت في المستند.';

const ENGLISH_REFLECTION =
  "Taken together, these rules bar a relative from the decision and require the relationship to be declared.";

const POLICY_HEADING = "7.11. HIRING RELATIVES & NEPOTISM";
const POLICY_SET_KEY = "set-key-1";

function policy(ruleCount = 6): AssembledPolicy {
  return {
    key: "prov-1",
    heading: POLICY_HEADING,
    heading_path: ["7. RECRUITMENT", POLICY_HEADING],
    topic_label: null,
    persisted: true,
    provision_id: "prov-1",
    document_version_id: "dv-1",
    source_elements: "e1,e2",
    page: 11,
    rule_count: ruleCount,
    passage_count: 2,
    route: "both",
    passages: [],
    rules: Array.from({ length: ruleCount }, (_, i) => ({
      rule_id: `AI-rule-${i}`,
      title: `Rule ${i}`,
      evaluation_mode: "ai_ready",
    })) as AssembledPolicy["rules"],
  } as AssembledPolicy;
}

function answer(overrides: Partial<AskResponse> & { grounding?: unknown } = {}) {
  return {
    groups: [
      {
        heading: "Declaring a relationship",
        facts: [{ text: ENGLISH_CLAUSE, source_label: "Staff Handbook — p11-para-2" }],
      },
    ],
    reflection: ENGLISH_REFLECTION,
    sources: [{ heading: "Staff Handbook", section: "7.11", clause_id: "c1", document_id: "d1" }],
    ...overrides,
  };
}

function requestBodies(fetchMock: ReturnType<typeof vi.fn>): Record<string, unknown>[] {
  return fetchMock.mock.calls.map(([, init]) => JSON.parse(String((init as RequestInit).body)));
}

function serve(result: unknown) {
  const fetchMock = vi.fn(
    async () => ({ ok: true, status: 200, json: async () => result }) as unknown as Response,
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

/** Opens the dialog from the button the policy header renders. */
function openDialog(p: AssembledPolicy = policy()) {
  render(<PolicyAskAiButton policy={p} policySetKey={POLICY_SET_KEY} />);
  fireEvent.click(screen.getByTestId("policy-ask-ai"));
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

describe("asking about a whole policy", () => {
  it("names the policy by the document's own heading and grounds on every rule the card shows", async () => {
    const fetchMock = serve(answer());
    openDialog();

    expect(document.querySelector(".ask-rule-header")?.textContent).toContain(POLICY_HEADING);

    clickSuggestion(ENGLISH.copy.scopes.policy.suggestions[0]);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    const [body] = requestBodies(fetchMock);
    expect(body.policy_set_key).toBe(POLICY_SET_KEY);
    // Document order, so a coverage sentence about "the first N" names a prefix
    // the reader can point at on the card.
    expect(body.focus_rule_ids).toEqual(policy().rules.map((r) => r.rule_id));
    // A policy question grounds on the policy and not on one rule of it.
    expect(body.focus_candidate_rule_id).toBeNull();
  });

  it("offers openers written for a policy rather than the ones written for a rule", () => {
    serve(answer());
    openDialog();

    for (const opener of ENGLISH.copy.scopes.policy.suggestions) {
      expect(screen.getByText(opener)).toBeTruthy();
    }
    // Paired with the above: the rule openers are absent, and the reason that
    // assertion means anything is that the policy openers were just found.
    for (const opener of ENGLISH.copy.scopes.rule.suggestions) {
      expect(screen.queryByText(opener)).toBeNull();
    }
  });

  it("moves every opener, the note and the placeholder to the chosen language", () => {
    serve(answer());
    openDialog();

    choose(ARABIC.endonym);

    for (const opener of ARABIC.copy.scopes.policy.suggestions) {
      expect(screen.getByText(opener)).toBeTruthy();
    }
    // Two passages, so the wider note is the one on screen.
    expect(screen.getByText(ARABIC.copy.scopes.policy.groundingNoteWider)).toBeTruthy();
    expect(screen.getByPlaceholderText(ARABIC.copy.scopes.policy.followUpPlaceholder)).toBeTruthy();
    for (const opener of ENGLISH.copy.scopes.policy.suggestions) {
      expect(screen.queryByText(opener)).toBeNull();
    }
    expect(screen.queryByText(ENGLISH.copy.scopes.policy.groundingNoteWider)).toBeNull();
  });

  it("asks the server for the answer in the chosen language and sends the opener the reader saw", async () => {
    const fetchMock = serve(answer());
    openDialog();

    choose(ARABIC.endonym);
    clickSuggestion(ARABIC.copy.scopes.policy.suggestions[0]);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [body] = requestBodies(fetchMock);
    expect(body.answer_language).toBe(ARABIC.tag);
    expect(body.question).toBe(ARABIC.copy.scopes.policy.suggestions[0]);
  });

  it("renders quoted source text identically in every language the table offers", async () => {
    // The assertion this whole file exists for, at the scope that quotes most.
    const rendered: string[] = [];

    for (const language of ASK_ANSWER_LANGUAGES) {
      serve(answer());
      openDialog();
      choose(language.endonym);
      clickSuggestion(language.copy.scopes.policy.suggestions[0]);
      await waitFor(() => expect(screen.getByTestId("ask-rule-quoted")).toBeTruthy());
      rendered.push(screen.getByTestId("ask-rule-fact").textContent ?? "");
      cleanup();
    }

    expect(rendered.length).toBe(ASK_ANSWER_LANGUAGES.length);
    expect(rendered[0]).toBe(ENGLISH_CLAUSE);
    for (const text of rendered) {
      expect(text).toBe(rendered[0]);
    }
  });

  it("keeps an Arabic document's clause in Arabic while the answer is English", async () => {
    // The mirror of the case above, and the one a two-language `if` gets wrong:
    // the rule is not "translate unless Arabic", it is "never translate what was
    // quoted", whichever direction the reader is going.
    serve(
      answer({
        groups: [{ heading: "الإفصاح", facts: [{ text: ARABIC_CLAUSE, source_label: "دليل الموظف" }] }],
        reflection: ENGLISH_REFLECTION,
      }),
    );
    openDialog();

    clickSuggestion(ENGLISH.copy.scopes.policy.suggestions[0]);
    await waitFor(() => expect(screen.getByTestId("ask-rule-quoted")).toBeTruthy());

    expect(screen.getByTestId("ask-rule-fact").textContent).toBe(ARABIC_CLAUSE);
    expect(screen.getByTestId("ask-rule-reflection").textContent).toContain(ENGLISH_REFLECTION);
  });

  it("marks its own words as its own and never claims a language for the document's", async () => {
    serve(answer({ reflection: ARABIC_REFLECTION }));
    openDialog();

    choose(ARABIC.endonym);
    clickSuggestion(ARABIC.copy.scopes.policy.suggestions[0]);
    await waitFor(() => expect(screen.getByTestId("ask-rule-reflection")).toBeTruthy());

    const reflection = screen.getByTestId("ask-rule-reflection");
    expect(reflection.getAttribute("lang")).toBe(ARABIC.tag);
    expect(reflection.textContent).toContain(ARABIC.copy.writtenByAppLabel);
    expect(reflection.textContent).toContain("✦");

    // The document's language is not this app's to assert. A `lang` here would
    // be a guess, announced by a screen reader as fact.
    const fact = screen.getByTestId("ask-rule-fact");
    expect(fact.getAttribute("lang")).toBeNull();
    expect(fact.closest("[lang]")).toBeNull();
  });

  it("lays out a mixed-script answer as runs rather than as one direction", async () => {
    serve(answer({ reflection: ARABIC_REFLECTION }));
    openDialog();

    choose(ARABIC.endonym);
    clickSuggestion(ARABIC.copy.scopes.policy.suggestions[0]);
    await waitFor(() => expect(screen.getByTestId("ask-rule-reflection")).toBeTruthy());

    // The dialog itself never declares a direction: an Arabic answer carrying a
    // Latin identifier laid out under one would read backwards. A passage may
    // align itself; the container it sits in may not decide for it.
    const reflection = screen.getByTestId("ask-rule-reflection");
    const dialog = reflection.closest("[role='dialog']");
    expect(dialog).not.toBeNull();
    expect((dialog as Element).getAttribute("dir")).toBeNull();
    expect(document.documentElement.getAttribute("dir")).toBeNull();

    const runs = [...reflection.querySelectorAll("bdi")];
    expect(runs.length).toBeGreaterThan(1);
    const latin = runs.find((r) => r.textContent?.includes("any-employee-found-guilty"));
    expect(latin?.getAttribute("dir")).toBe("ltr");
    const arabic = runs.find((r) => /[\u0600-\u06FF]/.test(r.textContent ?? ""));
    expect(arabic?.getAttribute("dir")).toBe("rtl");
    // And nothing was reordered on the way: the answer reads back whole.
    expect(reflection.textContent).toContain(ARABIC_REFLECTION);
  });
});

describe("how much of the policy the answer rests on", () => {
  const partial = { rule_count: 72, covered_rule_count: 12, covers_every_rule: false };

  it("says which part it read, with the counts, in the reader's language", async () => {
    for (const language of ASK_ANSWER_LANGUAGES) {
      serve(answer({ grounding: partial }));
      openDialog(policy(72));
      choose(language.endonym);
      clickSuggestion(language.copy.scopes.policy.suggestions[0]);
      await waitFor(() => expect(screen.getByTestId("ask-rule-coverage")).toBeTruthy());

      const said = screen.getByTestId("ask-rule-coverage").textContent ?? "";
      expect(said, language.tag).toContain(
        fillCounts(language.copy.scopes.policy.coverageNote, { covered: 12, total: 72 }).slice(0, 12),
      );
      expect(said, language.tag).toContain("12");
      expect(said, language.tag).toContain("72");
      // Never the scaffolding.
      expect(said, language.tag).not.toContain("{covered}");
      cleanup();
    }
  });

  it("says it before the answer rather than after it", async () => {
    serve(answer({ grounding: partial }));
    openDialog(policy(72));

    clickSuggestion(ENGLISH.copy.scopes.policy.suggestions[0]);
    await waitFor(() => expect(screen.getByTestId("ask-rule-coverage")).toBeTruthy());

    // A reader who learns halfway down that they were reading a partial
    // grounding has already read it as a whole one.
    const position = screen
      .getByTestId("ask-rule-coverage")
      .compareDocumentPosition(screen.getByTestId("ask-rule-quoted"));
    expect(position & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("says nothing when it read all of it", async () => {
    serve(answer({ grounding: { rule_count: 6, covered_rule_count: 6, covers_every_rule: true } }));
    openDialog();

    clickSuggestion(ENGLISH.copy.scopes.policy.suggestions[0]);
    await waitFor(() => expect(screen.getByTestId("ask-rule-quoted")).toBeTruthy());

    expect(screen.queryByTestId("ask-rule-coverage")).toBeNull();
  });

  it("says nothing when there was no coverage question to answer", async () => {
    // A server that reports nothing is not a server reporting completeness.
    serve(answer());
    openDialog();

    clickSuggestion(ENGLISH.copy.scopes.policy.suggestions[0]);
    await waitFor(() => expect(screen.getByTestId("ask-rule-quoted")).toBeTruthy());

    expect(screen.queryByTestId("ask-rule-coverage")).toBeNull();
  });
});

describe("the choice reaches this window and nothing else", () => {
  it("leaves the rule dialog in its own language", async () => {
    // Two dialogs of the same kind, open at once. Choosing Arabic in one must
    // not reach into the other, or "only in this window" is not what shipped.
    serve(answer());
    render(<PolicyAskAiButton policy={policy()} policySetKey={POLICY_SET_KEY} />);
    fireEvent.click(screen.getByTestId("policy-ask-ai"));

    choose(ARABIC.endonym);
    expect(screen.getByText(ARABIC.copy.scopes.policy.suggestions[0])).toBeTruthy();

    // The rule dialog, rendered fresh, still opens in the head of the table.
    cleanup();
    serve(answer());
    render(
      <AskAboutRuleModal
        candidate={
          {
            id: "candidate-1",
            policy_set_id: "set",
            rule: { rule_id: "AI-1", group_label: "" },
          } as never
        }
        onClose={() => {}}
      />,
    );
    expect(screen.getByText(ENGLISH.copy.scopes.rule.suggestions[0])).toBeTruthy();
    expect(screen.queryByText(ARABIC.copy.scopes.rule.suggestions[0])).toBeNull();
  });

  it("writes nothing down that would outlive the window", () => {
    // The request was for a choice in this window. A stored preference is a
    // different thing: it follows the reviewer onto other policies and other
    // projects, and would have someone open a dialog they never chose a
    // language for and find the chrome around the document's words in it.
    const stored: string[] = [];
    vi.stubGlobal("localStorage", {
      getItem: () => null,
      setItem: (k: string, v: string) => stored.push(`${k}=${v}`),
      removeItem: () => {},
      clear: () => {},
      key: () => null,
      length: 0,
    });
    serve(answer());
    openDialog();

    choose(ARABIC.endonym);

    expect(stored).toEqual([]);
    expect(document.documentElement.getAttribute("lang")).not.toBe(ARABIC.tag);
    expect(document.documentElement.getAttribute("dir")).toBeNull();
  });

  it("relabels no answer already on screen when the choice changes", async () => {
    // An answer was written in the language it was asked in. Moving the control
    // afterwards changes what is asked next; it cannot retitle what came back,
    // because the words under that heading did not change.
    serve(answer({ reflection: ARABIC_REFLECTION }));
    openDialog();

    choose(ARABIC.endonym);
    clickSuggestion(ARABIC.copy.scopes.policy.suggestions[0]);
    await waitFor(() => expect(screen.getByTestId("ask-rule-quoted")).toBeTruthy());

    choose(ENGLISH.endonym);

    expect(screen.getByTestId("ask-rule-quoted").textContent).toContain(ARABIC.copy.quotedHeading);
    expect(screen.getByTestId("ask-rule-quoted").textContent).not.toContain(ENGLISH.copy.quotedHeading);
    // And the placeholder, which is about what happens next, did move.
    expect(screen.getByPlaceholderText(ENGLISH.copy.scopes.policy.followUpPlaceholder)).toBeTruthy();
  });
});
