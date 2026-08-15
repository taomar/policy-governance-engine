/**
 * ASKING ABOUT A RECORD THAT CAN NO LONGER BE CHANGED.
 *
 * A published version is a sealed snapshot. Its rules carry the same `rule_id`
 * as the draft rows that produced them, and those drafts keep moving — a
 * revision is drafted against a published rule, so the two records diverge by
 * design. That makes the id alone an ambiguous way to name what an answer is
 * about, and an answer about the draft, shown to a reader looking at the
 * published version, is indistinguishable on screen from a correct one. It is
 * the same failure the no-translation rule guards at a different layer: content
 * presented as the record, which is not the record.
 *
 * So the assertions here are mostly about *which record was asked for*, and the
 * ones about language are there because the toggle has to keep working on a
 * surface that has no review workflow at all.
 *
 * WHY EACH ABSENCE IS PAIRED WITH A PRESENCE
 *
 * "No candidate id was sent" also passes when no request was sent, and "the
 * English text is gone" also passes when nothing rendered. Every negative below
 * sits beside a positive taken from the same run.
 */
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

import type { AskResponse, AssembledPolicy } from "../api";
import {
  ASK_ANSWER_LANGUAGES,
  ASK_RECORD_SOURCES,
  askAnswerLanguageByTag,
  fillCounts,
} from "../askAnswerLanguage";
import { PolicyAskAiButton } from "./PolicyAskAiButton";
import { PublishedRuleAskAiButton } from "./PublishedRuleAskAiButton";

