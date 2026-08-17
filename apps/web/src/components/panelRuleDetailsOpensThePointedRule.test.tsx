/**
 * The detail panel's per-rule "Details" opens the rule the reader pointed at.
 *
 * WHAT IS AT STAKE
 *
 * A policy opens in the detail panel; its Overview lists the rules it holds, and
 * each row offers a way onward to that rule's own page. The panel does not own
 * navigation — a host surface does — so the row's control is drawn only when the
 * host wires a handler to it, and it hands that handler the rule the row was
 * built from. The hazard this file guards is a specific one: `rule_id` is a hash
 * of a rule's content, so two rules a passage states in identical words carry
 * one id. A hop that answered a click by re-reading a rule from its id could
 * therefore open a different rule than the one clicked. The panel must forward
 * the rule it was handed, unchanged, and never reduce a click to an id and look
 * a rule back up.
 *
 * WHAT IS ASSERTED
 *
 *  - The Details control reaches the panel's Overview roster and, when clicked,
 *    calls the host's handler exactly once with the rule that row carries — by
 *    reference, not by a value re-derived from an id.
 *  - Opening a rule is a read: the control is offered, and behaves, the same on
 *    a sealed published record as on a draft under review. It is not gated on
 *    any status or permission.
 *  - When the host wires no handler, no Details control is drawn — the rules are
 *    still shown, but a way onward that reaches nothing is not, because an
 *    affordance that leads nowhere is worse than none.
 *  - When two rules share one content-hash id, clicking the second row hands
 *    back the second rule, not the first that the shared id resolves to.
 *
 * Nothing here is a phrase from any document, and no number in it is a
 * measurement of one.
 */
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import type { AssembledPolicy, CanonicalRule } from "../api";
import { buildPolicyCards } from "../policyCards";
import { PolicyDetailPanel } from "./PolicyDetailPanel";

type Card = ReturnType<typeof buildPolicyCards>[number];

// jsdom implements neither, and the component library measures its own layout.
// Neither stub affects what is asserted here, which is which rule a click opens.
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
});

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

