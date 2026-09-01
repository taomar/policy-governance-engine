/**
 * A CASE ASKS FOR INFORMATION, A VERDICT, OR BOTH.
 *
 * The state these tests exist for is the mixed one: a question that asks what
 * the policies state *and* how the case comes out, where the information track
 * answers and the verdict track is still waiting on a fact. That is a whole
 * reply, and the failure this file guards against is it being reduced to one
 * scalar — read as a failure because half of it is unanswered, or read as an
 * answer because half of it is. Each track is asserted separately, because that
 * is the only way to prove neither was folded into the other.
 *
 * The older single-branch replies are tested beside the new ones rather than
 * after them: this endpoint's old shape is still what an unmigrated server
 * returns, and a client that reads only the new one is a client that shows a
 * blank panel to anyone who has not deployed today.
 */
import { describe, expect, it } from "vitest";
import type { ProjectCaseAnswer, ProjectCaseEvaluation } from "../api";
import {
  NOT_EVALUATED,
  NOT_REQUESTED,
  NO_SECTION,
  missingInformationItems,
  readCaseTracks,
  readDiscovery,
  readLanguage,
  readRuleIndex,
  readRuleSlicing,
  representedRuleIds,
  ruleSelectionMethodFamily,
  trackProse,
  verificationRequirementItems,
} from "./projectCaseTracks";

function answerWith(
  evaluation: ProjectCaseEvaluation | null,
  overrides: Partial<ProjectCaseAnswer> = {},
): ProjectCaseAnswer {
  return {
    scope: "project",
    policy_set_key: "a-set",
    retrieval: { status: "narrowed", policies_considered: 2, policies_retained: 1, policies_discarded: 1 },
    considered: [],
    excluded: [],
    evaluation,
    size: { combined_chars: 100, budget_chars: 200000, oversize: false },
    ...overrides,
  };
}

const informationAnswered = {
  status: "answered",
  answer: "The policies state a weekly cap of forty hours. [rule-cap]",
  route: "informational",
  citations: [
    {
      rule_id: "rule-cap",
      policy: { provision_key: "hours", heading_path: ["Published", "Hours"] },
      source: { state: "quoted", text: "A week may not exceed forty hours.", page: 3, section: "7.1" },
    },
  ],
  note: "",
  grounding: { rules_available: 4, rules_cited: 1, policies_grounded: 1, fabricated_citations: [] },
};

const verdictNeedsFacts = {
  status: "missing_required_facts",
  verdict: "",
  answer: "The case cannot be decided until the hours actually worked are supplied.",
  route: "decision",
  missing_required_facts: ["hours worked in the week"],
  missing_information: [
    {
      fact: "hours_worked_in_week",
      label: "Hours worked in the week",
      why_needed: "The cap is measured over a week, so the total decides whether it was exceeded.",
      required_by_rule_ids: ["rule-cap"],
    },
  ],
  citations: [
    {
      rule_id: "rule-cap",
      policy: { provision_key: "hours", heading_path: ["Published", "Hours"] },
      source: { state: "quoted", text: "A week may not exceed forty hours.", page: 3, section: "7.1" },
    },
  ],
  note: "",
  grounding: { rules_available: 4, rules_cited: 1, policies_grounded: 1, fabricated_citations: [] },
};

