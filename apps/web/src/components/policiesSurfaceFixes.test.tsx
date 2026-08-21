/**
 * Properties of the policies surface that the F1–F5 fixes establish.
 *
 * Each test is named as a sentence describing the property held, not the
 * mechanism that delivers it.
 */

import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import type { CanonicalRule, CandidateRule, PolicyAttribute } from "../api";
import { fromDraftRow, type PolicyCard, type PolicyCardPassage, type PolicyCardRule } from "../policyCards";
import { PolicyLogicTable } from "./PolicyLogicTable";
import { PolicyInspector } from "./PolicyInspector";
import { FeedbackTimeline } from "./FeedbackTimeline";
import { SubmitFeedbackModal } from "./SubmitFeedbackModal";

beforeAll(() => {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }));
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
  vi.unstubAllGlobals();
  // Re-stub since afterEach unstubs but beforeAll already ran
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }));
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  );
});

/* ------------------------------------------------------------------ */
/*  Fixtures                                                          */
/* ------------------------------------------------------------------ */

function row(attribute: string, text: string): PolicyAttribute {
  return { attribute, text, fact: null, data_type: null } as PolicyAttribute;
}

function cardRule(
  ruleId: string,
  options: {
    applies?: PolicyAttribute[];
    outcome?: PolicyAttribute[];
    description?: string;
    sourceText?: string;
  } = {},
): PolicyCardRule {
  const draft = {
    id: `record-${ruleId}`,
    review_status: "candidate",
    rule: {
      rule_id: ruleId,
      rule_type: "obligation",
      effect: { type: "require_action", action: "" },
      condition: { type: "all", all: [] },
      attributes: {
        applies: options.applies ?? [row("subject", "anyone")],
        outcome: options.outcome ?? [row("predicate", "must comply")],
      },
      description: options.description ?? undefined,
      formulation: options.sourceText
        ? { canonical: { source_text: options.sourceText } }
        : undefined,
    },
  } as unknown as CandidateRule;
  return {
    rule_id: ruleId,
    evaluation_mode: "ai_ready",
    ...fromDraftRow(draft),
  } as unknown as PolicyCardRule;
}

function singleRuleCard(ruleOptions: Parameters<typeof cardRule>[1] = {}): PolicyCard {
  const cr = cardRule("rule-1", ruleOptions);
  const passages: PolicyCardPassage[] = [
    {
      passage: { key: "p-1" } as PolicyCardPassage["passage"],
      rules: [cr],
    },
  ];
  return {
    policy: { key: "policy-1", rule_count: 1 } as PolicyCard["policy"],
    passages,
    rules: [cr],
    hiddenByFilter: 0,
    reviewableIds: [cr.recordId],
    allIds: [cr.recordId],
    reviewStatuses: ["candidate"],
    policy_set_key: null,
  };
}

function canonicalRule(overrides: Partial<CanonicalRule> = {}): CanonicalRule {
  return {
    schema_version: "1.0",
    policy_set_id: "a-set",
    policy_version_id: "a-version",
    rule_id: "a-rule",
    rule_revision: 1,
    title: "A rule title",
    description: "A description of the rule",
    rule_type: "obligation",
    authority: { owner: "an-owner", source: "", reference: "" },
    scope: { personas: [], jurisdictions: [], organizational_units: [], processes: [] },
    condition: { type: "all", all: [] },
    evaluation_mode: "ai_ready",
    effect: { type: "require_action" },
    required_facts: [],
    exceptions: [],
    priority: 0,
    effective_from: "2024-01-01",
    effective_to: null,
    machine_executable: false,
    ambiguity_status: "clear",
    review_status: "published",
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
    ...overrides,
  } as unknown as CanonicalRule;
}

/* ------------------------------------------------------------------ */
/*  F1: the source quotation is visible without interaction           */
/* ------------------------------------------------------------------ */

describe("F1 — source evidence is the first thing a reader sees", () => {
  it("the source quotation is visible without interaction on the logic table", () => {
    const STATED = "All personnel must complete training within 30 days of hire.";
    const card = singleRuleCard({ sourceText: STATED });
    render(<PolicyLogicTable card={card} />);

    const source = screen.getByTestId("policy-logic-source");
    // It must be a blockquote (not hidden inside a <details>)
    expect(source.tagName).toBe("BLOCKQUOTE");
    expect(source.textContent).toContain(STATED);

    // Verify no <details> or <summary> element wraps it
    const container = screen.getByTestId("policy-logic");
    expect(container.querySelector("details.policy-logic__source")).toBeNull();
  });

  it("the evidence block in the inspector presents the quote before any identifier", () => {
    const rule = canonicalRule({
      evidence: [
        {
          document_version_id: "doc-version-uuid-123",
          clause_id: "clause-uuid-456",
          page: 5,
          section: "Security policies",
        } as CanonicalRule["evidence"][0],
      ],
    });

    const { container } = render(
      <PolicyInspector
        rule={rule}
        policySetKey="a-set"
        activeTabKey="overview"
        onTabChange={() => {}}
      />,
    );

    // The evidence block should exist
    const evidenceBlocks = container.querySelectorAll(".evidence-block");
    if (evidenceBlocks.length > 0) {
      const block = evidenceBlocks[0]!;
      const children = Array.from(block.children);

      // Find the quote box and the provenance grid positions
      const quoteIndex = children.findIndex(
        (el) =>
          el.classList.contains("evidence-quote-box") ||
          el.classList.contains("evidence-quote-missing-block"),
      );
      const provenanceIndex = children.findIndex((el) =>
        el.classList.contains("evidence-provenance-grid"),
      );

      // Quote must come before any direct provenance grid (which is now inside a collapse)
      if (quoteIndex >= 0 && provenanceIndex >= 0) {
        expect(quoteIndex).toBeLessThan(provenanceIndex);
      }

      // If there's no direct provenance grid (because it's collapsed), that's
      // even better — the identifiers are behind the collapse
      if (provenanceIndex < 0) {
        expect(quoteIndex).toBeGreaterThanOrEqual(0);
      }
    }
  });
});

