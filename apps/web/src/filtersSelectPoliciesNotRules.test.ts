/**
 * A status or delta filter selects policies. It does not carve one up.
 *
 * THE FAILURE THIS EXISTS TO PREVENT
 *
 * `cardsAreWholePolicies` settled this for the search box. The same defect
 * survived in the two filters that were still applied server-side, at rule
 * level, before any card was assembled: review status and delta status.
 *
 * Observed live before this change, on a real set: choosing "Needs review"
 * produced four cards and all four were fragments — `1 of 2 rules`, with a
 * single `Approve policy` sitting under them. The card had quietly become
 * "the pending part of this policy" while keeping the policy's name and the
 * authority of a policy-level decision, and the reviewer could not see the
 * rule they were not deciding, nor read the approved words beside the words
 * they were approving.
 *
 * These assert the derivation rather than a rendered queue, because the failure
 * renders perfectly: a fragment looks exactly like a small policy.
 *
 * Each test carries a control that fails if nothing was built or nothing was
 * narrowed, since "no rule was dropped" is also true of an empty card.
 */

import { describe, expect, it } from "vitest";
import type { AssembledPolicy, CandidateRule, CanonicalRule } from "./api";
import { buildPolicyCards } from "./policyCards";
import { placeableCandidates } from "./queueCardSelection";
import {
  candidateAnswersDelta,
  candidateAnswersRuleFilters,
  candidateAnswersStatus,
  candidateIdsAnsweringRuleFilters,
  cardsAnsweringRuleFilters,
  filterIsOff,
  policySelectionNote,
} from "./queueCardFilters";

/** Neutral placeholders. Nothing here leans on the vocabulary of any document. */
function canonical(ruleId: string): CanonicalRule {
  return {
    schema_version: "1.0",
    policy_set_id: "set",
    policy_version_id: "draft",
    rule_id: ruleId,
    rule_revision: 1,
    title: `A title for ${ruleId}`,
    description: `Description of ${ruleId}`,
    rule_type: "obligation",
    authority: { level: "ai_drafted", owner: "formulator", rank: 0 },
    scope: { jurisdictions: [], organizational_units: [], personas: [], processes: [] },
    condition: { type: "all", all: [] },
    attributes: { applies: [], produces: [] },
    effect: { action: "record", parameters: {} },
    evidence: [],
    provenance: { document_id: "doc", page: 1 },
    tags: [],
    category: null,
    group_label: null,
    required_facts: [],
    decision_readiness: null,
  } as unknown as CanonicalRule;
}

function candidate(ruleId: string, overrides: Partial<CandidateRule> = {}): CandidateRule {
  return {
    id: `cand-${ruleId}`,
    rule_id: ruleId,
    rule_type: "obligation",
    review_status: "candidate",
    delta_status: null,
    rule: canonical(ruleId),
    superseded_by_candidate_id: null,
    baseline_candidate_id: null,
    ...overrides,
  } as unknown as CandidateRule;
}

function policyOf(ruleIds: readonly string[]): AssembledPolicy {
  return {
    key: "policy-under-test",
    heading: "A heading the document supplies",
    heading_trail: [],
    page: 1,
    rule_count: ruleIds.length,
    passages: [
      {
        passage_id: "passage-1",
        text: "The sentence the policy is stated in.",
        title: null,
        rules: ruleIds.map((id) => ({ rule_id: id, evaluation_mode: "ai_ready" })),
      },
    ],
  } as unknown as AssembledPolicy;
}

const RULE_IDS = ["r-1", "r-2", "r-3"];

/** One policy whose rules are in three different review states at once — the
 *  ordinary case that the old rule-level filter turned into three fragments. */
function mixedFixture() {
  const candidates = [
    candidate("r-1", { review_status: "candidate", delta_status: "new" }),
    candidate("r-2", { review_status: "published", delta_status: "unchanged" }),
    candidate("r-3", { review_status: "approved", delta_status: null }),
  ];
  return { candidates, policies: [policyOf(RULE_IDS)] };
}

function cardsFor(fixture: ReturnType<typeof mixedFixture>) {
  const placeable = placeableCandidates(fixture.candidates);
  return { placeable, cards: buildPolicyCards(fixture.policies, placeable) };
}