describe("what a case was read as asking for", () => {
  it("reads an information-only case as one track asked and one never put", () => {
    const reading = readCaseTracks(
      answerWith({
        intent: "informational",
        information_requested: true,
        verdict_requested: false,
        classifier_version: "needs_v1",
        classification_reasoning: "The question asks what the policies say.",
        informational: informationAnswered,
        decision: null,
      }),
    );

    expect(reading.asked).toMatchObject({ information: true, verdict: false, declared: true });
    expect(reading.information.outcome).toBe("answered");
    expect(reading.information.answered).toBe(true);
    // Never asked for is not the same as asked for and refused, and it is not
    // the same as nothing having been evaluated.
    expect(reading.verdict.outcome).toBe(NOT_REQUESTED);
    expect(reading.verdict.requested).toBe(false);
    expect(reading.verdict.ran).toBe(false);
    expect(reading.verdict.section).toBeNull();
  });

  it("reads a verdict-only case the same way, from the other side", () => {
    const reading = readCaseTracks(
      answerWith({
        intent: "decision",
        information_requested: false,
        verdict_requested: true,
        classifier_version: "needs_v1",
        informational: null,
        decision: { ...verdictNeedsFacts, status: "answered", verdict: "not compliant", missing_required_facts: [], missing_information: [] },
      }),
    );

    expect(reading.asked).toMatchObject({ information: false, verdict: true });
    expect(reading.verdict.outcome).toBe("answered");
    expect(reading.verdict.answered).toBe(true);
    expect(reading.information.outcome).toBe(NOT_REQUESTED);
  });

  it("keeps both answers when a mixed case answers both", () => {
    const reading = readCaseTracks(
      answerWith({
        intent: "decision",
        information_requested: true,
        verdict_requested: true,
        classifier_version: "needs_v1",
        informational: informationAnswered,
        decision: {
          ...verdictNeedsFacts,
          status: "answered",
          verdict: "compliant",
          missing_required_facts: [],
          missing_information: [],
        },
      }),
    );

    expect(reading.information.answered).toBe(true);
    expect(reading.verdict.answered).toBe(true);
    // `intent` says `decision` for every mixed case. A reader that trusted it
    // alone would drop the information answer entirely.
    expect(reading.asked.information).toBe(true);
  });

  it("answers the information half while the verdict half still needs facts", () => {
    const reading = readCaseTracks(
      answerWith({
        intent: "decision",
        information_requested: true,
        verdict_requested: true,
        classifier_version: "needs_v1",
        informational: informationAnswered,
        decision: verdictNeedsFacts,
      }),
    );

    expect(reading.information.outcome).toBe("answered");
    expect(reading.information.answered).toBe(true);
    expect(reading.verdict.outcome).toBe("missing_required_facts");
    // The one thing that must never be true of this state: the verdict is not
    // reached, and no part of the reading claims it was.
    expect(reading.verdict.answered).toBe(false);
    expect(reading.verdict.section?.verdict ?? "").toBe("");
    // And the answered half is not degraded by the unanswered one.
    expect(trackProse(reading.information.section)).toContain("forty hours");
  });
});

describe("a case nothing was evaluated for", () => {
  it("reports both tracks as not evaluated rather than as silent policies", () => {
    const reading = readCaseTracks(
      answerWith(null, { retrieval: { status: "no_match", reason: "nothing bore on the question" } }),
    );

    expect(reading.evaluated).toBe(false);
    expect(reading.information.outcome).toBe(NOT_EVALUATED);
    expect(reading.verdict.outcome).toBe(NOT_EVALUATED);
    expect(reading.asked).toMatchObject({ information: false, verdict: false, classifierVersion: null });
    expect(reading.citations).toEqual([]);
  });

  it("tells a track that was asked for and returned nothing apart from one that failed", () => {
    const reading = readCaseTracks(
      answerWith({
        intent: "decision",
        information_requested: false,
        verdict_requested: true,
        informational: null,
        decision: null,
      }),
    );

    expect(reading.verdict.outcome).toBe(NO_SECTION);
    expect(reading.verdict.requested).toBe(true);
    expect(reading.verdict.known).toBe(false);
  });

  it("reports a failed track without disturbing the track that answered", () => {
    const reading = readCaseTracks(
      answerWith({
        information_requested: true,
        verdict_requested: true,
        informational: informationAnswered,
        decision: { status: "failed", verdict: "", answer: "", citations: [], note: "" },
      }),
    );

    expect(reading.verdict.outcome).toBe("failed");
    expect(reading.verdict.known).toBe(true);
    expect(reading.information.answered).toBe(true);
  });
});

