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
import { buildPublishedPolicyCards } from "../publishedPolicyCards";
import { PublishedPolicyCard } from "./PublishedPolicyCard";

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

function renderCard({
  ruleIds = ["r1", "r2"],
  statedRuleCount,
  onRevise,
}: {
  ruleIds?: string[];
  statedRuleCount?: number;
  onRevise?: (rule: CanonicalRule) => void;
} = {}) {
  const cards = buildPublishedPolicyCards(
    [policy(ruleIds, statedRuleCount)],
    ruleIds.map((id) => rule(id)),
  );
  return render(
    <PublishedPolicyCard
      card={cards[0]}
      open={false}
      selectedForExport={false}
      indeterminateForExport={false}
      onToggleExportSelection={() => {}}
      onOpen={() => {}}
      onSelectRule={() => {}}
      onToggleRule={() => {}}
      onRevise={onRevise}
      onViewHistory={() => {}}
      policySetKey="a-set"
      policyVersionId="a-version"
    />,
  );
}

afterEach(() => {
  cleanup();
});

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
    const kebabs = screen.getAllByTestId("record-actions-menu");
    expect(kebabs.length).toBeGreaterThan(0);
    // Opened, because a kebab that exists proves nothing about what is in it.
    fireEvent.click(kebabs[0]);
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
    const kebabs = screen.getAllByTestId("record-actions-menu");
    expect(kebabs.length).toBeGreaterThan(0);
    fireEvent.click(kebabs[0]);
    const offered = within(screen.getByRole("menu"))
      .getAllByRole("menuitem")
      .map((item) => item.getAttribute("data-action"));
    expect(offered).not.toContain("revise");
  });
});

describe("a published policy is never shown as less than it is", () => {
  it("says so, with the number, when the current narrowing hides part of it", () => {
    renderCard({ ruleIds: ["r1"], statedRuleCount: 3 });
    const partial = screen.getByTestId("policy-card-partial");
    // The words matter as much as the number: a reader seeing one rule under a
    // heading has no way to know two more exist unless the card says it.
    expect(partial.textContent).toMatch(/2/);
    expect(partial.textContent).toMatch(/more rules of this policy/i);
  });

  it("stays silent when it is showing the whole policy", () => {
    renderCard({ ruleIds: ["r1", "r2"] });
    expect(screen.queryByTestId("policy-card-partial")).toBeNull();
  });

  it("shows every rule of the policy together, under the document's own heading", () => {
    renderCard({ ruleIds: ["r1", "r2", "r3"] });
    // The failure this replaces split one policy's rules across several
    // headings this system invented. All of them must be on one card.
    expect(screen.getAllByTestId("policy-card-rule")).toHaveLength(3);
    expect(screen.getAllByTestId("published-policy-card")).toHaveLength(1);
  });
});
