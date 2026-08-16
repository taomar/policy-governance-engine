/**
 * A published record offers no way to change what the version already decided.
 *
 * WHAT IS AT STAKE
 *
 * A published version is a sealed snapshot: the server refuses an edit or a
 * review decision on anything inside one, and returns a conflict if asked. An
 * interface that draws Approve, Reject or Edit next to a published record is
 * therefore not merely wrong about what will happen — it invites the user to
 * make a judgement that has already been made and sealed, and then discards
 * their click. The published page is now built from the same reading the review
 * queue uses, which is exactly the circumstance in which a decision control can
 * arrive by resemblance rather than by intent.
 *
 * WHAT IS ASSERTED
 *
 * That a card built from a published version renders no affordance that would
 * record a decision or rewrite the record — and that this is checked by looking
 * for the words a user would actually see, so a control renamed but not removed
 * still fails.
 *
 * AND WHAT MUST SURVIVE
 *
 * `Revise` is not an exception to the above; it is the other side of it. It
 * does not touch the published record at all — it opens a new draft and leaves
 * the version standing, which is precisely the route the server names when it
 * refuses an edit. Asserting only "no editing controls" would let someone
 * satisfy this file by deleting the one control that makes a sealed version
 * workable, so its presence is asserted too.
 *
 * Nothing here is a phrase from any document, and no number in it is a
 * measurement of one.
 */
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import type { AssembledPolicy, CanonicalRule } from "../api";
import { buildPolicyCards } from "../policyCards";
import { PolicyReviewCard } from "./PolicyReviewCard";
import { PolicyDetailPanel } from "./PolicyDetailPanel";

// jsdom implements neither, and the component library measures its own layout.
// Neither stub affects what is asserted here, which is what the card renders.
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

/** Every word that would tell a user they may decide or rewrite this record.
 *  Matched case-insensitively against rendered text, so a control that is
 *  restyled or moved still trips it. */
const DECISION_WORDS = [
  /approve/i,
  /reject/i,
  /request changes/i,
  /send back/i,
  /^edit$/i,
  /draft candidate/i,
  /new candidate rule/i,
];

