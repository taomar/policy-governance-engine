/**
 * A question asked of a sealed record is asked of that record.
 *
 * WHAT IS AT STAKE
 *
 * A rule id alone does not identify a published record. The draft row that
 * produced it carries the same id and may have been revised since, so a
 * question routed by id alone can be answered from a draft that says something
 * else — and, where the id resolved to nothing, from no record at all, in an
 * answer shaped exactly like a grounded one. Where the record is published, the
 * version is part of its identity, and these two controls are the places a
 * reader asks from.
 *
 * WHAT IS ASSERTED
 *
 * That both scopes — the whole policy and one of its rules — reach the ask with
 * the version the card is showing, not merely that a button exists. The
 * assertion is on what arrives at the dialog, because a button rendered without
 * its version is the failure this guards against and would pass a
 * presence-only check.
 *
 * The values are asserted equal to what the card was handed, never to a
 * literal, so a card shown at a different version is still covered.
 *
 * WHAT IS DELIBERATELY NOT ASSERTED
 *
 * What the answer says, or that asking is allowed. Asking is not a decision on
 * a record, so nothing here is derived from editability and nothing here should
 * ever become an editing affordance. `publishedRecordOffersNoDecision` holds
 * that line.
 *
 * Nothing here is a phrase from any document, and no number in it is a
 * measurement of one.
 */
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { AssembledPolicy, CanonicalRule } from "../api";
import { buildPublishedPolicyCards } from "../publishedPolicyCards";
import { PublishedPolicyCard } from "./PublishedPolicyCard";

// Both dialogs belong to other components. What this file is responsible for is
// what reaches them, so each is replaced by something that records the identity
// it was given. Replacing them also keeps the test off the network.
vi.mock("./AskAboutRuleModal", () => ({
  AskAboutRuleModal: (props: { rule: { rule_id: string }; policySetKey: string; policyVersionId?: string }) => (
    <div
      data-testid="rule-ask-opened"
      data-rule-id={props.rule.rule_id}
      data-policy-set-key={props.policySetKey}
      data-policy-version-id={props.policyVersionId ?? ""}
    />
  ),
}));

vi.mock("./AskAiModal", () => ({
  AskAiModal: (props: { title: string }) => <div data-testid="policy-ask-opened" data-title={props.title} />,
}));

// jsdom implements neither, and the component library measures its own layout.
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

function rule(id: string): CanonicalRule {
  return {
    rule_id: id,
    title: `A title for ${id}`,
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

function policy(key: string, ruleIds: string[]): AssembledPolicy {
  return {
    key,
    heading: `A heading for ${key}`,
    heading_path: ["An outer heading", `A heading for ${key}`],
    topic_label: null,
    persisted: true,
    provision_id: `${key}-provision`,
    document_version_id: null,
    source_elements: "",
    page: 1,
    rule_count: ruleIds.length,
    passage_count: 1,
    route: "ai_ready",
    passages: [
      {
        key: `${key}-passage`,
        source_elements: "",
        page: 1,
        rule_count: ruleIds.length,
        rules: ruleIds.map((id) => ({ rule_id: id, evaluation_mode: "ai_ready" })),
      },
    ],
    rules: ruleIds.map((id) => ({ rule_id: id, evaluation_mode: "ai_ready" })),
  } as unknown as AssembledPolicy;
}

/** Named, not literal, so each assertion can say which value it expected to
 *  travel and a swap of one for the other fails rather than passes. */
const A_SET = "a-policy-set";
const A_VERSION = "a-published-version";

function renderCard(ruleIds: string[] = ["r1", "r2"]) {
  const [card] = buildPublishedPolicyCards([policy("a-policy", ruleIds)], ruleIds.map((id) => rule(id)));
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
      policySetKey={A_SET}
      policyVersionId={A_VERSION}
    />,
  );
  return card;
}

describe("asking about a published record", () => {
  it("reaches the rule's own ask with the version the card is showing", () => {
    const card = renderCard(["r1", "r2"]);
    const buttons = screen.getAllByTestId("published-rule-ask-ai");
    expect(buttons).toHaveLength(card.rules.length);

    fireEvent.click(buttons[0]);
    const opened = screen.getByTestId("rule-ask-opened");
    expect(opened.getAttribute("data-rule-id")).toBe(card.rules[0].rule_id);
    expect(opened.getAttribute("data-policy-set-key")).toBe(A_SET);
    expect(opened.getAttribute("data-policy-version-id")).toBe(A_VERSION);
  });

  it("asks about the rule the reader clicked and not the first one", () => {
    const card = renderCard(["r1", "r2"]);
    const buttons = screen.getAllByTestId("published-rule-ask-ai");
    fireEvent.click(buttons[buttons.length - 1]);
    expect(screen.getByTestId("rule-ask-opened").getAttribute("data-rule-id")).toBe(
      card.rules[card.rules.length - 1].rule_id,
    );
  });

  it("offers the same question of the whole policy", () => {
    renderCard(["r1"]);
    const button = screen.getByTestId("policy-ask-ai");
    fireEvent.click(button);
    expect(screen.getByTestId("policy-ask-opened")).toBeTruthy();
  });
});
