/**
 * The roster opens each rule to its own words, its effect, and its page.
 *
 * The Overview's "The rules it holds" list named a rule and stopped there — the
 * document's own sentence for the rule was not on this surface at all. This adds
 * it behind a native <details>, alongside the rule's effect and a way onward to
 * the rule's page by the one route this app already has (onSelectRule →
 * PolicyInspector). Additive, so nothing that was open is moved behind a click.
 *
 * The tests that matter here:
 *  - the sentence shown is the document's, verbatim and uncut (constraint 4);
 *  - a rule this app never held a formulation for is said to have none, and said
 *    differently from a rule whose formulation records an empty source — absent
 *    is not empty (constraint 5);
 *  - opening one row changes neither the others nor the count (constraint 10);
 *  - the way onward calls the existing route with the rule itself, and is simply
 *    absent where the surface cannot route rather than drawn as a dead control.
 */

import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import type { AssembledPolicy, CanonicalRule } from "../api";
import { PolicyOverviewPane, type PolicyRecordView } from "./policyTabPanes";

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
  globalThis.ResizeObserver ??= class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
});

beforeEach(() => cleanup());

/** A canonical rule, with just the fields these panes read. `formulation` and
 *  `effect` are the two this surface reasons about, so both are overridable. */
function rule(
  id: string,
  overrides: {
    title?: string;
    effect?: unknown;
    sourceText?: string | null;
    /** When true, the rule carries no formulation record at all (hand-authored
     *  or drafted before the formulator existed) — a different fact from a
     *  formulation whose source text is empty. */
    noFormulation?: boolean;
  } = {},
): CanonicalRule {
  const formulation = overrides.noFormulation
    ? undefined
    : { source_index: 0, canonical: { source_text: overrides.sourceText ?? "", extraction_status: "ok", relationships: [] }, dmn_decisions: [] };
  return {
    rule_id: id,
    title: overrides.title ?? `Rule ${id}`,
    effect: overrides.effect ?? { type: "allow", action: "" },
    condition: { type: "all", all: [] },
    obligations: [],
    exceptions: [],
    scope: {},
    source: { document_id: "d", quotes: [] },
    lineage: { extraction_run_id: "run-1", schema_version: "1" },
    formulation,
  } as unknown as CanonicalRule;
}

function record(rules: CanonicalRule[]): PolicyRecordView {
  return {
    policy: {
      key: "SECTION-KEY-42",
      heading: "The heading",
      heading_path: ["Above", "The heading"],
      passages: [],
      page: 1,
      persisted: true,
      provision_id: null,
      document_version_id: "dv-1",
      source_elements: "p1-E1",
      rules: [],
      rule_count: rules.length,
      passage_count: 0,
      route: "computable",
    } as unknown as AssembledPolicy,
    passageCount: 0,
    rules: rules.map((r) => ({ rule_id: r.rule_id, rule: r })),
    progress: null,
  };
}

const ENGLISH_SENTENCE =
  "Employees are expected to maintain the highest standards of performance, and all staff are subject to a formal annual performance appraisal.";
const ARABIC_SENTENCE =
  "يُتوقع من الموظفين الالتزام بأعلى معايير الأداء، ويخضع جميع الموظفين لتقييم أداء سنوي رسمي.";

function rowFor(ruleId: string): HTMLElement {
  const codes = [...document.querySelectorAll<HTMLElement>("[data-testid='overview-rule'] code")];
  const code = codes.find((c) => c.textContent === ruleId);
  const li = code?.closest<HTMLElement>("[data-testid='overview-rule']");
  if (!li) throw new Error(`no row for rule ${ruleId}`);
  return li;
}

describe("the roster opens each rule to the document's own words", () => {
  it("shows the rule's verbatim sentence, uncut, behind a native disclosure", () => {
    render(<PolicyOverviewPane record={record([rule("a", { sourceText: ENGLISH_SENTENCE })])} />);

    const disclosure = within(rowFor("a")).getByTestId("overview-rule-disclosure");
    expect(disclosure.tagName).toBe("DETAILS");

    const source = within(disclosure).getByTestId("overview-rule-source");
    // Verbatim and whole — never trimmed to keep a row even (constraint 4).
    expect(source.textContent).toBe(ENGLISH_SENTENCE);
    // Marked as the document's own words, not this app's (constraint 8/4).
    expect(source.getAttribute("data-verbatim")).toBe("true");
    // Laid out through the per-run splitter, not printed on a directioned
    // container (constraint 7).
    expect(source.querySelector(".directional-text--block")).not.toBeNull();
  });

  it("renders an Arabic sentence by its own run, still verbatim", () => {
    render(<PolicyOverviewPane record={record([rule("a", { sourceText: ARABIC_SENTENCE })])} />);
    const source = within(rowFor("a")).getByTestId("overview-rule-source");
    expect(source.textContent).toBe(ARABIC_SENTENCE);
    // Direction is a property of the run: the Arabic run is a right-to-left
    // `<bdi>`, isolated from its neighbours, not a direction set on the row
    // (constraint 7).
    expect(source.querySelector('bdi[dir="rtl"]')).not.toBeNull();
  });

  it("names the rule's effect as its documented nature, not a status", () => {
    render(
      <PolicyOverviewPane
        record={record([rule("a", { effect: { type: "deny", action: "disclose confidential data" }, sourceText: ENGLISH_SENTENCE })])}
      />,
    );
    const disclosure = within(rowFor("a")).getByTestId("overview-rule-disclosure");
    // The same word the compact card and the inspector header use for a deny.
    expect(disclosure.textContent).toContain("Prohibits");
  });
});

