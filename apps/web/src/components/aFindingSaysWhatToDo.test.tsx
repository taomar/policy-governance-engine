import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import type { CanonicalRule } from "../api";
import { candidateEditability } from "../candidateEditability";
import { READINESS_LABEL, splitDefectFinding } from "../ruleExecutability";
import { DecisionReadinessView } from "./DecisionReadinessView";

/**
 * A reviewer opened a rule and met a red box holding two words and one
 * sentence: "Decomposition damaged - the sentence was mis-split, so every claim
 * derived from it inherits the error." They asked what the error was.
 *
 * That question is the whole defect. The content was honest and it was the most
 * valuable thing on the tab - it says the fault is ours and that everything
 * downstream inherits it - but it was drawn as an alarm. It named no
 * consequence for the decision the reviewer was there to make, offered nothing
 * to do, and used a word for its own internals as its headline.
 *
 * A finding that does not say what to do next is only an alarm. These tests
 * hold three things about it:
 *
 *   1. it says what happened in words that name this app as the cause;
 *   2. it answers the reviewer's actual question - may I approve this;
 *   3. it gives a next step, and the step is read off the record's own state,
 *      so a rule that can still be re-split is told to re-split it and one that
 *      cannot is told the route out rather than pointed at a control it does
 *      not have.
 *
 * And one thing about the other four readiness values: they are readings of the
 * document, not defects, and none of them acquires this treatment.
 */

const OTHER_VERDICTS = [
  "decidable",
  "discretionary",
  "underspecified",
  "not_a_decision",
] as const;

/** Words that turn a finding into a crash report. */
const READS_AS_A_CRASH: readonly RegExp[] = [
  /\berror\b/i,
  /\bfailed\b/i,
  /\bfailure\b/i,
  /\bexception\b/i,
  /\bcrash/i,
  /\binvalid\b/i,
  /\bcorrupt/i,
];

/**
 * Internal vocabulary that a person governing a business does not use. The old
 * headline was one of these; the rule is that the headline is not another.
 */
const INTERNAL_VOCABULARY: readonly RegExp[] = [
  /decomposition/i,
  /\bmalformed\b/i,
  /\bnull\b/i,
  /\bparse/i,
  /[a-z]+_[a-z]+/,
];

function ruleWith(evaluability: string, review_status: string): CanonicalRule {
  return {
    schema_version: "1.0",
    policy_set_id: "set-under-test",
    policy_version_id: "version-under-test",
    rule_id: "rule-under-test",
    rule_revision: 1,
    title: "Rule under test",
    description: "",
    rule_type: "eligibility",
    authority: { level: "policy", owner: "Owner", rank: 1 },
    scope: { jurisdictions: [], organizational_units: [], personas: [], processes: [] },
    condition: { type: "all", all: [] },
    condition_provenance: null,
    effect: { type: "allow", action: "grant" },
    required_facts: [],
    exceptions: [],
    priority: 0,
    effective_from: "2024-01-01",
    effective_to: null,
    machine_executable: false,
    ambiguity_status: "none",
    review_status,
    evidence: [],
    lineage: {
      extraction_run_id: null,
      deployment_name: null,
      prompt_version: null,
      parser_version: null,
      schema_version: "1.0",
    },
    category: "",
    tags: [],
    group_label: "",
    related_rule_ids: [],
    is_explicit_override: false,
    supersedes_rule_ids: [],
    advice: [],
    decision_readiness: {
      evaluability,
      required_attributes: [{ phrase: "the employee", role: "subject" }],
      parties: [],
    },
  } as unknown as CanonicalRule;
}

afterEach(cleanup);