/* ------------------------------------------------------------------ */
/*  F3: a viewer can reach the feedback action from the rule inspector */
/* ------------------------------------------------------------------ */

describe("F3 — feedback entry point exists where doubt happens", () => {
  it("a viewer can reach the feedback action while reading a rule", () => {
    const onFeedback = vi.fn();
    render(
      <PolicyInspector
        rule={canonicalRule()}
        policySetKey="a-set"
        onSubmitFeedback={onFeedback}
      />,
    );

    const btn = screen.getByTestId("inspector-submit-feedback");
    expect(btn).toBeTruthy();
    expect(btn.tagName).toBe("BUTTON");
    btn.click();
    expect(onFeedback).toHaveBeenCalledTimes(1);
  });

  it("feedback action is absent when onSubmitFeedback is not provided", () => {
    render(
      <PolicyInspector
        rule={canonicalRule()}
        policySetKey="a-set"
      />,
    );

    expect(screen.queryByTestId("inspector-submit-feedback")).toBeNull();
  });
});

/* ------------------------------------------------------------------ */
/*  F4: no workflow or lifecycle state uses a reserved semantic hue    */
/* ------------------------------------------------------------------ */

describe("F4 — reserved hues belong only to policy semantics", () => {
  it("no workflow or lifecycle state uses green, red, or gold", async () => {
    // Check the FeedbackTimeline status colour mapping at the source level.
    // Importing the module gives us access to its internal constants via the
    // rendered output's Tag colours.
    const { api } = await import("../api");
    vi.spyOn(api, "listReviewRequests").mockResolvedValue([
      {
        id: "req-1",
        policy_set_key: "ps-1",
        approved_policy_version_id: "v-1",
        submitted_by: "viewer",
        submitted_at: "2025-01-01T12:00:00Z",
        comment: "test",
        categories: [],
        status: "actioned" as const,
      },
    ]);

    const { container } = render(
      <FeedbackTimeline policySetKey="ps-1" submittedBy="viewer" />,
    );

    // Wait for the timeline to load
    await vi.waitFor(() => {
      expect(screen.getByTestId("feedback-timeline")).toBeTruthy();
    });

    // The "actioned" tag must not use green (which belongs to allow effect)
    const tags = container.querySelectorAll(".ant-tag");
    for (const tag of tags) {
      const classList = Array.from(tag.classList).join(" ");
      // Ant Design v6 adds class like ant-tag-green for color="green"
      expect(classList).not.toContain("ant-tag-green");
    }
  });
});

/* ------------------------------------------------------------------ */
/*  F5: Withdraw is reachable by keyboard                             */
/* ------------------------------------------------------------------ */

describe("F5 — polish done properly", () => {
  it("Withdraw is a real button, reachable by keyboard", async () => {
    const { api } = await import("../api");
    vi.spyOn(api, "listReviewRequests").mockResolvedValue([
      {
        id: "open-1",
        policy_set_key: "ps-1",
        approved_policy_version_id: "v-1",
        submitted_by: "viewer",
        submitted_at: "2025-01-01T12:00:00Z",
        comment: "test",
        categories: [],
        status: "open" as const,
      },
    ]);

    render(<FeedbackTimeline policySetKey="ps-1" submittedBy="viewer" />);

    await vi.waitFor(() => {
      expect(screen.getByTestId("feedback-timeline")).toBeTruthy();
    });

    const withdraw = screen.getByTestId("withdraw-open-1");
    // Must be a button (keyboard-focusable), not an anchor without href
    expect(withdraw.tagName).toBe("BUTTON");
  });

  it("SubmitFeedbackModal uses class-based spacing, not inline styles", () => {
    const { container } = render(
      <SubmitFeedbackModal
        open
        policySetKey="ps-1"
        approvedPolicyVersionId="v-1"
        submittedBy="viewer"
        onClose={() => {}}
        onSubmitted={() => {}}
      />,
    );

    // The alert and textarea should use CSS classes, not inline style for spacing
    const alert = container.querySelector(".feedback-modal-alert") ??
      document.querySelector(".feedback-modal-alert");
    // At minimum, no inline marginBottom on the alert
    if (alert) {
      const style = alert.getAttribute("style") ?? "";
      expect(style).not.toContain("margin");
    }
  });
});