describe("a rule-level filter chooses policies, never their contents", () => {
  it("shows the whole policy when only one of its rules answers the status filter", () => {
    const fixture = mixedFixture();
    const { placeable, cards } = cardsFor(fixture);

    const matched = candidateIdsAnsweringRuleFilters(placeable, { status: "candidate" });
    // Control: the filter really did narrow the records, or this proves nothing.
    expect(matched.size).toBe(1);
    // Control: there is a card to keep whole.
    expect(cards).toHaveLength(1);

    const shown = cardsAnsweringRuleFilters(cards, { status: "candidate" }, matched);
    expect(shown).toHaveLength(1);
    expect(shown[0].rules).toHaveLength(RULE_IDS.length);
    expect(shown[0].rules.map((r) => r.rule_id).sort()).toEqual([...RULE_IDS].sort());
  });

  it("leaves nothing hidden by the filter, so the card has no fragment to apologise for", () => {
    const fixture = mixedFixture();
    const { placeable, cards } = cardsFor(fixture);
    const matched = candidateIdsAnsweringRuleFilters(placeable, { status: "candidate" });
    const shown = cardsAnsweringRuleFilters(cards, { status: "candidate" }, matched);

    // This is the number the card's footnote was rendered from. Zero means the
    // footnote has nothing to say, which is the measure of the fix.
    expect(shown[0].hiddenByFilter).toBe(0);
  });

  it("offers one Approve over every rule it displays, not a subset of them", () => {
    const fixture = mixedFixture();
    const { placeable, cards } = cardsFor(fixture);
    const matched = candidateIdsAnsweringRuleFilters(placeable, { status: "candidate" });
    const shown = cardsAnsweringRuleFilters(cards, { status: "candidate" }, matched);

    // Every id the decision writes to is an id the reviewer can see on the card.
    const visible = new Set(shown[0].rules.map((r) => r.candidate.id));
    for (const id of shown[0].allIds) expect(visible.has(id)).toBe(true);
  });

  it("offers the same policy under each filter its rules answer, whole both times", () => {
    const fixture = mixedFixture();
    const { placeable, cards } = cardsFor(fixture);

    for (const status of ["candidate", "published", "approved"]) {
      const matched = candidateIdsAnsweringRuleFilters(placeable, { status });
      expect(matched.size).toBe(1); // control: exactly one rule is in each state
      const shown = cardsAnsweringRuleFilters(cards, { status }, matched);
      expect(shown).toHaveLength(1);
      expect(shown[0].rules).toHaveLength(RULE_IDS.length);
    }
  });

  it("hides a policy no rule of which answers the filter", () => {
    const fixture = mixedFixture();
    const { placeable, cards } = cardsFor(fixture);
    // Control: unfiltered, the card is there to be hidden.
    expect(cardsAnsweringRuleFilters(cards, {}, new Set())).toHaveLength(1);

    const matched = candidateIdsAnsweringRuleFilters(placeable, { status: "rejected" });
    expect(matched.size).toBe(0);
    expect(cardsAnsweringRuleFilters(cards, { status: "rejected" }, matched)).toHaveLength(0);
  });

  it("returns the cards untouched when no rule-level filter is on", () => {
    const { cards } = cardsFor(mixedFixture());
    const shown = cardsAnsweringRuleFilters(cards, { status: "all", delta: "all" }, new Set());
    expect(shown).toHaveLength(1);
    expect(shown[0].rules).toHaveLength(RULE_IDS.length);
  });

  it("narrows by status and delta together, and still returns the policy whole", () => {
    const fixture = mixedFixture();
    const { placeable, cards } = cardsFor(fixture);

    const both = candidateIdsAnsweringRuleFilters(placeable, {
      status: "candidate",
      delta: "new",
    });
    expect(both.size).toBe(1);
    expect(cardsAnsweringRuleFilters(cards, { status: "candidate", delta: "new" }, both)[0].rules)
      .toHaveLength(RULE_IDS.length);

    // A combination no single rule satisfies hides the policy rather than
    // showing it with the rules that satisfied one half each.
    const neither = candidateIdsAnsweringRuleFilters(placeable, {
      status: "candidate",
      delta: "unchanged",
    });
    expect(neither.size).toBe(0);
    expect(
      cardsAnsweringRuleFilters(cards, { status: "candidate", delta: "unchanged" }, neither),
    ).toHaveLength(0);
  });
});