describe("the evidence a two-track answer rests on", () => {
  it("lists a rule both tracks cited once, carrying both tags", () => {
    const reading = readCaseTracks(
      answerWith({
        information_requested: true,
        verdict_requested: true,
        informational: informationAnswered,
        decision: verdictNeedsFacts,
      }),
    );

    expect(reading.citations).toHaveLength(1);
    expect(reading.citations[0].rule_id).toBe("rule-cap");
    expect(reading.citations[0].serves).toEqual(["information", "verdict"]);
    // The verbatim sentence survives the merge; it is the document's, and does
    // not change with which gather reached for it.
    expect(reading.citations[0].source?.text).toBe("A week may not exceed forty hours.");
  });

  it("tags a rule only one track cited with only that track", () => {
    const reading = readCaseTracks(
      answerWith({
        information_requested: true,
        verdict_requested: true,
        informational: informationAnswered,
        decision: {
          ...verdictNeedsFacts,
          citations: [{ rule_id: "rule-other", policy: { provision_key: "other" }, source: { state: "no_citation" } }],
        },
      }),
    );

    expect(reading.citations.map((citation) => [citation.rule_id, citation.serves])).toEqual([
      ["rule-cap", ["information"]],
      ["rule-other", ["verdict"]],
    ]);
  });

  it("believes a citation that already names the tracks it serves", () => {
    const reading = readCaseTracks(
      answerWith({
        information_requested: true,
        verdict_requested: false,
        informational: {
          ...informationAnswered,
          citations: [{ rule_id: "rule-cap", serves: ["information", "verdict"] }],
        },
      }),
    );

    expect(reading.citations[0].serves).toEqual(["information", "verdict"]);
  });

  it("names the rules a blocked verdict is waiting on alongside the cited ones", () => {
    const reading = readCaseTracks(
      answerWith({
        information_requested: false,
        verdict_requested: true,
        decision: {
          ...verdictNeedsFacts,
          citations: [],
          missing_information: [
            { fact: "hours", label: "Hours", why_needed: "", required_by_rule_ids: ["rule-waiting"] },
          ],
        },
      }),
    );

    expect(reading.ruleIds).toContain("rule-waiting");
  });
});

describe("the facts a verdict is waiting on", () => {
  it("carries the label, the reason and the rules waiting for each fact", () => {
    const items = missingInformationItems(verdictNeedsFacts);
    expect(items).toEqual([
      {
        fact: "hours_worked_in_week",
        label: "Hours worked in the week",
        whyNeeded: "The cap is measured over a week, so the total decides whether it was exceeded.",
        requiredByRuleIds: ["rule-cap"],
      },
    ]);
  });

  it("still names the facts when only the flat list arrived", () => {
    const items = missingInformationItems({
      status: "missing_required_facts",
      missing_required_facts: ["employee category", "date of hire"],
    });
    expect(items.map((item) => item.label)).toEqual(["employee category", "date of hire"]);
    expect(items.every((item) => item.whyNeeded === "")).toBe(true);
  });
});

describe("the checks a reached verdict is qualified by", () => {
  const verdictWithChecks = {
    status: "answered",
    verdict: "Entitled",
    answer: "The records confer the entitlement.",
    route: "decision",
    missing_required_facts: [],
    missing_information: [],
    verification_requirements: [
      {
        fact: "accrued_balance_on_the_day",
        label: "The balance standing on the day",
        why_needed: "The entitlement is owed; the days come out of a balance that has accrued.",
        required_by_rule_ids: ["rule-cap"],
      },
    ],
    citations: [],
    note: "",
    grounding: { rules_available: 4, rules_cited: 1, policies_grounded: 1, fabricated_citations: [] },
  };

  it("carries the label, what to confirm and the rules that impose it", () => {
    expect(verificationRequirementItems(verdictWithChecks)).toEqual([
      {
        fact: "accrued_balance_on_the_day",
        label: "The balance standing on the day",
        whyNeeded: "The entitlement is owed; the days come out of a balance that has accrued.",
        requiredByRuleIds: ["rule-cap"],
      },
    ]);
  });

  it("reads nothing from a section that reached no verdict", () => {
    // A condition on acting is meaningless where nothing is permitted yet, so a
    // reply that carried one on a blocked section is ignored rather than shown
    // beside the facts that block it.
    expect(
      verificationRequirementItems({
        ...verdictNeedsFacts,
        verification_requirements: verdictWithChecks.verification_requirements,
      }),
    ).toEqual([]);
  });

  it("reads nothing from an absent section", () => {
    expect(verificationRequirementItems(null)).toEqual([]);
  });

  it("falls back to the key when no label was composed, and never invents a reason", () => {
    const items = verificationRequirementItems({
      status: "answered",
      verification_requirements: [{ fact: "roster_cover", required_by_rule_ids: [] }],
    });
    expect(items).toEqual([
      { fact: "roster_cover", label: "roster_cover", whyNeeded: "", requiredByRuleIds: [] },
    ]);
  });

  it("counts a rule that imposes a check as evidence the case rests on", () => {
    const reading = readCaseTracks(
      answerWith({
        intent: "decision",
        informational: null,
        decision: verdictWithChecks,
      }),
    );
    expect(reading.ruleIds).toContain("rule-cap");
  });
});

