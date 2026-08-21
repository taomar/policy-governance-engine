/**
 * The record surface and its attributes, tested where the detail now lives.
 *
 * DESIGN.md: "Don't expand a record inside the register. Only the record
 * under review expands, and it expands in the inspector."
 *
 * F2 moved the detail from inline expansion to the inspector. The row is now
 * summary-only: clicking it calls `onOpenFullRecord` to populate the
 * inspector. The first describe block verifies the row carries no detail.
 * The second block tests the record surface (PolicyInspector) directly — the
 * same component the inspector mounts — to confirm the properties that
 * travelled with the detail still hold where the detail now lives.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useRef, useState } from "react";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import type { CandidateRule, CanonicalRule } from "./api";
import { ActorProvider } from "./ActorContext";
import { CandidateRow } from "./components/CandidateRow";
import { PolicyInspector } from "./components/PolicyInspector";
import { RecordedAttributes } from "./components/RecordedAttributes";

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

const DETAIL_ONLY_TEXT = "the words a case is judged against";
const ATTRIBUTE_NAME = "subject_of_the_statement";
const ARABIC_RUN = "إنذار كتابي";

function canonical(ruleId: string): CanonicalRule {
  return {
    schema_version: "1.0",
    policy_set_id: "set",
    policy_version_id: "draft",
    rule_id: ruleId,
    rule_revision: 1,
    title: `Summary line for ${ruleId}`,
    description: `${DETAIL_ONLY_TEXT} for ${ruleId}`,
    rule_type: "obligation",
    authority: { level: "ai_drafted", owner: "formulator", rank: 0 },
    scope: { jurisdictions: [], organizational_units: [], personas: [], processes: [] },
    condition: { type: "all", all: [] },
    attributes: {
      applies: [
        { attribute: ATTRIBUTE_NAME, text: `A party named by ${ruleId}`, fact: "party_kind", data_type: null },
      ],
      outcome: [
        { attribute: "object", text: `Written notice ${ARABIC_RUN}`, fact: null, data_type: null },
      ],
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
  const openedRef = useRef<string | null>(null);
  const renders = useRef(0);
  renders.current += 1;
  const rows = ruleIds.map((id) => candidate(id));
  return (
    <div>
      <output data-testid="queue-renders">{renders.current}</output>
      <output data-testid="opened-record">{openedRef.current ?? ""}</output>
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
              onOpenFullRecord={() => { openedRef.current = row.id; }}
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
    </div>
  );
}

describe("a rule does not expand inside the register", () => {
  it("puts no detail region in the document — the detail lives in the inspector", () => {
    render(<QueueHarness ruleIds={["R1", "R2", "R3"]} />);

    // Control: the summaries are all there.
    expect(screen.getAllByText(/Summary line for R/)).toHaveLength(3);

    // No detail region, no description text, no expander.
    expect(screen.queryByRole("region")).toBeNull();
    expect(screen.queryByText(new RegExp(DETAIL_ONLY_TEXT))).toBeNull();
  });

  it("has no expander button — the row is summary-only", () => {
    render(<QueueHarness ruleIds={["R1"]} />);
    const item = screen.getByTestId("item-R1");
    const buttons = within(item).queryAllByRole("button");
    const expanderLabels = buttons
      .map((b) => b.getAttribute("aria-label") ?? "")
      .filter((l) => /detail|expand/i.test(l));
    expect(expanderLabels).toHaveLength(0);
  });

  it("clicking the row calls onOpenFullRecord to populate the inspector", () => {
    render(<QueueHarness ruleIds={["R1", "R2"]} />);
    const item = screen.getByTestId("item-R1");
    const row = within(item).getAllByRole("button")[0];
    fireEvent.click(row);
    expect(screen.queryByRole("region")).toBeNull();
  });

  it("the queue's selection survives a row click", () => {
    render(<QueueHarness ruleIds={["R1", "R2", "R3"]} />);
    const checkbox = within(screen.getByTestId("item-R2")).getByRole("checkbox");
    fireEvent.click(checkbox);
    expect((checkbox as HTMLInputElement).checked).toBe(true);

    const row = within(screen.getByTestId("item-R1")).getAllByRole("button")[0];
    fireEvent.click(row);

    expect((within(screen.getByTestId("item-R2")).getByRole("checkbox") as HTMLInputElement).checked).toBe(true);
  });
});

describe("the record surface renders its attributes faithfully", () => {
  it("shows every attribute as its own row of three parts, with the words unaltered", () => {
    renderInspector("R1");

    const rows = screen.getAllByRole("row");
    // Control: two attribute groups, each with a header row and body rows.
    expect(rows.length).toBeGreaterThanOrEqual(4);

    const appliesRow = rows.find((r) => r.textContent?.includes(ATTRIBUTE_NAME));
    expect(appliesRow).toBeTruthy();
    const cells = Array.from((appliesRow as HTMLElement).querySelectorAll("th, td"));
    expect(cells).toHaveLength(3);
    expect(cells[0].textContent).toBe(ATTRIBUTE_NAME);
    expect(cells[1].textContent).toBe("A party named by R1");
    expect(cells[2].textContent).toContain("party_kind");

    // A run of the document that is not left-to-right is still the document's
    // words, whole. Direction is carried per run, not by the cell.
    const arabicRun = screen.getByText(ARABIC_RUN);
    expect(arabicRun.closest("bdi")).toBeTruthy();
    const arabicCell = arabicRun.closest("td");
    expect(arabicCell?.textContent).toBe(`Written notice ${ARABIC_RUN}`);
  });

  it("says a missing attribute table differently from an empty one", () => {
    // Rendered directly: the claim is about the display, not about where it is
    // mounted. It says the same thing wherever it appears because it is one
    // component.
    const withoutTable = candidate("R1");
    delete (withoutTable.rule as { attributes?: unknown }).attributes;
    const { unmount } = render(<RecordedAttributes attributes={withoutTable.rule.attributes} />);
    expect(screen.getAllByText(/did not carry an attribute table/)).toHaveLength(2);
    expect(screen.queryByText(/present and names none/)).toBeNull();
    unmount();

    const withEmptyTable = candidate("R2");
    withEmptyTable.rule.attributes = { applies: [], outcome: [] };
    render(<RecordedAttributes attributes={withEmptyTable.rule.attributes} />);
    expect(screen.getAllByText(/present and names none/)).toHaveLength(2);
    expect(screen.queryByText(/did not carry an attribute table/)).toBeNull();
  });
});