describe("the predicates say what they mean", () => {
  it("treats an absent filter and the word for 'all' as not filtering", () => {
    expect(filterIsOff("all")).toBe(true);
    expect(filterIsOff("")).toBe(true);
    expect(filterIsOff(null)).toBe(true);
    expect(filterIsOff(undefined)).toBe(true);
    expect(filterIsOff("candidate")).toBe(false);
  });

  it("matches a record's own recorded status and nothing derived", () => {
    const c = candidate("r-1", { review_status: "approved" });
    expect(candidateAnswersStatus(c, "approved")).toBe(true);
    expect(candidateAnswersStatus(c, "candidate")).toBe(false);
    expect(candidateAnswersStatus(c, "all")).toBe(true);
  });

  it("does not fold a record with no delta recorded into a named delta", () => {
    // Absent is not `unchanged`: nobody classified this record, and a filter
    // that says otherwise invents a judgement the run never made.
    const noDelta = candidate("r-1", { delta_status: null });
    expect(candidateAnswersDelta(noDelta, "unchanged")).toBe(false);
    expect(candidateAnswersDelta(noDelta, "baseline")).toBe(false);
    expect(candidateAnswersDelta(noDelta, "new")).toBe(false);
    // ...but it is not excluded when nothing is being filtered.
    expect(candidateAnswersDelta(noDelta, "all")).toBe(true);
  });

  it("requires a record to answer every filter that is on", () => {
    const c = candidate("r-1", { review_status: "candidate", delta_status: "new" });
    expect(candidateAnswersRuleFilters(c, { status: "candidate", delta: "new" })).toBe(true);
    expect(candidateAnswersRuleFilters(c, { status: "candidate", delta: "changed" })).toBe(false);
    expect(candidateAnswersRuleFilters(c, {})).toBe(true);
  });
});

describe("the queue does not ask the server to narrow rules within a policy", () => {
  const source = Object.values(
    import.meta.glob("./components/ReviewQueue.tsx", {
      query: "?raw",
      import: "default",
      eager: true,
    }),
  )[0] as string;

  it("reads the queue's own source", () => {
    expect(source.length).toBeGreaterThan(1000);
    expect(source).toContain("listCandidateRules");
  });

  it("does not send the status filter to the candidate-rules request", () => {
    // The request must not be given `statusFilter`, because a status-filtered
    // response cannot assemble a whole policy however carefully it is handled
    // afterwards -- the missing rules are simply not in the payload.
    const call = source.slice(
      source.indexOf("api.listCandidateRules"),
      source.indexOf("api.listCandidateRules") + 400,
    );
    expect(call).not.toContain("statusFilter");
    expect(call).not.toContain("delta_status");
  });

  it("filters the assembled cards instead", () => {
    expect(source).toContain("cardsAnsweringRuleFilters");
  });

  it("renders the note that reconciles the two counts", () => {
    // The strip counts records; the list counts policies. Both are right, and
    // the screen has to say which is which, so this must actually be rendered
    // -- not merely exported and forgotten.
    expect(source).toContain("policySelectionNote");
    expect(source).toContain("policy-selection-note");
  });

  it("names filters with the words the controls themselves use", () => {
    // Restating labels here would let the note drift from the button that set
    // the filter. It reads both tables instead.
    expect(source).toContain("REVIEW_STATUS_TABS");
    expect(source).toContain("DELTA_META");
  });
});