describe("an answer from a server that has not moved to two tracks", () => {
  it("reads a single informational branch as information asked for and no verdict put", () => {
    const reading = readCaseTracks(
      answerWith({ intent: "informational", informational: informationAnswered, decision: null }),
    );

    expect(reading.asked).toMatchObject({ information: true, verdict: false, declared: false });
    expect(reading.information.answered).toBe(true);
    expect(reading.verdict.outcome).toBe(NOT_REQUESTED);
  });

  it("reads a determination flattened onto the evaluation as the verdict track", () => {
    const reading = readCaseTracks(
      answerWith({
        intent: "decision",
        status: "answered",
        verdict: "not compliant",
        answer: "The rule prohibits it.",
        citations: [{ rule_id: "rule-old" }],
      }),
    );

    expect(reading.verdict.outcome).toBe("answered");
    expect(reading.verdict.section?.verdict).toBe("not compliant");
    expect(reading.citations.map((citation) => citation.rule_id)).toEqual(["rule-old"]);
    expect(reading.information.outcome).toBe(NOT_REQUESTED);
  });

  it("never reads a flattened informational answer as a verdict", () => {
    // The flat shape has no field saying which branch it is. Reading it as a
    // determination would manufacture a verdict out of a reply that reached
    // none, which is the one mistake this surface may not make.
    const reading = readCaseTracks(
      answerWith({ intent: "informational", status: "answered", answer: "What the policies state." }),
    );

    expect(reading.verdict.outcome).toBe(NOT_REQUESTED);
    expect(reading.verdict.section).toBeNull();
  });
});

describe("the narrowing that happens to the policies search kept", () => {
  it("says nothing when no policy was sliced and none was set aside for size", () => {
    expect(
      readRuleSlicing(
        answerWith(null, {
          considered: [
            { provision_id: "a", provision_key: "a", heading_path: ["A"], rules: 4, retained: true },
          ],
        }),
      ),
    ).toBeNull();
  });

  it("discloses a policy of more than fifteen rules read rule by rule", () => {
    const slicing = readRuleSlicing(
      answerWith(null, {
        retrieval: {
          status: "narrowed",
          large_policy_rule_threshold: 15,
          selected_rule_budget: 15,
          policies_rule_sliced: 1,
          payload_budget_chars: 120000,
          policies_over_payload_budget: 0,
        },
        considered: [
          {
            provision_id: "big",
            provision_key: "big-table",
            heading_path: ["Published", "Allowances"],
            rules: 74,
            retained: true,
            rule_selection: {
              total_rules: 74,
              selected_rules: 8,
              rules_discarded: 66,
              selected_rule_ids: ["r1", "r2"],
              method: "scenario_relevance_v2",
              sliced: true,
            },
          },
          { provision_id: "small", provision_key: "small", heading_path: ["Small"], rules: 3, retained: true },
        ],
      }),
    );

    expect(slicing).not.toBeNull();
    expect(slicing?.slicedCount).toBe(1);
    expect(slicing?.threshold).toBe(15);
    expect(slicing?.ruleBudget).toBe(15);
    expect(slicing?.policies).toHaveLength(1);
    expect(slicing?.policies[0].selection.selected_rules).toBe(8);
  });

  it("counts a slice the retrieval block did not total, from the policies themselves", () => {
    const slicing = readRuleSlicing(
      answerWith(null, {
        retrieval: { status: "narrowed" },
        considered: [
          {
            provision_id: "big",
            provision_key: "big",
            heading_path: ["Big"],
            rules: 40,
            retained: true,
            rule_selection: { total_rules: 40, selected_rules: 12 },
          },
        ],
      }),
    );

    expect(slicing?.slicedCount).toBe(1);
    expect(slicing?.threshold).toBeNull();
  });

  it("reports a policy set aside for size apart from one discarded for relevance", () => {
    const slicing = readRuleSlicing(
      answerWith(null, {
        retrieval: { status: "narrowed", policies_over_payload_budget: 1, payload_budget_chars: 120000 },
        considered: [
          {
            provision_id: "huge",
            provision_key: "huge",
            heading_path: ["Huge"],
            rules: 9,
            retained: false,
            discard_reason: "outside_payload_budget",
          },
        ],
      }),
    );

    expect(slicing?.overPayloadBudget).toBe(1);
    expect(slicing?.slicedCount).toBe(0);
  });
});

