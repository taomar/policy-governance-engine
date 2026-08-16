/**
 * The full record opens inside the row, and costs one tab to open.
 *
 * THE FAILURE THIS EXISTS TO PREVENT
 *
 * A rule used to have two controls: one that opened a short summary in place,
 * and one that sent the reviewer to a separate surface for everything the
 * summary left out — the logic tree, who the rule names, what it reaches, where
 * it came from, and its stored forms. The second control was the original cost
 * wearing a new label. The reviewer still left the policy they were comparing
 * against, and still had to click back and find their place.
 *
 * There is now one control, and what was on the other surface is inside it.
 * That is only worth having if three things hold, and each can break on its own
 * in a way that looks fine on screen:
 *
 *   1. A closed row builds nothing. Not hidden — absent. A policy can hold
 *      dozens of rules, and a row that renders seven tab bodies and shows one
 *      pays for six nobody asked for, times the length of the queue.
 *   2. A closed tab builds nothing, for the same reason and at seven times the
 *      rate. This is the claim a tab library will quietly break by mounting
 *      every pane up front, or by keeping every visited pane mounted.
 *   3. Opening and switching leaves the queue exactly as it was: same scroll,
 *      same selection, no re-render above the row.
 *
 * And the strip must be a strip: a real `role="tablist"` of real buttons, one
 * selected, each naming the panel it controls, so a reviewer who never sees the
 * screen is told what a sighted one is shown.
 *
 * Every assertion is paired with a control that fails when nothing rendered at
 * all, because `expect(x).toBeNull()` is also what a blank page returns.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useRef, useState } from "react";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import type { CandidateRule, CanonicalRule } from "./api";
import { ActorProvider } from "./ActorContext";
import type { PolicyCard } from "./policyCards";
import { fromDraftRow } from "./policyCards";
import { CandidateRow } from "./components/CandidateRow";
import { PolicyDetailPanel } from "./components/PolicyDetailPanel";
import { RuleDetailInline } from "./components/RuleDetailInline";

beforeEach(() => {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }));
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
  vi.unstubAllGlobals();
});

/** A phrase that appears in exactly one tab, so its presence names which tab is open. */
const ONLY_IN_OVERVIEW = "Every attribute, as recorded";
const ONLY_IN_LOGIC = "Condition — when this rule fires";
const ONLY_IN_SCOPE = "Applies to";
const ONLY_IN_HISTORY = "What has happened to this record";
const ONLY_IN_JSON = "Evaluator JSON";
const ONLY_IN_NOTES = "Review discussion";
const ARABIC_RUN = "إنذار كتابي";

const EVERY_TAB = ["Overview", "Logic", "Parties & routes", "Scope", "History", "Notes", "JSON"];

function canonical(ruleId: string): CanonicalRule {
  return {
    schema_version: "1.0",
    policy_set_id: "set",
    policy_version_id: "draft",
    rule_id: ruleId,
    rule_revision: 1,
    title: `Summary line for ${ruleId}`,
    description: `The words the document uses for ${ruleId}`,
    rule_type: "obligation",
    authority: { level: "ai_drafted", owner: "formulator", rank: 0 },
    scope: { jurisdictions: [], organizational_units: [], personas: [], processes: [] },
    condition: { type: "all", all: [] },
    attributes: {
      applies: [
        { attribute: "subject_of_the_statement", text: `A party named by ${ruleId}`, fact: "party_kind", data_type: null },
      ],
      outcome: [{ attribute: "object", text: `Written notice ${ARABIC_RUN}`, fact: null, data_type: null }],
    },
    effect: { type: "require_action", action: "act" },
    required_facts: [],
    exceptions: [],
    priority: 0,
    effective_from: "2026-01-01",
    effective_to: null,
    machine_executable: false,
    ambiguity_status: "clear",
    review_status: "candidate",
    evidence: [],
    lineage: {
      extraction_run_id: "run",
      deployment_name: "model",
      prompt_version: "v1",
      parser_version: "v1",
      schema_version: "1.0",
    },
    category: "general",
    tags: [],
    group_label: "",
    related_rule_ids: [],
    is_explicit_override: false,
    supersedes_rule_ids: [],
    advice: [],
  } as CanonicalRule;
}

