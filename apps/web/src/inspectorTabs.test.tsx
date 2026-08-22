/**
 * The inspector's tab strip and its properties.
 *
 * THE FAILURE THIS EXISTS TO PREVENT
 *
 * The detail used to open inside each row. F2 moved it to the inspector, but
 * the *behaviour* of the tabs — lazy construction, caching, ARIA relationships,
 * keyboard navigation, and one-renderer-per-record — is the same wherever the
 * detail lives. This file tests those properties against PolicyInspector
 * directly. A second describe block tests that the row itself carries no tabs
 * (the row is now summary-only). A third reads ReviewQueue.tsx source to
 * confirm one record surface, one import path, and correct notes targets.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useState } from "react";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import type { CandidateRule, CanonicalRule } from "./api";
import { ActorProvider } from "./ActorContext";
import { CandidateRow } from "./components/CandidateRow";
import { PolicyInspector } from "./components/PolicyInspector";
import * as ruleIdentity from "./ruleIdentity";

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
const ONLY_IN_HISTORY = "Current revision";
const ONLY_IN_JSON = "Evaluator JSON";
const ONLY_IN_NOTES = "Review discussion";
const ARABIC_RUN = "إنذار كتابي";

/** The caption marking the source text — the record's traceability claim. */
const THE_SOURCE_BLOCK = /Original source text — the exact words from the source document/i;

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

/** Render the inspector the same way the queue does when a record is selected. */
function renderInspector(ruleId: string) {
  const row = candidate(ruleId);
  return render(
    <ActorProvider>
      <PolicyInspector
        rule={row.rule}
        policySetKey="set"
        variant="embedded"
        recordKind="candidate"
        recordLabel="candidate"
        notesTarget={{
          entityType: "candidate_rule",
          entityId: row.id,
          title: "Review discussion",
        }}
      />
    </ActorProvider>,
  );
}

