import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { PolicyExplainButton } from "./PolicyExplainButton";
import { aiApi, PolicyPlatformApiError, type PolicyExplanation } from "../api";

/**
 * AN EXPLANATION IS OURS, IS ABOUT OUR RECORD, AND IS CHECKABLE.
 *
 * The dialog puts a fluent paragraph in front of someone whose whole job is
 * deciding whether an extraction is faithful. Three things make that safe, and
 * each of them is one careless edit from being lost, so each is asserted here.
 *
 * 1. IT IS MARKED AS OURS. Unquoted, carrying the mark the generated subject
 *    label established, never rendered in the element the document's words are
 *    rendered in. A reader must never take it for a citation.
 *
 * 2. THE DOCUMENT'S WORDS ARE BESIDE IT. Not behind a second click. The reading
 *    is worth having because it can be checked; a reading that cannot be
 *    checked is an assertion.
 *
 * 3. IT SAYS WHAT IT IS ABOUT. It describes the extraction, and the extraction
 *    is the thing under suspicion. A dialog that let a reader believe they were
 *    reading about the document would confirm what they came to test.
 *
 * WHY THE ROUTE GUARD IS RE-STATED HERE
 *
 * `routeNotFault.test.ts` reads the counter cells' `<dt>`/`<dd>` structure. It
 * cannot see prose, so it cannot see a word of this file's subject. Four
 * phrasings have already passed that guard; the assumption here is that a fifth
 * would too, so this scans the copy itself.
 */

const EXPLANATION: PolicyExplanation = {
  provision_id: "p1",
  heading_path: ["7.2 A heading"],
  rule_count: 3,
  rules: [
    {
      rule_id: "r1",
      title: "First rule",
      states: { subject: "someone", modality: "must" },
      effect: "a thing follows",
      stated_text: "ZQXJV WRTPLM, the document's own sentence.",
    },
    {
      rule_id: "r2",
      title: "Second rule",
      states: { subject: "someone" },
      effect: "",
      stated_text: "KHDFG BNYCS, a second sentence.",
    },
  ],
  covers_every_rule: true,
  explanation: "Someone must do a thing, and a second thing follows from it.",
  unavailable_code: null,
  generated_at: "2024-05-01T10:00:00Z",
  model_deployment: "a-deployment",
  prompt_version: "policy-explain-v1",
  source_digest: "abc123",
};

function answer(overrides: Partial<PolicyExplanation> = {}) {
  return vi
    .spyOn(aiApi, "explainPolicy")
    .mockResolvedValue({ ...EXPLANATION, ...overrides });
}

