/**
 * A published policy is told the same way, and told whole.
 *
 * WHAT IS AT STAKE
 *
 * Two surfaces show the same policies: the queue, before a decision, and the
 * published page, after one. They were built at different times and drifted, so
 * a reviewer who approved something on one surface met a materially poorer
 * account of it on the other — fewer tabs, a different arrangement, and a card
 * that could be showing part of a policy while looking exactly like a whole
 * one. Closing that gap by copying the queue's components would have produced
 * the same drift again within weeks, so the panes are shared and each surface
 * hands them the same neutral view of a record.
 *
 * WHAT IS ASSERTED
 *
 * Three things, each of which fails if the parity is undone:
 *
 *  - Every question the queue answers about a policy is answerable here. Named
 *    by the words a reader sees on the tab, so a tab renamed away still fails.
 *  - A narrowing selects policies and never their contents, checked by object
 *    identity so that a card cannot be quietly rebuilt with fewer rules.
 *  - The serialised document holds every rule the card does. This is the guard
 *    on the one bridge between a published card and the single serialiser: if
 *    that bridge ever stops carrying a rule, this says so rather than emitting
 *    a document that silently omits it.
 *
 * WHAT IS DELIBERATELY NOT ASSERTED
 *
 * That the two surfaces render identically. They must not: one offers a
 * decision and the other cannot. The decision controls are asserted absent by
 * `publishedRecordOffersNoDecision`, which is the other half of this pair.
 *
 * Nothing here is a phrase from any document, and no number in it is a
 * measurement of one.
 */
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { AssembledPolicy, CanonicalRule } from "../api";
import {
  buildPolicyCards,
  cardsAnsweringNarrowing,
  policyJsonDocument,
} from "../policyCards";
import {
  PARTIES_AND_ROUTES_TAB_LABEL,
  policyRecord,
  type PolicySightingView,
} from "./policyTabPanes";
import { PolicyDetailPanel } from "./PolicyDetailPanel";

// jsdom implements neither, and the component library measures its own layout.
// Stubbed once for the file: restoring them between tests strips the stub for
// every test after the first.
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

