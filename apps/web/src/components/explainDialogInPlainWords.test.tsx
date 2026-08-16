/**
 * The Explain dialog reads a policy back in plain words, now in the reader's
 * chosen language — and translates nothing that is the document's.
 *
 * WHAT THE READER ASKED FOR
 *
 * The same English/Arabic choice that the Overview pane beside this dialog
 * already offers. The two are visible together, which is what made the gap
 * obvious: the pane could answer in Arabic and the dialog could not.
 *
 * WHAT MUST NOT SLIP WHILE DOING IT
 *
 *  - Only the app's own reading takes the chosen language. This dialog shows
 *    *more* of the document's own words than the pane does — one quote per rule,
 *    not none — so there is more here for a stray translation to spoil. This
 *    file pins that the whole source section is byte-for-byte the same whichever
 *    language is chosen, and still holds every rule's own sentence.
 *
 *  - The tag travels on the request; a reading is marked in the language it was
 *    written in; and a reading already on screen is not relabelled when the
 *    toggle later moves, because a claim in a language those words were not
 *    written in would be a false one.
 *
 *  - The default travels as no language at all, so an English request stays the
 *    byte-identical, same-cached one it has always been.
 */
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { PolicyExplainButton } from "./PolicyExplainButton";
import { aiApi, type PolicyExplanation } from "../api";

beforeAll(() => {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }),
  });
  globalThis.ResizeObserver ??= class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

// The document's own sentences, one per rule. They are fixed English strings and
// never vary by the language asked for — that is the server's contract and the
// thing this file proves the client honours: the reading changes language, the
// quotes do not.
const DOC_ONE = "ZQXJV-DOCUMENT-SENTENCE-ONE.";
const DOC_TWO = "KHDFG-DOCUMENT-SENTENCE-TWO.";
const ENGLISH_READING = "A plain reading of this record, in English.";
const ARABIC_READING = "قراءةٌ سهلةٌ لهذا السجلّ بالعربية.";

/** A reading whose text is in the language asked for, carrying rules whose own
 *  quoted sentences are the document's and stay put whatever is asked. */
function explanationIn(answerLanguage: string | undefined): PolicyExplanation {
  return {
    provision_id: "p1",
    heading_path: ["7.2 A heading"],
    rule_count: 2,
    rules: [
      {
        rule_id: "r1",
        title: "First rule",
        states: { subject: "someone", modality: "must" },
        effect: "a thing follows",
        stated_text: DOC_ONE,
      },
      {
        rule_id: "r2",
        title: "Second rule",
        states: { subject: "someone" },
        effect: "",
        stated_text: DOC_TWO,
      },
    ],
    covers_every_rule: true,
    explanation: answerLanguage === "ar" ? ARABIC_READING : ENGLISH_READING,
    unavailable_code: null,
    generated_at: "2024-05-01T10:00:00Z",
    model_deployment: "a-deployment",
    prompt_version: "policy-explain-v1",
    source_digest: "abc123",
  } as PolicyExplanation;
}

function mockExplain() {
  return vi
    .spyOn(aiApi, "explainPolicy")
    .mockImplementation(async (_provisionId, _regenerate, answerLanguage) =>
      explanationIn(answerLanguage),
    );
}

function openIt() {
  render(<PolicyExplainButton provisionId="p1" policyKey="POL-1" />);
  fireEvent.click(screen.getByTestId("policy-explain-button"));
}

function readingText(): HTMLElement | null {
  return screen
    .getByTestId("policy-explain-reading")
    .querySelector<HTMLElement>(".policy-explain__text");
}

describe("the Explain dialog offers the reading in a language", () => {
  it("shows an English/Arabic toggle once a reading is in hand", async () => {
    mockExplain();
    openIt();
    await screen.findByTestId("policy-explain-reading");
    expect(screen.getByTestId("ask-rule-language")).toBeTruthy();
    expect(screen.getByTestId("ask-rule-language-en")).toBeTruthy();
    expect(screen.getByTestId("ask-rule-language-ar")).toBeTruthy();
  });

  it("reads in the default language on open, sending no override", async () => {
    const asked = mockExplain();
    openIt();
    await screen.findByTestId("policy-explain-reading");
    // Opening reads the record in the server's own language; the default must
    // travel as no language at all, leaving that request byte-for-byte itself.
    expect(asked).toHaveBeenCalledWith("p1", false, undefined);
  });

  it("carries the chosen tag when Arabic is selected and written again", async () => {
    const asked = mockExplain();
    openIt();
    await screen.findByTestId("policy-explain-reading");

    fireEvent.click(screen.getByTestId("ask-rule-language-ar"));
    fireEvent.click(screen.getByText("Write it again"));

    await waitFor(() => expect(asked).toHaveBeenCalledWith("p1", true, "ar"));
  });

  it("marks the reading in the language it was written in", async () => {
    mockExplain();
    openIt();
    await screen.findByTestId("policy-explain-reading");
    // The first, default reading is English.
    expect(readingText()?.getAttribute("lang")).toBe("en");

    fireEvent.click(screen.getByTestId("ask-rule-language-ar"));
    fireEvent.click(screen.getByText("Write it again"));

    await waitFor(() => expect(readingText()?.getAttribute("lang")).toBe("ar"));
  });

  it("does not relabel a reading already on screen when the toggle later moves", async () => {
    mockExplain();
    openIt();
    await screen.findByTestId("policy-explain-reading");
    expect(readingText()?.getAttribute("lang")).toBe("en");

    // The reader moves the toggle but does not write again. The words on screen
    // were written in English, so their label must not change to claim Arabic.
    fireEvent.click(screen.getByTestId("ask-rule-language-ar"));
    expect(readingText()?.getAttribute("lang")).toBe("en");
  });
});

describe("what the dialog's language never reaches", () => {
  it("leaves every rule's own quoted words untranslated when Arabic is asked for", async () => {
    mockExplain();
    openIt();
    await screen.findByTestId("policy-explain-reading");

    const sourceBefore = screen.getByTestId("policy-explain-source").textContent ?? "";
    expect(sourceBefore).toContain(DOC_ONE);
    expect(sourceBefore).toContain(DOC_TWO);

    fireEvent.click(screen.getByTestId("ask-rule-language-ar"));
    fireEvent.click(screen.getByText("Write it again"));
    await waitFor(() => expect(readingText()?.textContent).toBe(ARABIC_READING));

    // The reading turned Arabic; the document's own words did not move a
    // character. One quote per rule means more to get wrong than on the pane, so
    // assert the whole source section is identical across the two languages.
    const sourceAfter = screen.getByTestId("policy-explain-source").textContent ?? "";
    expect(sourceAfter).toBe(sourceBefore);
    expect(sourceAfter).toContain(DOC_ONE);
    expect(sourceAfter).toContain(DOC_TWO);
  });

  it("keeps the document's quoted words out of the reading, in any language", async () => {
    mockExplain();
    openIt();
    await screen.findByTestId("policy-explain-reading");

    fireEvent.click(screen.getByTestId("ask-rule-language-ar"));
    fireEvent.click(screen.getByText("Write it again"));
    await waitFor(() => expect(readingText()?.textContent).toBe(ARABIC_READING));

    // The reading is the app's own words. The document's sentences belong to the
    // source section and are never duplicated into the reading — so there is
    // nothing in the reading for a language to translate.
    const reading = screen.getByTestId("policy-explain-reading");
    expect(reading.textContent).not.toContain(DOC_ONE);
    expect(reading.textContent).not.toContain(DOC_TWO);
  });
});
