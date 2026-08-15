/**
 * No kind of record is a lesser kind of record.
 *
 * A definition is evidence about a document exactly as an obligation is. The
 * copy that says which records a surface is not showing is one word away from
 * telling a reviewer they need not bother — "only definitions", "just
 * supporting entries", "nothing but glossary items" — and a reviewer who
 * believes that stops checking a large part of the corpus.
 *
 * This is the same shape of mistake as framing `ai_ready` as a fault, and the
 * existing route guard does not look at these strings. So this one does.
 *
 * It reads the sentences the app actually produces, and the text the card
 * actually renders, rather than the source files they live in. Scanning source
 * catches a component's unrelated prose and, worse, misses copy assembled at
 * run time from parts that each look innocent. Everything a reviewer can read
 * here comes out of `notShownSentence` or out of that one node, so those are
 * what is read.
 *
 * Nothing here is a phrase from any document, and no count in it is a
 * measurement of one.
 */
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import {
  forgetRecordKinds,
  noteRecordKinds,
  notShownSentence,
  recordsNotShown,
  registerRecordDestinations,
  type PolicyLikeCard,
} from "./recordsNotShown";
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

function ranked(sentence: string): string[] {
  return RANKING.filter((pattern) => pattern.test(sentence)).map(String);
}

function record(ruleId: string, kind: string) {
  return { rule_type: kind, rule: { rule_id: ruleId } };
}

/** Kinds invented for this test. Two are shaped like schema values this app
 *  has never seen, because the guard has to hold for a kind extraction learns
 *  tomorrow as well as for the ones it knows today. */
const KINDS = [
  "definition",
  "obligation",
  "human_judgment_requirement",
  "access_restriction",
  "escalation",
  "a_kind_this_app_has_never_met",
  "advisory_note",
];

afterEach(() => {
  forgetRecordKinds();
  cleanup();
});

describe("every sentence this feature can produce", () => {
  it("names a kind without ranking it, across every mixture it can hit", () => {
    const offences: string[] = [];

    for (const kind of KINDS) {
      for (const other of KINDS) {
        for (const hiddenOfKind of [1, 2, 15]) {
          forgetRecordKinds();
          const ids: string[] = ["shown"];
          const records = [record("shown", "obligation")];
          for (let i = 0; i < hiddenOfKind; i += 1) {
            ids.push(`k${i}`);
            records.push(record(`k${i}`, kind));
          }
          if (other !== kind) {
            ids.push("other");
            records.push(record("other", other));
          }
          noteRecordKinds(records);
          registerRecordDestinations([
            { label: "Here (1)", holds: (one) => one === "obligation", isCurrent: true },
            { label: "There (2)", holds: (one) => one !== "obligation" },
          ]);

          const card: PolicyLikeCard = {
            hiddenByFilter: ids.length - 1,
            rules: [{ rule_id: "shown" }],
            policy: { passages: [{ rules: ids.map((rule_id) => ({ rule_id })) }] },
          };
          const sentence = notShownSentence(recordsNotShown(card));
          for (const pattern of ranked(sentence)) {
            offences.push(`${pattern} in: ${sentence}`);
          }
        }
      }
    }

    expect(offences).toEqual([]);
  });

  it("ranks nothing when it can name nothing, which is where a hedge would go", () => {
    const bare: PolicyLikeCard = { hiddenByFilter: 15, rules: [], policy: {} };

    expect(ranked(notShownSentence(recordsNotShown(bare)))).toEqual([]);
  });

  it("fails on a ranking wording, which is the only reason it is worth having", () => {
    // Mutation, run in process. No source file is hand-edited to prove the
    // guard bites, so the proof cannot rot when someone forgets to restore.
    expect(
      ranked("15 more rules of this policy are only definitions and can be ignored."),
    ).not.toEqual([]);
    expect(ranked("The rest are just supporting entries.")).not.toEqual([]);
    expect(ranked("The remaining records are background material.")).not.toEqual([]);
  });
});

function card(shownIds: string[], allIds: string[]): PolicyCard {
  const shownRules = shownIds.map((rule_id, index) => ({
    rule_id,
    evaluation_mode: "deterministic",
    candidate: {
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
    },
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
    reviewableIds: shownRules.map((rule) => rule.candidate.id),
    allIds: shownRules.map((rule) => rule.candidate.id),
    hiddenByFilter: allIds.length - shownIds.length,
  } as unknown as PolicyCard;
}

describe("what the card actually renders", () => {
  it("says what a policy is made of without ranking either half", () => {
    // The card now states its own composition, so a reviewer sees the mix
    // instead of choosing a side. That sentence is one word away from telling
    // them which half matters, and the half it would demote is the larger one.
    const offences: string[] = [];
    for (const decide of [1, 3, 15]) {
      for (const define of [1, 3, 15]) {
        const label = policyCompositionLabel({ decide, define }) ?? "";
        for (const pattern of ranked(label)) offences.push(`${pattern} in: ${label}`);
      }
    }

    expect(offences).toEqual([]);
  });

  it("tells the reviewer what is out of view, where it is, and what Approve decides", () => {
    // The case the user hit: three of eighteen shown, the other fifteen one tab
    // away. They asked what "15 more rules" meant. This is the answer.
    const shown = ["v1", "v2", "v3"];
    const hidden = Array.from({ length: 15 }, (_, index) => `h${index}`);
    noteRecordKinds([
      ...shown.map((id) => record(id, "obligation")),
      ...hidden.map((id) => record(id, "definition")),
    ]);
    registerRecordDestinations([
      { label: "Policies & Rules (265)", holds: (kind) => kind !== "definition", isCurrent: true },
      { label: "Definitions & Glossary (14)", holds: (kind) => kind === "definition" },
    ]);

    const { container } = render(
      <PolicyReviewCard
        card={card(shown, [...shown, ...hidden])}
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

    const said = container.querySelector(".policy-card__partial")?.textContent ?? "";

    expect(said).toContain("15 more rules of this policy are definitions");
    expect(said).toContain("Definitions & Glossary (14)");
    // The load-bearing warning, unchanged: Approve decides the three on screen.
    expect(said).toContain("Approving here decides the rules shown above");
    expect(ranked(said)).toEqual([]);
  });

  it("says nothing about out-of-view records when there are none", () => {
    const { container } = render(
      <PolicyReviewCard
        card={card(["v1"], ["v1"])}
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

    expect(container.querySelector(".policy-card__partial")).toBeNull();
    expect(screen.getAllByTestId("policy-card-rule")).toHaveLength(1);
  });
});
