/**
 * The review-list card leaves explaining to the detail panel.
 *
 * WHY THIS EXISTS
 *
 * "Explain this policy in plain words" is one reading of one policy, and the
 * detail panel already offers it twice over: a button in the panel's header and
 * an inline opener in its Overview pane. The review-list card — the card on the
 * left of the queue — used to mount a third copy of the very same button, with
 * the same props, reaching the same modal. Three doors to one room.
 *
 * A reader asked for the left card's copy to go. It is safe to remove because it
 * is a duplicate, not a distinction: the button and its props are identical on
 * both surfaces, and the list card only ever exists when the detail panel can be
 * summoned from it — opening the policy (its title, or its open control) brings
 * up the panel where the one Explain lives. Nothing is stranded; a shortcut is
 * withdrawn, not a route.
 *
 * WHAT THIS PINS
 *
 *   1. The list card offers no Explain button of its own, even when it has a
 *      persisted policy that could be explained. The absence is paired with a
 *      presence — the card still renders and still offers the way to open the
 *      policy — so this cannot pass merely because the card failed to draw.
 *   2. The detail panel still offers Explain for the same policy. The reading is
 *      not removed from the app, only from the card that duplicated it.
 *
 * Nothing here is a phrase from any document, and no count in it is a
 * measurement of one.
 */
