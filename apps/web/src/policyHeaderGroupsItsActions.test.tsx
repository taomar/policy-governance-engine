/**
 * The policy header groups its controls by what pressing one does.
 *
 * THE FAILURE THIS EXISTS TO PREVENT
 *
 * A header gains a control at a time. Approve, reject, expand, hide, explain,
 * ask — appended in the order they were asked for, they become one row of six
 * equal-looking buttons in which the two that write to the record sit flush
 * against the two that move furniture. The reviewer's eye has nothing to sort
 * them by, and the two irreversible ones are no more prominent than the one
 * that collapses a panel.
 *
 * So the row is three labelled groups: the decisions, the two ways of asking,
 * and the panel's own chrome. This holds the grouping to that, and holds the
 * two assistive controls apart from each other by name — one answers a fixed
 * question nobody typed, the other answers the reviewer's own, and a reviewer
 * must be able to tell which is which without pressing either.
 *
 * Each absence is paired with a presence, because a header that failed to
 * render also has no ask button in it.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import type { AssembledPolicy, CandidateRule, CanonicalRule } from "./api";
import { ActorProvider } from "./ActorContext";
import type { PolicyCard } from "./policyCards";
import { PolicyDetailPanel } from "./components/PolicyDetailPanel";

beforeEach(() => {
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
  vi.unstubAllGlobals();
});

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

function cardFor(provisionId: string | null): PolicyCard {
  const row = candidate("R1");
  const entry = { rule_id: "R1", candidate: row, evaluation_mode: "ai_ready" as const };
  const policy = {
    key: "prov-1",
    heading: "Hiring relatives",
    heading_path: ["Recruitment", "Hiring relatives"],
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

function renderPanel(options: { provisionId?: string | null; policySetKey?: string | null; chrome?: boolean } = {}) {
  const { provisionId = "prov-1", chrome = true } = options;
  // Read through `in` rather than a default, so a test can say "no set key"
  // and mean it: a default parameter treats an explicit `undefined` as absent
  // and hands back the default, which is exactly the case under test.
  const policySetKey = "policySetKey" in options ? options.policySetKey : "staff-handbook";
  return render(
    <ActorProvider>
      <PolicyDetailPanel
        card={cardFor(provisionId)}
        statusColor={() => "default"}
        statusLabel={() => "Pending"}
        onApprove={() => {}}
        onReject={() => {}}
        policySetKey={policySetKey ?? undefined}
        actions={chrome ? <button type="button">Hide</button> : undefined}
      />
    </ActorProvider>,
  );
}

describe("the policy header sorts its controls by what they do", () => {
  it("asks about the whole policy from the header, in the group that decides nothing", () => {
    renderPanel();

    // Control: the header is on screen with its decisions.
    expect(screen.getByRole("button", { name: /Approve policy/ })).toBeTruthy();

    const ask = screen.getByTestId("policy-ask-ai");
    expect(ask).toBeTruthy();
    // One policy, one way to ask about the whole of it.
    expect(screen.getAllByTestId("policy-ask-ai")).toHaveLength(1);

    const decisions = screen.getByRole("group", { name: "Decide this policy" });
    const asking = screen.getByRole("group", { name: "Ask about this policy" });
    const chrome = screen.getByRole("group", { name: "This panel" });

    // The ask control is in the group that changes nothing, not beside the two
    // that write to the record and not among the panel's furniture.
    expect(asking.contains(ask)).toBe(true);
    expect(decisions.contains(ask)).toBe(false);
    expect(chrome.contains(ask)).toBe(false);

    expect(within(decisions).getByRole("button", { name: /Approve policy/ })).toBeTruthy();
    expect(within(decisions).getByRole("button", { name: /Reject policy/ })).toBeTruthy();
    expect(within(chrome).getByRole("button", { name: "Hide" })).toBeTruthy();
  });

  it("keeps the two ways of asking together, and tells them apart by name", () => {
    renderPanel();

    const asking = screen.getByRole("group", { name: "Ask about this policy" });
    const explain = within(asking).getByTestId("policy-explain-button");
    const ask = within(asking).getByTestId("policy-ask-ai");

    // Siblings: same group, same size, next to each other.
    expect(explain).toBeTruthy();
    expect(ask).toBeTruthy();

    // …and not two spellings of one idea. Whatever either is called, a reviewer
    // must not read the same words twice.
    const explainName = (explain.textContent ?? "").trim().toLowerCase();
    const askName = (ask.textContent ?? "").trim().toLowerCase();
    expect(explainName.length).toBeGreaterThan(0);
    expect(askName.length).toBeGreaterThan(0);
    expect(explainName).not.toBe(askName);
  });

  it("draws no ask control when nothing can say which set the question is about", () => {
    renderPanel({ policySetKey: null });

    // Control: the header rendered, and the other reading is still offered.
    expect(screen.getByRole("button", { name: /Approve policy/ })).toBeTruthy();
    expect(screen.getByTestId("policy-explain-button")).toBeTruthy();

    // A button that could only fail when pressed is not drawn.
    expect(screen.queryByTestId("policy-ask-ai")).toBeNull();
  });

  it("draws no group at all when nothing in it can be offered", () => {
    renderPanel({ provisionId: null, policySetKey: null });

    // Control: the header rendered.
    expect(screen.getByRole("button", { name: /Approve policy/ })).toBeTruthy();

    // An empty group would leave a labelled region and a separator rule with
    // nothing inside them.
    expect(screen.queryByRole("group", { name: "Ask about this policy" })).toBeNull();
    expect(screen.getByRole("group", { name: "Decide this policy" })).toBeTruthy();
  });
});

