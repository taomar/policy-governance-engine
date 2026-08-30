/**
 * TESTING A CASE IN THE PRODUCT, WHEN THE CASE ASKS FOR TWO THINGS.
 *
 * These render the dialog a reviewer actually uses, against the replies the
 * server actually sends. The state they exist for is the mixed one: the
 * information track answers, the verdict track is still waiting on a fact, and
 * both are true at once. A surface that collapses that into one status can only
 * show it as a failure or as an answer, and both are lies about what the
 * policies said.
 *
 * `ProjectCaseRunner.test.tsx` keeps the single-branch replies this endpoint
 * has always returned, and keeps passing unchanged — that file is the guard
 * that this redesign did not quietly require a new server.
 */
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { ProjectCaseRunner } from "./ProjectCaseRunner";
import { api, PolicyPlatformApiError, type ProjectCaseAnswer } from "../api";

beforeAll(() => {
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  );
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  );
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const CAP_CITATION = {
  rule_id: "rule-cap",
  policy: { provision_key: "hours", heading_path: ["Published", "Working hours"] },
  source: { state: "quoted", text: "A week may not exceed forty hours.", page: 3, section: "7.1" },
};

const INFORMATION_ANSWERED = {
  status: "answered",
  answer: "The published policies cap a working week at forty hours. [rule-cap]",
  route: "informational",
  citations: [CAP_CITATION],
  note: "",
  grounding: { rules_available: 4, rules_cited: 1, policies_grounded: 1, fabricated_citations: [] },
};

function projectAnswer(evaluation: ProjectCaseAnswer["evaluation"]): ProjectCaseAnswer {
  return {
    scope: "project",
    policy_set_key: "a-set",
    retrieval: {
      status: "narrowed",
      method: "hybrid_vector_topk",
      policies_considered: 2,
      policies_retained: 1,
      policies_discarded: 1,
    },
    considered: [
      {
        provision_id: "hours-id",
        provision_key: "hours",
        heading_path: ["Published", "Working hours"],
        rules: 4,
        retained: true,
      },
      {
        provision_id: "other-id",
        provision_key: "other",
        heading_path: ["Published", "Other"],
        rules: 2,
        retained: false,
        discard_reason: "outside_budget",
      },
    ],
    excluded: [],
    evaluation,
    size: { combined_chars: 1200, budget_chars: 200000, oversize: false },
  };
}

async function runCase(answer: ProjectCaseAnswer, scenario: string) {
  vi.spyOn(api, "answerProjectCase").mockResolvedValue(answer);
  render(<ProjectCaseRunner policySetKey="a-set" open onClose={() => {}} />);
  fireEvent.change(screen.getByTestId("project-case-scenario"), { target: { value: scenario } });
  fireEvent.click(screen.getByTestId("project-case-run"));
  return await screen.findByTestId("project-case-tracks");
}

describe("a case that asks only what the policies state", () => {
  it("answers the information track and says plainly that no verdict was asked for", async () => {
    await runCase(
      projectAnswer({
        intent: "informational",
        information_requested: true,
        verdict_requested: false,
        classifier_version: "case_needs_v1",
        classification_reasoning: "The question asks what the policies say, not how a case comes out.",
        informational: INFORMATION_ANSWERED,
        decision: null,
      }),
      "What is the weekly cap?",
    );

    expect(screen.getByTestId("project-case-asked-information").textContent).toBe("What the policies state");
    expect(screen.getByTestId("project-case-asked-verdict").textContent).toBe("Not: a verdict on the case");
    expect(screen.getByText(/asks what the policies say, not how a case comes out/i)).toBeTruthy();
    expect(screen.getByText("The published policies cap a working week at forty hours. [rule-cap]")).toBeTruthy();

    const verdict = screen.getByTestId("project-case-verdict-track");
    expect(within(verdict).getByText("Not asked for")).toBeTruthy();
    expect(verdict.getAttribute("data-outcome")).toBe("not_requested");
    expect(within(verdict).getByText(/did not ask for a verdict/i)).toBeTruthy();
    // A track nobody asked for never shows a determination, and the words say
    // it is the question's shape rather than a refusal by the policies.
    expect(screen.queryByTestId("project-case-verdict")).toBeNull();
    expect(within(verdict).getByText(/not a refusal by the policies/i)).toBeTruthy();
  });
});

describe("a case that asks only for a verdict", () => {
  it("shows the determination and says the information track was not put", async () => {
    await runCase(
      projectAnswer({
        intent: "decision",
        information_requested: false,
        verdict_requested: true,
        classifier_version: "case_needs_v1",
        informational: null,
        decision: {
          status: "answered",
          verdict: "not compliant",
          answer: "Fifty hours exceeds the forty-hour cap. [rule-cap]",
          route: "decision",
          missing_required_facts: [],
          missing_information: [],
          citations: [CAP_CITATION],
          note: "",
          grounding: { rules_available: 4, rules_cited: 1, policies_grounded: 1, fabricated_citations: [] },
        },
      }),
      "I worked fifty hours; was that within the cap?",
    );

    expect(screen.getByTestId("project-case-verdict").textContent).toContain("not compliant");
    expect(screen.getByText("Fifty hours exceeds the forty-hour cap. [rule-cap]")).toBeTruthy();
    expect(screen.getByText(/The decision above came from the evaluator/i)).toBeTruthy();

    const information = screen.getByTestId("project-case-information-track");
    expect(within(information).getByText("Not asked for")).toBeTruthy();
    expect(information.getAttribute("data-outcome")).toBe("not_requested");
  });
});

