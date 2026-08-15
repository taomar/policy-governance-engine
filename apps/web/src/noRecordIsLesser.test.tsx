/**
 * No kind of record is a lesser kind of record, and no copy sends a reviewer to
 * a control that is not there.
 *
 * A definition is evidence about a document exactly as an obligation is. Copy
 * that sorts records into groups, counts them, or says a card is not whole is
 * one word away from telling a reviewer they need not bother — "only
 * definitions", "just supporting entries", "nothing but glossary items" — and a
 * reviewer who believes that stops checking a large part of the corpus. This is
 * the same shape of mistake as framing `ai_ready` as a fault, and the existing
 * route guard does not look at these strings. So this one does.
 *
 * The second guard is newer and comes from a defect this file's predecessor
 * caught in its own author's work. The queue used to split records into two
 * lanes, and the copy here named the sibling lane so a reviewer knew where the
 * rest had gone. That split has been removed. Copy naming a filter, a lane or a
 * tab is now copy naming something the reviewer cannot see, which is worse than
 * saying nothing: it sends them looking for a control that does not exist.
 *
 * Both read the text the card actually renders rather than the source file it
 * lives in. Scanning source catches a component's unrelated prose and, worse,
 * misses copy assembled at run time from parts that each look innocent.
 *
 * Nothing here is a phrase from any document, and no count in it is a
 * measurement of one.
 */
import { afterEach, describe, expect, it } from "vitest";
import type { CandidateRule } from "./api";
import { fromDraftRow } from "./policyCards";
import { cleanup, render, screen } from "@testing-library/react";
import { PolicyReviewCard } from "./components/PolicyReviewCard";
import { policyCompositionLabel } from "./policyRecordFacts";
import type { PolicyCard } from "./policyCards";

/**
 * Wordings that rank one kind of record below another.
 *
 * Not a list of kinds — no `rule_type` appears here — but a list of the
 * judgements the copy must never pass on whatever kind it is naming. Blunt on
 * purpose: these run against generated copy, where "only" and "just" have no
 * innocent use.
 */
export const RANKING = [
  /\bonly\b/i,
  /\bjust\b/i,
  /\bmerely?\b/i,
  /\bsimply\b/i,
  /\bnothing but\b/i,
  /\bminor\b/i,
  /\bincidental\b/i,
  /\btrivial\b/i,
  /\bunimportant\b/i,
  /\bless important\b/i,
  /\bnot important\b/i,
  /\bsecondary\b/i,
  /\bauxiliary\b/i,
  /\bsupporting\b/i,
  /\bbackground\b/i,
  /\bnon-?essential\b/i,
  /\bsafely ignor/i,
  /\b(can|may) be ignored\b/i,
  /\bignore\b/i,
  /\bno need to\b/i,
  /\bnothing to review\b/i,
  /\bdo(es)? not need review/i,
  /\bnot worth\b/i,
  /\blesser\b/i,
  /\bskip\b/i,
  /\bboilerplate\b/i,
  /\bfiller\b/i,
  /\bnoise\b/i,
];

/**
 * Wordings that promise the reviewer a control.
 *
 * Every one of these was true copy while the queue had two lanes. None of them
 * is true now, and each would have a reviewer hunting the screen for something
 * that was deleted.
 */
export const PROMISES_A_CONTROL = [
  /\bfilter\b/i,
  /\btabs?\b/i,
  /\blanes?\b/i,
  /\bswitch to\b/i,
  /\bsegment/i,
  /\bthe other view\b/i,
  /\belsewhere on this page\b/i,
  /\bglossary\b/i,
];

function matching(patterns: RegExp[], text: string): string[] {
  return patterns.filter((pattern) => pattern.test(text)).map(String);
}

const ranked = (text: string) => matching(RANKING, text);
const promised = (text: string) => matching(PROMISES_A_CONTROL, text);

afterEach(cleanup);

/** A card holding `shownIds` out of a policy that states `allIds`. */
function card(shownIds: string[], allIds: string[]): PolicyCard {
  const shownRules = shownIds.map((rule_id, index) => ({
    rule_id,
    evaluation_mode: "deterministic",
    ...fromDraftRow({
      id: `candidate-${index}`,
      review_status: "pending",
      rule_type: "obligation",
      rule: {
        rule_id,
        title: "A statement",
        description: "A statement",
        evaluation_mode: "deterministic",
        condition: { type: "all", all: [] },
        effect: { type: "obligation", action: "an action" },
      },
    } as unknown as CandidateRule),
  }));

  return {
    policy: {
      key: "a-key",
      heading: "A heading",
      heading_path: ["A heading"],
      topic_label: null,
      persisted: true,
      provision_id: "a-provision-id",
      document_version_id: null,
      source_elements: "p1-E1",
      page: 1,
      rule_count: allIds.length,
      passage_count: 1,
      route: "deterministic",
      passages: [{ rules: allIds.map((rule_id) => ({ rule_id })) }],
      rules: [],
    },
    passages: [{ passage: { key: "a-passage-key" }, rules: shownRules }],
    rules: shownRules,
    reviewableIds: shownRules.map((rule) => rule.recordId),
    allIds: shownRules.map((rule) => rule.recordId),
    hiddenByFilter: allIds.length - shownIds.length,
  } as unknown as PolicyCard;
}

function renderCard(subject: PolicyCard) {
  return render(
    <PolicyReviewCard
      card={subject}
      selected={false}
      indeterminate={false}
      open={false}
      statusColor={() => "default"}
      statusLabel={(status: string) => status}
      findingsFor={() => 0}
      onToggleSelect={() => {}}
      onOpen={() => {}}
    />,
  );
}