/**
 * AN EXACT COPY AND A NEAR-COPY ARE NOT THE SAME FINDING.
 *
 * A policy collapsed as a *duplicate* was proven to govern identically to one
 * already retrieved, and its terms reached the gather through that record. A
 * policy *deferred for diversity* was proven nothing of the sort: it merely
 * required the same thing as a higher-ranked policy, it kept its own rank and
 * score, and its terms were not read at all.
 *
 * Told as one number, the interface either claims a distinct policy was read
 * when it was not, or reports the corpus as holding one policy where it holds
 * two copies of one. So the two counts are read from two fields, neither is
 * derived from the other, and these tests assert they stay apart.
 */
describe("collapsed duplicates and diversity-deferred near-copies", () => {
  it("keeps the two counts apart and never sums them", () => {
    const slicing = readRuleSlicing(
      answerWith(null, {
        retrieval: {
          status: "narrowed",
          policy_selection_order: "relevance_then_normative_content_v1",
          policies_duplicate_collapsed: 1,
          policies_diversity_deferred: 2,
          policies_discarded: 3,
        },
        considered: [
          {
            provision_id: "copy",
            provision_key: "leave-policy-copy",
            heading_path: ["Published", "Leave (copy)"],
            rules: 5,
            retained: false,
            discard_reason: "duplicate_policy_content",
            duplicate_of_provision_key: "leave-policy",
          },
          {
            provision_id: "near",
            provision_key: "near-copy",
            heading_path: ["Published", "Near"],
            rules: 5,
            retained: false,
            best_rank: 2,
            best_score: 0.71,
            discard_reason: "outside_budget",
          },
        ],
      }),
    );

    expect(slicing?.duplicateCollapsed).toBe(1);
    expect(slicing?.diversityDeferred).toBe(2);
    expect(slicing?.selectionOrder).toBe("relevance_then_normative_content_v1");
    // The deferred policy is not listed as a duplicate: it names no
    // representative, because there is none to name.
    expect(slicing?.duplicatePolicies.map((entry) => entry.policy.provision_key)).toEqual(["leave-policy-copy"]);
    expect(slicing?.duplicatePolicies[0].representative).toBe("leave-policy");
  });

  it("never infers a deferral, because a deferred policy looks like any other discard", () => {
    // A deferred policy carries the ordinary `outside_budget` reason. Guessing
    // at the count from the candidate list would be inventing the finding.
    const slicing = readRuleSlicing(
      answerWith(null, {
        retrieval: { status: "narrowed", policies_duplicate_collapsed: 1 },
        considered: [
          {
            provision_id: "copy",
            provision_key: "copy",
            heading_path: ["Copy"],
            rules: 2,
            retained: false,
            discard_reason: "duplicate_policy_content",
            duplicate_of_provision_key: "original",
          },
          {
            provision_id: "other",
            provision_key: "other",
            heading_path: ["Other"],
            rules: 2,
            retained: false,
            discard_reason: "outside_budget",
          },
        ],
      }),
    );

    expect(slicing?.diversityDeferred).toBe(0);
    expect(slicing?.duplicateCollapsed).toBe(1);
  });

  it("counts a collapse the retrieval block did not total, from the policies that name a representative", () => {
    const slicing = readRuleSlicing(
      answerWith(null, {
        retrieval: { status: "narrowed" },
        considered: [
          {
            provision_id: "copy",
            provision_key: "copy",
            heading_path: ["Copy"],
            rules: 2,
            retained: false,
            discard_reason: "duplicate_policy_content",
            duplicate_of_provision_key: "original",
          },
        ],
      }),
    );

    expect(slicing?.duplicateCollapsed).toBe(1);
    expect(slicing?.diversityDeferred).toBe(0);
  });

  it("will not read a policy discarded for another reason as a collapsed copy", () => {
    const slicing = readRuleSlicing(
      answerWith(null, {
        retrieval: { status: "narrowed", policies_over_payload_budget: 1 },
        considered: [
          {
            provision_id: "huge",
            provision_key: "huge",
            heading_path: ["Huge"],
            rules: 9,
            retained: false,
            discard_reason: "outside_payload_budget",
            duplicate_of_provision_key: "something",
          },
        ],
      }),
    );

    expect(slicing?.duplicatePolicies).toEqual([]);
    expect(slicing?.duplicateCollapsed).toBe(0);
  });

  it("totals the exact rule copies a sliced policy stood in for, and names them", () => {
    const slicing = readRuleSlicing(
      answerWith(null, {
        retrieval: { status: "narrowed", policies_rule_sliced: 1, large_policy_rule_threshold: 15 },
        considered: [
          {
            provision_id: "big",
            provision_key: "big",
            heading_path: ["Big"],
            rules: 74,
            retained: true,
            rule_selection: {
              total_rules: 74,
              selected_rules: 8,
              rules_discarded: 66,
              duplicate_rules_collapsed: 3,
              represented_rule_ids: ["r-40", "r-41", "r-42"],
              method: "scenario_relevance_v2",
              sliced: true,
            },
          },
        ],
      }),
    );

    expect(slicing?.duplicateRulesCollapsed).toBe(3);
    expect(representedRuleIds(slicing?.policies[0].selection)).toEqual(["r-40", "r-41", "r-42"]);
    // The represented rules are part of the unselected count, not a separate
    // pool beside it, and are never counted as read.
    expect(slicing?.policies[0].selection.rules_discarded).toBe(66);
    expect(slicing?.policies[0].selection.selected_rules).toBe(8);
  });

  it("reports no represented rules when the server named none", () => {
    expect(representedRuleIds(undefined)).toEqual([]);
    expect(representedRuleIds({ total_rules: 3, selected_rules: 3 })).toEqual([]);
  });
});