describe("a mixed case both tracks answer", () => {
  it("shows two answers, and names the rule they share once", async () => {
    await runCase(
      projectAnswer({
        intent: "decision",
        information_requested: true,
        verdict_requested: true,
        classifier_version: "case_needs_v1",
        reasoning_effort: "medium",
        informational: INFORMATION_ANSWERED,
        decision: {
          status: "answered",
          verdict: "compliant",
          answer: "Thirty hours is within the forty-hour cap. [rule-cap]",
          route: "decision",
          missing_required_facts: [],
          missing_information: [],
          citations: [CAP_CITATION],
          note: "",
          grounding: { rules_available: 4, rules_cited: 1, policies_grounded: 1, fabricated_citations: [] },
        },
      }),
      "What is the cap, and was my thirty-hour week within it?",
    );

    expect(screen.getByTestId("project-case-asked-information").textContent).toBe("What the policies state");
    expect(screen.getByTestId("project-case-asked-verdict").textContent).toBe("A verdict on the case");
    expect(screen.getByTestId("project-case-mixed-note").textContent).toMatch(/each is answered on its own/i);

    expect(screen.getByTestId("project-case-verdict").textContent).toContain("compliant");
    expect(screen.getByText("The published policies cap a working week at forty hours. [rule-cap]")).toBeTruthy();
    expect(screen.getByText("Thirty hours is within the forty-hour cap. [rule-cap]")).toBeTruthy();

    // One rule, cited by both, listed once and tagged twice.
    const evidence = screen.getByTestId("project-case-evidence");
    expect(within(evidence).getByText("Cited for Information")).toBeTruthy();
    expect(within(evidence).getByText("Cited for Verdict")).toBeTruthy();
    expect(within(evidence).getAllByText("rule-cap")).toHaveLength(1);
    expect(within(evidence).getByText(/cited by both tracks and is listed once/i)).toBeTruthy();

    // Each track keeps its own raw section; neither is the other's.
    expect(screen.getAllByText("Show raw response")).toHaveLength(2);
    expect(screen.getByTestId("project-case-trace").textContent).toContain("case_needs_v1");
  });
});

describe("a mixed case answered on information while the verdict still needs facts", () => {
  it("keeps both halves whole instead of collapsing them into one status", async () => {
    await runCase(
      projectAnswer({
        intent: "decision",
        information_requested: true,
        verdict_requested: true,
        classifier_version: "case_needs_v1",
        classification_reasoning: "The question asks what the cap is and whether a particular week was within it.",
        informational: INFORMATION_ANSWERED,
        decision: {
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
          citations: [CAP_CITATION],
          note: "",
          grounding: { rules_available: 4, rules_cited: 1, policies_grounded: 1, fabricated_citations: [] },
        },
      }),
      "What is the cap, and was my week within it?",
    );

    // The information half is answered, and stays answered.
    const information = screen.getByTestId("project-case-information-track");
    expect(information.getAttribute("data-outcome")).toBe("answered");
    expect(within(information).getByText("Answered")).toBeTruthy();
    expect(screen.getByText("The published policies cap a working week at forty hours. [rule-cap]")).toBeTruthy();

    // The verdict half is not reached, and nothing pretends otherwise.
    const verdict = screen.getByTestId("project-case-verdict-track");
    expect(verdict.getAttribute("data-outcome")).toBe("missing_required_facts");
    expect(within(verdict).getByText("Needs facts")).toBeTruthy();
    expect(screen.queryByTestId("project-case-verdict")).toBeNull();
    expect(within(verdict).getByText(/It is not a verdict/i)).toBeTruthy();

    // And the fact it is waiting on is something a form could be built from.
    const missing = screen.getByTestId("project-case-missing-facts");
    expect(missing.textContent).toContain("Hours worked in the week");
    expect(missing.textContent).toContain("The cap is measured over a week");
    expect(missing.textContent).toContain("rule-cap");
  });
});