describe("the roster tells absent from empty (constraint 5)", () => {
  it("says a rule whose formulation was never stored has none, and fakes no quote", () => {
    render(<PolicyOverviewPane record={record([rule("a", { noFormulation: true })])} />);
    const disclosure = within(rowFor("a")).getByTestId("overview-rule-disclosure");

    // No invented sentence.
    expect(within(disclosure).queryByTestId("overview-rule-source")).toBeNull();
    // The absent case, stated.
    const absent = within(disclosure).getByTestId("overview-rule-source-absent");
    expect(absent.textContent?.toLowerCase()).toContain("not stored");
    // And it is not the empty case.
    expect(within(disclosure).queryByTestId("overview-rule-source-empty")).toBeNull();
  });

  it("says a rule whose stored source is empty holds none, and says it differently", () => {
    render(<PolicyOverviewPane record={record([rule("a", { sourceText: "   " })])} />);
    const disclosure = within(rowFor("a")).getByTestId("overview-rule-disclosure");

    expect(within(disclosure).queryByTestId("overview-rule-source")).toBeNull();
    const empty = within(disclosure).getByTestId("overview-rule-source-empty");
    expect(empty.textContent).toBeTruthy();
    // Covered separately from the not-stored case, and worded differently.
    expect(within(disclosure).queryByTestId("overview-rule-source-absent")).toBeNull();

    // The two states must not read the same.
    cleanup();
    render(<PolicyOverviewPane record={record([rule("a", { noFormulation: true })])} />);
    const absentText = within(within(rowFor("a")).getByTestId("overview-rule-disclosure"))
      .getByTestId("overview-rule-source-absent").textContent;
    expect(empty.textContent).not.toBe(absentText);
  });
});

describe("the details action reuses the one route to a rule's page", () => {
  it("opens the rule's own page with the rule itself, by the existing route", () => {
    const onSelectRule = vi.fn();
    render(
      <PolicyOverviewPane
        record={record([rule("a", { sourceText: ENGLISH_SENTENCE }), rule("b", { sourceText: "Another." })])}
        onSelectRule={onSelectRule}
      />,
    );

    const details = within(rowFor("b")).getByTestId("overview-rule-details");
    fireEvent.click(details);

    expect(onSelectRule).toHaveBeenCalledTimes(1);
    expect(onSelectRule.mock.calls[0][0].rule_id).toBe("b");
  });

  it("offers no details control where the surface cannot route", () => {
    render(<PolicyOverviewPane record={record([rule("a", { sourceText: ENGLISH_SENTENCE })])} />);
    expect(within(rowFor("a")).queryByTestId("overview-rule-details")).toBeNull();
  });
});

describe("opening one rule leaves the roster whole (constraint 10)", () => {
  it("keeps every rule listed and its words its own when one is opened", () => {
    render(
      <PolicyOverviewPane
        record={record([
          rule("a", { sourceText: "Alpha sentence." }),
          rule("b", { sourceText: "Bravo sentence." }),
          rule("c", { sourceText: "Charlie sentence." }),
        ])}
      />,
    );

    expect(screen.getAllByTestId("overview-rule")).toHaveLength(3);
    expect(screen.getAllByTestId("overview-rule-disclosure")).toHaveLength(3);

    // Open one row. Native <details> keeps its children in the DOM whether or
    // not it is open, so opening is the reader's move, not a remount.
    const disclosureB = within(rowFor("b")).getByTestId("overview-rule-disclosure") as HTMLDetailsElement;
    disclosureB.open = true;

    // The count and the others are untouched, and each row still holds its own
    // sentence rather than a neighbour's.
    expect(screen.getAllByTestId("overview-rule")).toHaveLength(3);
    expect(within(rowFor("a")).getByTestId("overview-rule-source").textContent).toBe("Alpha sentence.");
    expect(within(rowFor("b")).getByTestId("overview-rule-source").textContent).toBe("Bravo sentence.");
    expect(within(rowFor("c")).getByTestId("overview-rule-source").textContent).toBe("Charlie sentence.");
  });
});