function candidate(ruleId: string): CandidateRule {
  return {
    id: `record-${ruleId}`,
    policy_set_id: "set",
    extraction_run_id: "run",
    rule_type: "obligation",
    revision: 1,
    review_status: "candidate",
    reviewed_by: null,
    reviewed_at: null,
    review_notes: null,
    published_version_id: null,
    created_at: "2026-01-01T00:00:00Z",
    delta_status: null,
    reworded: false,
    baseline_candidate_id: null,
    superseded_by_candidate_id: null,
    superseded_at: null,
    rule: canonical(ruleId),
  };
}

/**
 * A page of the queue, carrying the two things a single row cannot show on its
 * own: a scroll container the rows sit inside, and state owned above them — the
 * bulk selection, and a count of how many times this component has rendered.
 */
function QueueHarness({ ruleIds }: { ruleIds: string[] }) {
  const [selected, setSelected] = useState<ReadonlySet<string>>(new Set());
  const renders = useRef(0);
  renders.current += 1;
  const rows = ruleIds.map((id) => candidate(id));
  return (
    <ActorProvider>
      <output data-testid="queue-renders">{renders.current}</output>
      <div className="candidate-list" data-testid="candidate-list" style={{ overflowY: "auto", height: 200 }}>
        {rows.map((row) => (
          <div key={row.id} className="candidate-item" data-testid={`item-${row.rule.rule_id}`}>
            <CandidateRow
              candidate={row}
              active={false}
              selected={selected.has(row.id)}
              selectable
              findingsCount={0}
              statusColor="default"
              statusLabel="Pending"
              renderDetail={() => <RuleDetailInline candidate={row} />}
              onToggleSelect={() =>
                setSelected((current) => {
                  const next = new Set(current);
                  if (!next.delete(row.id)) next.add(row.id);
                  return next;
                })
              }
            />
          </div>
        ))}
      </div>
    </ActorProvider>
  );
}

function expanderFor(ruleId: string): HTMLElement {
  const item = screen.getByTestId(`item-${ruleId}`);
  return within(item).getByRole("button", { name: new RegExp(`the detail for Summary line for ${ruleId}`) });
}

/**
 * The panel arranges its own contents in tabs, and which of those opens first
 * is that panel's decision to make and to change. What this file tests is the
 * behaviour of a rule row, so it asks for the rule list to be on screen rather
 * than assuming whichever arrangement happens to be current. Written as a
 * request and not an assertion: if the rules are already showing there is
 * nothing to do, and if the panel later drops the tabs entirely this still
 * reads correctly.
 */
function revealTheRuleList(): void {
  const reading = screen
    .queryAllByRole("tab")
    .find((tab) => /reading/i.test(tab.textContent ?? ""));
  if (reading && reading.getAttribute("aria-selected") !== "true") {
    fireEvent.click(reading);
  }
}