/**
 * A SELECTION METHOD IS A FAMILY, NOT A LITERAL.
 *
 * The contract says the version suffix moves when the selection algorithm
 * changes, so a stored receipt names the algorithm that produced it. A client
 * that pinned the literal it was written against would not fail loudly on the
 * next change — it would quietly print `Scenario Relevance V3` at a reviewer,
 * which looks like a working interface and is not one. The backend has already
 * moved once, from `_v1` to `_v2`, which is exactly the event these tests are
 * written for.
 */
describe("how a policy's rules were chosen, across versions of the algorithm", () => {
  it("recognises the relevance family at the version the server emits today", () => {
    expect(ruleSelectionMethodFamily("scenario_relevance_v2")).toBe("scenario_relevance");
  });

  it("recognises the version it was written against, and versions not yet written", () => {
    // A receipt stored under the older algorithm is still read back, and a
    // future one must not need a client release to be described.
    expect(ruleSelectionMethodFamily("scenario_relevance_v1")).toBe("scenario_relevance");
    expect(ruleSelectionMethodFamily("scenario_relevance_v3")).toBe("scenario_relevance");
    expect(ruleSelectionMethodFamily("scenario_relevance_v17")).toBe("scenario_relevance");
  });

  it("recognises the unversioned families as themselves", () => {
    expect(ruleSelectionMethodFamily("whole_policy")).toBe("whole_policy");
    expect(ruleSelectionMethodFamily("document_order")).toBe("document_order");
    // And would keep recognising them if they ever acquired a version.
    expect(ruleSelectionMethodFamily("whole_policy_v2")).toBe("whole_policy");
    expect(ruleSelectionMethodFamily("document_order_v4")).toBe("document_order");
  });

  it("claims nothing about an algorithm it has never heard of", () => {
    // Stripping a suffix must not become a licence to guess. A method outside
    // the known families comes back null so the interface shows its name rather
    // than describing, in confident words, something it cannot know.
    expect(ruleSelectionMethodFamily("scenario_relevance_experimental")).toBeNull();
    expect(ruleSelectionMethodFamily("semantic_rerank_v1")).toBeNull();
    expect(ruleSelectionMethodFamily("relevance")).toBeNull();
    expect(ruleSelectionMethodFamily("")).toBeNull();
    expect(ruleSelectionMethodFamily(null)).toBeNull();
    expect(ruleSelectionMethodFamily(undefined)).toBeNull();
  });

  it("tells the rule index taking part from the same selection run without it", () => {
    // `hybrid_rule_v1` means the rule index's own ranking was fused in.
    // `scenario_relevance_v3` is that same selection after the index's query
    // failed recoverably, and `_v2` is it never being consulted. One family
    // each: "the index placed these" and "the index could not" are different
    // accounts of the same list of rules.
    expect(ruleSelectionMethodFamily("hybrid_rule_v1")).toBe("hybrid_rule");
    expect(ruleSelectionMethodFamily("hybrid_rule_v2")).toBe("hybrid_rule");
    expect(ruleSelectionMethodFamily("scenario_relevance_v3")).toBe("scenario_relevance");
    expect(ruleSelectionMethodFamily("hybrid_rule")).toBe("hybrid_rule");
  });

  it("strips only a numeric version suffix", () => {
    // `_vNext` is not a version this rule understands, and pretending it is
    // would map an unknown algorithm onto a known description.
    expect(ruleSelectionMethodFamily("scenario_relevance_vNext")).toBeNull();
    expect(ruleSelectionMethodFamily("scenario_relevance_v")).toBeNull();
  });
});

