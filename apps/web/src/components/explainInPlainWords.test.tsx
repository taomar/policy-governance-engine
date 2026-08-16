/**
 * The Overview pane reads a policy back in plain words, now in the reader's
 * chosen language — and translates nothing that is the document's.
 *
 * WHAT THE READER ASKED FOR
 *
 * Two things. The section was to lose its explanatory paragraph and its button
 * was to say only "Explain this policy in plain words"; and it was to gain an
 * English/Arabic toggle so the reading could be produced in Arabic.
 *
 * WHAT MUST NOT SLIP WHILE DOING IT
 *
 *  - The caveat the paragraph carried — that this is the app's account of its
 *    *extraction*, not the document — is load-bearing and moves to the result,
 *    not away. Removing the paragraph must not remove the distinction.
 *
 *  - Only the app's own reading takes the chosen language. The pane's reading
 *    component renders the generated words and nothing the document wrote, so
 *    the language label can only ever land on the app's own account. This file
 *    pins that the tag travels on the request, that the reading is marked in the
 *    language it was written in, and that a reading already on screen is not
 *    relabelled when the toggle later moves — a claim in a language those words
 *    were not written in would be a false one.
 */
import { beforeAll, afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import type { AssembledPassage, AssembledPolicy, CanonicalRule } from "../api";
import { aiApi, type PolicyExplanation } from "../api";
import { PolicyOverviewPane, type PolicyRecordView } from "./policyTabPanes";

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

function rule(id: string): CanonicalRule {
  return {
    rule_id: id,
    title: `Rule ${id}`,
    effect: "allow",
    condition: { type: "all", all: [] },
    obligations: [],
    exceptions: [],
    scope: {},
    source: { document_id: "d", quotes: [] },
    lineage: { extraction_run_id: "run-1", schema_version: "1" },
  } as unknown as CanonicalRule;
}

function passage(page: number): AssembledPassage {
  return { key: `p${page}`, source_elements: `p${page}-E1`, page, rule_count: 1, rules: [] };
}

function record(provisionId: string, key: string): PolicyRecordView {
  return {
    policy: {
      key,
      heading: `Heading ${key}`,
      heading_path: ["Above", `Heading ${key}`],
      passages: [passage(1)],
      page: 1,
      persisted: true,
      provision_id: provisionId,
      document_version_id: "dv-1",
      source_elements: "p1-E1",
      rules: [],
      rule_count: 1,
      passage_count: 1,
      route: "computable",
    } as unknown as AssembledPolicy,
    passageCount: 1,
    rules: [{ rule_id: "a", rule: rule("a") }],
    progress: undefined,
  };
}

/** A reading whose text names the policy, and whose response also carries the
 *  document's own sentence — the thing the pane's reading must never show, so a
 *  test can prove it is absent from the section rather than merely unstyled. */
function explanationFor(provisionId: string): PolicyExplanation {
  return {
    provision_id: provisionId,
    heading_path: ["A heading"],
    rule_count: 1,
    rules: [
      {
        rule_id: "a",
        title: "First rule",
        states: { subject: "someone", modality: "must" },
        effect: "a thing follows",
        stated_text: "THE-DOCUMENTS-OWN-SENTENCE.",
      },
    ],
    covers_every_rule: true,
    explanation: `Reading of ${provisionId}.`,
    unavailable_code: null,
    generated_at: "2024-05-01T10:00:00Z",
    model_deployment: "a-deployment",
    prompt_version: "policy-explain-v1",
    source_digest: `digest-${provisionId}`,
  } as PolicyExplanation;
}

const A = "prov-A";

function readingText(container: HTMLElement): HTMLElement | null {
  return container.querySelector<HTMLElement>(".policy-pane__reading-text");
}

describe("the simplified plain-words section", () => {
  it("offers a plain button and drops the explanatory paragraph", () => {
    render(<PolicyOverviewPane record={record(A, "POLICY-A")} />);
    const button = screen.getByTestId("overview-request-plain-words");
    // Exactly the words the reader asked for — no sentence explaining it first.
    expect(button.textContent).toBe("Explain this policy in plain words");
    expect(screen.queryByText(/read its own extraction/i)).toBeNull();
  });

  it("shows an English/Arabic toggle", () => {
    render(<PolicyOverviewPane record={record(A, "POLICY-A")} />);
    expect(screen.getByTestId("ask-rule-language")).toBeTruthy();
    expect(screen.getByTestId("ask-rule-language-en")).toBeTruthy();
    expect(screen.getByTestId("ask-rule-language-ar")).toBeTruthy();
  });
});

describe("asking for the reading in a language", () => {
  it("asks in the default language with no override on the request", async () => {
    const asked = vi
      .spyOn(aiApi, "explainPolicy")
      .mockImplementation(async (provisionId: string) => explanationFor(provisionId));

    render(<PolicyOverviewPane record={record(A, "POLICY-A")} />);
    fireEvent.click(screen.getByTestId("overview-request-plain-words"));
    await screen.findByTestId("overview-plain-words-text");

    // The server writes in its own language when none is sent; the default must
    // travel as no language at all, leaving that request byte-for-byte itself.
    expect(asked).toHaveBeenCalledWith(A, false, undefined);
  });

  it("carries the chosen tag when Arabic is selected", async () => {
    const asked = vi
      .spyOn(aiApi, "explainPolicy")
      .mockImplementation(async (provisionId: string) => explanationFor(provisionId));

    render(<PolicyOverviewPane record={record(A, "POLICY-A")} />);
    fireEvent.click(screen.getByTestId("ask-rule-language-ar"));
    fireEvent.click(screen.getByTestId("overview-request-plain-words"));
    await screen.findByTestId("overview-plain-words-text");

    expect(asked).toHaveBeenCalledWith(A, false, "ar");
  });

  it("marks the reading in the language it was written in", async () => {
    vi.spyOn(aiApi, "explainPolicy").mockImplementation(
      async (provisionId: string) => explanationFor(provisionId),
    );

    const { container } = render(<PolicyOverviewPane record={record(A, "POLICY-A")} />);
    fireEvent.click(screen.getByTestId("ask-rule-language-ar"));
    fireEvent.click(screen.getByTestId("overview-request-plain-words"));
    await screen.findByTestId("overview-plain-words-text");

    expect(readingText(container)?.getAttribute("lang")).toBe("ar");
  });

  it("does not relabel a reading already on screen when the toggle later moves", async () => {
    vi.spyOn(aiApi, "explainPolicy").mockImplementation(
      async (provisionId: string) => explanationFor(provisionId),
    );

    const { container } = render(<PolicyOverviewPane record={record(A, "POLICY-A")} />);
    // Asked and answered in the default language.
    fireEvent.click(screen.getByTestId("overview-request-plain-words"));
    await screen.findByTestId("overview-plain-words-text");
    expect(readingText(container)?.getAttribute("lang")).toBe("en");

    // The reader moves the toggle. The words on screen were not written in that
    // language, so their label must not change to claim they were.
    fireEvent.click(screen.getByTestId("ask-rule-language-ar"));
    expect(readingText(container)?.getAttribute("lang")).toBe("en");
  });
});

describe("what the language never reaches", () => {
  it("keeps the document's own sentence out of the reading, in any language", async () => {
    vi.spyOn(aiApi, "explainPolicy").mockImplementation(
      async (provisionId: string) => explanationFor(provisionId),
    );

    render(<PolicyOverviewPane record={record(A, "POLICY-A")} />);
    fireEvent.click(screen.getByTestId("ask-rule-language-ar"));
    fireEvent.click(screen.getByTestId("overview-request-plain-words"));
    await screen.findByTestId("overview-plain-words-text");

    // The reading section shows the app's own words. The document's sentence,
    // carried on the same response, is not the pane's to render — so there is
    // nothing here for a language to translate.
    const section = screen.getByTestId("overview-plain-words");
    expect(within(section).queryByText(/THE-DOCUMENTS-OWN-SENTENCE/)).toBeNull();
  });

  it("keeps the caveat that this is the app's extraction, not the document", async () => {
    vi.spyOn(aiApi, "explainPolicy").mockImplementation(
      async (provisionId: string) => explanationFor(provisionId),
    );

    render(<PolicyOverviewPane record={record(A, "POLICY-A")} />);
    fireEvent.click(screen.getByTestId("overview-request-plain-words"));
    await screen.findByTestId("overview-plain-words-text");

    // The paragraph went; the distinction it carried stays, beside the result.
    const section = screen.getByTestId("overview-plain-words");
    expect(section.textContent).toContain("In plain words, by this app");
    expect(section.textContent).toContain("not what the document says");
  });
});