describe("a case nothing was evaluated for", () => {
  it("says nothing was evaluated rather than that the policies said nothing", async () => {
    vi.spyOn(api, "answerProjectCase").mockResolvedValue({
      scope: "project",
      policy_set_key: "a-set",
      retrieval: { status: "no_match", reason: "No published policy bears on this question." },
      considered: [],
      excluded: [],
      evaluation: null,
      size: { combined_chars: 0, budget_chars: 200000, oversize: false },
    });

    render(<ProjectCaseRunner policySetKey="a-set" open onClose={() => {}} />);
    fireEvent.change(screen.getByTestId("project-case-scenario"), { target: { value: "Anything on parking?" } });
    fireEvent.click(screen.getByTestId("project-case-run"));

    await screen.findByTestId("project-case-tracks");
    expect(screen.getByTestId("project-case-asked").textContent).toMatch(/never classified/i);
    const verdict = screen.getByTestId("project-case-verdict-track");
    const information = screen.getByTestId("project-case-information-track");
    expect(within(verdict).getByText("Nothing evaluated")).toBeTruthy();
    expect(within(information).getByText("Nothing evaluated")).toBeTruthy();
    expect(within(verdict).getByText(/not the policies saying nothing bears/i)).toBeTruthy();
    expect(screen.queryByTestId("project-case-verdict")).toBeNull();
    expect(screen.queryByTestId("project-case-evidence")).toBeNull();
  });

  it("shows a track that was asked for and answered nothing as exactly that", async () => {
    await runCase(
      projectAnswer({
        intent: "decision",
        information_requested: false,
        verdict_requested: true,
        classifier_version: "case_needs_v1",
        informational: null,
        decision: null,
      }),
      "Was this allowed?",
    );

    const verdict = screen.getByTestId("project-case-verdict-track");
    expect(within(verdict).getByText("Nothing returned")).toBeTruthy();
    expect(within(verdict).getByText(/no verdict section was returned/i)).toBeTruthy();
    expect(screen.queryByTestId("project-case-verdict")).toBeNull();
  });
});