describe("the rest of the narrowing reading", () => {
  it("stays silent for a reply that carries none of the newer narrowing fields", () => {
    // An older v2 reply, or a v1 replay, has no selection order, no duplicate
    // count and no deferral count. The reading must be the same silence it was
    // before those fields existed, not a row of zeroes implying the narrowings
    // were checked and found empty.
    expect(
      readRuleSlicing(
        answerWith(null, {
          retrieval: { status: "narrowed", policies_considered: 2, policies_retained: 1, policies_discarded: 1 },
          considered: [
            { provision_id: "a", provision_key: "a", heading_path: ["A"], rules: 4, retained: true },
            {
              provision_id: "b",
              provision_key: "b",
              heading_path: ["B"],
              rules: 2,
              retained: false,
              discard_reason: "outside_budget",
            },
          ],
        }),
      ),
    ).toBeNull();
  });
});

/**
 * WHAT THE SEARCH REACHED, AND IN WHICH LANGUAGE.
 *
 * Three readings, and all three share one rule: absence is not zero. A reply
 * that says nothing about the rule index, about what the search matched, or
 * about the language boundary produces `null` rather than a row of zeroes,
 * because a zero here is a claim about a question that was actually put. The
 * older servers that say nothing are the whole reason the rule matters.
 */
describe("what the discovery search reached", () => {
  it("reads the two document counts, the scan and what rule-level retrieval did", () => {
    const discovery = readDiscovery({
      status: "narrowed",
      policy_documents_matched: 4,
      rule_documents_matched: 11,
      rule_scan: 120,
      policies_elevated_by_rule: 2,
      rule_index_state: "matched",
      projection_profile: "policy-english-projection-v1",
      projection_ready: true,
    });

    expect(discovery).toMatchObject({
      policyDocuments: 4,
      ruleDocuments: 11,
      ruleScan: 120,
      elevatedByRule: 2,
      ruleIndexState: "matched",
      projectionProfile: "policy-english-projection-v1",
      projectionReady: true,
    });
  });

  it("keeps zero elevations as an answer rather than as silence", () => {
    // Rule-level retrieval ran and raised nothing. That is a finding about this
    // question, and it is not the same as a reply that never mentioned it.
    expect(readDiscovery({ status: "narrowed", policies_elevated_by_rule: 0 })?.elevatedByRule).toBe(0);
  });

  it("says nothing at all when the reply said nothing", () => {
    expect(readDiscovery({ status: "narrowed", policies_considered: 3 })).toBeNull();
    expect(readDiscovery({ status: "bypassed", reason: "single policy chosen" })).toBeNull();
  });

  it("carries the discovery into the narrowing disclosure, so an index-only reply still discloses", () => {
    const slicing = readRuleSlicing(
      answerWith(null, {
        retrieval: { status: "narrowed", rule_index_state: "degraded", policies_elevated_by_rule: 0 },
        considered: [{ provision_id: "a", provision_key: "a", heading_path: ["A"], rules: 3, retained: true }],
      }),
    );

    expect(slicing?.discovery?.ruleIndexState).toBe("degraded");
    expect(slicing?.slicedCount).toBe(0);
  });
});