function policy(ruleIds: string[]): AssembledPolicy {
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
    rule_count: ruleIds.length,
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

/** A published, sealed policy: the record carries no draft row, so `place()`
 *  leaves its candidate undefined and the rows read as published. */
function sealedCard(ruleIds: string[]): Card {
  return buildPolicyCards(
    [policy(ruleIds)],
    ruleIds.map((id) => ({ rule: rule(id) })),
    "a-set",
  )[0];
}

/** A draft policy under review: each input carries both an id and a review
 *  status, which is exactly what makes `place()` treat the row as a live
 *  candidate rather than a sealed rule. */
function draftCard(ruleIds: string[]): Card {
  return buildPolicyCards(
    [policy(ruleIds)],
    ruleIds.map((id) => ({
      rule: rule(id, { review_status: "pending_review" }),
      id: `draft-${id}`,
      review_status: "pending_review",
    })),
    "a-set",
  )[0];
}

/** The panel as the published surface draws it, given only the props that bear
 *  on which rule a Details click opens. */
function renderPanel(card: Card, onSelectRule?: (rule: CanonicalRule) => void) {
  return render(
    <PolicyDetailPanel
      card={card}
      statusColor={() => "purple"}
      statusLabel={(status) => status}
      policySetKey="a-set"
      onSelectRule={onSelectRule}
    />,
  );
}

describe("the detail panel routes a rule's Details to the surface that opens rules", () => {
  it("hands back the exact rule the clicked row was built from, not one re-read from an id", () => {
    const onSelectRule = vi.fn();
    const card = sealedCard(["r1", "r2"]);
    renderPanel(card, onSelectRule);

    // One way onward per rule, drawn because a handler reached the roster.
    const details = screen.getAllByTestId("overview-rule-details");
    expect(details).toHaveLength(2);

    // The reader points at the second rule.
    fireEvent.click(details[1]);

    expect(onSelectRule).toHaveBeenCalledTimes(1);
    // The rule object the row carried, by reference. If a hop had reduced the
    // click to `rule_id` and resolved a rule from it, this would be a different
    // object with the same fields, and `toBe` would fail.
    expect(onSelectRule.mock.calls[0][0]).toBe(card.rules[1].rule);
    expect(onSelectRule.mock.calls[0][0].rule_id).toBe("r2");
  });

  it("draws no Details control when the surface wires no handler", () => {
    const card = sealedCard(["r1", "r2"]);
    renderPanel(card);

    // The rules are shown — the roster is present — but the way onward is not,
    // because a control that reaches nothing is worse than its absence.
    expect(screen.getByTestId("overview-roster")).toBeTruthy();
    expect(screen.queryAllByTestId("overview-rule-details")).toHaveLength(0);
  });
});

describe("opening a rule is a read, offered the same on a sealed record as on a draft", () => {
  it("opens a rule from a published, sealed policy", () => {
    const onSelectRule = vi.fn();
    const card = sealedCard(["r1", "r2"]);
    // A sealed row reads as published and carries no draft candidate.
    expect(card.rules[0].reviewStatus).toBe("published");
    expect(card.rules[0].candidate).toBeUndefined();

    renderPanel(card, onSelectRule);
    fireEvent.click(screen.getAllByTestId("overview-rule-details")[0]);

    expect(onSelectRule).toHaveBeenCalledTimes(1);
    expect(onSelectRule.mock.calls[0][0]).toBe(card.rules[0].rule);
  });

  it("opens a rule from a draft under review the same way, and is not gated on status", () => {
    const onSelectRule = vi.fn();
    const card = draftCard(["r1", "r2"]);
    // This one is a live draft: a candidate row, a status that is not published.
    expect(card.rules[0].candidate).toBeDefined();
    expect(card.rules[0].reviewStatus).not.toBe("published");

    renderPanel(card, onSelectRule);
    // Present on the draft exactly as on the sealed record — opening a rule is a
    // read, so nothing about the record's editability may withhold it.
    const details = screen.getAllByTestId("overview-rule-details");
    expect(details).toHaveLength(2);

    fireEvent.click(details[0]);
    expect(onSelectRule).toHaveBeenCalledTimes(1);
    expect(onSelectRule.mock.calls[0][0]).toBe(card.rules[0].rule);
  });
});

describe("it opens the rule pointed at, never a namesake that shares its content-hash id", () => {
  it("hands back the clicked row's own rule when two rules share one rule_id", () => {
    // `rule_id` is a hash of a rule's content, so two rules stated in identical
    // words carry one id. Build exactly that pair — distinct rules, one id — the
    // way a card would hold them, then click the second. A hop that resolved the
    // click by id would open the first of the pair no matter which was clicked.
    const twinA = rule("dup", { title: "The first of the pair" });
    const twinB = rule("dup", { title: "The second of the pair" });
    const base = sealedCard(["dup"]);
    const proto = base.rules[0];
    const entryA = { ...proto, rule: twinA };
    const entryB = { ...proto, rule: twinB };
    const card: Card = {
      ...base,
      rules: [entryA, entryB],
      passages: base.passages.map((block, index) =>
        index === 0 ? { ...block, rules: [entryA, entryB] } : block,
      ),
    };

    const onSelectRule = vi.fn();
    renderPanel(card, onSelectRule);

    const rows = screen.getAllByTestId("overview-rule");
    expect(rows).toHaveLength(2);

    // Reach the second row by what it shows, not by its position.
    const secondRow = rows.find((row) => within(row).queryByText(/second of the pair/i));
    expect(secondRow).toBeTruthy();
    fireEvent.click(within(secondRow!).getByTestId("overview-rule-details"));

    expect(onSelectRule).toHaveBeenCalledTimes(1);
    // The second rule, by reference — not `twinA`, which the shared id resolves
    // to first.
    expect(onSelectRule.mock.calls[0][0]).toBe(twinB);
    expect(onSelectRule.mock.calls[0][0].title).toBe("The second of the pair");
  });
});