describe("the narrowing a retained policy still went through", () => {
  it("discloses a policy of more than fifteen rules that was read rule by rule", async () => {
    vi.spyOn(api, "answerProjectCase").mockResolvedValue({
      scope: "project",
      policy_set_key: "a-set",
      retrieval: {
        status: "narrowed",
        policies_considered: 2,
        policies_retained: 2,
        policies_discarded: 0,
        large_policy_rule_threshold: 15,
        selected_rule_budget: 15,
        policies_rule_sliced: 1,
        payload_budget_chars: 120000,
        policies_over_payload_budget: 1,
      },
      considered: [
        {
          provision_id: "big-id",
          provision_key: "allowances",
          heading_path: ["Published", "Allowances"],
          rules: 74,
          retained: true,
          rule_selection: {
            total_rules: 74,
            selected_rules: 8,
            rules_discarded: 66,
            selected_rule_ids: ["r-1", "r-2"],
            method: "scenario_relevance_v2",
            sliced: true,
          },
        },
        {
          provision_id: "huge-id",
          provision_key: "huge",
          heading_path: ["Published", "Huge"],
          rules: 9,
          retained: false,
          discard_reason: "outside_payload_budget",
        },
      ],
      excluded: [],
      evaluation: {
        intent: "informational",
        information_requested: true,
        verdict_requested: false,
        informational: INFORMATION_ANSWERED,
        decision: null,
      },
      size: { combined_chars: 90000, budget_chars: 200000, oversize: false },
    });

    render(<ProjectCaseRunner policySetKey="a-set" open onClose={() => {}} />);
    fireEvent.change(screen.getByTestId("project-case-scenario"), { target: { value: "What allowance applies?" } });
    fireEvent.click(screen.getByTestId("project-case-run"));

    const slicing = await screen.findByTestId("project-case-rule-slicing");
    expect(slicing.textContent).toMatch(/1 retained policy was read rule by rule rather than whole/i);
    expect(slicing.textContent).toMatch(/more than 15 rules/i);
    expect(slicing.textContent).toMatch(/at most 15 of its rules/i);
    expect(slicing.textContent).toMatch(/no rule was trimmed to fit/i);

    // A policy search kept but size set aside is not a relevance decision, and
    // is not reported as one.
    expect(slicing.textContent).toMatch(/set aside whole because its record would not fit/i);
    expect(slicing.textContent).toMatch(/size decision, not a relevance one/i);

    // And the per-policy counts are on the row, so "74 rules" can never be read
    // as "74 rules read".
    const considered = screen.getByTestId("project-case-considered");
    expect(within(considered).getByText("74 · 8 read for this case")).toBeTruthy();
    // The method is described in words, and by family: the server has already
    // moved this identifier from `_v1` to `_v2`, and a label pinned to one
    // version would be printing `Scenario Relevance V2` at a reviewer here.
    expect(within(considered).getByText(/66 not selected · selected by relevance to this case/i)).toBeTruthy();
    expect(within(considered).queryByText(/Scenario Relevance V/i)).toBeNull();
  });

  it("describes a selection algorithm this client has not seen by its own name", async () => {
    // Not a guess dressed as a description. An unknown method is shown as
    // itself so a reviewer can ask what it is, rather than being told
    // confidently that rules were "selected by relevance" when nobody knows.
    vi.spyOn(api, "answerProjectCase").mockResolvedValue({
      scope: "project",
      policy_set_key: "a-set",
      retrieval: { status: "narrowed", policies_rule_sliced: 1, large_policy_rule_threshold: 15 },
      considered: [
        {
          provision_id: "big-id",
          provision_key: "allowances",
          heading_path: ["Published", "Allowances"],
          rules: 40,
          retained: true,
          rule_selection: {
            total_rules: 40,
            selected_rules: 10,
            rules_discarded: 30,
            method: "semantic_rerank_v1",
            sliced: true,
          },
        },
      ],
      excluded: [],
      evaluation: {
        intent: "informational",
        information_requested: true,
        verdict_requested: false,
        informational: INFORMATION_ANSWERED,
        decision: null,
      },
      size: { combined_chars: 5000, budget_chars: 200000, oversize: false },
    });

    render(<ProjectCaseRunner policySetKey="a-set" open onClose={() => {}} />);
    fireEvent.change(screen.getByTestId("project-case-scenario"), { target: { value: "Which allowance?" } });
    fireEvent.click(screen.getByTestId("project-case-run"));

    const considered = await screen.findByTestId("project-case-considered");
    expect(within(considered).getByText(/30 not selected · semantic rerank v1/i)).toBeTruthy();
    expect(within(considered).queryByText(/selected by relevance to this case/i)).toBeNull();
  });

  it("tells an exact copy apart from a near-copy that was merely deferred", async () => {
    vi.spyOn(api, "answerProjectCase").mockResolvedValue({
      scope: "project",
      policy_set_key: "a-set",
      retrieval: {
        status: "narrowed",
        method: "hybrid_vector_topk",
        policies_considered: 4,
        policies_retained: 2,
        policies_discarded: 2,
        policy_selection_order: "relevance_then_normative_content_v1",
        policies_duplicate_collapsed: 1,
        policies_diversity_deferred: 1,
      },
      considered: [
        {
          provision_id: "leave-id",
          provision_key: "leave-policy",
          heading_path: ["Published", "Leave"],
          rules: 6,
          retained: true,
          best_rank: 1,
          best_score: 0.88,
        },
        {
          provision_id: "copy-id",
          provision_key: "leave-policy-copy",
          heading_path: ["Published", "Leave (annexe)"],
          rules: 6,
          retained: false,
          best_rank: 3,
          best_score: 0.81,
          discard_reason: "duplicate_policy_content",
          duplicate_of_provision_key: "leave-policy",
        },
        {
          provision_id: "near-id",
          provision_key: "near-copy",
          heading_path: ["Published", "Absence"],
          rules: 4,
          retained: false,
          best_rank: 2,
          best_score: 0.84,
          discard_reason: "outside_budget",
        },
      ],
      excluded: [],
      evaluation: {
        intent: "informational",
        information_requested: true,
        verdict_requested: false,
        classifier_version: "case_needs_v1",
        informational: INFORMATION_ANSWERED,
        decision: null,
      },
      size: { combined_chars: 4000, budget_chars: 200000, oversize: false },
    });

    render(<ProjectCaseRunner policySetKey="a-set" open onClose={() => {}} />);
    fireEvent.change(screen.getByTestId("project-case-scenario"), { target: { value: "How much leave is there?" } });
    fireEvent.click(screen.getByTestId("project-case-run"));

    // The collapsed copy: its terms were read, and the record they were read in
    // is named. This is the one discard that costs the reader nothing.
    const duplicates = await screen.findByTestId("project-case-duplicate-policies");
    expect(duplicates.textContent).toMatch(/collapsed as an exact copy of another that was retrieved/i);
    expect(duplicates.textContent).toMatch(/its terms were read, through the policy named beside it/i);
    expect(duplicates.textContent).toMatch(/the one discard whose content still reached the answer/i);

    // The deferred near-copy: not a duplicate, and not read. Stated in its own
    // sentence with its own count, never folded into the one above.
    const deferred = screen.getByTestId("project-case-diversity-deferred");
    expect(deferred.textContent).toMatch(/ranked inside the retention budget and was offered after it/i);
    expect(deferred.textContent).toMatch(/because a policy requiring the same thing was offered first/i);
    expect(deferred.textContent).toMatch(/It is not a duplicate/i);
    expect(deferred.textContent).toMatch(/its terms were not read/i);
    // The two findings are separate elements with separate counts; neither
    // sentence claims the other's number.
    expect(duplicates).not.toBe(deferred);
    expect(deferred.textContent).not.toMatch(/exact copy/i);
    expect(duplicates.textContent).not.toMatch(/deferred|offered after/i);

    // On the row, the copy names where it was read; the deferred policy keeps
    // the ordinary discard reason and claims nothing.
    const considered = screen.getByTestId("project-case-considered");
    expect(within(considered).getByTestId("project-case-duplicate-of").textContent).toMatch(
      /Its terms were read in leave-policy; this record was not read/i,
    );
    expect(within(considered).getByText("Outside Budget")).toBeTruthy();

    // And how the retained set was ordered is on the provenance disclosure,
    // which is what explains a rank-2 policy sitting outside the budget.
    expect(screen.getByTestId("project-case-trace").textContent).toContain(
      "relevance_then_normative_content_v1",
    );
  });

  it("names exact rule copies as represented, never as read", async () => {
    vi.spyOn(api, "answerProjectCase").mockResolvedValue({
      scope: "project",
      policy_set_key: "a-set",
      retrieval: {
        status: "narrowed",
        policies_considered: 1,
        policies_retained: 1,
        policies_discarded: 0,
        large_policy_rule_threshold: 15,
        selected_rule_budget: 15,
        policies_rule_sliced: 1,
      },
      considered: [
        {
          provision_id: "big-id",
          provision_key: "allowances",
          heading_path: ["Published", "Allowances"],
          rules: 74,
          retained: true,
          rule_selection: {
            total_rules: 74,
            selected_rules: 8,
            rules_discarded: 66,
            duplicate_rules_collapsed: 3,
            represented_rule_ids: ["rule-40", "rule-41", "rule-42"],
            method: "scenario_relevance_v2",
            sliced: true,
          },
        },
      ],
      excluded: [],
      evaluation: {
        intent: "informational",
        information_requested: true,
        verdict_requested: false,
        informational: INFORMATION_ANSWERED,
        decision: null,
      },
      size: { combined_chars: 9000, budget_chars: 200000, oversize: false },
    });

    render(<ProjectCaseRunner policySetKey="a-set" open onClose={() => {}} />);
    fireEvent.change(screen.getByTestId("project-case-scenario"), { target: { value: "Which allowance?" } });
    fireEvent.click(screen.getByTestId("project-case-run"));

    const copies = await screen.findByTestId("project-case-duplicate-rules");
    expect(copies.textContent).toMatch(/exact copies of rules that were read/i);
    expect(copies.textContent).toMatch(/represented rather than read/i);
    expect(copies.textContent).toMatch(/never put in front of the model/i);
    // The claim being avoided: that 3 more rules were read. The read count on
    // the row stays 8.
    expect(copies.textContent).not.toMatch(/11 read/i);

    const row = within(screen.getByTestId("project-case-considered"));
    expect(row.getByText("74 · 8 read for this case")).toBeTruthy();
    expect(row.getByTestId("project-case-represented-rules").textContent).toMatch(
      /3 of those are exact copies, represented by rules that were read, not read themselves: rule-40, rule-41, rule-42/i,
    );
  });

  it("says none of it for a server that reports none of those fields", async () => {
    // An older v2 reply, or a v1 replay. The disclosure is absent rather than
    // present and full of zeroes, which would claim narrowings were checked.
    await runCase(
      projectAnswer({
        intent: "informational",
        information_requested: true,
        verdict_requested: false,
        informational: INFORMATION_ANSWERED,
        decision: null,
      }),
      "What applies?",
    );

    expect(screen.queryByTestId("project-case-rule-slicing")).toBeNull();
    expect(screen.queryByTestId("project-case-duplicate-policies")).toBeNull();
    expect(screen.queryByTestId("project-case-diversity-deferred")).toBeNull();
    expect(screen.queryByTestId("project-case-duplicate-rules")).toBeNull();
    expect(screen.getByTestId("project-case-trace").textContent).not.toMatch(/selection order/i);
  });
});

