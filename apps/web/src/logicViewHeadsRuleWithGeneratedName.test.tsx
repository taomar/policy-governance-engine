/**
 * THE LOGIC TAB HEADS EACH RULE WITH THE NAME THIS APP GENERATED FOR IT.
 *
 * WHAT THIS EXISTS TO PROVE
 *
 * The Logic tab draws each rule whole. A reviewer's words: it names those rules
 * only by the run of source element ids the pipeline addresses them by --
 * `p9-E000071` -- with no sign of the short handle this app generates so a
 * reader can tell one rule from its siblings at a glance. The component's own
 * description already said each rule "carries the name generated for it", and
 * the stylesheet already reserved a place for it "under the name generated for
 * it" -- but the name was never asked for here. The capability was described
 * and never wired, so it reached nobody. That is the defect this pins shut.
 *
 * WHAT IS ASSERTED
 *
 * That a card which knows the set it was built for asks for its rules' names by
 * (set, rule id) -- the one address that resolves on the review queue and in a
 * published version alike -- and heads each rule with what comes back, marked
 * as ours and kept apart from the document's own verbatim title. And that
 * wiring the name in took nothing away: the element run that addresses the
 * passage is still on the page, and the sentence the rule was read out of still
 * opens from its own disclosure and remains the only thing behind one.
 *
 * WHY IT FAILS WITHOUT THE CHANGE
 *
 * Before the name was wired into the rule head, PolicyLogicTable never mounted
 * the naming component, so `ruleNames` was never called and no handle ever
 * rendered. Every assertion that a name is asked for and shown fails on the
 * unwired component.
 *
 * A generated name is ours, not the document's. This file therefore also holds
 * the line that it must never be dressed as the document's own words: the
 * handle carries `data-generated`, the title carries `data-verbatim`, and the
 * two must never be the same node.
 *
 * Nothing here is a phrase from any document, and no number in it is a
 * measurement of one.
 */
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import type { CandidateRule, PolicyAttribute } from "./api";
import { fromDraftRow } from "./policyCards";
import type { PolicyCard, PolicyCardPassage, PolicyCardRule } from "./policyCards";

const ruleNames = vi.fn();

vi.mock("./api", async () => {
  const actual = await vi.importActual<typeof import("./api")>("./api");
  return { ...actual, aiApi: { ...actual.aiApi, ruleNames } };
});

const { forgetRuleNames } = await import("./components/RuleName");
const { PolicyLogicTable } = await import("./components/PolicyLogicTable");

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

afterEach(cleanup);

function rowAttr(attribute: string, text: string): PolicyAttribute {
  return { attribute, text, fact: null, data_type: null } as PolicyAttribute;
}

/** One rule as the review queue holds it: a draft row, decomposed. */
function cardRule(
  ruleId: string,
  options: { title?: string; statedText?: string | null; section?: string | null } = {},
): PolicyCardRule {
  return {
    rule_id: ruleId,
    evaluation_mode: "deterministic",
    ...fromDraftRow({
      id: `record-${ruleId}`,
      review_status: "candidate",
      rule: {
        rule_id: ruleId,
        title: options.title ?? `What ${ruleId} requires`,
        rule_type: "obligation",
        effect: { type: "require_action", action: "" },
        condition: { type: "all", all: [] },
        attributes: { applies: [rowAttr("subject", `subject of ${ruleId}`)], outcome: [] },
        description: options.statedText ?? undefined,
        evidence:
          options.section === null
            ? []
            : [{ section: options.section ?? "Chapter 3 — Leave", quote: "" }],
      },
    } as unknown as CandidateRule),
  } as unknown as PolicyCardRule;
}

/**
 * A card, as a surface builds it, told (or not told) the set it belongs to.
 * The set rides the record, never the logic shape, so it is a field of the card
 * and not an argument to the view.
 */
function card(
  blocks: { key: string; page?: number | null; rules: PolicyCardRule[] }[],
  policySetKey: string | null,
): PolicyCard {
  const passages: PolicyCardPassage[] = blocks.map((block) => ({
    passage: {
      key: block.key,
      page: block.page ?? null,
    } as PolicyCardPassage["passage"],
    rules: block.rules,
  }));
  const rules = blocks.flatMap((block) => block.rules);
  return {
    policy: { key: "policy-1", rule_count: rules.length } as PolicyCard["policy"],
    passages,
    rules,
    hiddenByFilter: 0,
    reviewableIds: rules.map((rule) => rule.recordId),
    allIds: rules.map((rule) => rule.recordId),
    reviewStatuses: ["candidate"],
    policy_set_key: policySetKey,
  };
}

