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
import { PolicyInspector } from "./components/PolicyInspector";

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
const ONLY_IN_HISTORY = "Current revision";
const ONLY_IN_JSON = "Evaluator JSON";
const ONLY_IN_NOTES = "Review discussion";
const ARABIC_RUN = "إنذار كتابي";

const EVERY_TAB = ["Overview", "Logic", "Parties & routes", "Scope", "Test scenario", "History", "Notes", "JSON"];

/** The caption that marks the real reading of a record, and the one thing the
 *  expansion's predecessor never carried: the words of the source document,
 *  quoted, with their citation. */
const THE_SOURCE_BLOCK = /Original source text — the exact words from the source document/i;

/** What the shipped queue passes when it opens a rule under its row. Written
 *  once so the harness cannot drift from the call site it stands for: the same
 *  component, embedded, told it is looking at a candidate, and given the policy
 *  set so the reviewer can put a case to the record they are deciding. */
function inlineRecord(row: CandidateRule) {
  return (
    <PolicyInspector
      rule={row.rule}
      policySetKey="set"
      variant="embedded"
      recordKind="candidate"
      recordLabel="candidate"
      notesTarget={{ entityType: "candidate_rule", entityId: row.id, title: "Review discussion" }}
    />
  );
}

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
              renderDetail={() => inlineRecord(row)}
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
    // Trimmed: a tab's label may carry a decorative icon beside its words, and
    // the whitespace that separates them is not a claim about anything.
    expect(tabs.map((t) => (t.textContent ?? "").trim())).toEqual(EVERY_TAB);

    // Exactly one is selected, and it is the first.
    const selected = tabs.filter((t) => t.getAttribute("aria-selected") === "true");
    expect(selected).toHaveLength(1);
    expect(selected[0].textContent).toBe("Overview");

    // What a reviewer judges the rule on is open, unclicked.
    //
    // THE LINE BETWEEN THE FIRST TAB AND THE REST
    //
    // Overview carries the rule as the document states it: its statement, and
    // every attribute as recorded — the subject, the condition, the modality,
    // the predicate and the consequence, each in the document's own words,
    // beside the identifier a case supplies a value for. That is the test in
    // the words it was written in, and it is enough to judge the rule.
    //
    // Logic carries the same rule compiled — the condition as a tree, the
    // required facts, the exceptions and the caps it shares. That is a derived
    // reading, and one click for a derived reading is the right price. It is
    // not copied onto Overview: a second copy of the record's logic is exactly
    // the drift the fold was built to close.
    const panel = screen.getByRole("tabpanel");
    expect(within(panel).getByText(ONLY_IN_OVERVIEW)).toBeTruthy();
    expect(within(panel).getByText("Every attribute, as recorded")).toBeTruthy();
    expect(panel.textContent).toContain("The words the document uses for R1");
  });

  it("builds nothing for a tab that has not been opened, and keeps what it built", () => {
    render(<QueueHarness ruleIds={["R1"]} />);
    fireEvent.click(expanderFor("R1"));

    // Control: the open tab's body is there to be found.
    expect(screen.getByText(ONLY_IN_OVERVIEW)).toBeTruthy();

    // Nothing else is built. This is the claim that matters at the length of a
    // queue: a row that renders every pane and shows one pays for all of them,
    // times the number of rows.
    for (const unopened of [ONLY_IN_LOGIC, ONLY_IN_HISTORY, ONLY_IN_JSON, ONLY_IN_NOTES]) {
      expect(screen.queryByText(unopened)).toBeNull();
    }

    fireEvent.click(screen.getByRole("tab", { name: "Logic" }));
    expect(screen.getByText(ONLY_IN_LOGIC)).toBeTruthy();
    // Still nothing built for the tabs nobody has asked for.
    expect(screen.queryByText(ONLY_IN_JSON)).toBeNull();
    expect(screen.queryByText(ONLY_IN_HISTORY)).toBeNull();

    // A pane that has been opened stays built. This is a change from the
    // queue's own tab strip, which tore each pane down on the way out, and it
    // is the better behaviour rather than a cost of adopting the shared one:
    // going to Logic to check a rule fires and back to Overview must not
    // discard what the reviewer had already scrolled to or typed. What is
    // avoided is building panes nobody opened, and that still holds above.
    expect(screen.getByText(ONLY_IN_OVERVIEW)).toBeTruthy();
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

    // One strip, and every tab in it points at the panel it opens, so a reader
    // who never sees the screen is told what a sighted one is shown.
    expect(screen.getAllByRole("tablist")).toHaveLength(1);

    const tabs = screen.getAllByRole("tab");
    for (const tab of tabs) {
      expect(tab.getAttribute("aria-controls")).toBeTruthy();
    }
    // Reaching the strip costs one Tab, and leaving it costs one more.
    expect(tabs.filter((t) => t.getAttribute("tabindex") === "0")).toHaveLength(1);

    const open = tabs.find((t) => t.getAttribute("aria-selected") === "true") as HTMLElement;
    const panel = screen.getByRole("tabpanel");
    expect(panel.id).toBe(open.getAttribute("aria-controls"));
    expect(panel.getAttribute("aria-labelledby")).toBe(open.id);
  });

  /**
   * The strip is manually activated: arrows move the focus, Enter or Space
   * opens what the focus is on.
   *
   * This is the deliberate half of adopting the shared strip. Automatic
   * activation — open whatever the arrow lands on — builds every pane a
   * keyboard user travels past, and the panes here are the whole record: the
   * logic tree, the version history, the raw JSON. A reader crossing the strip
   * to reach JSON would build six panes to read one. Manual activation is what
   * the ARIA practices recommend exactly when panes are expensive, and it is
   * what makes "costs what its reader opened" hold for a keyboard user too.
   */
  it("moves the focus with the arrow keys, and opens what it lands on with Enter or Space", () => {
    render(<QueueHarness ruleIds={["R1"]} />);
    fireEvent.click(expanderFor("R1"));

    const openTab = () => {
      const tab = screen.getByRole("tab", { selected: true });
      // The strip inserts its own position announcement — "Tab 2 of 8" — for a
      // reader who cannot see how far along the strip they are. It is not part
      // of the tab's name, so it comes off before comparing.
      return (tab.textContent ?? "").replace(/^Tab \d+ of \d+/, "").trim();
    };
    /** Any tab in the strip reaches the strip's own handler, and the first one
     *  is the stable handle: its name gains a position announcement once it is
     *  focused, so it is taken by position rather than by name. */
    const strip = () => screen.getAllByRole("tab")[0];
    const press = (code: string) => fireEvent.keyDown(strip(), { code });

    expect(openTab()).toBe("Overview");

    // Travelling past a tab does not open it.
    press("ArrowRight");
    expect(openTab()).toBe("Overview");

    // Asking for it does.
    press("Enter");
    expect(openTab()).toBe("Logic");

    press("End");
    expect(openTab()).toBe("Logic");
    press("Space");
    expect(openTab()).toBe("JSON");

    press("Home");
    press("Enter");
    expect(openTab()).toBe("Overview");

    press("ArrowLeft");
    press("Enter");
    expect(openTab()).toBe("JSON");
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

  it("repeats the statement, and earns the repetition by carrying the source", () => {
    const row = candidate("R1");
    render(<ActorProvider>{inlineRecord(row)}</ActorProvider>);

    // The card above quotes the statement, and so does this. That repetition
    // used to be suppressed by a flag, back when the expansion drew panes of its
    // own and had nothing else to offer. Keeping the flag meant keeping a second
    // reading of a record alive, which is the drift this work exists to close.
    expect(screen.getAllByText(/The words the document uses for R1/).length).toBeGreaterThan(0);

    // What the repetition buys: the source document's own words, under a
    // caption naming them as such. The predecessor never carried this — it
    // linked out to "the full record" as though the full record were elsewhere.
    expect(screen.getByText(THE_SOURCE_BLOCK)).toBeTruthy();

    // Control: this is the record's reading and not some fragment of it.
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

    // 72 rows open: 72 strips, and 72 panels — one each, not one per tab.
    expect(panels).toHaveLength(72);
    expect(tabs).toHaveLength(72 * EVERY_TAB.length);
    // Not one unopened tab's body was built, over 72 rows.
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
   * The other half of the same claim: a row costs the tabs its reader opened.
   *
   * A tab strip that mounts everything up front looks identical on screen to one
   * that does not — the reviewer sees one pane either way — and the cost only
   * shows up after a reviewer has worked down a long policy. So this measures
   * what an untouched row costs against what a row costs whose reader has been
   * through every tab, and asserts the first is a fraction of the second.
   *
   * A pane, once opened, stays. That is deliberate and is asserted above: going
   * to Logic and back must not discard what the reviewer had scrolled to or
   * typed into Overview. What must never happen is paying that price for tabs
   * nobody opened, which is what the gap measured here proves is not happening.
   */
  it("costs what its reader opened, not what it could open", () => {
    render(<QueueHarness ruleIds={["R1"]} />);
    const empty = document.querySelectorAll("*").length;
    fireEvent.click(expanderFor("R1"));

    // A row nobody has clicked a tab in: one pane, the one it opened on.
    const justOpened = document.querySelectorAll("*").length - empty;

    const perTab: Record<string, number> = {};
    let running = justOpened;
    for (const name of EVERY_TAB) {
      fireEvent.click(screen.getByRole("tab", { name }));
      const now = document.querySelectorAll("*").length - empty;
      perTab[name] = now - running;
      running = now;
    }
    const afterWalk = document.querySelectorAll("*").length - empty;

    // The whole point: reading a rule costs a fraction of reading all of it.
    expect(justOpened).toBeLessThan(afterWalk);
    // Control: the strip itself is not the whole cost, so the gap is panes.
    expect(justOpened).toBeGreaterThan(0);

    // eslint-disable-next-line no-console
    console.log(
      `[one rule] DOM elements added by the open row — on opening: ${justOpened}; ` +
        `added by each tab as it was opened — ` +
        EVERY_TAB.map((name) => `${name}: ${perTab[name]}`).join("; ") +
        `; after opening every tab: ${afterWalk} ` +
        `(×72 rules: ${justOpened * 72} read, vs ${afterWalk * 72} fully explored)`,
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
      // No set: this fixture exercises where a rule's tabs open, not where the
      // policy was published from. Absent, so nothing is looked up by it.
      policy_set_key: null,
    };

    render(
      <ActorProvider>
        <PolicyDetailPanel
          card={card}
          statusColor={() => "default"}
          statusLabel={() => "Pending"}
          ruleDetail={() => inlineRecord(row)}
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

/**
 * ONE READING OF A RECORD, ACROSS THE WHOLE FILE
 *
 * The behavioural tests above prove that the expansion they render is the full
 * record. They cannot prove there is no *second* expansion elsewhere in the
 * queue rendering something shorter — and that is exactly how this drifted the
 * first time. A guard written against the one expansion its author was looking
 * at passed while a second sat hundreds of lines below it, and the two readings
 * of one record went on diverging.
 *
 * So this reads the whole file and counts. It is deliberately mechanical: it
 * does not care which expansion is which, only that every one of them mounts
 * the same component and that no shorter renderer is reachable at all.
 */
describe("the queue has one reading of a record and no second one", () => {
  const SOURCES = import.meta.glob("./components/ReviewQueue.tsx", {
    query: "?raw",
    import: "default",
    eager: true,
  }) as Record<string, string>;

  const source = () => {
    const entries = Object.entries(SOURCES);
    // Control: a glob that matches nothing passes every assertion below in
    // silence, so the file count is asserted before anything is read from it.
    expect(entries).toHaveLength(1);
    return entries[0][1];
  };

  it("imports no shorter renderer of a rule", () => {
    const text = source();
    // Control: the file does import the reading it is supposed to use, so a
    // rename that broke every match would fail here rather than pass quietly.
    expect(text).toContain("PolicyInspector");

    for (const shorter of ["RuleDetailInline", "InlineTabs", "RuleCard"]) {
      expect(text.includes(shorter)).toBe(false);
    }
  });

  it("mounts the record surface everywhere a rule's detail is drawn", () => {
    const text = source();

    // Every callback the queue hands to a row or a card for drawing a rule's
    // detail. Both names are counted because the two surfaces spell it
    // differently, and a third spelling should show up here as a shortfall
    // rather than as an unnoticed second reading.
    const detailCallbacks = [
      ...text.matchAll(/\b(renderDetail|ruleDetail)=\{/g),
    ].map((m) => m[1]);
    const mounts = [...text.matchAll(/<PolicyInspector\b/g)];

    // Control: both are found, so neither count is the count of a typo.
    expect(detailCallbacks.length).toBeGreaterThan(0);
    expect(mounts.length).toBeGreaterThan(0);

    // Pinned. A fourth mount or a third detail callback is a decision about
    // where a record can be read, and it should be made on purpose.
    expect(detailCallbacks).toHaveLength(2);
    expect(mounts).toHaveLength(4);
  });

  it("tells the record surface whose notes it is showing, wherever it is embedded", () => {
    const text = source();

    // A rule's notes default to the published rule's own identity. An embedded
    // expansion of a *candidate* that accepted that default would file a
    // reviewer's note against the record they are not looking at, so every
    // embedded mount has to name its target.
    const embedded = [...text.matchAll(/<PolicyInspector\b[\s\S]{0,900}?\/>/g)]
      .map((m) => m[0])
      .filter((m) => m.includes('variant="embedded"'));

    // Control: the embedded mounts exist to be checked.
    expect(embedded).toHaveLength(2);
    for (const mount of embedded) {
      expect(mount).toContain("notesTarget=");
      expect(mount).toContain("candidate_rule");
    }
  });
});

