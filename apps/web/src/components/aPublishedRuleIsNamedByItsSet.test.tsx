/**
 * A RULE PUBLISHED WITHOUT A DRAFT ROW IS STILL NAMED.
 *
 * WHAT IS AT STAKE
 *
 * This app generates a short handle for a rule so a reader can find it again
 * and refer to it out loud. A rule is addressed by one of two handles, and
 * which one depends on the record rather than on the page: a draft row under
 * review is addressed by its own row id; a rule inside a sealed version has no
 * such row and is addressed by the set it was published in together with its
 * rule id. The lookup accepts both, keeps them apart deliberately, and answers
 * nothing at all when asked the wrong way round.
 *
 * Both published readings — the card's rule rows and the roster in the policy's
 * Overview — used to ask only the first way. A sealed rule has no draft row, so
 * the guard was simply never true and the name never rendered. Nothing appeared
 * to be wrong: a rule with no generated name and a rule whose name was asked
 * for down a dead address look identical, which is exactly why this file exists
 * rather than a manual check.
 *
 * WHAT IS ASSERTED
 *
 * That a card carrying its set asks for its sealed rules by (set, rule id) and
 * renders what comes back, on both readings; that a card carrying no set asks
 * nothing at all rather than guessing at an address; and that a draft row is
 * still addressed by its row id, because the fix must not swap one dead address
 * for another.
 *
 * WHY IT FAILS WITHOUT THE CHANGE
 *
 * Before the card carried its set, the only way to reach these renderings was a
 * prop threaded from the page, which the Overview roster never received at all.
 * Remove `policy_set_key` from the card and every assertion below that a name
 * appears fails, because nothing is ever asked for.
 *
 * Nothing here is a phrase from any document, and no number in it is a
 * measurement of one.
 */
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import type { AssembledPolicy, CanonicalRule } from "../api";

const ruleNames = vi.fn();

vi.mock("../api", async () => {
  const actual = await vi.importActual<typeof import("../api")>("../api");
  return { ...actual, aiApi: { ...actual.aiApi, ruleNames } };
});

const { buildPolicyCards } = await import("../policyCards");
const { forgetRuleNames } = await import("./RuleName");
const { PolicyReviewCard } = await import("./PolicyReviewCard");
const { PolicyOverviewPane, policyRecord } = await import("./policyTabPanes");

const A_SET = "a-set";

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

beforeEach(() => {
  forgetRuleNames();
  ruleNames.mockReset();
  ruleNames.mockResolvedValue({ names: {} });
});

afterEach(() => {
  cleanup();
});

