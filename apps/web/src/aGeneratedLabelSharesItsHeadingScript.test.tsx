/**
 * A generated label the heading shares no script with is withheld.
 *
 * WHAT THIS IS ABOUT
 *
 * The eyebrow above a policy card is this app's own generated name for the
 * subject (see `policyTopicLabel`). It is drawn to be read at a glance beside
 * the document's own heading directly below it. When the label is written in a
 * script the heading shares none of, it cannot be read as naming that heading:
 * to a reader following the heading it captions it is an unreadable line in the
 * card's most prominent place, and to anyone it risks being taken for the
 * source's own words in the one spot least equipped to notice — everything
 * around it can be cited, and this cannot.
 *
 * THE CASE, READ FROM THE CORPUS RATHER THAN INVENTED
 *
 * Unlike the sibling file `policyTopicLabel.test.tsx`, which is deliberately
 * free of any phrase from any document, this file quotes the one real pair the
 * corpus actually contains, so the case is reproducible from the file alone and
 * is not an injected pure-Arabic sample standing in for bilingual reality.
 *
 * In the AIS Employee Handbook, of the 65 generated labels, exactly one is
 * written in a script its heading shares none of: the provision headed, in the
 * document's own words, "Table of Violations and Penalties" carries a generated
 * label reading "قائمة المخالفات والعقوبات". Measured from the store as
 * `provision_topic_labels.label_text` against the same provision's
 * `document_provisions.heading_path_json`. The label is a cross-script
 * restatement of the heading, which the word-for-word redundancy check cannot
 * see because the two share no character — so before this rule it was shown.
 *
 * The label's words are this app's, not the document's; they are quoted here as
 * a fixture, never presented as a quotation on screen.
 */
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { policyJsonDocument, policyTopicLabel } from "./policyCards";
import type { PolicyCard } from "./policyCards";
import type { AssembledPolicy, PolicyTopicLabel } from "./api";
import { PolicyReviewCard } from "./components/PolicyReviewCard";

// Read from the corpus. The label is generated (this app's words); the heading
// is the document's own. They share no script — the case the item names.
const ARABIC_LABEL = "\u0642\u0627\u0626\u0645\u0629 \u0627\u0644\u0645\u062e\u0627\u0644\u0641\u0627\u062a \u0648\u0627\u0644\u0639\u0642\u0648\u0628\u0627\u062a";
const ENGLISH_HEADING = "Table of Violations and Penalties";

// A real handbook cell that puts both scripts in one heading. A label sharing
// one script with it is legible beside it and must stay — this is the case that
// tells "shares no script" apart from "is not identical".
const BILINGUAL_HEADING = "Written Warning \u0625\u0646\u0630\u0627\u0631 \u0643\u062a\u0627\u0628\u064a";

function labelPayload(text: string | null): PolicyTopicLabel {
  return {
    generated: true,
    text,
    unavailable_code: null,
    model_deployment: "a-deployment",
    prompt_version: "a-version",
    generated_at: "2024-01-01T00:00:00+00:00",
  };
}

function policy(text: string | null, headingPath: string[]): AssembledPolicy {
  return {
    key: "a-key",
    heading: headingPath[headingPath.length - 1] ?? "",
    heading_path: headingPath,
    topic_label: text === null ? null : labelPayload(text),
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

function card(text: string | null, headingPath: string[]): PolicyCard {
  return {
    policy: policy(text, headingPath),
    passages: [],
    rules: [],
    reviewableIds: [],
    allIds: [],
    reviewStatuses: [],
    hiddenByFilter: 0,
  } as unknown as PolicyCard;
}

function renderCard(text: string | null, headingPath: string[]) {
  return render(
    <PolicyReviewCard
      card={card(text, headingPath)}
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

afterEach(() => {
  cleanup();
});

describe("a generated label whose script the heading shares none of", () => {
  it("is read as withheld, a distinct fact from named or absent", () => {
    // Red before the rule: the label is not a restatement its heading's words
    // contain, so it read as `named` and was shown. It is withheld now, and for
    // a reason of its own, not folded into "repeats the heading" or "no name".
    const state = policyTopicLabel(policy(ARABIC_LABEL, [ENGLISH_HEADING]));
    expect(state.state).not.toBe("named");
    expect(state.state).toBe("foreign_to_heading");
  });

  it("draws no eyebrow on the card, and the heading still names the row", () => {
    renderCard(ARABIC_LABEL, [ENGLISH_HEADING]);

    // The reviewer sees no generated line above the heading.
    expect(screen.queryByTestId("policy-topic-label")).toBeNull();
    // The document's own heading is untouched and is what names the card.
    expect(document.querySelector(".policy-card__title")?.textContent).toBe(
      ENGLISH_HEADING,
    );
  });

  it("keeps the generated words in the export, marked as not shown", () => {
    // Withholding is not blanking. The file records what was generated and,
    // separately, that a reader was not shown it, so nothing is lost to the
    // eye is also not lost to the record.
    const document = policyJsonDocument(card(ARABIC_LABEL, [ENGLISH_HEADING]));
    const label = document.generated_topic_label as Record<string, unknown>;

    expect(label.text).toBe(ARABIC_LABEL);
    expect(label.shown_on_card).toBe(false);
    // And it never leaked into a field holding the document's own characters.
    expect(document.heading).toBe(ENGLISH_HEADING);
    expect(JSON.stringify(document.heading_path)).not.toContain(ARABIC_LABEL);
  });

  it("keeps a label that shares one script with a bilingual heading", () => {
    // The over-eager-fix catcher. This heading is written in both scripts, so it
    // shares the label's script; the label reads beside it and is not withheld.
    // A rule that withheld on "scripts not identical" rather than "scripts
    // disjoint" would wrongly drop this one.
    const state = policyTopicLabel(policy(ARABIC_LABEL, [BILINGUAL_HEADING]));
    expect(state.state).toBe("named");

    renderCard(ARABIC_LABEL, [BILINGUAL_HEADING]);
    expect(screen.getByTestId("policy-topic-label").textContent).toContain(
      ARABIC_LABEL,
    );
  });
});
