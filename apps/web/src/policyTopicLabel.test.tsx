/**
 * A generated label is never mistaken for the document's words.
 *
 * WHAT IS AT STAKE
 *
 * Every string on a policy card except this one is characters the source wrote,
 * and a reviewer approves rules by reading them. A generated label sitting
 * among them would be an assertion nobody sourced, in the one place a reader is
 * least equipped to notice — because everything around it can be cited.
 *
 * WHAT IS ASSERTED, AND WHAT DELIBERATELY IS NOT
 *
 * Not that the label's characters differ from the document's. A good subject
 * name reuses the document's nouns — that is what naming a subject is — and
 * requiring difference would push generation towards paraphrase, which reads
 * less like the source while being no safer.
 *
 * What is asserted is placement and attribution, which is what a reader
 * actually goes on: the label never enters a field holding the source's
 * characters, it leaves the app under its own key with its own provenance, it
 * renders outside the title and outside every quotation, it is never wrapped in
 * quote marks, and the line it sits on says whose words they are.
 */
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { labelAddsNothing, policyJsonDocument, policyTopicLabel } from "./policyCards";
import type { PolicyCard } from "./policyCards";
import type { AssembledPolicy, PolicyTopicLabel } from "./api";
import { PolicyReviewCard } from "./components/PolicyReviewCard";

// Written for this file. Nothing here is a phrase from any document, and no
// number in it is a measurement of one.
const HEADING = "Section one";
const GENERATED = "Stated arrangement";

function labelPayload(overrides: Partial<PolicyTopicLabel> = {}): PolicyTopicLabel {
  return {
    generated: true,
    text: GENERATED,
    unavailable_code: null,
    model_deployment: "a-deployment",
    prompt_version: "a-version",
    generated_at: "2024-01-01T00:00:00+00:00",
    ...overrides,
  };
}

function policy(
  topic: PolicyTopicLabel | null,
  headingPath: string[] = ["Outer", HEADING],
): AssembledPolicy {
  return {
    key: "a-key",
    heading: headingPath[headingPath.length - 1] ?? HEADING,
    heading_path: headingPath,
    topic_label: topic,
    persisted: true,
    provision_id: "a-provision-id",
    document_version_id: null,
    source_elements: "p1-E1",
    page: 1,
    rule_count: 1,
    passage_count: 1,
    route: "deterministic",
    passages: [],
    rules: [],
  };
}

function card(topic: PolicyTopicLabel | null, headingPath?: string[]): PolicyCard {
  return {
    policy: policy(topic, headingPath),
    passages: [],
    rules: [],
    reviewableIds: [],
    hiddenByFilter: 0,
  } as unknown as PolicyCard;
}

afterEach(() => {
  cleanup();
});

function renderCard(topic: PolicyTopicLabel | null, headingPath?: string[]) {
  return render(
    <PolicyReviewCard
      card={card(topic, headingPath)}
      selected={false}
      indeterminate={false}
      open={false}
      statusColor={() => "default"}
      statusLabel={(status) => status}
      findingsFor={() => 0}
      onToggleSelect={() => {}}
      onOpen={() => {}}
    />,
  );
}

describe("reading a generated label off a policy", () => {
  it("reports four states, and never a fifth", () => {
    // The reader must be able to tell "we tried and got nothing" from "nobody
    // has tried". A single nullable string cannot say both.
    expect(policyTopicLabel(policy(labelPayload())).state).toBe("named");
    expect(
      policyTopicLabel(
        policy(labelPayload({ text: null, unavailable_code: "a_code" })),
      ).state,
    ).toBe("unavailable");
    expect(policyTopicLabel(policy(null)).state).toBe("absent");
    // A name that only repeats the heading is a fourth fact, not a missing one.
    expect(
      policyTopicLabel(policy(labelPayload({ text: HEADING }), ["Outer", HEADING])).state,
    ).toBe("redundant");
  });

  it("treats an empty label as a failure and never as a name", () => {
    // A blank where a name goes is indistinguishable on screen from a name
    // nobody asked for. It is a failed attempt and is reported as one.
    expect(policyTopicLabel(policy(labelPayload({ text: "   " }))).state).toBe(
      "unavailable",
    );
  });

  it("refuses to present anything the server did not mark as generated", () => {
    // The flag is the server's assertion that these words are ours. Text
    // arriving without it has no such assertion behind it and is not shown.
    const unmarked = { ...labelPayload(), generated: false } as unknown as PolicyTopicLabel;
    expect(policyTopicLabel(policy(unmarked)).state).toBe("absent");
  });

  it("never composes a label of its own when there is none", () => {
    // A fallback would be this app naming a document's subject out of its own
    // vocabulary. The absence travels to the screen intact.
    const state = policyTopicLabel(policy(null));
    expect(state).toEqual({ state: "absent" });
  });

  it("keeps provenance reachable from the words it describes", () => {
    const state = policyTopicLabel(policy(labelPayload()));
    if (state.state !== "named") throw new Error("expected a named label");
    expect(state.provenance).toContain("a-deployment");
    expect(state.provenance).toContain("a-version");
  });
});