function rule(id: string, overrides: Partial<CanonicalRule> = {}): CanonicalRule {
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
    ...overrides,
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

function cardsFor(spec: Record<string, string[]>) {
  const policies = Object.entries(spec).map(([key, ids]) => policy(key, ids));
  const rules = Object.values(spec)
    .flat()
    .map((id) => ({ rule: rule(id) }));
  return buildPolicyCards(policies, rules);
}

/** The questions a reviewer can ask of a policy, named as a reader sees them.
 *  Not a count: the assertion is that each is reachable, and a count would pass
 *  while any two were swapped for each other.
 *
 *  One of them is read from the constant the surfaces import rather than
 *  written out here, because that tab had three spellings across three files
 *  and the third had drifted back to the word the first two dropped. A literal
 *  in this list would have agreed with whichever spelling it was copied from. */
const QUESTIONS = [
  "Overview",
  "Reading",
  "Logic",
  PARTIES_AND_ROUTES_TAB_LABEL,
  "Scope",
  "Tests",
  "History",
  "Notes",
  "JSON",
];

function renderOne(ruleIds: string[] = ["r1", "r2"]) {
  const [card] = cardsFor({ "a-policy": ruleIds });
  return render(
    <PolicyDetailPanel
      card={card}
      statusColor={() => "purple"}
      statusLabel={(status) => status}
      policySetKey="a-set"
    />,
  );
}

function renderWithHistory(props: {
  onRequestHistory: (provisionKey: string) => void;
  history?: readonly PolicySightingView[] | null;
  historyLoading?: boolean;
}) {
  const [card] = cardsFor({ "a-policy": ["r1"] });
  render(
    <PolicyDetailPanel
      card={card}
      statusColor={() => "purple"}
      statusLabel={(status) => status}
      policySetKey="a-set"
      history={props.history ?? null}
      historyLoading={props.historyLoading}
      onRequestHistory={props.onRequestHistory}
    />,
  );
  return { card };
}

describe("a published policy answers the same questions the queue does", () => {
  for (const question of QUESTIONS) {
    it(`can be asked: ${question}`, () => {
      renderOne();
      expect(screen.getByRole("tab", { name: question })).toBeTruthy();
    });
  }

  it("opens on what this record is, the same as the queue's panel does", () => {
    renderOne();
    // One panel, one opening question, on both surfaces. It used to open on
    // "Reading" here and "Overview" there, because this page drew its own card
    // with its own tab strip; a reader moving between the two met a different
    // first answer to the same click. There is one strip now.
    expect(screen.getByRole("tab", { name: "Overview", selected: true })).toBeTruthy();
  });
});

describe("a narrowing chooses policies, never parts of one", () => {
  it("keeps a policy whole when only one of its rules answered", () => {
    const cards = cardsFor({ "a-policy": ["r1", "r2", "r3"] });
    const shown = cardsAnsweringNarrowing(cards, new Set(["r2"]));
    expect(shown).toHaveLength(1);
    // Identity, not shape: a rebuilt card with the same fields would pass a
    // deep comparison while having had its contents chosen for it.
    expect(shown[0]).toBe(cards[0]);
    expect(shown[0].rules.map((entry) => entry.rule_id)).toEqual(["r1", "r2", "r3"]);
  });

  it("drops a policy no rule of which answered", () => {
    const cards = cardsFor({ "policy-a": ["r1"], "policy-b": ["r2"] });
    const shown = cardsAnsweringNarrowing(cards, new Set(["r2"]));
    expect(shown.map((card) => card.policy.key)).toEqual(["policy-b"]);
  });

  it("shows every policy when everything answers", () => {
    const cards = cardsFor({ "policy-a": ["r1"], "policy-b": ["r2"] });
    const shown = cardsAnsweringNarrowing(cards, new Set(["r1", "r2"]));
    expect(shown).toHaveLength(cards.length);
  });
});

describe("the policy as one document", () => {
  it("holds every rule the card holds", () => {
    const [card] = cardsFor({ "a-policy": ["r1", "r2", "r3"] });
    const document = policyJsonDocument(card);
    const passages = document.passages as { rules: CanonicalRule[] }[];
    const serialised = passages.flatMap((passage) => passage.rules.map((r) => r.rule_id));
    expect(serialised).toEqual(["r1", "r2", "r3"]);
  });

  it("carries the rules themselves and not a husk of them", () => {
    const [card] = cardsFor({ "a-policy": ["r1"] });
    const document = policyJsonDocument(card);
    const passages = document.passages as { rules: CanonicalRule[] }[];
    expect(passages[0].rules[0]).toBe(card.rules[0].rule);
  });
});

describe("the neutral view a shared pane reads", () => {
  it("names every rule of the policy, with the id it is known by", () => {
    const [card] = cardsFor({ "a-policy": ["r1", "r2"] });
    const record = policyRecord(card);
    expect(record.rules.map((entry) => entry.rule_id)).toEqual(["r1", "r2"]);
    expect(record.rules.map((entry) => entry.rule)).toEqual(card.rules.map((entry) => entry.rule));
  });

  it("says nothing about who may act on the record", () => {
    const [card] = cardsFor({ "a-policy": ["r1"] });
    const record = policyRecord(card) as unknown as Record<string, unknown>;
    // A pane that can see a status can branch on it, and the branch is how the
    // two surfaces drifted apart the first time.
    for (const forbidden of ["editable", "canReview", "readOnly", "status", "reviewStatus"]) {
      expect(record[forbidden]).toBeUndefined();
    }
  });
});

/**
 * History is the one tab whose data is fetched per policy rather than per page.
 *
 * The card this page used to draw asked only when the reader opened History,
 * because there was one card per policy on screen and asking on render would
 * have spent a request per card. The panel is not a card: exactly one is
 * mounted, for the one policy the reader chose. So it asks once on open — and
 * it must, because Overview traces where this policy has been published, and
 * that trace is a fact needed to judge the record. Leaving it behind the
 * History tab would put it behind a click.
 *
 * What still has to hold is that it is asked for once, and never for something
 * already held or already out.
 */
describe("history is asked for once, when the policy is opened", () => {
  it("asks for this policy by the key that survives a re-extraction", () => {
    const asked: string[] = [];
    const { card } = renderWithHistory({ onRequestHistory: (key) => asked.push(key) });
    expect(asked).toEqual([card.policy.key]);
  });

  it("does not ask again when the reader opens the tab it feeds", () => {
    const asked: string[] = [];
    const { card } = renderWithHistory({ onRequestHistory: (key) => asked.push(key) });
    fireEvent.click(screen.getByRole("tab", { name: "History" }));
    expect(asked).toEqual([card.policy.key]);
  });

  it("does not ask for a history it already holds", () => {
    const asked: string[] = [];
    renderWithHistory({
      onRequestHistory: (key) => asked.push(key),
      history: [],
    });
    fireEvent.click(screen.getByRole("tab", { name: "History" }));
    expect(asked).toEqual([]);
  });

  it("does not ask while a request for it is already out", () => {
    const asked: string[] = [];
    renderWithHistory({ onRequestHistory: (key) => asked.push(key), historyLoading: true });
    fireEvent.click(screen.getByRole("tab", { name: "History" }));
    expect(asked).toEqual([]);
  });
});
