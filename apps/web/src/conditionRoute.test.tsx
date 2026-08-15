import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import type { CanonicalRule, ConditionProvenance } from "./api";
import { CONDITION_ROUTE, UNKNOWN_CONDITION_ROUTE, conditionRoute } from "./conditionRoute";
import { ConditionRouteNote } from "./components/ConditionRouteNote";
import { PolicyInspector } from "./components/PolicyInspector";

/**
 * The routing reason reaches a reviewer, in words, whatever the code says.
 *
 * Which codes exist is checked from the other side of the boundary, by
 * `tests/unit/test_condition_route_wording.py` — it imports the declared set
 * out of `contracts/policy.py` and fails when one of them has no entry here.
 * That direction cannot be run from this side: the declaration is Python, and
 * reading it from a browser test would mean parsing a language this project
 * has a parser for one directory over.
 *
 * What is checked here is everything that stays true whatever the set is: that
 * the entries are real sentences rather than placeholders, that a code nobody
 * has heard of still produces something a reviewer can read, that no reader is
 * ever shown an internal identifier, and — the one that actually failed before
 * — that the panel is mounted where a reviewer will meet it. Wording that
 * exists and is rendered by nothing is the state this work found the codebase
 * in: two helpers with wording for these codes, styled and unused, and a
 * comment promising a panel that had been deleted.
 */

const KNOWN_CODES = Object.keys(CONDITION_ROUTE);

/**
 * What the mapping held when this was written.
 *
 * A floor, not an equality — adding a code is ordinary and the guard beside
 * this one already insists a new one gets wording. Losing the lot is not
 * ordinary, and every loop below over `KNOWN_CODES` would pass by running zero
 * times if it happened. Lowering this should be a deliberate edit.
 */
const CODES_AT_WRITING = 5;

/** A code no build has wording for. Deliberately shaped like a real one. */
const UNSEEN_CODE = "conditions_deferred_to_a_later_reading";

function provenance(
  code: string,
  unsupported_expression = "",
  unprojected_quantity = ""
): ConditionProvenance {
  return { code, unsupported_expression, unprojected_quantity };
}

/**
 * A record with nothing on it but what the inspector needs to draw.
 *
 * No evidence, so the panel resolves no clauses and no document metadata and
 * the test needs no server. Everything about the routing note is passed in.
 */
function ruleWith(condition_provenance: ConditionProvenance | null): CanonicalRule {
  return {
    schema_version: "1.0",
    policy_set_id: "set-under-test",
    policy_version_id: "version-under-test",
    rule_id: "rule-under-test",
    rule_revision: 1,
    title: "Rule under test",
    description: "",
    rule_type: "eligibility",
    authority: { level: "policy", owner: "Owner", rank: 1 },
    scope: { jurisdictions: [], organizational_units: [], personas: [], processes: [] },
    condition: { type: "all", all: [] },
    condition_provenance,
    effect: { type: "allow", action: "grant" },
    required_facts: [],
    exceptions: [],
    priority: 0,
    effective_from: "2024-01-01",
    effective_to: null,
    machine_executable: false,
    ambiguity_status: "none",
    review_status: "approved",
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
  };
}

beforeEach(() => {
  // antd measures the viewport; jsdom provides neither of these.
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
    }))
  );
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    }
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("condition route wording", () => {
  it("has a code to check in the first place", () => {
    // A mapping that emptied out would let every test below pass by iterating
    // nothing, which is the failure mode of a guard rather than of a feature.
    expect(KNOWN_CODES.length).toBeGreaterThanOrEqual(CODES_AT_WRITING);
  });

  it("says something for every code it knows, and never the code itself", () => {
    let checked = 0;
    for (const code of KNOWN_CODES) {
      const entry = CONDITION_ROUTE[code];
      expect(entry.route.length, code).toBeGreaterThan(0);
      // Long enough to be a statement about the source rather than a label
      // repeated in sentence position.
      expect(entry.reason.split(" ").length, code).toBeGreaterThan(10);
      for (const other of KNOWN_CODES) {
        expect(`${entry.route} ${entry.reason}`, code).not.toContain(other);
      }
      checked += 1;
    }
    // Counted inside the loop, so this cannot be satisfied by the loop being
    // skipped. The test above states the same floor; this one proves the body
    // actually ran, which is a different claim and survives that test being
    // deleted.
    expect(checked).toBeGreaterThanOrEqual(CODES_AT_WRITING);
  });

  it("answers for a code it has never seen, without printing it", () => {
    const route = conditionRoute(provenance(UNSEEN_CODE));

    expect(route).toBe(UNKNOWN_CONDITION_ROUTE);
    expect(route?.reason.length).toBeGreaterThan(0);
    expect(route?.reason).not.toContain(UNSEEN_CODE);
    // No route is claimed. Which of the two an unknown code means is not
    // knowable from the code, and guessing would be the interface inventing a
    // fact about the record.
    expect(route?.route).toBe("");
  });

  it("says nothing about a record that carries no provenance", () => {
    // Hand-authored rules never went through the formulator. An explanation
    // for one would have to be made up.
    expect(conditionRoute(null)).toBeNull();
    expect(conditionRoute(undefined)).toBeNull();
  });
});