describe("exporting a policy that carries a generated label", () => {
  it("files it apart from every field holding the document's characters", () => {
    const document = policyJsonDocument(card(labelPayload()));

    // The four keys a consumer reads to get the source's own words.
    expect(document.heading).toBe(HEADING);
    expect(document.title).toBe(HEADING);
    expect(document.heading_path).not.toContain(GENERATED);
    expect(JSON.stringify(document.passages ?? [])).not.toContain(GENERATED);

    // And its own key, saying it was generated.
    const generated = document.generated_topic_label as Record<string, unknown>;
    expect(generated.generated).toBe(true);
    expect(generated.text).toBe(GENERATED);
    expect(generated.model_deployment).toBe("a-deployment");
  });

  it("says nothing was generated rather than omitting the question", () => {
    const document = policyJsonDocument(card(null));
    expect(document.generated_topic_label).toBeNull();
    expect(document.heading).toBe(HEADING);
  });
});

describe("rendering a generated label beside the document's heading", () => {
  it("keeps it out of the title and marks it as this app's", () => {
    renderCard(labelPayload());

    const line = screen.getByTestId("policy-topic-label");
    expect(line.textContent).toContain(GENERATED);
    // Attributed on the line itself, not in a legend somewhere else.
    expect(line.textContent?.toLowerCase()).toContain("this app");
    expect(line.getAttribute("data-generated")).toBe("true");

    // Never quoted: quote marks around these words would present them as
    // somebody's exact words, and they are nobody's.
    expect(line.textContent).not.toContain(`"${GENERATED}"`);
    expect(line.textContent).not.toContain(`\u201c${GENERATED}\u201d`);

    // The title stays the document's, and holds nothing generated.
    const title = document.querySelector(".policy-card__title");
    expect(title?.textContent).toBe(HEADING);
    expect(title?.textContent).not.toContain(GENERATED);

    // And the trail of the document's headings holds nothing generated either.
    expect(screen.getByTestId("policy-heading-trail").textContent).not.toContain(
      GENERATED,
    );
  });

  it("draws no line at all when generation was attempted and produced no name", () => {
    // A reversal of how this line first behaved, and deliberate. It used to
    // announce the failure, on the principle that an absent answer must never
    // be mistaken for an empty one. That principle guards against losing a fact
    // to silence, and here no fact is lost: the document's own heading is
    // immediately below and fully legible. The eyebrow is the most prominent
    // line on the card, and spending it to say we have nothing to add is worse
    // than spending it on nothing.
    renderCard(labelPayload({ text: null, unavailable_code: "a_code" }));

    expect(screen.queryByTestId("policy-topic-label")).toBeNull();
    // The document's heading is still the card's name, and is untouched.
    expect(document.querySelector(".policy-card__title")?.textContent).toBe(HEADING);
    // The internal token never reaches a reader through any other route either.
    expect(document.body.textContent).not.toContain("a_code");
  });

  it("draws no line when no name has been generated yet", () => {
    renderCard(null);

    expect(screen.queryByTestId("policy-topic-label")).toBeNull();
    expect(document.querySelector(".policy-card__title")?.textContent).toBe(HEADING);
  });

  it("keeps failed and never-attempted apart where that is worth reading", () => {
    // The card draws nothing in either case, because neither tells the reviewer
    // anything they cannot see. But the two are different facts, and a reviewer
    // asking why a policy has no name must still be able to find out -- so the
    // distinction moves to the exported file rather than being discarded.
    const failed = policyTopicLabel({
      topic_label: labelPayload({ text: null, unavailable_code: "a_code" }),
      heading_path: [HEADING],
    } as Parameters<typeof policyTopicLabel>[0]);
    const never = policyTopicLabel({
      topic_label: null,
      heading_path: [HEADING],
    } as Parameters<typeof policyTopicLabel>[0]);

    expect(failed.state).toBe("unavailable");
    expect(never.state).toBe("absent");
    expect(failed.state).not.toBe(never.state);
  });

  it("renders a label in a right-to-left script as its own run", () => {
    // Direction is a property of the run, never of the page. The label may be
    // in a different script from the heading beside it, and both must read.
    const arabic = "\u0627\u0644\u062a\u0631\u062a\u064a\u0628";
    renderCard(labelPayload({ text: arabic }));

    const line = screen.getByTestId("policy-topic-label");
    expect(line.querySelector("bdi")?.textContent).toBe(arabic);
    expect(document.querySelector(".policy-card__title")?.textContent).toBe(HEADING);
  });
});

