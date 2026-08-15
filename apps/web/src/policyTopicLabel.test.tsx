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
import { policyJsonDocument, policyTopicLabel } from "./policyCards";
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

function policy(topic: PolicyTopicLabel | null): AssembledPolicy {
  return {
    key: "a-key",
    heading: HEADING,
    heading_path: ["Outer", HEADING],
    topic_label: topic,
    persisted: true,
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

function card(topic: PolicyTopicLabel | null): PolicyCard {
  return {
    policy: policy(topic),
    passages: [],
    rules: [],
    reviewableIds: [],
    hiddenByFilter: 0,
  } as unknown as PolicyCard;
}

afterEach(() => {
  cleanup();
});

function renderCard(topic: PolicyTopicLabel | null) {
  return render(
    <PolicyReviewCard
      card={card(topic)}
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
  it("reports three states, and never a fourth", () => {
    // The reader must be able to tell "we tried and got nothing" from "nobody
    // has tried". A single nullable string cannot say both.
    expect(policyTopicLabel(policy(labelPayload())).state).toBe("named");
    expect(
      policyTopicLabel(
        policy(labelPayload({ text: null, unavailable_code: "a_code" })),
      ).state,
    ).toBe("unavailable");
    expect(policyTopicLabel(policy(null)).state).toBe("absent");
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

  it("says the label could not be produced rather than showing nothing", () => {
    renderCard(labelPayload({ text: null, unavailable_code: "a_code" }));

    const line = screen.getByTestId("policy-topic-label");
    expect(line.textContent?.trim().length).toBeGreaterThan(0);
    // The stored code is an internal token and is never put in front of a
    // reader; the line is worded for them instead.
    expect(line.textContent).not.toContain("a_code");
    // The document's heading is still the card's name.
    expect(document.querySelector(".policy-card__title")?.textContent).toBe(HEADING);
  });

  it("words a label nobody has asked for differently from one that failed", () => {
    const { unmount } = renderCard(null);
    const absent = screen.getByTestId("policy-topic-label").textContent ?? "";
    unmount();

    renderCard(labelPayload({ text: null, unavailable_code: "a_code" }));
    const failed = screen.getByTestId("policy-topic-label").textContent ?? "";

    // A reviewer told "not generated yet" about a policy that already failed
    // would wait for something that is not coming.
    expect(absent).not.toBe(failed);
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