describe("ConditionRouteNote", () => {
  it("renders the reason for every code, and shows no identifier", () => {
    let rendered = 0;
    for (const code of KNOWN_CODES) {
      const { unmount } = render(<ConditionRouteNote provenance={provenance(code)} />);
      expect(screen.getByText(CONDITION_ROUTE[code].reason)).toBeTruthy();
      expect(document.body.textContent).not.toContain(code);
      unmount();
      rendered += 1;
    }
    // `not.toContain` is clean against a component that renders nothing at
    // all, and so is a loop that never runs. Counting the renders is what
    // separates "no identifier reached the page" from "no page".
    expect(rendered).toBeGreaterThanOrEqual(CODES_AT_WRITING);
  });

  it("still tells a reviewer a reason exists when it cannot name it", () => {
    render(<ConditionRouteNote provenance={provenance(UNSEEN_CODE)} />);

    // The failure being guarded against is silence: an unrecognised code that
    // rendered nothing would leave the reviewer unable to tell the record was
    // routed for a reason at all.
    expect(screen.getByText(UNKNOWN_CONDITION_ROUTE.reason)).toBeTruthy();
    expect(document.body.textContent).not.toContain(UNSEEN_CODE);
  });

  it("shows the extracted expression when there is one, and nothing when there is not", () => {
    const expression = "amount <= 0.1 * salary";
    const { unmount } = render(
      <ConditionRouteNote provenance={provenance(KNOWN_CODES[0], expression)} />
    );
    expect(screen.getByText(expression)).toBeTruthy();
    unmount();

    render(<ConditionRouteNote provenance={provenance(KNOWN_CODES[0])} />);
    // Positive control first. Without it the assertion below passes against a
    // render that produced nothing at all, and would report the block correctly
    // withheld when in fact the panel never drew.
    expect(screen.getByText(CONDITION_ROUTE[KNOWN_CODES[0]].reason)).toBeTruthy();
    // Keyed on content, so the common case carries no empty block.
    expect(document.querySelector(".condition-route-expression")).toBeNull();
  });

  it("says nothing at all for a record with no provenance", () => {
    // Same shape, same component, one field different — so the empty result
    // below is attributable to the missing provenance and not to the render.
    const { container: withCode } = render(
      <ConditionRouteNote provenance={provenance(KNOWN_CODES[0])} />
    );
    expect(withCode.textContent).not.toBe("");

    const { container } = render(<ConditionRouteNote provenance={null} />);
    expect(container.textContent).toBe("");
  });
});