function QueueHarness({ ruleIds }: { ruleIds: string[] }) {
  const [selected, setSelected] = useState<ReadonlySet<string>>(new Set());
  const rows = ruleIds.map((id) => candidate(id));
  return (
    <div data-testid="candidate-list">
      {rows.map((row) => (
        <div key={row.id} data-testid={`item-${row.rule.rule_id}`}>
          <CandidateRow
            candidate={row}
            active={false}
            selected={selected.has(row.id)}
            selectable
            findingsCount={0}
            statusColor="default"
            statusLabel="Pending"
            onOpenFullRecord={() => {}}
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
  );
}

// ---------------------------------------------------------------------------
// Inspector tab behaviour — tested directly against PolicyInspector
// ---------------------------------------------------------------------------

describe("the inspector's tab strip", () => {
  it("builds nothing for a tab that has not been opened, and keeps what it built", () => {
    renderInspector("R1");

    // Control: the open tab's body is there to be found.
    expect(screen.getByText(ONLY_IN_OVERVIEW)).toBeTruthy();

    // Nothing else is built.
    for (const unopened of [ONLY_IN_LOGIC, ONLY_IN_HISTORY, ONLY_IN_JSON, ONLY_IN_NOTES]) {
      expect(screen.queryByText(unopened)).toBeNull();
    }

    fireEvent.click(screen.getByRole("tab", { name: "Logic" }));
    expect(screen.getByText(ONLY_IN_LOGIC)).toBeTruthy();
    // Still nothing built for the tabs nobody has asked for.
    expect(screen.queryByText(ONLY_IN_JSON)).toBeNull();
    expect(screen.queryByText(ONLY_IN_HISTORY)).toBeNull();

    // A pane that has been opened stays built — going to Logic and back must
    // not discard what the reviewer had scrolled to.
    expect(screen.getByText(ONLY_IN_OVERVIEW)).toBeTruthy();
  });

  it("does not run an unopened tab's body, not merely hide it", () => {
    // The assertion above cannot tell a lazy inspector from an eager one.
    // Antd does not mount a hidden pane either way, so "the text is absent"
    // holds even when every body was constructed and thrown away — which is
    // exactly the cost this surface pays per row, on a policy that can hold
    // seventy of them.
    //
    // So this watches for *work*, not for DOM. `withRuleIdentity` runs while
    // the Overview body is being built and nowhere else, and Overview is
    // opened here only on the second half of the test. An eager inspector
    // calls it on the first render regardless of which tab is showing.
    //
    // This is the guard that was missing: the lazy construction landed on a
    // sibling branch, was lost when this branch forked, and every tab test
    // still passed without it.
    const spy = vi.spyOn(ruleIdentity, "withRuleIdentity");
    const row = candidate("R1");

    function Harness() {
      const [tab, setTab] = useState("logic");
      return (
        <ActorProvider>
          <PolicyInspector
            rule={row.rule}
            policySetKey="set"
            variant="embedded"
            recordKind="candidate"
            recordLabel="candidate"
            activeTabKey={tab}
            onTabChange={setTab}
            notesTarget={{ entityType: "candidate_rule", entityId: row.id, title: "Review discussion" }}
          />
        </ActorProvider>
      );
    }

    render(<Harness />);

    // Logic is showing. Overview was never opened, so its body was never built.
    expect(screen.getByText(ONLY_IN_LOGIC)).toBeTruthy();
    expect(spy).not.toHaveBeenCalled();

    // Opening it builds it, which is the other half of the property: lazy, not absent.
    fireEvent.click(screen.getByRole("tab", { name: "Overview" }));
    expect(screen.getByText(ONLY_IN_OVERVIEW)).toBeTruthy();
    expect(spy).toHaveBeenCalled();

    spy.mockRestore();
  });

  it("keeps the logic tree the reviewer already reads, rather than a second rendering of it", () => {
    renderInspector("R1");
    fireEvent.click(screen.getByRole("tab", { name: "Logic" }));

    const panel = screen.getByRole("tabpanel");
    expect(within(panel).getByText(ONLY_IN_LOGIC)).toBeTruthy();
    expect(panel.querySelector(".policy-attr-name")).toBeTruthy();
    expect(panel.textContent).toContain("subject_of_the_statement");
    // The document's non-Latin run is still one isolated run of the document's
    // own characters, inside the tree.
    const arabic = within(panel).getByText(ARABIC_RUN);
    expect(arabic.tagName).toBe("BDI");
    expect(arabic.getAttribute("dir")).toBe("rtl");
    expect(within(panel).getByText(/Written notice/).tagName).toBe("BDI");
  });

  it("names the panel each tab controls, and keeps one tab in the page's tab order", () => {
    renderInspector("R1");

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
   * Manual activation: arrows move focus, Enter or Space opens the tab.
   * Automatic activation would build every pane a keyboard user travels past.
   */
  it("moves the focus with the arrow keys, and opens what it lands on with Enter or Space", () => {
    renderInspector("R1");

    const openTab = () => {
      const tab = screen.getByRole("tab", { selected: true });
      return (tab.textContent ?? "").replace(/^Tab \d+ of \d+/, "").trim();
    };
    const strip = () => screen.getAllByRole("tab")[0];
    const press = (code: string) => fireEvent.keyDown(strip(), { code });

    expect(openTab()).toBe("Overview");

    // Travelling past a tab does not open it.
    press("ArrowRight");
    expect(openTab()).toBe("Overview");

    // Asking for it does.
    press("Enter");
    expect(openTab()).toBe("Logic");

    // Space works too.
    press("ArrowRight");
    press("Space");
    expect(openTab()).toBe("Parties & routes");

    // End and Home.
    press("End");
    expect(openTab()).toBe("Parties & routes");
    press("Space");
    expect(openTab()).toBe("JSON");

    press("Home");
    press("Enter");
    expect(openTab()).toBe("Overview");

    // Wrap around.
    press("ArrowLeft");
    press("Enter");
    expect(openTab()).toBe("JSON");
  });

  it("repeats the statement, and earns the repetition by carrying the source", () => {
    renderInspector("R1");

    expect(screen.getAllByText(/The words the document uses for R1/).length).toBeGreaterThan(0);

    // What the repetition buys: the source document's own words, under a
    // caption naming them as such.
    expect(screen.getByText(THE_SOURCE_BLOCK)).toBeTruthy();

    // Control: this is the record's full reading.
    expect(screen.getByText(ONLY_IN_OVERVIEW)).toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
// The row carries no tabs (F2)
// ---------------------------------------------------------------------------

describe("the row does not expand in place", () => {
  it("puts no tab strip, no tab panel, and no detail region inside the row", () => {
    render(<QueueHarness ruleIds={["R1", "R2", "R3"]} />);

    // Control: summaries render.
    expect(screen.getAllByText(/Summary line for R/)).toHaveLength(3);

    expect(screen.queryAllByRole("tablist")).toHaveLength(0);
    expect(screen.queryAllByRole("tab")).toHaveLength(0);
    expect(screen.queryAllByRole("tabpanel")).toHaveLength(0);
    expect(screen.queryByRole("region")).toBeNull();
  });

  it("scales: 72 rows build 72 summaries and nothing else", () => {
    const many = Array.from({ length: 72 }, (_, i) => `R${i + 1}`);
    render(<QueueHarness ruleIds={many} />);

    expect(screen.getAllByText(/Summary line for R/)).toHaveLength(72);
    expect(screen.queryAllByRole("tablist")).toHaveLength(0);
    expect(screen.queryAllByRole("tabpanel")).toHaveLength(0);
  });
});

// ---------------------------------------------------------------------------
// One reading of a record, across ReviewQueue.tsx — source-level guards
// ---------------------------------------------------------------------------

describe("the queue has one reading of a record and no second one", () => {
  const SOURCES = import.meta.glob("./components/ReviewQueue.tsx", {
    query: "?raw",
    import: "default",
    eager: true,
  }) as Record<string, string>;

  const source = () => {
    const entries = Object.entries(SOURCES);
    expect(entries).toHaveLength(1);
    return entries[0][1];
  };

  it("imports no shorter renderer of a rule", () => {
    const text = source();
    // Control: the file does import the reading it is supposed to use.
    expect(text).toContain("PolicyInspector");

    for (const shorter of ["RuleDetailInline", "InlineTabs", "RuleCard"]) {
      expect(text.includes(shorter)).toBe(false);
    }
  });

  it("mounts the record surface everywhere a rule's detail is drawn", () => {
    const text = source();

    // F2 removed inline expansion: only one detail callback remains (the
    // PolicyDetailPanel's `ruleDetail`). Pinned so a new callback or mount
    // is a deliberate decision.
    const detailCallbacks = [
      ...text.matchAll(/\b(renderDetail|ruleDetail)=\{/g),
    ].map((m) => m[1]);
    const mounts = [...text.matchAll(/<PolicyInspector\b/g)];

    expect(detailCallbacks.length).toBeGreaterThan(0);
    expect(mounts.length).toBeGreaterThan(0);

    expect(detailCallbacks).toHaveLength(1);
    expect(mounts).toHaveLength(3);
  });

  it("tells the record surface whose notes it is showing, wherever it is embedded", () => {
    const text = source();

    const embedded = [...text.matchAll(/<PolicyInspector\b[\s\S]{0,900}?\/>/g)]
      .map((m) => m[0])
      .filter((m) => m.includes('variant="embedded"'));

    // One embedded mount remains (the PolicyDetailPanel's ruleDetail callback).
    // The panel mount and the superseded-record modal use no variant.
    expect(embedded).toHaveLength(1);
    for (const mount of embedded) {
      expect(mount).toContain("notesTarget=");
      expect(mount).toContain("candidate_rule");
    }
  });
});