function rule(ruleId: string, overrides: Partial<CanonicalRule> = {}): CanonicalRule {
  return {
    schema_version: "1.0",
    policy_set_id: "a-set",
    policy_version_id: "a-version",
    rule_id: ruleId,
    rule_revision: 1,
    title: `Title for ${ruleId}`,
    description: `Description for ${ruleId}`,
    rule_type: "obligation",
    authority: { owner: "an-owner", source: "", reference: "" },
    scope: { jurisdictions: [], organizational_units: [], processes: [] },
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

function policy(ruleIds: string[], statedRuleCount = ruleIds.length): AssembledPolicy {
  return {
    key: "a-policy-key",
    heading: "A heading",
    heading_path: ["An outer heading", "A heading"],
    topic_label: null,
    persisted: true,
    provision_id: "a-provision-id",
    document_version_id: null,
    source_elements: "",
    page: 1,
    rule_count: statedRuleCount,
    passage_count: 1,
    route: "ai_ready",
    passages: [
      {
        key: "a-passage-key",
        source_elements: "",
        page: 1,
        rule_count: ruleIds.length,
        rules: ruleIds.map((id) => ({ rule_id: id, evaluation_mode: "ai_ready" })),
      },
    ],
    rules: ruleIds.map((id) => ({ rule_id: id, evaluation_mode: "ai_ready" })),
  } as unknown as AssembledPolicy;
}

/**
 * The published surface as the page actually draws it: the card, and the panel
 * that opens beside it.
 *
 * Both, because there is no longer a component that is "the published card" —
 * there is the one card the review queue draws and the one panel it opens, and
 * what makes this surface read-only is what the *record* says, plus the handlers
 * this page withholds. Asserting over the card alone would let a decision
 * control reappear in the panel and pass.
 */
function renderCard({
  ruleIds = ["r1", "r2"],
  statedRuleCount,
  onRevise,
}: {
  ruleIds?: string[];
  statedRuleCount?: number;
  onRevise?: (rule: CanonicalRule) => void;
} = {}) {
  const cards = buildPolicyCards(
    [policy(ruleIds, statedRuleCount)],
    ruleIds.map((id) => ({ rule: rule(id) })),
    // The set rides the card, so both the card and the panel address these
    // sealed rules the one way.
    "a-set",
  );
  const card = cards[0];
  const statusColor = () => "purple";
  const statusLabel = (status: string) => status;
  return render(
    <>
      <PolicyReviewCard
        card={card}
        selected={false}
        indeterminate={false}
        open
        statusColor={statusColor}
        statusLabel={statusLabel}
        findingsFor={() => 0}
        onToggleSelect={() => {}}
        onOpen={() => {}}
        onSelectRule={() => {}}
        selectedRuleId={null}
        documentName={null}
      />
      <PolicyDetailPanel
        card={card}
        statusColor={statusColor}
        statusLabel={statusLabel}
        policySetKey="a-set"
        ruleActions={(ruleId) => {
          const entry = card.rules.find((r) => r.rule_id === ruleId);
          if (!entry) return {};
          return onRevise ? { revise: () => onRevise(entry.rule) } : {};
        }}
      />
    </>,
  );
}

afterEach(() => {
  cleanup();
});

/**
 * The kebab on a rule row, reached the way a reader reaches it.
 *
 * The panel opens on its summary; the rules themselves are one tab along. That
 * is a navigation, not a fact hidden behind a click — every fact needed to
 * judge this record is on the summary already. What is behind the tab is the
 * per-rule *actions*, and an action is not a fact.
 */
function ruleKebab(ruleTitle = "Title for r1") {
  fireEvent.click(screen.getByRole("tab", { name: "Reading" }));
  return screen.getByRole("button", { name: `More actions for ${ruleTitle}` });
}

describe("a published policy on the page that reads published versions", () => {
  it("draws nothing that would record a decision or rewrite the record", () => {
    const { container } = renderCard({ onRevise: () => {} });
    const text = container.textContent ?? "";
    for (const word of DECISION_WORDS) {
      expect(text).not.toMatch(word);
    }
    // Checked separately from the text sweep because a control can carry its
    // words in an accessible name rather than in its label.
    for (const control of Array.from(container.querySelectorAll("button"))) {
      const name = `${control.textContent ?? ""} ${control.getAttribute("aria-label") ?? ""}`;
      for (const word of DECISION_WORDS) {
        expect(name).not.toMatch(word);
      }
    }
  });

  it("offers no selection that would gather records for a decision", () => {
    // The one checkbox on the card gathers records for an export, which is a
    // read. Its accessible description has to say so, or it reads as the
    // review queue's control in a place where reviewing is impossible.
    const { container } = renderCard();
    const boxes = container.querySelectorAll("input[type=checkbox]");
    expect(boxes.length).toBeLessThanOrEqual(1);
  });

  it("keeps the one route a sealed version leaves open", () => {
    // Asserted so that "remove every editing control" cannot be satisfied by
    // removing this one: revising does not change the published record, it
    // starts a new draft beside it.
    renderCard({ onRevise: () => {} });
    // Opened, because a kebab that exists proves nothing about what is in it.
    fireEvent.click(ruleKebab());
    const offered = within(screen.getByRole("menu"))
      .getAllByRole("menuitem")
      .map((item) => item.getAttribute("data-action"));
    expect(offered).toContain("revise");
  });

  it("does not invent an action when no revision can be started from this version", () => {
    // An older version cannot be revised. The kebab still exists — copying an
    // id and reading a history are reads — but it must not offer a route the
    // caller did not supply.
    renderCard();
    fireEvent.click(ruleKebab());
    const offered = within(screen.getByRole("menu"))
      .getAllByRole("menuitem")
      .map((item) => item.getAttribute("data-action"));
    expect(offered).not.toContain("revise");
  });

  it("offers no decision on the policy either, whatever the caller wires", () => {
    // The policy-scope menu is a second place a decision control could arrive,
    // and it is drawn even when no rule row is on screen.
    renderCard({ onRevise: () => {} });
    fireEvent.click(screen.getByRole("button", { name: "More actions for A heading" }));
    const offered = within(screen.getByRole("menu"))
      .getAllByRole("menuitem")
      .map((item) => item.getAttribute("data-action"));
    for (const forbidden of [
      "edit",
      "suggest-rewrite",
      "request-changes",
      "override-approve",
      "override-reject",
    ]) {
      expect(offered).not.toContain(forbidden);
    }
  });
});

describe("a published policy is never shown as less than it is", () => {
  it("says so, with the numbers, when the current narrowing hides part of it", () => {
    renderCard({ ruleIds: ["r1"], statedRuleCount: 3 });
    const partial = screen.getByTestId("policy-card-partial");
    // The words matter as much as the numbers: a reader seeing one rule under a
    // heading has no way to know the policy states more unless the card says
    // it. Both numbers are asserted rather than the difference between them,
    // because that is what the one surviving card prints — a reader is told
    // how much is here and how much the policy states, and is not asked to
    // trust a subtraction this system performed out of sight.
    expect(partial.textContent).toMatch(/\b1\b/);
    expect(partial.textContent).toMatch(/\b3\b/);
    expect(partial.textContent).toMatch(/rules this policy\s+states/i);
  });

  it("stays silent when it is showing the whole policy", () => {
    renderCard({ ruleIds: ["r1", "r2"] });
    expect(screen.queryByTestId("policy-card-partial")).toBeNull();
  });

  it("shows every rule of the policy together, under the document's own heading", () => {
    renderCard({ ruleIds: ["r1", "r2", "r3"] });
    // The failure this replaces split one policy's rules across several
    // headings this system invented. All of them must be on one card.
    expect(within(screen.getByTestId("policy-card")).getAllByTestId("policy-card-rule")).toHaveLength(3);
    expect(screen.getAllByTestId("policy-card")).toHaveLength(1);
  });
});
