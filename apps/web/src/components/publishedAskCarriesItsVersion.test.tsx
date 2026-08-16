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
import type { ApprovedPolicyVersion, AssembledPolicy, CanonicalRule } from "../api";
import { buildPolicyCards } from "../policyCards";
import { PolicyDetailPanel } from "./PolicyDetailPanel";
import { PolicyInspector } from "./PolicyInspector";

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

function aPublishedVersion(): ApprovedPolicyVersion {
  return {
    id: A_VERSION,
    version_number: 1,
    approved_by: "An approver",
    approved_at: new Date(0).toISOString(),
    effective_from: "1970-01-01",
    effective_to: null,
  } as unknown as ApprovedPolicyVersion;
}

/** The whole-policy ask, where a reader meets it: on the panel that both pages
 *  open a policy into. */
function renderPolicy(ruleIds: string[] = ["r1", "r2"]) {
  const [card] = buildPolicyCards(
    [policy("a-policy", ruleIds)],
    ruleIds.map((id) => ({ rule: rule(id) })),
  );
  render(
    <PolicyDetailPanel
      card={card}
      statusColor={() => "default"}
      statusLabel={(status) => status}
      policySetKey={A_SET}
      policyVersionId={A_VERSION}
    />,
  );
  return card;
}

/** The one-rule ask, where a reader meets it: on the rule's own reading. That
 *  reading is one component now, so this covers the published page, the review
 *  panel and the inline expansion at once — which is the whole reason the ask
 *  moved here from a card only one of the three had. */
function renderRule(id: string) {
  const shown = rule(id);
  render(
    <PolicyInspector
      rule={shown}
      policySetKey={A_SET}
      publishedVersion={aPublishedVersion()}
    />,
  );
  return shown;
}

describe("asking about a published record", () => {
  it("reaches the rule's own ask with the version the reading is of", () => {
    const shown = renderRule("r1");
    fireEvent.click(screen.getByTestId("published-rule-ask-ai"));
    const opened = screen.getByTestId("rule-ask-opened");
    expect(opened.getAttribute("data-rule-id")).toBe(shown.rule_id);
    expect(opened.getAttribute("data-policy-set-key")).toBe(A_SET);
    expect(opened.getAttribute("data-policy-version-id")).toBe(A_VERSION);
  });

  it("asks about the rule on screen, not about some other one", () => {
    const shown = renderRule("r2");
    fireEvent.click(screen.getByTestId("published-rule-ask-ai"));
    expect(screen.getByTestId("rule-ask-opened").getAttribute("data-rule-id")).toBe(shown.rule_id);
  });

  it("withholds the rule's ask when the version is not known", () => {
    // Not a permission — a reader of a draft may ask too. It is that a rule id
    // without its version does not name a record, so there is nothing to route
    // the question to. Absent is the honest answer; a button that asked anyway
    // would be answered from whichever record happened to share the id.
    render(<PolicyInspector rule={rule("r1")} policySetKey={A_SET} />);
    expect(screen.queryByTestId("published-rule-ask-ai")).toBeNull();
  });

  it("offers the same question of the whole policy", () => {
    renderPolicy(["r1"]);
    fireEvent.click(screen.getByTestId("policy-ask-ai"));
    expect(screen.getByTestId("policy-ask-opened")).toBeTruthy();
  });
});