describe("the logic tab heads a rule with the name this app generated for it", () => {
  it("asks for the name by (set, rule id) and heads the rule with what comes back", async () => {
    ruleNames.mockResolvedValue({
      names: {},
      names_by_rule_id: {
        a: { text: "Leave request lodging window", unavailable_code: null, generated: true },
      },
    });

    const { container } = render(
      <PolicyLogicTable
        card={card([{ key: "p9-E000071", page: 9, rules: [cardRule("a")] }], A_SET)}
      />,
    );

    // The address that resolves on both surfaces: never a bare draft-row id, and
    // never a rule id sent down the draft-row door where it would answer nothing.
    await waitFor(() => expect(ruleNames).toHaveBeenCalledTimes(1));
    expect(ruleNames.mock.calls[0][1]).toEqual({ policySetKey: A_SET, ruleIds: ["a"] });

    await waitFor(() =>
      expect(screen.getAllByTestId("rule-name").length).toBeGreaterThan(0),
    );
    const name = screen.getAllByTestId("rule-name")[0];
    expect(name.textContent).toMatch(/Leave request lodging window/);

    // The handle sits inside the rule's own block, and it heads it: it precedes
    // the line that carries the rule's ordinal and facets.
    const article = container.querySelector('[data-testid="policy-logic-rule"]');
    expect(article?.contains(name)).toBe(true);
    const ruleLine = article?.querySelector(".policy-logic__rule-line");
    expect(ruleLine).not.toBeNull();
    const nameLeadsTheLine = Boolean(
      name.compareDocumentPosition(ruleLine as Node) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    );
    expect(nameLeadsTheLine).toBe(true);
  });

  it("marks the name as ours and keeps it apart from the document's verbatim title", async () => {
    ruleNames.mockResolvedValue({
      names: {},
      names_by_rule_id: {
        a: { text: "Leave request lodging window", unavailable_code: null, generated: true },
      },
    });

    const { container } = render(
      <PolicyLogicTable
        card={card([{ key: "p9-E000071", page: 9, rules: [cardRule("a", { title: "Leave" })] }], A_SET)}
      />,
    );

    await waitFor(() =>
      expect(screen.getAllByTestId("rule-name").length).toBeGreaterThan(0),
    );
    const name = screen.getAllByTestId("rule-name")[0];

    // Constraint 8: the name is this app's, and says so.
    expect(name.getAttribute("data-generated")).toBe("true");
    expect(name.textContent).toMatch(/named by this app/i);

    // A generated name and a verbatim title are different kinds of thing and
    // must stay distinguishable: the title is the document's own characters and
    // carries the quotation mark this app reserves for them; the name never does.
    const article = container.querySelector('[data-testid="policy-logic-rule"]');
    const title = article?.querySelector(".policy-logic__rule-title");
    expect(title?.getAttribute("data-verbatim")).toBe("true");
    expect(name.getAttribute("data-verbatim")).toBeNull();
    expect(name).not.toBe(title);
  });

  it("takes nothing away: the element run stays reachable and the source text still expands", async () => {
    ruleNames.mockResolvedValue({
      names: {},
      names_by_rule_id: {
        a: { text: "A handle", unavailable_code: null, generated: true },
      },
    });

    const { container } = render(
      <PolicyLogicTable
        card={card(
          [
            {
              key: "p9-E000071",
              page: 9,
              rules: [cardRule("a", { statedText: "The sentence the rule was read out of." })],
            },
          ],
          A_SET,
        )}
      />,
    );

    await waitFor(() =>
      expect(screen.getAllByTestId("rule-name").length).toBeGreaterThan(0),
    );

    // The run that addresses the passage is still printed, as the reference it is.
    expect(container.querySelector(".policy-logic__passage-key")?.textContent).toBe(
      "p9-E000071",
    );

    // The source sentence is still offered, still closed, and still the only
    // thing on this surface behind a disclosure.
    const disclosures = container.querySelectorAll("details");
    expect(disclosures).toHaveLength(1);
    expect(disclosures[0].getAttribute("data-testid")).toBe("policy-logic-source");
  });

  it("asks nothing at all when the card was not told which set it belongs to", async () => {
    render(
      <PolicyLogicTable
        card={card([{ key: "p9-E000071", page: 9, rules: [cardRule("a")] }], null)}
      />,
    );

    // Half an address is not an address. A rule id sent as though it were a
    // draft-row id would answer nothing and look ordinary doing it, so a card
    // with no set asks for nothing rather than guessing.
    await Promise.resolve();
    expect(ruleNames).not.toHaveBeenCalled();
    expect(screen.queryAllByTestId("rule-name")).toHaveLength(0);
  });
});