describe("no filter asks what a record is about", () => {
  // The distinction between a record that constrains someone and one that
  // supplies a meaning is sound, and is read from effect.type rather than from
  // the words, so it needs no vocabulary. What the corpus refuted is asking it
  // at this level: measured over four extraction runs, at most one policy per
  // run is purely a glossary, because definitions sit inside real policies
  // rather than forming their own. A lane here would hold one card, and could
  // only be filled by carving rules back out of policies.
  const filterSource = Object.values(
    import.meta.glob("./queueCardFilters.ts", {
      query: "?raw",
      import: "default",
      eager: true,
    }) as Record<string, string>,
  )[0];
  const queueSource = Object.values(
    import.meta.glob("./components/ReviewQueue.tsx", {
      query: "?raw",
      import: "default",
      eager: true,
    }) as Record<string, string>,
  )[0];

  it("does not classify a record by its type or its topic", () => {
    for (const reDerivation of ['rule_type === "definition"', 'rule_type == "definition"']) {
      expect(filterSource).not.toContain(reDerivation);
      expect(queueSource).not.toContain(reDerivation);
    }
  });

  it("does not read the effect vocabulary, so it cannot hold a second opinion", () => {
    // recordStance is the one place that reads effect.type. A copy here would
    // be the drift that produced two renderings of one record.
    expect(filterSource).not.toContain('"informational"');
    expect(filterSource).not.toContain("recordStance");
  });

  it("offers no content lane or lens over the queue", () => {
    for (const gone of ["STANCE_LENSES", "stance-lens", "stanceFilter", "Glossary"]) {
      expect(queueSource).not.toContain(gone);
    }
  });

  it("keeps the record of why the lane went, so it is not rebuilt", () => {
    // The history is the point: the distinction was right and the level wrong,
    // and the measurement that settled it must outlive whoever read it.
    expect(filterSource).toContain("glossary-only");
    expect(queueSource).toContain("WHY THERE IS NO CONTENT-KIND LANE HERE ANY MORE");
  });

  it("passes only the two filters that are properties of a record", () => {
    const rules = [candidate("r1"), candidate("r2")];
    const cards = buildPolicyCards([policyOf(["r1", "r2"])], rules);
    const filters = {};
    const chosen = cardsAnsweringRuleFilters(
      cards,
      filters,
      candidateIdsAnsweringRuleFilters(rules, filters),
    );
    expect(chosen).toHaveLength(1);
    expect(chosen[0].rules).toHaveLength(2);
  });
});

describe("the note reconciling record counts with policy counts", () => {
  it("says nothing when no filter is narrowing anything", () => {
    expect(policySelectionNote(22, [])).toBeNull();
  });

  it("says nothing when the list is empty, leaving that to the empty state", () => {
    // Absent and empty are different, and the queue already describes empty.
    // A second sentence saying it is one more than a reader needs.
    expect(policySelectionNote(0, ["Approved"])).toBeNull();
  });

  it("names both units, so neither number has to be guessed", () => {
    const note = policySelectionNote(22, ["Needs review"]);
    expect(note).toContain("22 policies");
    expect(note).toContain("rule");
  });

  it("explains why a policy lists rules the filter did not select", () => {
    const note = policySelectionNote(4, ["Published"]) ?? "";
    expect(note).toContain("every rule of the policy");
    expect(note).toContain("did not select");
  });

  it("agrees with itself for a single policy", () => {
    const note = policySelectionNote(1, ["Rejected"]) ?? "";
    expect(note).toContain("1 policy ");
    expect(note).not.toContain("1 policies");
    expect(note).toContain("matches");
  });

  it("names every active filter, not just the first", () => {
    const note = policySelectionNote(3, ["Approved", "New"]) ?? "";
    expect(note).toContain("Approved");
    expect(note).toContain("New");
  });

  it("quotes the filter's own label rather than inflecting it into a sentence", () => {
    // Grammar built from a label breaks the moment a label is added. Quoting
    // sidesteps it, and keeps the label recognisably the control's word.
    const note = policySelectionNote(2, ["Changes requested"]) ?? "";
    expect(note).toContain("“Changes requested”");
  });

  it("frames a route as a route, never as a shortfall", () => {
    const note = policySelectionNote(9, ["Needs review", "Unchanged"]) ?? "";
    for (const banned of [
      "cannot",
      "can't",
      "unable",
      "fail",
      "not supported",
      "unsupported",
      "missing",
      "incomplete",
      "only",
      "limitation",
      "fallback",
    ]) {
      expect(note.toLowerCase()).not.toContain(banned);
    }
  });

  it("carries no vocabulary from any one document or domain", () => {
    const note = policySelectionNote(7, ["Approved"]) ?? "";
    for (const domain of ["employee", "policy set", "handbook", "clause", "HR", "leave"]) {
      expect(note.toLowerCase()).not.toContain(domain.toLowerCase());
    }
  });
});