describe("a label earns its line only by saying something the heading did not", () => {
  it("withholds a label whose every word the heading already carries", () => {
    // The reader has this answer already, in the document's own words, on the
    // next line. Repeating it costs a line and teaches nothing -- and a line
    // that is sometimes the whole value of the card and sometimes an echo is a
    // line people learn to skip, informative cases included.
    expect(labelAddsNothing("Section one", ["Outer", "Section one"])).toBe(true);
    expect(labelAddsNothing("SECTION ONE", ["Outer", "Section one"])).toBe(true);
    renderCard(labelPayload({ text: "Section one" }), ["Outer", "Section one"]);
    expect(screen.queryByTestId("policy-topic-label")).toBeNull();
  });

  it("keeps a label that introduces any word the heading did not", () => {
    expect(labelAddsNothing("Stated arrangement", ["Outer", "Section one"])).toBe(false);
    renderCard(labelPayload(), ["Outer", "Section one"]);
    expect(screen.getByTestId("policy-topic-label")).toBeTruthy();
  });

  it("judges the whole heading chain, because the card shows the whole chain", () => {
    // A label repeating an outer heading is as redundant to a reader looking at
    // the trail as one repeating the innermost.
    expect(labelAddsNothing("Outer", ["Outer", "Section one"])).toBe(true);
  });

  it("treats a word and its inflection as the same word, but stops well short of that", () => {
    // Directional: the question is whether the label's content is already in
    // the heading, so a heading word may be the longer of the pair. "Probation"
    // in a label against "Probationary" in a heading is the same subject said
    // twice, and the reader gains nothing from the second saying.
    expect(labelAddsNothing("probation", ["Probationary period"])).toBe(true);
    expect(labelAddsNothing("employee travel", ["EMPLOYEES' DAY OF TRAVEL"])).toBe(true);

    // The guard: a shared opening is only an inflection when what is left over
    // is shorter than what matched. Otherwise every short word would swallow
    // every long one that happens to start the same way, and the rule would
    // hide labels that say something new.
    expect(labelAddsNothing("man", ["Manpower planning"])).toBe(false);
    expect(labelAddsNothing("car", ["Carpentry"])).toBe(false);
    expect(labelAddsNothing("a", ["Absence"])).toBe(false);
  });

  it("does not let a symbol standing for a word make the label look new", () => {
    // A heading joining its terms with a symbol says the same thing as a label
    // joining them with a word. Counting the symbols the heading uses that way
    // bounds how many label words may go unmatched -- it reads what the heading
    // did, and carries no list of words in any language.
    expect(
      labelAddsNothing("Absence and leave", ["7.10. ABSENCE, LATENESS, TARDINESS & LEAVE"]),
    ).toBe(true);
    expect(
      labelAddsNothing("Manpower planning and recruitment", [
        "1. Manpower Planning, Recruitment & Selection",
      ]),
    ).toBe(true);

    // A heading with no such symbol has spent nothing, so an extra label word
    // is genuinely new and the label is kept.
    expect(labelAddsNothing("Gifts and hospitality", ["8.9. GIFTS"])).toBe(false);
  });

  it("ignores the numbering a heading carries, which names no subject", () => {
    expect(labelAddsNothing("Overtime", ["7.9. OVERTIME"])).toBe(true);
    // The same rule applied to the label: numbering is not content, so a label
    // made only of numbering has nothing to add and is withheld. Nothing is
    // hidden by that -- there was nothing there to show.
    expect(labelAddsNothing("7.9", ["Working hours"])).toBe(true);
  });

  it("applies the same rule to a script the heading does not use", () => {
    // A label in another script shares no word with a Latin heading, so it is
    // always new -- which is right: it is exactly the case the reader cannot
    // read off the heading. No language is named to reach that answer.
    const arabic = "\u0627\u0644\u062a\u0631\u062a\u064a\u0628";
    expect(labelAddsNothing(arabic, ["Section one"])).toBe(false);
    expect(labelAddsNothing(arabic, [arabic])).toBe(true);
  });

  it("holds no heading, no vocabulary and no fitted threshold of its own", () => {
    // The rule is a relation between two strings handed to it. If it carried a
    // list of headings, or a threshold fitted to a corpus, it would be right
    // about one set of documents and wrong about the next.
    //
    // Asserted precisely rather than crudely: `0` and `1` are structural (an
    // empty check, an index) and cannot encode a measurement, so those are
    // allowed and anything else is not. A string literal containing a letter is
    // how domain vocabulary would arrive, so none may.
    const source = labelAddsNothing.toString();
    const numbers = (source.match(/\b\d+\b/g) ?? []).filter(
      (literal) => literal !== "0" && literal !== "1",
    );
    expect(numbers).toEqual([]);
    const stringsWithWords = (source.match(/"[^"]*"|'[^']*'/g) ?? []).filter((literal) =>
      /\p{L}/u.test(literal),
    );
    expect(stringsWithWords).toEqual([]);
  });

  it("records a withheld label in the export rather than dropping it", () => {
    // What was generated and what a reader was shown are different facts, and
    // neither may be inferred from the other's absence.
    const doc = policyJsonDocument(card(labelPayload({ text: "Section one" }), ["Section one"]));
    const label = doc.generated_topic_label as Record<string, unknown>;
    expect(label.text).toBe("Section one");
    expect(label.shown_on_card).toBe(false);
  });
});