/**
 * A QUESTION IS READ IN ONE LANGUAGE, AND THE EVIDENCE IS NEVER TRANSLATED.
 *
 * The pipeline reasons in one language, so a question asked in another is
 * carried into it before any policy is read. That means the words a reviewer
 * typed are not the words that were adjudicated — and the only person who can
 * catch a rendering that changed the question is the reviewer, comparing the
 * two. So the adjudicated text is shown, in full, whenever a rendering
 * happened, and the panel stays out of the way when none did.
 *
 * What must never move is the evidence. A document's own sentence is its own
 * characters in its own language, in every state of the boundary, and the
 * interface says so where a reader might otherwise wonder.
 *
 * These run in English with the language block stubbed: the point under test is
 * what the surface does with the metadata, not that a model can translate.
 */
describe("the language a case was read and answered in", () => {
  it("shows the text that was actually adjudicated when the question was rendered", async () => {
    await runCase(
      {
        ...projectAnswer({
          intent: "informational",
          information_requested: true,
          verdict_requested: false,
          classifier_version: "case_needs_v1",
          informational: INFORMATION_ANSWERED,
          decision: null,
        }),
        language: {
          source_language: "ar",
          processing_language: "en",
          response_language: "ar",
          boundary_state: "rendered",
          output_rendering_state: "rendered",
          guidance_rendering_state: "not_required",
          input_translation_profile: "case-language-v4",
          output_translation_profile: "case-language-v4",
          processing_scenario: "What is the maximum number of working hours in a week?",
          processing_scenario_hash: "sha256:abc",
          projection_profile: "policy-english-projection-v1",
        },
      },
      "ما هو الحد الأقصى لساعات العمل؟",
    );

    const language = await screen.findByTestId("project-case-language");
    expect(within(language).getByText("What is the maximum number of working hours in a week?")).toBeTruthy();
    expect(language.textContent).toMatch(/carried into en before any policy was read/i);
    expect(language.textContent).toMatch(/not the words you typed/i);
    // The promise that keeps the evidence trustworthy.
    expect(language.textContent).toMatch(/Evidence is not translated/i);
    expect(language.textContent).toMatch(/document's own characters/i);

    // The rendering contracts are provenance, and sit with the rest of it.
    const trace = screen.getByTestId("project-case-trace").textContent ?? "";
    expect(trace).toContain("case-language-v4");
    expect(trace).toContain("policy-english-projection-v1");
    expect(trace).toMatch(/ar → en → ar/);
  });

  it("stays out of the way when the question was already in the processing language", async () => {
    await runCase(
      {
        ...projectAnswer({
          intent: "informational",
          information_requested: true,
          verdict_requested: false,
          informational: INFORMATION_ANSWERED,
          decision: null,
        }),
        language: {
          source_language: "en",
          processing_language: "en",
          response_language: "en",
          boundary_state: "identity",
          output_rendering_state: "not_required",
          guidance_rendering_state: "not_required",
          input_translation_profile: "case-language-v4",
          processing_scenario: "What is the weekly cap?",
          processing_scenario_hash: "sha256:def",
        },
      },
      "What is the weekly cap?",
    );

    await screen.findByTestId("project-case-tracks");
    // Nothing was rendered, so the words on screen are the words that were
    // read and there is nothing to reconcile. A panel here would be noise.
    expect(screen.queryByTestId("project-case-language")).toBeNull();
    // The contract is still provenance and is still available.
    expect(screen.getByTestId("project-case-trace").textContent).toContain("case-language-v4");
  });

  it("says when presentation guidance was dropped rather than applied un-rendered", async () => {
    await runCase(
      {
        ...projectAnswer({
          intent: "informational",
          information_requested: true,
          verdict_requested: false,
          informational: INFORMATION_ANSWERED,
          decision: null,
        }),
        language: {
          source_language: "fr",
          processing_language: "en",
          response_language: "fr",
          boundary_state: "rendered",
          output_rendering_state: "rendered",
          guidance_rendering_state: "unrendered_dropped",
          input_translation_profile: "case-language-v4",
          processing_scenario: "Is parking covered?",
          processing_scenario_hash: "sha256:ghi",
        },
      },
      "Le parking est-il couvert ?",
    );

    const dropped = await screen.findByTestId("project-case-guidance-dropped");
    expect(dropped.textContent).toMatch(/dropped rather than applied un-rendered/i);
    expect(dropped.textContent).toMatch(/What was decided is unaffected/i);
  });

  it("shows no language panel at all for an answer produced before the boundary existed", async () => {
    await runCase(
      projectAnswer({
        intent: "informational",
        information_requested: true,
        verdict_requested: false,
        informational: INFORMATION_ANSWERED,
        decision: null,
      }),
      "What applies?",
    );

    expect(screen.queryByTestId("project-case-language")).toBeNull();
    expect(screen.getByTestId("project-case-trace").textContent).not.toMatch(/rendering contract/i);
  });
});

/**
 * WHAT THE SEARCH REACHED, INCLUDING THE RULES IT REACHED ON THEIR OWN TERMS.
 *
 * A policy too large for one case to read whole is indexed a document per rule
 * as well as its own, so a rule past what its policy's combined text could
 * carry is findable. `policies_elevated_by_rule` is the count that says whether
 * that mattered here, and it is reported even when it is zero — a reader is
 * owed "rule-level retrieval changed nothing on this question" rather than
 * silence they will read as "it was not tried".
 */
describe("what the discovery search matched", () => {
  it("reports both document counts, the elevation, and the corpus projection", async () => {
    vi.spyOn(api, "answerProjectCase").mockResolvedValue({
      scope: "project",
      policy_set_key: "a-set",
      retrieval: {
        status: "narrowed",
        method: "hybrid_policy_rule_rrf_v1",
        policies_considered: 4,
        policies_retained: 2,
        policies_discarded: 2,
        policy_documents_matched: 4,
        rule_documents_matched: 11,
        rule_scan: 120,
        policies_elevated_by_rule: 2,
        rule_index_state: "matched",
        projection_profile: "policy-english-projection-v1",
        projection_ready: true,
      },
      considered: [
        {
          provision_id: "hours-id",
          provision_key: "hours",
          heading_path: ["Published", "Working hours"],
          rules: 4,
          retained: true,
        },
      ],
      excluded: [],
      evaluation: {
        intent: "informational",
        information_requested: true,
        verdict_requested: false,
        informational: INFORMATION_ANSWERED,
        decision: null,
      },
      size: { combined_chars: 2000, budget_chars: 200000, oversize: false },
    });

    render(<ProjectCaseRunner policySetKey="a-set" open onClose={() => {}} />);
    fireEvent.change(screen.getByTestId("project-case-scenario"), { target: { value: "What is the cap?" } });
    fireEvent.click(screen.getByTestId("project-case-run"));

    const discovery = await screen.findByTestId("project-case-discovery");
    expect(discovery.textContent).toMatch(/4 policy documents and 11 rule documents/i);
    expect(discovery.textContent).toMatch(/from 120 rule documents examined/i);
    expect(screen.getByTestId("project-case-elevated").textContent).toMatch(
      /2 policies were ranked higher because one of their own rules surfaced/i,
    );
    expect(screen.getByTestId("project-case-projection").textContent).toMatch(
      /policy-english-projection-v1 corpus projection/i,
    );
    // A matched index is the ordinary case and needs no sentence of its own.
    expect(screen.queryByTestId("project-case-rule-index-state")).toBeNull();
  });

  it("says plainly when rule-level retrieval changed nothing, and when the index could not be used", async () => {
    vi.spyOn(api, "answerProjectCase").mockResolvedValue({
      scope: "project",
      policy_set_key: "a-set",
      retrieval: {
        status: "narrowed",
        policies_considered: 2,
        policies_retained: 1,
        policies_discarded: 1,
        policies_elevated_by_rule: 0,
        rule_index_state: "degraded",
      },
      considered: [
        { provision_id: "a", provision_key: "a", heading_path: ["A"], rules: 3, retained: true },
      ],
      excluded: [],
      evaluation: {
        intent: "informational",
        information_requested: true,
        verdict_requested: false,
        informational: INFORMATION_ANSWERED,
        decision: null,
      },
      size: { combined_chars: 900, budget_chars: 200000, oversize: false },
    });

    render(<ProjectCaseRunner policySetKey="a-set" open onClose={() => {}} />);
    fireEvent.change(screen.getByTestId("project-case-scenario"), { target: { value: "What applies?" } });
    fireEvent.click(screen.getByTestId("project-case-run"));

    const elevated = await screen.findByTestId("project-case-elevated");
    expect(elevated.textContent).toMatch(/rule-level retrieval changed nothing on this question/i);
    const state = screen.getByTestId("project-case-rule-index-state");
    expect(state.textContent).toMatch(/the query against them failed/i);
    // Degraded is not "no rules were chosen by relevance": the selection still
    // ran, just without that one ranking.
    expect(state.textContent).toMatch(/not by document order/i);
  });

  it("says nothing about discovery for a server that reports none of it", async () => {
    await runCase(
      projectAnswer({
        intent: "informational",
        information_requested: true,
        verdict_requested: false,
        informational: INFORMATION_ANSWERED,
        decision: null,
      }),
      "What applies?",
    );

    expect(screen.queryByTestId("project-case-discovery")).toBeNull();
    expect(screen.queryByTestId("project-case-elevated")).toBeNull();
  });
});

/**
 * HOW ONE POLICY'S RULES WERE PLACED, AND WHAT THAT DOES NOT MEAN.
 *
 * The quantity rank is the one most easily misread: a rule stating an interval
 * that admits a value the question states is *worth reading*, and that is all
 * it is. It has decided nothing. The label says "by stated quantity" and the
 * cell never calls it a finding.
 */
describe("how one policy's rules were placed", () => {
  it("reports each rank, the evidence quota, and rules the index could not project", async () => {
    vi.spyOn(api, "answerProjectCase").mockResolvedValue({
      scope: "project",
      policy_set_key: "a-set",
      retrieval: {
        status: "narrowed",
        policies_considered: 1,
        policies_retained: 1,
        policies_discarded: 0,
        large_policy_rule_threshold: 15,
        selected_rule_budget: 15,
        policies_rule_sliced: 1,
        rule_index_state: "matched",
      },
      considered: [
        {
          provision_id: "big-id",
          provision_key: "allowances",
          heading_path: ["Published", "Allowances"],
          rules: 74,
          retained: true,
          rule_selection: {
            total_rules: 74,
            selected_rules: 8,
            rules_discarded: 66,
            method: "hybrid_rule_v1",
            sliced: true,
            rule_index_state: "matched",
            rule_index_hits: 6,
            lexical_candidates: 12,
            quantity_candidates: 3,
            fused_candidates: 15,
            evidence_diversity_quota: 4,
            rules_without_projection: 2,
          },
        },
      ],
      excluded: [],
      evaluation: {
        intent: "informational",
        information_requested: true,
        verdict_requested: false,
        informational: INFORMATION_ANSWERED,
        decision: null,
      },
      size: { combined_chars: 9000, budget_chars: 200000, oversize: false },
    });

    render(<ProjectCaseRunner policySetKey="a-set" open onClose={() => {}} />);
    fireEvent.change(screen.getByTestId("project-case-scenario"), { target: { value: "Which allowance?" } });
    fireEvent.click(screen.getByTestId("project-case-run"));

    const cell = await screen.findByTestId("project-case-rule-index");
    expect(cell.textContent).toMatch(/The rule index was queried and its ranking was used/i);
    expect(cell.textContent).toMatch(/12 by relevance/i);
    // A retrieval rank, and the words never let it read as a determination.
    expect(cell.textContent).toMatch(/3 by stated quantity/i);
    expect(cell.textContent).toMatch(/6 by the rule index/i);
    expect(cell.textContent).toMatch(/15 in the fused pool the budget chose from/i);
    expect(cell.textContent).toMatch(/4 slots reserved so distinct source passages are covered/i);

    // Rules the index held no English projection for scored zero on relevance —
    // which is not the same as saying nothing relevant, and is not a match
    // attempted against the document's own language.
    expect(screen.getByTestId("project-case-without-projection").textContent).toMatch(
      /2 rules could not be scored for relevance/i,
    );
    expect(screen.getByTestId("project-case-without-projection").textContent).toMatch(
      /scored zero rather than matched against the document's own language/i,
    );

    // And the method reads as the rule index taking part, not as relevance alone.
    const considered = screen.getByTestId("project-case-considered");
    expect(within(considered).getByText(/placed by the rule index, relevance and quantity together/i)).toBeTruthy();
  });

  it("keeps an index that placed nothing apart from one that was never asked", async () => {
    vi.spyOn(api, "answerProjectCase").mockResolvedValue({
      scope: "project",
      policy_set_key: "a-set",
      retrieval: { status: "narrowed", policies_considered: 1, policies_retained: 1, policies_discarded: 0 },
      considered: [
        {
          provision_id: "big-id",
          provision_key: "allowances",
          heading_path: ["Published", "Allowances"],
          rules: 40,
          retained: true,
          rule_selection: {
            total_rules: 40,
            selected_rules: 10,
            rules_discarded: 30,
            method: "scenario_relevance_v3",
            sliced: true,
            rule_index_state: "matched",
            rule_index_hits: 0,
          },
        },
      ],
      excluded: [],
      evaluation: {
        intent: "informational",
        information_requested: true,
        verdict_requested: false,
        informational: INFORMATION_ANSWERED,
        decision: null,
      },
      size: { combined_chars: 5000, budget_chars: 200000, oversize: false },
    });

    render(<ProjectCaseRunner policySetKey="a-set" open onClose={() => {}} />);
    fireEvent.change(screen.getByTestId("project-case-scenario"), { target: { value: "Which allowance?" } });
    fireEvent.click(screen.getByTestId("project-case-run"));

    const cell = await screen.findByTestId("project-case-rule-index");
    expect(cell.textContent).toMatch(/it placed none of this policy's rules, which is an answer, not an absence/i);
    // v3 is the selection running without the index's ranking, and says so.
    const considered = screen.getByTestId("project-case-considered");
    expect(within(considered).getByText(/without the rule index/i)).toBeTruthy();
  });
});

/**
 * A CORPUS THAT COULD NOT BE COMPARED IS NOT AN EMPTY CORPUS.
 *
 * This is the refusal the whole surface must not soften. Matching a rendered
 * question against an index that was never rendered scores near zero on every
 * policy, which reads exactly like "no published policy bears on your
 * question". A reviewer told that goes looking for a policy that is already
 * published and already relevant, and concludes their corpus is wrong when
 * their index is.
 */
describe("a project whose index cannot be compared against a question", () => {
  it("says a rebuild is required and never that no policy bears", async () => {
    const onOpenPolicyIndex = vi.fn();
    vi.spyOn(api, "answerProjectCase").mockRejectedValue(
      new PolicyPlatformApiError(
        503,
        "the policy index for 'a-set' holds no retrieval projection under policy-english-projection-v1",
        { code: "index_projection_unavailable" },
      ),
    );

    render(<ProjectCaseRunner policySetKey="a-set" open onClose={() => {}} onOpenPolicyIndex={onOpenPolicyIndex} />);
    fireEvent.change(screen.getByTestId("project-case-scenario"), { target: { value: "What is the cap?" } });
    fireEvent.click(screen.getByTestId("project-case-run"));

    const refusal = await screen.findByTestId("project-case-refusal-index_projection_unavailable");
    expect(refusal.textContent).toMatch(/policy index must be rebuilt before a case can be tested/i);
    expect(refusal.textContent).toMatch(/No policy was read and nothing was compared/i);
    expect(refusal.textContent).toMatch(/not the same as no published policy bearing on your question/i);
    expect(refusal.textContent).toMatch(/rebuilding is the whole repair/i);
    // The words that would send a reviewer to fix the wrong thing.
    expect(refusal.textContent).not.toMatch(/no published policy bears on this question/i);
    expect(refusal.textContent).not.toMatch(/none matched this case/i);

    // And the repair is one click from the refusal, not a sentence about a
    // panel the reader has to go and find.
    fireEvent.click(screen.getByRole("button", { name: /open index repair/i }));
    expect(onOpenPolicyIndex).toHaveBeenCalledWith("index_projection_unavailable");
  });

  it("tells a question that could not be read apart from an answer that could not be returned", async () => {
    vi.spyOn(api, "answerProjectCase").mockRejectedValue(
      new PolicyPlatformApiError(503, "the rendering call did not complete", {
        code: "scenario_translation_unavailable",
      }),
    );

    render(<ProjectCaseRunner policySetKey="a-set" open onClose={() => {}} />);
    fireEvent.change(screen.getByTestId("project-case-scenario"), { target: { value: "Une question" } });
    fireEvent.click(screen.getByTestId("project-case-run"));

    const refusal = await screen.findByTestId("project-case-refusal-scenario_translation_unavailable");
    expect(refusal.textContent).toMatch(/could not be carried into the language this platform reads in/i);
    expect(refusal.textContent).toMatch(/No policy was read/i);
    expect(refusal.textContent).toMatch(/refusal rather than an answer drawn from the original text/i);
  });

  it("still shows an ordinary failure as its own sentence", async () => {
    vi.spyOn(api, "answerProjectCase").mockRejectedValue(
      new PolicyPlatformApiError(503, "Azure OpenAI is not configured on this server"),
    );

    render(<ProjectCaseRunner policySetKey="a-set" open onClose={() => {}} />);
    fireEvent.change(screen.getByTestId("project-case-scenario"), { target: { value: "What applies?" } });
    fireEvent.click(screen.getByTestId("project-case-run"));

    expect(await screen.findByText("Azure OpenAI is not configured on this server")).toBeTruthy();
    expect(screen.queryByTestId("project-case-refusal-index_projection_unavailable")).toBeNull();
  });
});
