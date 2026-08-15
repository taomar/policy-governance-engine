/**
 * Both surfaces ask a policy the same questions.
 *
 * WHAT WENT WRONG BEFORE, AND WHY THIS TEST EXISTS
 *
 * The review page and the published page were built at different times and
 * drifted, and the drift was invisible: each page looked complete on its own,
 * and a reviewer who had never used both had no way to discover that the sealed
 * version answered fewer questions than the draft. The whole of this line of
 * work is closing that gap and keeping it closed.
 *
 * Every test written so far checks one surface at a time. That is exactly the
 * shape of check that let the drift open, because a tab added to one file and
 * not the other passes both. So this asserts the *relation*: whatever set of
 * questions one surface offers, the other offers the same set.
 *
 * WHY IT IS NOT A LIST OF EIGHT NAMES
 *
 * A literal list here would be a third opinion, free to agree with neither
 * surface, and would need editing every time a tab is added — which is the
 * moment a hurried change would edit it to match whichever file it just
 * touched. Read from the two components instead, so the test cannot be brought
 * into line with a half-finished change; it can only pass when they agree.
 *
 * WHAT IT DOES NOT ASSERT
 *
 * Not that the two pages are identical. They must differ: a draft can be
 * approved, edited and rejected, and a sealed record cannot. That difference is
 * covered elsewhere, by the tests that a published record offers no decision.
 * The questions a reader may ask are a different thing from the decisions a
 * reviewer may take, and only the first has to match.
 *
 * Nothing here is a phrase from any document, and no number in it is a
 * measurement of one.
 */
import { render, screen, cleanup } from "@testing-library/react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import type { AssembledPolicy, CanonicalRule } from "../api";
import { buildPolicyCards } from "../policyCards";
import { buildPublishedPolicyCards } from "../publishedPolicyCards";
import { PolicyDetailPanel } from "./PolicyDetailPanel";
import { PublishedPolicyCard } from "./PublishedPolicyCard";

vi.mock("./PolicyLogicTable", () => ({
  PolicyLogicTable: () => <div data-testid="logic" />,
}));
vi.mock("./PolicyExplainButton", () => ({
  PolicyExplainButton: () => <div />,
}));
vi.mock("./PolicyAskAiButton", () => ({ PolicyAskAiButton: () => <div /> }));
vi.mock("./PublishedRuleAskAiButton", () => ({
  PublishedRuleAskAiButton: () => <div />,
}));
vi.mock("./NotesPanel", () => ({ NotesPanel: () => <div data-testid="notes" /> }));

beforeAll(() => {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }),
  });
  window.ResizeObserver =
    window.ResizeObserver ??
    (class {
      observe() {}
      unobserve() {}
      disconnect() {}
    } as unknown as typeof ResizeObserver);
});

beforeEach(() => cleanup());

const RULE_IDS = ["r1", "r2"];

function rule(ruleId: string): CanonicalRule {
  return {
    rule_id: ruleId,
    title: `A title for ${ruleId}`,
    description: "A description.",
    rule_type: "obligation",
    evaluation_mode: "ai_ready",
    condition: { type: "all", all: [] },
    effect: { type: "requirement", description: "An effect." },
    scope: {
      jurisdictions: [],
      organizational_units: [],
      processes: [],
      personas: [],
      channels: [],
      systems: [],
    },
    authority: { owner: "An owner", level: "A level", reference: "" },
    required_facts: [],
    decision_readiness: null,
    source_refs: [],
    ambiguity_status: "clear",
    review_status: "published",
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
    evidence: [],
  } as unknown as CanonicalRule;
}

function policies(): AssembledPolicy[] {
  return [
    {
      key: "a-policy",
      heading: "A heading",
      heading_path: ["An outer heading", "A heading"],
      topic_label: null,
      persisted: true,
      provision_id: "a-provision",
      document_version_id: null,
      source_elements: "",
      page: 1,
      rule_count: RULE_IDS.length,
      passage_count: 1,
      route: "ai_ready",
      passages: [
        {
          key: "a-passage",
          source_elements: "",
          page: 1,
          rule_count: RULE_IDS.length,
          rules: RULE_IDS.map((id) => ({ rule_id: id, evaluation_mode: "ai_ready" })),
        },
      ],
      rules: RULE_IDS.map((id) => ({ rule_id: id, evaluation_mode: "ai_ready" })),
    } as unknown as AssembledPolicy,
  ];
}

/** The names on the tab strip, in the order a reader meets them. Read off what
 *  was rendered, never off a list written here, so this cannot be edited into
 *  agreement with a half-finished change. */
function questionsOnScreen(): string[] {
  return screen
    .getAllByRole("tab")
    .map((tab) => tab.textContent?.trim() ?? "")
    .filter(Boolean);
}

function questionsOnTheReviewSurface(): string[] {
  const [card] = buildPolicyCards(
    policies(),
    RULE_IDS.map((id) => ({ rule: rule(id), review_status: "candidate", id: `${id}-row` })),
  );
  render(
    <PolicyDetailPanel
      card={card}
      onApprove={() => {}}
      onReject={() => {}}
      statusColor={() => "default"}
      statusLabel={(status) => status}
    />,
  );
  return questionsOnScreen();
}

function questionsOnThePublishedSurface(): string[] {
  const [card] = buildPublishedPolicyCards(
    policies(),
    RULE_IDS.map((id) => rule(id)),
  );
  render(
    <PublishedPolicyCard
      card={card}
      open={false}
      selectedForExport={false}
      indeterminateForExport={false}
      onToggleExportSelection={() => {}}
      onOpen={() => {}}
      onSelectRule={() => {}}
      onToggleRule={() => {}}
      onViewHistory={() => {}}
      policySetKey="a-set"
      policyVersionId="a-version"
    />,
  );
  return questionsOnScreen();
}

describe("the questions a policy answers", () => {
  it("are the same on the page where it is reviewed and the page where it is published", () => {
    const review = questionsOnTheReviewSurface();
    cleanup();
    const published = questionsOnThePublishedSurface();

    // Sorted, because the two surfaces are free to order the strip differently
    // — one is entered to decide and the other to read. What may not differ is
    // which questions can be asked at all.
    expect([...published].sort()).toEqual([...review].sort());
  });

  it("is a set neither surface can quietly shrink", () => {
    // The guard for the assertion above: it would also pass if both surfaces
    // rendered nothing. Two is arbitrary and deliberately low — this asserts
    // that a strip exists, not how long it is, because a length written here
    // would be a number nobody could check and an edit nobody could refuse.
    expect(questionsOnTheReviewSurface().length).toBeGreaterThan(2);
  });
});