describe("how one policy's rules were placed", () => {
  it("reads every rank apart, and the quota and unprojected rules with them", () => {
    const reading = readRuleIndex({
      total_rules: 74,
      selected_rules: 8,
      rule_index_state: "matched",
      rule_index_hits: 6,
      lexical_candidates: 12,
      quantity_candidates: 3,
      fused_candidates: 15,
      evidence_diversity_quota: 4,
      rules_without_projection: 2,
    });

    expect(reading).toMatchObject({
      state: "matched",
      known: true,
      hits: 6,
      lexical: 12,
      quantity: 3,
      fused: 15,
      evidenceQuota: 4,
      withoutProjection: 2,
    });
  });

  it("keeps an index that placed nothing apart from one that was never asked", () => {
    // Both would render as "0" to a surface that only counted. They are not the
    // same fact: one is an answer, the other is a question never put.
    const asked = readRuleIndex({
      total_rules: 20,
      selected_rules: 5,
      rule_index_state: "matched",
      rule_index_hits: 0,
    });
    const notAsked = readRuleIndex({ total_rules: 20, selected_rules: 5, rule_index_state: "unavailable" });

    expect(asked).toMatchObject({ state: "matched", hits: 0 });
    expect(notAsked).toMatchObject({ state: "unavailable", hits: null });
  });

  it("knows the three states it can describe, and admits when it meets another", () => {
    expect(readRuleIndex({ total_rules: 1, selected_rules: 1, rule_index_state: "degraded" })?.known).toBe(true);
    expect(readRuleIndex({ total_rules: 1, selected_rules: 1, rule_index_state: "wedged" })?.known).toBe(false);
  });

  it("says nothing for a selection from a server that reports none of it", () => {
    expect(
      readRuleIndex({ total_rules: 20, selected_rules: 5, method: "scenario_relevance_v2", sliced: true }),
    ).toBeNull();
    expect(readRuleIndex(null)).toBeNull();
    expect(readRuleIndex(undefined)).toBeNull();
  });
});

describe("which language the case was read and answered in", () => {
  it("reports a question that was carried into the processing language", () => {
    const reading = readLanguage(
      answerWith(null, {
        language: {
          source_language: "ar",
          processing_language: "en",
          response_language: "ar",
          boundary_state: "rendered",
          output_rendering_state: "rendered",
          guidance_rendering_state: "not_required",
          input_translation_profile: "case-language-v4",
          output_translation_profile: "case-language-v4",
          processing_scenario: "May a worker exceed the weekly cap?",
          processing_scenario_hash: "sha256:abc",
          projection_profile: "policy-english-projection-v1",
        },
      }),
    );

    expect(reading).toMatchObject({
      reported: true,
      questionRendered: true,
      answerRendered: true,
      guidanceDropped: false,
      sourceLanguage: "ar",
      processingLanguage: "en",
      responseLanguage: "ar",
      processingScenario: "May a worker exceed the weekly cap?",
      projectionProfile: "policy-english-projection-v1",
    });
  });

  it("reports an identity crossing as no rendering having happened", () => {
    // An English question to an English pipeline. The words on screen are the
    // words that were read, and there is nothing for a reader to reconcile.
    const reading = readLanguage(
      answerWith(null, {
        language: {
          source_language: "en",
          processing_language: "en",
          response_language: "en",
          boundary_state: "identity",
          output_rendering_state: "not_required",
          guidance_rendering_state: "not_required",
          input_translation_profile: "case-language-v4",
          processing_scenario: "What is the weekly cap?",
        },
      }),
    );

    expect(reading).toMatchObject({ questionRendered: false, answerRendered: false, guidanceDropped: false });
    expect(reading?.reported).toBe(true);
  });

  it("reports guidance that was dropped rather than applied un-rendered", () => {
    const reading = readLanguage(
      answerWith(null, {
        language: {
          source_language: "fr",
          processing_language: "en",
          response_language: "fr",
          boundary_state: "rendered",
          output_rendering_state: "rendered",
          guidance_rendering_state: "unrendered_dropped",
          input_translation_profile: "case-language-v4",
          processing_scenario: "Anything on parking?",
        },
      }),
    );

    expect(reading?.guidanceDropped).toBe(true);
  });

  it("says nothing for an answer produced before the boundary existed", () => {
    // Absent is not "the boundary reported nothing"; the two must stay
    // distinguishable, and only one of them is silence.
    expect(readLanguage(answerWith(null))).toBeNull();
    expect(readLanguage(answerWith(null, { language: null }))).toBeNull();
  });
});