describe("a mis-split sentence is reported as a finding, not as an alarm", () => {
  it("is drawn for a mis-split rule and for no other reading of the document", () => {
    render(<DecisionReadinessView rule={ruleWith("malformed", "candidate")} />);
    expect(screen.getByTestId("split-defect-finding")).toBeTruthy();

    for (const verdict of OTHER_VERDICTS) {
      cleanup();
      render(<DecisionReadinessView rule={ruleWith(verdict, "candidate")} />);
      // Positive control on the same mount: the pane drew, so an absent finding
      // is an absent finding rather than an absent pane.
      expect(screen.getByText("Attributes the evaluator must find")).toBeTruthy();
      expect(screen.queryByTestId("split-defect-finding")).toBeNull();
    }
  });

  it("names this app as the cause rather than the document", () => {
    const finding = splitDefectFinding("candidate");
    expect(/this app/i.test(finding.heading)).toBe(true);
    // The document is not blamed for it anywhere in the finding.
    const whole = `${finding.heading} ${finding.consequence} ${finding.nextStep}`;
    expect(/the document (?:is|was) (?:wrong|at fault|to blame)/i.test(whole)).toBe(false);
  });

  it("answers the question the reviewer is there to ask", () => {
    // A mis-split rule is not a claim the document makes, so it is not safe to
    // approve. The finding must say that in the affirmative rather than leave a
    // reviewer to infer it from the colour of a box.
    expect(splitDefectFinding("candidate").blocksApproval).toBe(true);

    render(<DecisionReadinessView rule={ruleWith("malformed", "candidate")} />);
    const verdict = screen.getByTestId("split-defect-approval").textContent ?? "";
    expect(verdict.trim().length).toBeGreaterThan(0);
    expect(/do not approve/i.test(verdict)).toBe(true);
  });

  it("gives a next step, and it is never empty", () => {
    for (const status of ["candidate", "changes_requested", "rejected", "approved", "published"]) {
      cleanup();
      render(<DecisionReadinessView rule={ruleWith("malformed", status)} />);
      const step = screen.getByTestId("split-defect-next-step").textContent ?? "";
      expect(step.trim().length).toBeGreaterThan(0);
    }
  });

  it("says what happened, what it costs, and what to do - three distinct things", () => {
    const finding = splitDefectFinding("candidate");
    const parts = [finding.heading, finding.consequence, finding.nextStep];
    // None repeats another, or the reviewer is reading the same sentence three
    // times and still has no step.
    expect(new Set(parts).size).toBe(3);
    for (const part of parts) expect(part.trim().length).toBeGreaterThan(0);
  });
});

describe("the step is read off the record, not off the surface drawing it", () => {
  it("points a record that can still be changed at the control that changes it", () => {
    for (const status of ["candidate", "changes_requested", "rejected"]) {
      expect(candidateEditability(status).canEdit).toBe(true);
      const finding = splitDefectFinding(status);
      expect(/suggest rewrite/i.test(finding.nextStep)).toBe(true);
    }
  });

  it("never points a sealed record at a control it does not have", () => {
    for (const status of ["approved", "published"]) {
      expect(candidateEditability(status).canEdit).toBe(false);
      const finding = splitDefectFinding(status);
      expect(/suggest rewrite/i.test(finding.nextStep)).toBe(false);
      // It says the route out instead - the same sentence the edit controls
      // give, so the reviewer meets one account of what this record admits.
      expect(finding.nextStep).toBe(candidateEditability(status).editBlockedReason);
    }
  });

  it("still gives a step for a status this build has never heard of", () => {
    const finding = splitDefectFinding("a-status-from-a-later-build");
    expect(finding.nextStep.trim().length).toBeGreaterThan(0);
    expect(/suggest rewrite/i.test(finding.nextStep)).toBe(false);
  });
});

describe("it reads as a finding a person can act on", () => {
  it("uses no crash vocabulary", () => {
    const finding = splitDefectFinding("candidate");
    const whole = `${finding.heading} ${finding.consequence} ${finding.nextStep}`;
    const offenders = READS_AS_A_CRASH.filter((pattern) => pattern.test(whole));
    expect(offenders.map(String)).toEqual([]);
  });

  it("uses no internal vocabulary in the headline", () => {
    const finding = splitDefectFinding("candidate");
    const offenders = INTERNAL_VOCABULARY.filter((pattern) => pattern.test(finding.heading));
    expect(offenders.map(String)).toEqual([]);
  });

  it("carries the retired two-word label nowhere a reader can reach it", () => {
    expect(/decomposition/i.test(READINESS_LABEL.malformed)).toBe(false);
    render(<DecisionReadinessView rule={ruleWith("malformed", "candidate")} />);
    expect(/decomposition/i.test(document.body.textContent ?? "")).toBe(false);
  });

  it("says the reading below it cannot be relied on, because it is read off the bad split", () => {
    const finding = splitDefectFinding("candidate");
    expect(/relied on|trust/i.test(finding.consequence)).toBe(true);
  });
});