describe("the record detail view", () => {
  it("shows the routing reason beside the condition it explains", () => {
    // The point of the whole exercise. Wording nothing renders is what the
    // codebase already had.
    const code = "no_scope_derived" in CONDITION_ROUTE ? "no_scope_derived" : KNOWN_CODES[0];
    render(
      <PolicyInspector
        rule={ruleWith(provenance(code))}
        activeTabKey="logic"
        onTabChange={() => {}}
      />
    );

    // Proven mount-sensitive: with ConditionRouteNote stubbed to render null,
    // this query returns nothing and this line is what fails. It is not
    // satisfied by the reason appearing anywhere else in the app, because
    // nothing else renders it, and not by a pane the reviewer cannot reach,
    // because the sibling test below shows it is absent on another tab.
    expect(screen.getByText(CONDITION_ROUTE[code].reason)).toBeTruthy();
  });

  it("puts it on the tab that shows the condition, not on every tab", () => {
    // Guards the claim in the test above. antd keeps visited panes mounted, so
    // "it rendered" and "it rendered where a reviewer meets it" are different
    // facts and only this one distinguishes them.
    const code = KNOWN_CODES[0];
    render(
      <PolicyInspector
        rule={ruleWith(provenance(code))}
        activeTabKey="overview"
        onTabChange={() => {}}
      />
    );

    // Positive control: we are on the tab we asked for, and it drew. Without
    // this, an inspector that rendered no tabs at all would satisfy the two
    // assertions below and be reported as correct scoping.
    //
    // Queried by role, not by antd's class names. The first draft of this line
    // used `.ant-tabs-tabpane-active` and matched nothing — a control that
    // would have passed for the wrong reason had it been written as an absence
    // check, which is the failure it exists to prevent.
    expect(screen.getByRole("tabpanel")).toBeTruthy();
    expect(screen.getByRole("tab", { selected: true }).textContent).toContain("Overview");
    expect(screen.queryByText(/Condition — when this rule fires/i)).toBeNull();
    expect(screen.queryByText(CONDITION_ROUTE[code].reason)).toBeNull();
  });

  it("leaves the panel alone for a record that carries no provenance", () => {
    render(
      <PolicyInspector rule={ruleWith(null)} activeTabKey="logic" onTabChange={() => {}} />
    );

    // Positive control. Asserting only the absence would pass against an
    // inspector that failed to draw the Logic tab, against a stubbed-out note,
    // and against a build where this whole feature had been reverted.
    expect(screen.getByText(/Condition — when this rule fires/i)).toBeTruthy();
    expect(document.querySelector(".condition-route")).toBeNull();
  });
});

/**
 * The figure the routing reason says is shown.
 *
 * Two of the wordings above end by telling the reviewer the quantity is
 * visible: "The clause's own quantity is shown alongside, so the grouping can
 * be checked", and "The figure found in the line is shown alongside". The
 * server has been sending it, on `unprojected_quantity`, and the interface
 * declared no such field and drew nothing.
 *
 * That is worse than an omission. A reviewer told the evidence is beside the
 * claim and shown none does not conclude the panel is incomplete; they
 * conclude the document had no figure, which is the opposite of what the
 * refusal recorded. The sentence made the absence unreadable as an absence.
 */
describe("the quantity behind a refused projection", () => {
  afterEach(cleanup);

  /** The wordings that promise it. Named so a reworded one is noticed here. */
  const CODES_PROMISING_THE_FIGURE = [
    "stated_quantity_is_one_clause_of_a_provision",
    "stated_quantity_comes_from_a_table_row",
  ];

  it("is promised by wording that is still in the mapping", () => {
    // Positive control for the two tests below. If a reword removed the
    // promise, they would be enforcing a claim nothing makes any more.
    for (const code of CODES_PROMISING_THE_FIGURE) {
      expect(CONDITION_ROUTE[code]).toBeTruthy();
      expect(CONDITION_ROUTE[code].reason).toMatch(/shown alongside/i);
    }
  });

  it("is rendered when the server sends one", () => {
    render(
      <ConditionRouteNote
        provenance={provenance(
          "stated_quantity_comes_from_a_table_row",
          "",
          "not more than 10% of the stated amount"
        )}
      />
    );

    expect(screen.getByText("not more than 10% of the stated amount")).toBeTruthy();
  });

  it("is rendered whatever the code says, because the promise is about content", () => {
    // Keyed on content, not on the two codes above, for the reason the sibling
    // block gives: a third code carrying a figure would otherwise send it back
    // to being computed and unread.
    render(
      <ConditionRouteNote
        provenance={provenance("quantity_states_nothing_counted", "", "30")}
      />
    );

    expect(screen.getByText("30")).toBeTruthy();
  });

  it("draws no empty figure when the server sends none", () => {
    const { container } = render(
      <ConditionRouteNote provenance={provenance("conditions_not_projected")} />
    );

    // Positive control first: the note itself drew, so the absence below is an
    // absence of the figure and not of the panel.
    expect(container.querySelector(".condition-route")).toBeTruthy();
    expect(container.querySelector(".condition-route-quantity")).toBeNull();
  });
});