function rule(ruleId: string): CanonicalRule {
  return {
    schema_version: "1.0",
    policy_set_id: A_SET,
    policy_version_id: "a-version",
    rule_id: ruleId,
    rule_revision: 1,
    title: `Title for ${ruleId}`,
    description: `Description for ${ruleId}`,
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

/** A card of sealed rules, as the published page builds it. */
function sealedCard(ruleIds: string[], policySetKey: string | null) {
  return buildPolicyCards(
    [policy(ruleIds)],
    ruleIds.map((id) => ({ rule: rule(id) })),
    policySetKey,
  )[0];
}

/** A card of draft rows, as the review queue builds it. */
function draftCard(ruleIds: string[], policySetKey: string | null) {
  return buildPolicyCards(
    [policy(ruleIds)],
    ruleIds.map((id) => ({
      rule: rule(id),
      id: `row-for-${id}`,
      review_status: "candidate",
    })),
    policySetKey,
  )[0];
}

function renderCard(card: ReturnType<typeof sealedCard>) {
  return render(
    <PolicyReviewCard
      card={card}
      selected={false}
      indeterminate={false}
      open
      statusColor={() => "default"}
      statusLabel={(status) => status}
      findingsFor={() => 0}
      onOpen={() => {}}
      onSelectRule={() => {}}
      selectedRuleId={null}
      documentName={null}
    />,
  );
}

function renderOverview(card: ReturnType<typeof sealedCard>) {
  return render(<PolicyOverviewPane record={policyRecord(card)} />);
}

describe("the card carries the set, so nothing has to be told it twice", () => {
  it("puts the set the cards were built for on every card", () => {
    const card = sealedCard(["r1"], A_SET);
    expect(card.policy_set_key).toBe(A_SET);
  });

  it("says a set was never given as absent, not as an empty one", () => {
    // Absent and empty are different facts, and only absent means "ask
    // nothing". An empty string would be an address, and a wrong one.
    const card = sealedCard(["r1"], null);
    expect(card.policy_set_key).toBeNull();
  });

  it("keeps the set off the logic shape, which both surfaces must share", async () => {
    // The shape is the thing asserted identical across review and published.
    // Where a record came from is a fact about the record, not about its logic,
    // and putting it in the shape would make the two surfaces differ by
    // construction.
    const { policyLogicShape } = await import("../policyLogicShape");
    const shape = policyLogicShape(sealedCard(["r1"], A_SET));
    expect(JSON.stringify(shape)).not.toContain(A_SET);
  });
});

describe("a sealed rule on the card is named by its set and its rule id", () => {
  it("asks that way round, and renders the answer", async () => {
    ruleNames.mockResolvedValue({
      names: {},
      names_by_rule_id: {
        r1: { text: "Tide register upkeep", unavailable_code: null, generated: true },
      },
    });

    renderCard(sealedCard(["r1"], A_SET));

    await waitFor(() => expect(ruleNames).toHaveBeenCalledTimes(1));
    expect(ruleNames.mock.calls[0][1]).toEqual({ policySetKey: A_SET, ruleIds: ["r1"] });
    await waitFor(() => expect(screen.getAllByTestId("rule-name").length).toBeGreaterThan(0));
    expect(screen.getAllByTestId("rule-name")[0].textContent).toMatch(/Tide register upkeep/);
  });

  it("asks nothing at all when the card was not told which set it belongs to", async () => {
    renderCard(sealedCard(["r1"], null));

    // Half an address is not an address. Sending a rule id as though it were a
    // draft row id is the failure this whole file is about, and it must not be
    // reintroduced as the "no set" fallback.
    await Promise.resolve();
    expect(ruleNames).not.toHaveBeenCalled();
    expect(screen.queryAllByTestId("rule-name")).toHaveLength(0);
  });

  it("still addresses a draft row by its row id, set or no set", async () => {
    ruleNames.mockResolvedValue({
      names: { "row-for-r1": { text: "A drafted handle", unavailable_code: null, generated: true } },
    });

    renderCard(draftCard(["r1"], A_SET));

    await waitFor(() => expect(ruleNames).toHaveBeenCalledTimes(1));
    expect(ruleNames.mock.calls[0][0]).toEqual(["row-for-r1"]);
    expect(ruleNames.mock.calls[0][1]).toBeUndefined();
    await waitFor(() => expect(screen.getAllByTestId("rule-name").length).toBeGreaterThan(0));
    expect(screen.getAllByTestId("rule-name")[0].textContent).toMatch(/A drafted handle/);
  });
});

describe("the roster in a policy's overview names its rules the same way", () => {
  // A second reading of the same rules, and the one that had no way to ask at
  // all before the set rode the record: it is given a policy, not a page.
  it("asks by set and rule id for a sealed record, and renders the answer", async () => {
    ruleNames.mockResolvedValue({
      names: {},
      names_by_rule_id: {
        r1: { text: "Tide register upkeep", unavailable_code: null, generated: true },
      },
    });

    const { container } = renderOverview(sealedCard(["r1"], A_SET));

    await waitFor(() => expect(ruleNames).toHaveBeenCalledTimes(1));
    expect(ruleNames.mock.calls[0][1]).toEqual({ policySetKey: A_SET, ruleIds: ["r1"] });
    await waitFor(() => expect(within(container).getAllByTestId("rule-name").length).toBe(1));
    expect(within(container).getAllByTestId("rule-name")[0].textContent).toMatch(
      /Tide register upkeep/,
    );
  });

  it("asks nothing when the record does not say which set it belongs to", async () => {
    renderOverview(sealedCard(["r1"], null));

    await Promise.resolve();
    expect(ruleNames).not.toHaveBeenCalled();
    expect(screen.queryAllByTestId("rule-name")).toHaveLength(0);
  });

  it("carries the set onto the record the panes read", () => {
    expect(policyRecord(sealedCard(["r1"], A_SET)).policySetKey).toBe(A_SET);
    expect(policyRecord(sealedCard(["r1"], null)).policySetKey).toBeNull();
  });
});