function openIt() {
  render(<PolicyExplainButton provisionId="p1" policyKey="POL-1" />);
  fireEvent.click(screen.getByTestId("policy-explain-button"));
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("nothing is generated until it is asked for", () => {
  it("asks for nothing while the card merely renders", () => {
    const asked = answer();
    render(<PolicyExplainButton provisionId="p1" policyKey="POL-1" />);
    expect(asked).not.toHaveBeenCalled();
  });

  it("asks once when the button is pressed", async () => {
    const asked = answer();
    openIt();
    await waitFor(() => expect(asked).toHaveBeenCalledTimes(1));
  });
});

describe("the reading is visibly ours", () => {
  it("carries the mark and names itself as this app's words", async () => {
    answer();
    openIt();
    const reading = await screen.findByTestId("policy-explain-reading");
    expect(reading.getAttribute("data-generated")).toBe("true");
    expect(reading.textContent).toContain("by this app");
  });

  it("does not wrap the reading in quotation marks", async () => {
    answer();
    openIt();
    const reading = await screen.findByTestId("policy-explain-reading");
    const text = reading.querySelector(".policy-explain__text")?.textContent ?? "";
    expect(text).toBe(EXPLANATION.explanation);
    expect(text.startsWith('"')).toBe(false);
    expect(text.startsWith("\u201c")).toBe(false);
  });

  it("does not render the reading in the element the document's words use", async () => {
    answer();
    openIt();
    const reading = await screen.findByTestId("policy-explain-reading");
    expect(reading.querySelector("blockquote")).toBeNull();
    // ... while the source section does use one, so the distinction above is a
    // real one and not an artefact of nothing being quoted anywhere.
    const source = screen.getByTestId("policy-explain-source");
    expect(source.querySelector("blockquote")).not.toBeNull();
  });

  it("records what wrote it and when", async () => {
    answer();
    openIt();
    const reading = await screen.findByTestId("policy-explain-reading");
    expect(reading.textContent).toContain("a-deployment");
  });
});

describe("the document's words stay reachable from the reading", () => {
  it("renders every rule's own text in the same view", async () => {
    answer();
    openIt();
    const source = await screen.findByTestId("policy-explain-source");
    for (const rule of EXPLANATION.rules) {
      expect(source.textContent).toContain(rule.stated_text);
    }
  });

  it("says which words are the document's", async () => {
    answer();
    openIt();
    const source = await screen.findByTestId("policy-explain-source");
    expect(source.textContent).toContain("The document's own words");
  });

  it("says the reading is about the extraction and not about the document", async () => {
    answer();
    openIt();
    const body = await screen.findByTestId("policy-explain-body");
    expect(body.textContent).toContain("what this app extracted, not what the document");
  });

  it("says so when a policy's rules carry no text to check against", async () => {
    answer({ rules: [] });
    openIt();
    const source = await screen.findByTestId("policy-explain-source");
    expect(source.textContent).toContain("nothing here to read the record against");
  });

  it("says how much of the policy the reading covers when not all of it", async () => {
    answer({ covers_every_rule: false, rule_count: 40 });
    openIt();
    const reading = await screen.findByTestId("policy-explain-reading");
    expect(reading.textContent).toContain("first 2");
    expect(reading.textContent).toContain("40");
  });
});

describe("absent, failed and refused are three different things", () => {
  it("shows a request in flight as neither an answer nor a failure", async () => {
    vi.spyOn(aiApi, "explainPolicy").mockImplementation(
      () => new Promise(() => {}) as Promise<PolicyExplanation>,
    );
    openIt();
    expect(await screen.findByTestId("policy-explain-pending")).toBeTruthy();
    expect(screen.queryByTestId("policy-explain-failed")).toBeNull();
    expect(screen.queryByTestId("policy-explain-none")).toBeNull();
  });

  it("offers a retry when the request did not land", async () => {
    vi.spyOn(aiApi, "explainPolicy").mockRejectedValue(
      new PolicyPlatformApiError(502, "gateway said no"),
    );
    openIt();
    const failed = await screen.findByTestId("policy-explain-failed");
    expect(failed.textContent).toContain("did not complete");
    expect(screen.queryByTestId("policy-explain-none")).toBeNull();
  });

  it("separates a refusal from a failure, and says why", async () => {
    answer({ explanation: null, unavailable_code: "record_states_a_single_rule" });
    openIt();
    const none = await screen.findByTestId("policy-explain-none");
    expect(none.textContent).toContain("states one rule");
    expect(screen.queryByTestId("policy-explain-failed")).toBeNull();
    expect(screen.queryByTestId("policy-explain-reading")).toBeNull();
  });

  it("distinguishes never having asked from having asked and got nothing", async () => {
    answer({ explanation: null, unavailable_code: null });
    openIt();
    const none = await screen.findByTestId("policy-explain-none");
    expect(none.textContent).toContain("No language model is configured");
  });

  it("keeps the document's words on every one of those paths", async () => {
    for (const code of [
      "record_states_a_single_rule",
      "reply_declined_to_explain",
      "reply_no_shorter_than_the_source",
      "reply_unusable",
      "model_call_failed",
      null,
    ]) {
      answer({ explanation: null, unavailable_code: code });
      render(<PolicyExplainButton provisionId="p1" policyKey="POL-1" />);
      fireEvent.click(screen.getAllByTestId("policy-explain-button")[0]);
      const source = await screen.findByTestId("policy-explain-source");
      expect(source.textContent).toContain(EXPLANATION.rules[0].stated_text);
      cleanup();
    }
  });

  it("gives every code its own words", async () => {
    const codes = [
      "record_states_a_single_rule",
      "reply_no_shorter_than_the_source",
      "no_record_to_explain",
      "reply_declined_to_explain",
      "reply_named_a_decision_route",
      "reply_unusable",
      "model_call_failed",
      null,
    ];
    const seen = new Set<string>();
    for (const code of codes) {
      answer({ explanation: null, unavailable_code: code });
      render(<PolicyExplainButton provisionId="p1" policyKey="POL-1" />);
      fireEvent.click(screen.getAllByTestId("policy-explain-button")[0]);
      const none = await screen.findByTestId("policy-explain-none");
      seen.add(none.textContent ?? "");
      cleanup();
    }
    expect(seen.size).toBe(codes.length);
  });
});

describe("neither decision route is the lesser one", () => {
  /**
   * Read off the source rather than off a render, so a branch no fixture
   * happens to reach is covered too. A guard that only sees what a test
   * rendered is a guard on the tests, not on the copy.
   */
  const SOURCE = "./PolicyExplainButton.tsx";

  function copy(): string {
    // The house idiom (`routeNotFault.test.ts`, `projectRegisterRow.test.ts`):
    // read through the bundler, so this cannot resolve against a wrong root and
    // then read nothing at all.
    const sources = import.meta.glob("./PolicyExplainButton.tsx", {
      query: "?raw",
      import: "default",
      eager: true,
    }) as Record<string, string>;
    const text = sources[SOURCE] ?? "";
    // Asserted, because a guard reading an empty string passes every check
    // below while looking at nothing.
    expect(text.length).toBeGreaterThan(1000);
    return text;
  }

  it("never frames either route as a shortcoming", async () => {
    const text = (copy()).toLowerCase();
    // Built from atoms so this file plants no forbidden phrase for the sibling
    // Python framing guard, which scans this directory and reads a quoted
    // string holding a space as language rather than as data.
    const routes = [
      ["ai", "ready"],
      ["deterministic"],
      ["machine", "executable"],
    ];
    const faults = [
      "cannot",
      "could not be made",
      "not possible",
      "falls short",
      "limitation",
      "shortcoming",
      "deficien",
      "gap",
      "unfortunately",
      "only",
      "merely",
      "fails to",
      "lacks",
      "weaker",
      "less certain",
      "harder to",
    ];
    for (const route of routes) {
      for (const joiner of [" ", "-", "_"]) {
        const term = route.join(joiner);
        let at = text.indexOf(term);
        while (at >= 0) {
          const near = text.slice(Math.max(0, at - 240), at + 240);
          for (const fault of faults) {
            expect(near.includes(fault), `${term} framed with "${fault}"`).toBe(false);
          }
          at = text.indexOf(term, at + 1);
        }
      }
    }
  });

  it("names no decision route in anything a reviewer reads", async () => {
    // The strongest form: the copy does not discuss routes at all. An
    // explanation is about what a policy requires, and how it will be decided
    // is a different question this dialog does not answer.
    const rendered = (copy())
      .split("\n")
      .filter((line) => !line.trimStart().startsWith("*") && !line.trimStart().startsWith("//"))
      .join("\n")
      .toLowerCase();
    for (const term of ["ai" + "-" + "ready", "ai" + " " + "ready", "deterministic"]) {
      // Present only inside the identifier of the code the server may send,
      // which is data and not language shown to a reader.
      const outside = rendered
        .replace(/reply_named_a_decision_route/g, "")
        .includes(term);
      expect(outside, term).toBe(false);
    }
  });

  it("does not describe a policy as being hard or easy to explain", async () => {
    const text = (copy()).toLowerCase();
    for (const phrase of ["too complex", "hard to explain", "difficult to"]) {
      expect(text.includes(phrase), phrase).toBe(false);
    }
  });
});