describe("what the card actually renders", () => {
  it("says what a policy is made of without ranking either half", () => {
    // The card states its own composition, so a reviewer sees the mix instead
    // of choosing a side. That sentence is one word away from telling them
    // which half matters, and the half it would demote is the larger one.
    const offences: string[] = [];
    for (const decide of [0, 1, 3, 15]) {
      for (const define of [0, 1, 3, 15]) {
        for (const unstated of [0, 1, 3]) {
          const label = policyCompositionLabel({ decide, define, unstated }) ?? "";
          for (const pattern of ranked(label)) offences.push(`${pattern} in: ${label}`);
        }
      }
    }

    expect(offences).toEqual([]);
  });

  it("names no control and ranks no record when a card is short", () => {
    // Deliberately separate from the wording assertions below. A guard that
    // sits behind `expect(said).toContain(...)` stops running the moment
    // someone rewrites the sentence — which is exactly when it is needed. This
    // one asserts nothing about the words, so no rewrite can silence it.
    const shown = ["v1", "v2", "v3"];
    const hidden = Array.from({ length: 15 }, (_, index) => `h${index}`);
    const { container } = renderCard(card(shown, [...shown, ...hidden]));

    const said = container.querySelector(".policy-card__partial")?.textContent ?? "";

    expect(said).not.toEqual("");
    // One array, not two assertions: the first `expect` to fail ends the test,
    // and a sentence that both ranks and points would report as only ranking.
    expect([...ranked(said), ...promised(said)]).toEqual([]);
  });

  it("states the shortfall and what Approve decides", () => {
    // A card can still hold part of a policy — the queue can be narrowed to one
    // review status while the policy it is measured against is not. So the
    // warning survives. What it may no longer do is point anywhere.
    const shown = ["v1", "v2", "v3"];
    const hidden = Array.from({ length: 15 }, (_, index) => `h${index}`);
    const { container } = renderCard(card(shown, [...shown, ...hidden]));

    const said = container.querySelector(".policy-card__partial")?.textContent ?? "";

    // Both facts, in the reviewer's terms: how much of the policy is here, and
    // what one Approve settles.
    expect(said).toContain("3 of the 18 rules");
    expect(said).toContain("Approving here decides the rules shown above");
  });

  it("fails on copy that ranks or points, which is the only reason it is worth having", () => {
    // Mutation, run in process. No source file is hand-edited to prove the
    // guards bite, so the proof cannot rot when someone forgets to restore.
    expect(ranked("15 more rules of this policy are only definitions.")).not.toEqual([]);
    expect(ranked("The rest are just supporting entries.")).not.toEqual([]);
    expect(promised("15 more rules are outside the current filter.")).not.toEqual([]);
    expect(promised("They are in the Definitions & Glossary tab.")).not.toEqual([]);
  });

  it("says nothing about a shortfall when the card holds the whole policy", () => {
    // The default state of the queue, and the one that must stay silent: a
    // notice that fires on a whole policy trains reviewers to ignore it.
    const { container } = renderCard(card(["v1"], ["v1"]));

    expect(container.querySelector(".policy-card__partial")).toBeNull();
    expect(screen.getAllByTestId("policy-card-rule")).toHaveLength(1);
  });

  it("heads a run of records without ranking the run below it", () => {
    // The card groups its rules by whether they bind anyone, and puts the ones
    // that do first. That ordering is the exact shape of a ranking, so the
    // words over each group are where "only definitions" would reappear —
    // this time about records that are on screen rather than off it.
    const { container } = renderCard(mixedCard());

    const written = [
      ...[...container.querySelectorAll('[data-testid="rule-group"]')].map(
        (node) => node.textContent ?? "",
      ),
      container.querySelector('[data-testid="rule-grouping-note"]')?.textContent ?? "",
    ];

    expect(written.filter((text) => text.length > 0)).not.toEqual([]);
    const offences = written.flatMap((text) => [
      ...ranked(text).map((pattern) => `${pattern} in: ${text}`),
      ...promised(text).map((pattern) => `${pattern} in: ${text}`),
    ]);
    expect(offences).toEqual([]);
  });
});

/** A policy whose rules fall on both sides of the constraining question. */
function mixedCard(): PolicyCard {
  const rules = ["deny", "informational", "require_action", "informational"].map(
    (type, index) => ({
      rule_id: `r${index}`,
      evaluation_mode: "deterministic",
      ...fromDraftRow({
        id: `candidate-${index}`,
        review_status: "pending",
        rule_type: "obligation",
        rule: {
          rule_id: `r${index}`,
          title: `statement ${index}`,
          description: "a sentence of the source",
          evaluation_mode: "deterministic",
          condition: { type: "all", all: [] },
          effect: { type, action: "an action" },
        },
      } as unknown as CandidateRule),
    }),
  );

  return {
    policy: {
      key: "a-key",
      heading: "A heading",
      heading_path: ["A heading"],
      topic_label: null,
      persisted: true,
      provision_id: "a-provision-id",
      document_version_id: null,
      source_elements: "p1-E1",
      page: 1,
      rule_count: rules.length,
      passage_count: 1,
      route: "deterministic",
      passages: [{ rules: rules.map(({ rule_id }) => ({ rule_id })) }],
      rules: [],
    },
    passages: [{ passage: { key: "a-passage-key" }, rules }],
    rules,
    reviewableIds: rules.map((rule) => rule.recordId),
    allIds: rules.map((rule) => rule.recordId),
    hiddenByFilter: 0,
  } as unknown as PolicyCard;
}