import { afterEach, beforeAll, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import type { AssembledPolicy, CandidateRule, CanonicalRule } from "../api";
import { fromDraftRow } from "../policyCards";
import type { PolicyCard } from "../policyCards";
import { ActorProvider } from "../ActorContext";
import { PolicyReviewCard } from "./PolicyReviewCard";
import { PolicyDetailPanel } from "./PolicyDetailPanel";

const EXPLAIN = "policy-explain-button";

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

afterEach(() => cleanup());

// ── The list card (left of the queue) ──────────────────────────────────────
//
// One passage, one rule, and a persisted policy — so the old card would have
// drawn Explain (its only gate is the provision id).

function listRule(): CanonicalRule {
  return {
    rule_id: "r0",
    title: "A rule the card names",
    description: "The words the document uses for this rule.",
    evaluation_mode: "deterministic",
    condition: { type: "all", all: [] },
    effect: { type: "require_action", action: "an action" },
  } as unknown as CanonicalRule;
}

function listCard(provisionId: string | null): PolicyCard {
  const entry = {
    rule_id: "r0",
    evaluation_mode: "deterministic",
    ...fromDraftRow({
      id: "candidate-0",
      review_status: "pending",
      rule_type: "obligation",
      rule: listRule(),
    } as unknown as CandidateRule),
  };
  return {
    policy: {
      key: "a-key",
      heading: "A heading",
      heading_path: ["A heading"],
      topic_label: null,
      persisted: provisionId !== null,
      provision_id: provisionId,
      document_version_id: null,
      source_elements: "p1-E1",
      page: 1,
      rule_count: 1,
      passage_count: 1,
      route: "deterministic",
      passages: [{ rules: [{ rule_id: "r0" }] }],
      rules: [],
    },
    passages: [{ passage: { key: "passage-0" }, rules: [entry] }],
    rules: [entry],
    reviewableIds: [entry.recordId],
    allIds: [entry.recordId],
    hiddenByFilter: 0,
  } as unknown as PolicyCard;
}

function drawListCard(provisionId: string | null) {
  return render(
    <PolicyReviewCard
      card={listCard(provisionId)}
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

// ── The detail panel (right of the queue) ──────────────────────────────────
//
// The surface that keeps Explain. Built from the same kind of record, with a
// persisted policy, so the header draws its assistive group.

function canonical(ruleId: string): CanonicalRule {
  return {
    schema_version: "1.0",
    policy_set_id: "set",
    policy_version_id: "draft",
    rule_id: ruleId,
    rule_revision: 1,
    title: `Summary line for ${ruleId}`,
    description: `The words the document uses for ${ruleId}`,
    rule_type: "obligation",
    authority: { level: "ai_drafted", owner: "formulator", rank: 0 },
    scope: { jurisdictions: [], organizational_units: [], personas: [], processes: [] },
    condition: { type: "all", all: [] },
    attributes: { applies: [], outcome: [] },
    effect: { type: "require_action", action: "act" },
    required_facts: [],
    exceptions: [],
    priority: 0,
    effective_from: "2026-01-01",
    effective_to: null,
    machine_executable: false,
    ambiguity_status: "clear",
    review_status: "candidate",
    evidence: [],
    lineage: {
      extraction_run_id: "run",
      deployment_name: "model",
      prompt_version: "v1",
      parser_version: "v1",
      schema_version: "1.0",
    },
    category: "general",
    tags: [],
    group_label: "",
    related_rule_ids: [],
    is_explicit_override: false,
    supersedes_rule_ids: [],
    advice: [],
  } as CanonicalRule;
}

function candidate(ruleId: string): CandidateRule {
  return {
    id: `record-${ruleId}`,
    policy_set_id: "set",
    extraction_run_id: "run",
    rule_type: "obligation",
    revision: 1,
    review_status: "candidate",
    reviewed_by: null,
    reviewed_at: null,
    review_notes: null,
    published_version_id: null,
    created_at: "2026-01-01T00:00:00Z",
    delta_status: null,
    reworded: false,
    baseline_candidate_id: null,
    superseded_by_candidate_id: null,
    superseded_at: null,
    rule: canonical(ruleId),
  };
}

function detailCard(provisionId: string | null): PolicyCard {
  const row = candidate("R1");
  const entry = {
    rule_id: "R1",
    rule: row.rule,
    reviewStatus: row.review_status,
    recordId: row.id,
    candidate: row,
    evaluation_mode: "ai_ready" as const,
  };
  const policy = {
    key: "prov-1",
    heading: "A heading",
    heading_path: ["A heading"],
    persisted: provisionId !== null,
    provision_id: provisionId,
    document_version_id: "doc-1",
    source_elements: "p1-E1",
    page: 11,
    rule_count: 1,
    passage_count: 1,
    route: "read",
    passages: [],
    rules: [{ rule_id: "R1", title: canonical("R1").title }],
  } as unknown as AssembledPolicy;
  return {
    policy,
    passages: [
      {
        passage: { key: "p1-E1", source_elements: "p1-E1", page: 11, rule_count: 1, rules: [] },
        rules: [entry],
      },
    ],
    rules: [entry],
    hiddenByFilter: 0,
    reviewableIds: [row.id],
    allIds: [row.id],
    reviewStatuses: ["candidate"],
  } as unknown as PolicyCard;
}

function drawDetailPanel(provisionId: string | null) {
  return render(
    <ActorProvider>
      <PolicyDetailPanel
        card={detailCard(provisionId)}
        statusColor={() => "default"}
        statusLabel={() => "Pending"}
        onApprove={() => {}}
        onReject={() => {}}
      />
    </ActorProvider>,
  );
}

describe("the review-list card leaves explaining to the detail panel", () => {
  it("offers no Explain button of its own, even with a policy to explain", () => {
    const { container } = drawListCard("a-provision-id");

    // Paired with a presence: the card is on screen and still offers the way
    // in — its title opens the detail panel, where the one Explain lives. So a
    // null below means the duplicate was withdrawn, not that the card vanished.
    expect(screen.getByTestId("policy-card")).toBeTruthy();
    expect(container.querySelector(".policy-card__title")).toBeTruthy();

    // The third door is gone.
    expect(screen.queryByTestId(EXPLAIN)).toBeNull();
  });

  it("leaves the one Explain to the detail panel, which still offers it", () => {
    // The reading is not removed from the app — only from the card that
    // duplicated it. Opening the same policy still reaches it here.
    drawDetailPanel("a-provision-id");

    expect(screen.getByTestId(EXPLAIN)).toBeTruthy();
  });
});