describe("the full record opens inside the row it belongs to", () => {
  it("puts no tab strip and no tab body in the document until the row is opened", () => {
    render(<QueueHarness ruleIds={["R1", "R2", "R3"]} />);

    // Control: the rows are on screen, so the absences below are absences and
    // not a page that failed to render.
    expect(screen.getAllByText(/Summary line for R/)).toHaveLength(3);

    expect(screen.queryAllByRole("tablist")).toHaveLength(0);
    expect(screen.queryAllByRole("tab")).toHaveLength(0);
    expect(screen.queryAllByRole("tabpanel")).toHaveLength(0);
    for (const phrase of [ONLY_IN_OVERVIEW, ONLY_IN_LOGIC, ONLY_IN_HISTORY, ONLY_IN_JSON]) {
      expect(screen.queryByText(phrase)).toBeNull();
    }

    fireEvent.click(expanderFor("R1"));

    // One row opened is one strip, not three.
    expect(screen.getAllByRole("tablist")).toHaveLength(1);
    expect(screen.getAllByRole("tabpanel")).toHaveLength(1);
  });

  it("offers every tab the separate surface offered, and opens on the one that holds the judgement", () => {
    render(<QueueHarness ruleIds={["R1"]} />);
    fireEvent.click(expanderFor("R1"));

    const tabs = screen.getAllByRole("tab");
    expect(tabs.map((t) => t.textContent)).toEqual(EVERY_TAB);

    // Exactly one is selected, and it is the first.
    const selected = tabs.filter((t) => t.getAttribute("aria-selected") === "true");
    expect(selected).toHaveLength(1);
    expect(selected[0].textContent).toBe("Overview");

    // What a reviewer judges the rule on is open, unclicked: the attributes as
    // recorded, the test as recorded, and the document's own words.
    const panel = screen.getByRole("tabpanel");
    expect(within(panel).getByText(ONLY_IN_OVERVIEW)).toBeTruthy();
    expect(within(panel).getByText("The test, as recorded")).toBeTruthy();
    expect(panel.textContent).toContain("The words the document uses for R1");
  });

  it("builds one tab's body and no others", () => {
    render(<QueueHarness ruleIds={["R1"]} />);
    fireEvent.click(expanderFor("R1"));

    // Control: the open tab's body is there to be found.
    expect(screen.getByText(ONLY_IN_OVERVIEW)).toBeTruthy();

    for (const closed of [ONLY_IN_LOGIC, ONLY_IN_HISTORY, ONLY_IN_JSON, ONLY_IN_NOTES]) {
      expect(screen.queryByText(closed)).toBeNull();
    }

    fireEvent.click(screen.getByRole("tab", { name: "Logic" }));

    // The one that was open is now gone, not merely hidden.
    expect(screen.getByText(ONLY_IN_LOGIC)).toBeTruthy();
    expect(screen.queryByText(ONLY_IN_OVERVIEW)).toBeNull();
    expect(screen.queryByText(ONLY_IN_JSON)).toBeNull();
    // Still exactly one panel, however many tabs have now been visited.
    expect(screen.getAllByRole("tabpanel")).toHaveLength(1);

    fireEvent.click(screen.getByRole("tab", { name: "JSON" }));
    expect(screen.getByText(ONLY_IN_JSON)).toBeTruthy();
    expect(screen.queryByText(ONLY_IN_LOGIC)).toBeNull();
  });

  it("keeps the logic tree the reviewer already reads, rather than a second rendering of it", () => {
    render(<QueueHarness ruleIds={["R1"]} />);
    fireEvent.click(expanderFor("R1"));
    fireEvent.click(screen.getByRole("tab", { name: "Logic" }));

    const panel = screen.getByRole("tabpanel");
    // The attribute-name chips and the groups they sit in are the projection
    // view's, unchanged: this is the same component the full record renders.
    expect(within(panel).getByText(ONLY_IN_LOGIC)).toBeTruthy();
    expect(panel.querySelector(".policy-attr-name")).toBeTruthy();
    expect(panel.textContent).toContain("subject_of_the_statement");
    // The document's non-Latin run is still one isolated run of the document's
    // own characters, inside the tree.
    const arabic = within(panel).getByText(ARABIC_RUN);
    expect(arabic.tagName).toBe("BDI");
    expect(arabic.getAttribute("dir")).toBe("rtl");
    // …and the Latin half of the same value is a run of its own, so neither
    // half can reorder the other.
    expect(within(panel).getByText(/Written notice/).tagName).toBe("BDI");
  });

  it("names the panel each tab controls, and keeps one tab in the page's tab order", () => {
    render(<QueueHarness ruleIds={["R1"]} />);
    fireEvent.click(expanderFor("R1"));

    const list = screen.getByRole("tablist");
    expect(list.getAttribute("aria-label")).toContain("Summary line for R1");

    const tabs = screen.getAllByRole("tab");
    for (const tab of tabs) {
      expect(tab.tagName).toBe("BUTTON");
      expect(tab.getAttribute("aria-controls")).toBeTruthy();
    }
    // Reaching the strip costs one Tab, and leaving it costs one more.
    expect(tabs.filter((t) => t.getAttribute("tabindex") === "0")).toHaveLength(1);

    const open = tabs.find((t) => t.getAttribute("aria-selected") === "true") as HTMLElement;
    const panel = screen.getByRole("tabpanel");
    expect(panel.id).toBe(open.getAttribute("aria-controls"));
    expect(panel.getAttribute("aria-labelledby")).toBe(open.id);
  });

  it("moves between tabs with the arrow keys, and to the ends with Home and End", () => {
    render(<QueueHarness ruleIds={["R1"]} />);
    fireEvent.click(expanderFor("R1"));

    const list = screen.getByRole("tablist");
    fireEvent.keyDown(list, { key: "ArrowRight" });
    expect(screen.getByRole("tab", { selected: true }).textContent).toBe("Logic");

    fireEvent.keyDown(list, { key: "End" });
    expect(screen.getByRole("tab", { selected: true }).textContent).toBe("JSON");

    fireEvent.keyDown(list, { key: "Home" });
    expect(screen.getByRole("tab", { selected: true }).textContent).toBe("Overview");

    fireEvent.keyDown(list, { key: "ArrowLeft" });
    expect(screen.getByRole("tab", { selected: true }).textContent).toBe("JSON");
  });

  it("leaves the queue's scroll, its selection and its render count alone while tabs are used", () => {
    render(<QueueHarness ruleIds={["R1", "R2", "R3", "R4"]} />);

    const list = screen.getByTestId("candidate-list");
    list.scrollTop = 120;
    const checkbox = within(screen.getByTestId("item-R2")).getByRole("checkbox");
    fireEvent.click(checkbox);
    expect((checkbox as HTMLInputElement).checked).toBe(true);

    const rendersBefore = screen.getByTestId("queue-renders").textContent;
    // Control: the harness has rendered, so an unchanged count is a real
    // "it did not render again" and not a missing element.
    expect(Number(rendersBefore)).toBeGreaterThan(0);

    fireEvent.click(expanderFor("R3"));
    fireEvent.click(screen.getByRole("tab", { name: "Scope" }));
    expect(screen.getByText(ONLY_IN_SCOPE)).toBeTruthy();
    fireEvent.click(screen.getByRole("tab", { name: "History" }));
    expect(screen.getByText(ONLY_IN_HISTORY)).toBeTruthy();

    expect(list.scrollTop).toBe(120);
    expect((within(screen.getByTestId("item-R2")).getByRole("checkbox") as HTMLInputElement).checked).toBe(true);
    expect(screen.getByTestId("queue-renders").textContent).toBe(rendersBefore);

    // And closing it takes the whole strip out again.
    fireEvent.click(expanderFor("R3"));
    expect(screen.queryAllByRole("tablist")).toHaveLength(0);
    expect(list.scrollTop).toBe(120);
    expect(screen.getByTestId("queue-renders").textContent).toBe(rendersBefore);
  });

  it("does not repeat a statement the surface above already quotes", () => {
    const row = candidate("R1");
    const { unmount } = render(
      <ActorProvider>
        <RuleDetailInline candidate={row} />
      </ActorProvider>,
    );
    // Nothing above a queue row carries the statement, so the detail carries it.
    expect(screen.getByText("What the document says")).toBeTruthy();
    unmount();

    render(
      <ActorProvider>
        <RuleDetailInline candidate={row} statementVisibleAbove />
      </ActorProvider>,
    );
    expect(screen.queryByText("What the document says")).toBeNull();
    // Control: the rest of the tab is still there, so this is a suppressed
    // block and not a component that failed to render.
    expect(screen.getByText(ONLY_IN_OVERVIEW)).toBeTruthy();
  });

  /**
   * The scaling claim, measured rather than asserted by eye.
   *
   * A policy of this size is the case the design has to survive. The numbers
   * are printed so they can be read in CI output and compared against the day
   * this was written, not just compared against a threshold.
   */
  it("costs one pane per open row, not seven, on a policy of many rules", () => {
    const many = Array.from({ length: 72 }, (_, i) => `R${i + 1}`);
    render(<QueueHarness ruleIds={many} />);

    const nodesClosed = document.querySelectorAll("*").length;
    expect(screen.queryAllByRole("tabpanel")).toHaveLength(0);

    for (const id of many) fireEvent.click(expanderFor(id));

    const nodesOpen = document.querySelectorAll("*").length;
    const panels = screen.getAllByRole("tabpanel");
    const tabs = screen.getAllByRole("tab");

    // 72 rows open: 72 strips of 7 tabs, and 72 panels — one each, not seven.
    expect(panels).toHaveLength(72);
    expect(tabs).toHaveLength(72 * 7);
    // Not one closed tab's body was built, over 72 rows.
    expect(screen.queryByText(ONLY_IN_JSON)).toBeNull();
    expect(screen.queryByText(ONLY_IN_HISTORY)).toBeNull();
    expect(screen.queryAllByText(ONLY_IN_OVERVIEW)).toHaveLength(72);

    // eslint-disable-next-line no-console
    console.log(
      `[72-rule policy] DOM elements — all rows closed: ${nodesClosed}; all rows open: ${nodesOpen}; ` +
        `per open row: ${((nodesOpen - nodesClosed) / 72).toFixed(1)}; tab panels built: ${panels.length}`,
    );
  }, 60_000);

  /**
   * The other half of the same claim: visiting a tab must not leave it mounted.
   *
   * A tab library that keeps every visited pane alive looks identical on screen
   * to one that does not — the reviewer sees one pane either way — and the cost
   * only shows up after a reviewer has worked down a long policy. So this walks
   * every tab, records what each one costs on its own, and asserts that after
   * the walk the row costs what its current tab costs and not the sum.
   */
  it("does not accumulate panes as tabs are visited", () => {
    render(<QueueHarness ruleIds={["R1"]} />);
    const empty = document.querySelectorAll("*").length;
    fireEvent.click(expanderFor("R1"));

    const perTab: Record<string, number> = {};
    for (const name of EVERY_TAB) {
      fireEvent.click(screen.getByRole("tab", { name }));
      perTab[name] = document.querySelectorAll("*").length - empty;
    }
    const afterWalk = document.querySelectorAll("*").length - empty;
    const ifAllSeven = EVERY_TAB.reduce((sum, name) => sum + perTab[name], 0);

    // Having been through all seven, the row costs what its last tab costs.
    expect(afterWalk).toBe(perTab[EVERY_TAB[EVERY_TAB.length - 1]]);
    // Control: the tabs are not all empty, so the comparison means something.
    expect(ifAllSeven).toBeGreaterThan(afterWalk);

    // eslint-disable-next-line no-console
    console.log(
      `[one rule] DOM elements added by the open row, per tab — ` +
        EVERY_TAB.map((name) => `${name}: ${perTab[name]}`).join("; ") +
        `; after visiting all seven: ${afterWalk}; if all seven were mounted at once: ${ifAllSeven} ` +
        `(×72 rules: ${afterWalk * 72} vs ${ifAllSeven * 72})`,
    );
  }, 30_000);

  /**
   * The panel that holds a whole policy: one control per rule, not two.
   *
   * This is the change stated at its plainest. A test that only checks the
   * expansion's contents would still pass with the second control sitting
   * beside it, and the second control is the thing the reviewer was losing
   * their place to.
   */
  it("gives a rule in the policy panel one control, and it opens the record in place", () => {
    const row = candidate("R1");
    const card: PolicyCard = {
      policy: {
        key: "prov-1",
        heading: "Attendance",
        heading_path: ["Staff handbook", "Attendance"],
        persisted: true,
        provision_id: "prov-1",
        document_version_id: "doc-1",
        source_elements: "p1-E1",
        page: 1,
        rule_count: 1,
        passage_count: 1,
        route: "read",
        passages: [],
        rules: [],
      },
      passages: [
        {
          passage: {
            key: "p1-E1",
            source_elements: "p1-E1",
            page: 1,
            rule_count: 1,
            rules: [],
          },
          rules: [{ rule_id: "R1", ...fromDraftRow(row), evaluation_mode: "ai_ready" }],
        },
      ],
      rules: [{ rule_id: "R1", ...fromDraftRow(row), evaluation_mode: "ai_ready" }],
      hiddenByFilter: 0,
      reviewableIds: [row.id],
      allIds: [row.id],
      reviewStatuses: ["candidate"],
    };

    render(
      <ActorProvider>
        <PolicyDetailPanel
          card={card}
          statusColor={() => "default"}
          statusLabel={() => "Pending"}
          ruleDetail={() => <RuleDetailInline candidate={row} statementVisibleAbove />}
        />
      </ActorProvider>,
    );

    // Control: the policy and its rule are on screen.
    expect(screen.getByText("Attendance")).toBeTruthy();
    revealTheRuleList();
    expect(screen.getAllByText(/Summary line for R1/).length).toBeGreaterThan(0);

    // No second destination.
    expect(screen.queryByRole("button", { name: /open rule/i })).toBeNull();

    const expander = screen.getByRole("button", { name: /Details/ });
    expect(expander.getAttribute("aria-expanded")).toBe("false");
    // The panel has chrome of its own, so count rather than assume zero: what
    // matters is that opening one rule adds exactly one strip.
    const stripsBefore = screen.queryAllByRole("tablist").length;

    fireEvent.click(expander);

    expect(screen.queryAllByRole("tablist")).toHaveLength(stripsBefore + 1);
    expect(expander.getAttribute("aria-expanded")).toBe("true");
    const region = document.getElementById(expander.getAttribute("aria-controls") ?? "");
    expect(region).toBeTruthy();
    expect(within(region as HTMLElement).getByRole("tablist")).toBeTruthy();
    expect(within(region as HTMLElement).getAllByRole("tab")).toHaveLength(EVERY_TAB.length);

    // The panel already quotes the passage above, so the detail does not quote
    // it a second time — it leads with what the panel does not already show.
    expect(within(region as HTMLElement).queryByText("What the document says")).toBeNull();
    expect(within(region as HTMLElement).getByText(ONLY_IN_OVERVIEW)).toBeTruthy();
  });
});