beforeAll(() => {
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

const POLICY_SET_KEY = "ais-employee-handbook";
const VERSION_ID = "8f2b1c44-0a3e-4d51-9c77-51bd2f6ae010";
const PUBLISHED_RULE = { rule_id: "AI-eb7e2e437d", group_label: "Hiring relatives" };

/** A clause as the English document wrote it. */
const ENGLISH_CLAUSE =
  "No employee may participate in a hiring decision concerning a relative, and any such involvement must be declared in writing.";

/** The same obligation, from a document written in Arabic. */
const ARABIC_CLAUSE = "لا يجوز لأي موظف المشاركة في قرار توظيف يخص أحد أقاربه، ويجب الإفصاح عن ذلك كتابيًا.";

/** This app's own words in Arabic, carrying a Latin identifier and an English
 *  fragment of the clause under discussion. */
const ARABIC_REFLECTION =
  'هذه النسخة المنشورة تُلزم بالإفصاح: يشير المُعرِّف any-employee-found-guilty إلى عبارة "declared in writing" كما وردت في المستند.';

const ENGLISH_REFLECTION =
  "This published rule bars a relative from the decision and requires the relationship to be declared.";

function policy(ruleCount = 6): AssembledPolicy {
  return {
    key: "prov-1",
    heading: "7.11. HIRING RELATIVES & NEPOTISM",
    heading_path: ["7. RECRUITMENT", "7.11. HIRING RELATIVES & NEPOTISM"],
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
      rule_id: `AI-published-${i}`,
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
    grounding: {
      rule_count: 1,
      covered_rule_count: 1,
      covers_every_rule: true,
      record_source: "published_version",
    },
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

function choose(endonym: string) {
  fireEvent.click(screen.getByRole("radio", { name: endonym }));
}

function clickSuggestion(label: string) {
  const tag = screen.getByText(label).closest(".ask-rule-suggestion");
  expect(tag).not.toBeNull();
  fireEvent.click(tag as Element);
}

function openPublishedRule() {
  render(
    <PublishedRuleAskAiButton
      rule={PUBLISHED_RULE}
      policySetKey={POLICY_SET_KEY}
      policyVersionId={VERSION_ID}
    />,
  );
  fireEvent.click(screen.getByTestId("published-rule-ask-ai"));
}

function openPublishedPolicy(p: AssembledPolicy = policy()) {
  render(
    <PolicyAskAiButton policy={p} policySetKey={POLICY_SET_KEY} policyVersionId={VERSION_ID} />,
  );
  fireEvent.click(screen.getByTestId("policy-ask-ai"));
}

describe("a published record can be asked about, and about itself", () => {
  it("asks about the rule of that version, never about a draft row", async () => {
    const fetchMock = serve(answer());
    openPublishedRule();

    // Presence first: the dialog is the rule dialog, named by the rule's own id.
    expect(document.querySelector(".ask-rule-header")?.textContent).toContain(
      PUBLISHED_RULE.rule_id,
    );

    clickSuggestion(ENGLISH.copy.scopes.rule.suggestions[0]);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    const [body] = requestBodies(fetchMock);
    expect(body.policy_set_key).toBe(POLICY_SET_KEY);
    expect(body.policy_version_id).toBe(VERSION_ID);
    // The rule is named by its own id, which is the only identity a sealed
    // record has…
    expect(body.focus_rule_ids).toEqual([PUBLISHED_RULE.rule_id]);
    // …and no draft row is pinned, because there may be none, and the one that
    // exists is a different record.
    expect(body.focus_candidate_rule_id).toBeNull();
  });

  it("asks about the policy of that version, by its rules' own ids", async () => {
    const fetchMock = serve(answer());
    openPublishedPolicy();

    clickSuggestion(ENGLISH.copy.scopes.policy.suggestions[0]);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    const [body] = requestBodies(fetchMock);
    expect(body.policy_version_id).toBe(VERSION_ID);
    expect(body.focus_rule_ids).toEqual(policy().rules.map((r) => r.rule_id));
    expect(body.focus_candidate_rule_id).toBeNull();
  });

  it("still sends no version when the review queue asks, so the drafts stay the drafts", async () => {
    // The paired half of the two tests above. If the version were sent
    // unconditionally, the queue would start answering about published records
    // while a reviewer decided on drafts — the same confusion, mirrored.
    const fetchMock = serve(answer({ grounding: null }));
    render(<PolicyAskAiButton policy={policy()} policySetKey={POLICY_SET_KEY} />);
    fireEvent.click(screen.getByTestId("policy-ask-ai"));

    clickSuggestion(ENGLISH.copy.scopes.policy.suggestions[0]);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    const [body] = requestBodies(fetchMock);
    expect(body.policy_version_id).toBeNull();
    expect(body.focus_rule_ids).toEqual(policy().rules.map((r) => r.rule_id));
  });

  it("names which record the answer was read from, in the reader's language", async () => {
    const fetchMock = serve(answer());
    openPublishedRule();
    clickSuggestion(ENGLISH.copy.scopes.rule.suggestions[0]);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    const note = await screen.findByTestId("ask-rule-record-source");
    expect(note.textContent).toContain(ENGLISH.copy.recordSourceNotes.published_version);
    // Marked as this app's own words, the way every other generated sentence is.
    expect(note.textContent?.startsWith("✦")).toBe(true);
    // Paired: the other source's sentence is not the one on screen.
    expect(note.textContent).not.toContain(ENGLISH.copy.recordSourceNotes.draft_records);
  });

  it("says the same thing about provenance in Arabic", async () => {
    const fetchMock = serve(
      answer({ reflection: ARABIC_REFLECTION, groups: [] as AskResponse["groups"] }),
    );
    openPublishedRule();
    choose(ARABIC.endonym);
    clickSuggestion(ARABIC.copy.scopes.rule.suggestions[0]);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    const note = await screen.findByTestId("ask-rule-record-source");
    expect(note.textContent).toContain(ARABIC.copy.recordSourceNotes.published_version);
    expect(note.textContent).not.toContain(ENGLISH.copy.recordSourceNotes.published_version);
    // The line is this app's writing, so it carries the reader's language tag.
    expect(note.querySelector(`[lang="${ARABIC.tag}"]`)).not.toBeNull();
  });

  it("distinguishes 'none of them could be read' from 'the first few were'", async () => {
    // The pre-existing hazard this closes: a request that named rules, resolved
    // none of them, and answered anyway from general retrieval. That reads on
    // screen exactly like an answer about the policy.
    const fetchMock = serve(
      answer({
        grounding: {
          rule_count: 6,
          covered_rule_count: 0,
          covers_every_rule: false,
          record_source: "published_version",
        },
      }),
    );
    openPublishedPolicy();
    clickSuggestion(ENGLISH.copy.scopes.policy.suggestions[0]);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    const alert = await screen.findByTestId("ask-rule-grounded-nothing");
    expect(alert.textContent).toContain(
      fillCounts(ENGLISH.copy.groundedNothingNote, { covered: 0, total: 6 }),
    );
    // Paired: this is *not* the prefix sentence, which would understate it.
    expect(alert.textContent).not.toContain(
      fillCounts(ENGLISH.copy.coverageNote, { covered: 0, total: 6 }),
    );
    expect(screen.queryByTestId("ask-rule-coverage")).toBeNull();
  });

  it("keeps the prefix sentence for a partial grounding", async () => {
    const fetchMock = serve(
      answer({
        grounding: {
          rule_count: 63,
          covered_rule_count: 8,
          covers_every_rule: false,
          record_source: "published_version",
        },
      }),
    );
    openPublishedPolicy();
    clickSuggestion(ENGLISH.copy.scopes.policy.suggestions[0]);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    const alert = await screen.findByTestId("ask-rule-coverage");
    expect(alert.textContent).toContain(
      fillCounts(ENGLISH.copy.coverageNote, { covered: 8, total: 63 }),
    );
    expect(screen.queryByTestId("ask-rule-grounded-nothing")).toBeNull();
  });

  it("says nothing about provenance when the server named none", async () => {
    // Absent is not "the drafts". A reply from a deployment that predates the
    // field carries no claim, and inventing one would be a provenance statement
    // with nothing behind it.
    const fetchMock = serve(
      answer({
        grounding: { rule_count: 1, covered_rule_count: 1, covers_every_rule: true },
      }),
    );
    openPublishedRule();
    clickSuggestion(ENGLISH.copy.scopes.rule.suggestions[0]);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    // Paired with a presence assertion so this cannot pass by rendering nothing.
    expect(await screen.findByText(ENGLISH_REFLECTION)).toBeTruthy();
    expect(screen.queryByTestId("ask-rule-record-source")).toBeNull();
  });
});

describe("the language toggle works on a record with no review workflow", () => {
  it("moves the openers, the note and the placeholder, at rule scope", () => {
    serve(answer());
    openPublishedRule();

    choose(ARABIC.endonym);

    for (const opener of ARABIC.copy.scopes.rule.suggestions) {
      expect(screen.getByText(opener)).toBeTruthy();
    }
    expect(screen.getByPlaceholderText(ARABIC.copy.scopes.rule.followUpPlaceholder)).toBeTruthy();
    for (const opener of ENGLISH.copy.scopes.rule.suggestions) {
      expect(screen.queryByText(opener)).toBeNull();
    }
  });

  it("asks the server for the reader's language and nothing else about it", async () => {
    const fetchMock = serve(answer());
    openPublishedRule();
    choose(ARABIC.endonym);
    clickSuggestion(ARABIC.copy.scopes.rule.suggestions[0]);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    const [body] = requestBodies(fetchMock);
    expect(body.answer_language).toBe(ARABIC.tag);
    // The choice is about this app's own words. It does not change which record
    // is read, which is the whole of what the published surface adds.
    expect(body.policy_version_id).toBe(VERSION_ID);
  });

  it("sets no direction on the dialog, whichever language is chosen", () => {
    serve(answer());
    openPublishedRule();
    choose(ARABIC.endonym);

    const dialog = document.querySelector(".ask-rule-modal");
    expect(dialog).not.toBeNull();
    // Direction belongs to a text run. A dialog told it is right-to-left lays a
    // Latin rule id and an English quotation out backwards inside it.
    expect((dialog as Element).getAttribute("dir")).toBeNull();
  });
});

describe("a published answer's quoted text is the document's, in every language", () => {
  for (const language of ASK_ANSWER_LANGUAGES) {
    it(`renders both quotations byte-for-byte when the answer is asked for in ${language.tag}`, async () => {
      const fetchMock = serve(
        answer({
          groups: [
            {
              heading: "Declaring a relationship",
              facts: [
                { text: ENGLISH_CLAUSE, source_label: "Staff Handbook — p11" },
                { text: ARABIC_CLAUSE, source_label: "دليل الموظفين — ص ١١" },
              ],
            },
          ],
          reflection: language.tag === "ar" ? ARABIC_REFLECTION : ENGLISH_REFLECTION,
        }),
      );
      openPublishedPolicy();
      choose(language.endonym);
      clickSuggestion(language.copy.scopes.policy.suggestions[0]);
      await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

      const quoted = await screen.findByTestId("ask-rule-quoted");
      const text = quoted.textContent ?? "";
      // A quoted English clause stays English inside an Arabic answer, and a
      // quoted Arabic clause stays Arabic inside an English one.
      expect(text).toContain(ENGLISH_CLAUSE);
      expect(text).toContain(ARABIC_CLAUSE);
      // No quoted run carries the reader's language tag: these are not this
      // app's words and must not be announced as if they were. Asserted on the
      // facts themselves rather than on the block, because the block's heading
      // *is* this app's words and correctly carries the tag.
      const facts = [...quoted.querySelectorAll('[data-testid="ask-rule-fact"]')];
      expect(facts.length, `${language.tag} rendered no quoted facts`).toBe(2);
      for (const fact of facts) {
        expect(fact.getAttribute("lang")).not.toBe(language.tag);
        expect(fact.querySelector(`[lang="${language.tag}"]`)).toBeNull();
      }
    });
  }

  it("renders identical quoted text across every language in the table", async () => {
    // The assertion the whole feature stands on, at published scope. Rendered
    // once per language and compared character for character; a translation
    // pass anywhere on the way out fails this.
    const rendered: string[] = [];
    for (const language of ASK_ANSWER_LANGUAGES) {
      const fetchMock = serve(
        answer({
          groups: [
            {
              heading: "Declaring a relationship",
              facts: [
                { text: ENGLISH_CLAUSE, source_label: "Staff Handbook — p11" },
                { text: ARABIC_CLAUSE, source_label: "دليل الموظفين — ص ١١" },
              ],
            },
          ],
        }),
      );
      openPublishedPolicy();
      choose(language.endonym);
      clickSuggestion(language.copy.scopes.policy.suggestions[0]);
      await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
      const facts = [...document.querySelectorAll('[data-testid="ask-rule-fact"]')];
      expect(facts.length, `${language.tag} rendered no quoted facts`).toBe(2);
      rendered.push(facts.map((el) => el.textContent).join("\u0000"));
      cleanup();
    }
    expect(rendered.length).toBe(ASK_ANSWER_LANGUAGES.length);
    for (const text of rendered) expect(text).toBe(rendered[0]);
  });
});

describe("the published surface says nothing about how a rule is decided", () => {
  it("frames a record source as where it was read, never as what it lacks", () => {
    // The English guard in `tests/unit/test_no_readiness_framing.py` scans this
    // repository's Latin source strings and cannot see Arabic at all, so the
    // Arabic copy is unguarded by construction and is checked in
    // `askAnswerLanguage.test.ts`. What is checked here is the shape of the new
    // sentences in both: a provenance note is about which table was read, and a
    // phrase like "could not" or "not supported" would turn it into a verdict
    // on the record.
    const forbidden = [
      ["not", "supported"].join(" "),
      ["cannot", "be"].join(" "),
      ["not", "capable"].join(" "),
      ["لا", "يدعم"].join(" "),
      ["غير", "مدعوم"].join(" "),
    ];
    for (const language of ASK_ANSWER_LANGUAGES) {
      for (const source of ASK_RECORD_SOURCES) {
        const note = language.copy.recordSourceNotes[source];
        for (const phrase of forbidden) {
          expect(note.includes(phrase), `${language.tag}.${source}: ${phrase}`).toBe(false);
        }
      }
    }
  });
});
