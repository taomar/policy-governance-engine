/**
 * A rule opens where it stands, and the queue around it does not move.
 *
 * THE FAILURE THIS EXISTS TO PREVENT
 *
 * Reading a rule used to mean leaving the queue. The click sent the rule to a
 * separate surface and returning was a second click, and in between the
 * reviewer lost the thing they were actually doing: comparing this rule against
 * the rest of the policy it came from. They came back to a list they had to
 * find their place in again — a cost paid once per rule, on a queue of 692.
 *
 * So the detail opens in place. That is only worth anything if opening it
 * leaves everything else alone, and "leaves everything else alone" is four
 * separate claims that a plausible implementation can each break on its own:
 *
 *   1. The list does not scroll. An implementation that re-mounts rows, or
 *      focuses the opened region, moves the page under the reader's eyes.
 *   2. The reviewer's bulk selection survives. Selection lives above the row;
 *      an implementation that routes expansion through the queue's state can
 *      clear it without anyone noticing until a batch approval goes wrong.
 *   3. The queue itself does not re-render. A page holds dozens of rows and a
 *      row holds a rule; opening one must cost one row's work, not the page's.
 *      Asserted by counting the parent's renders, because the cheap version of
 *      this check — "it looks fast" — is not a check.
 *   4. Nothing of the detail exists in the document while the row is closed.
 *
 * And the expander must be an expander: a real button carrying `aria-expanded`
 * and pointing at the region it opens, so a reviewer who never sees the screen
 * is told the same thing as one who does.
 *
 * Every assertion below is paired with a control that fails when nothing
 * renders at all, because `expect(x).toBeNull()` is also what a blank page
 * returns.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useRef, useState } from "react";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import type { CandidateRule, CanonicalRule } from "./api";
import { CandidateRow } from "./components/CandidateRow";
import { PolicyInspector } from "./components/PolicyInspector";
import { RecordedAttributes } from "./components/RecordedAttributes";

beforeEach(() => {
  // antd reads both on mount and jsdom implements neither. Restored before
  // every test because the teardown below removes every stub, and the record
  // surface mounts antd components that read them on their first render.
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

/** Words that appear only inside the detail, never in the collapsed summary. */
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

/**
 * A page of the queue, standing in for ReviewQueue's list.
 *
 * It carries the two things the assertions are about that a single row cannot
 * show on its own: a scroll container the rows sit inside, and state owned
 * above the rows — the bulk selection, and a count of how many times this
 * component has rendered.
 */
function QueueHarness({ ruleIds }: { ruleIds: string[] }) {
  const [selected, setSelected] = useState<ReadonlySet<string>>(new Set());
  const renders = useRef(0);
  renders.current += 1;
  const rows = ruleIds.map((id) => candidate(id));
  return (
    <div>
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
              renderDetail={() => (
                /* The same reading the queue ships: the row's expansion is the
                   full record, not a shorter retelling of it. */
                <PolicyInspector
                  rule={row.rule}
                  variant="embedded"
                  recordKind="candidate"
                  recordLabel="candidate"
                  notesTarget={{
                    entityType: "candidate_rule",
                    entityId: row.id,
                    title: "Review discussion",
                  }}
                />
              )}
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

function expanderFor(ruleId: string): HTMLElement {
  const item = screen.getByTestId(`item-${ruleId}`);
  return within(item).getByRole("button", { name: new RegExp(`the detail for Summary line for ${ruleId}`) });
}

describe("a rule's detail opens where the rule stands", () => {
  it("puts none of the detail in the document until the row is opened", () => {
    render(<QueueHarness ruleIds={["R1", "R2", "R3"]} />);

    // Control: the summaries are all there, so an empty assertion below would
    // be reporting on a page that rendered.
    expect(screen.getAllByText(/Summary line for R/)).toHaveLength(3);

    expect(screen.queryByText(new RegExp(DETAIL_ONLY_TEXT))).toBeNull();
    expect(screen.queryByText(ATTRIBUTE_NAME)).toBeNull();
    expect(screen.queryByRole("region", { name: "Summary line for R1" })).toBeNull();

    fireEvent.click(expanderFor("R1"));

    expect(screen.getByRole("region", { name: "Summary line for R1" })).toBeTruthy();
    expect(screen.getByText(new RegExp(`${DETAIL_ONLY_TEXT} for R1`))).toBeTruthy();
    // Opening one row opens one row.
    expect(screen.queryByText(new RegExp(`${DETAIL_ONLY_TEXT} for R2`))).toBeNull();
  });

  it("says it is an expander, and says what it expands", () => {
    render(<QueueHarness ruleIds={["R1", "R2"]} />);

    const button = expanderFor("R1");
    expect(button.tagName).toBe("BUTTON");
    expect(button.getAttribute("aria-expanded")).toBe("false");
    expect(button.getAttribute("aria-controls")).toBeNull();

    fireEvent.click(button);

    const reopened = expanderFor("R1");
    expect(reopened.getAttribute("aria-expanded")).toBe("true");
    const controls = reopened.getAttribute("aria-controls");
    expect(controls).toBeTruthy();
    // The region it names is the region that holds the detail, and it exists.
    const region = document.getElementById(controls as string);
    expect(region).toBeTruthy();
    expect(region?.textContent).toContain(`${DETAIL_ONLY_TEXT} for R1`);

    fireEvent.click(expanderFor("R1"));
    expect(expanderFor("R1").getAttribute("aria-expanded")).toBe("false");
    expect(document.getElementById(controls as string)).toBeNull();
  });

  it("leaves the queue's scroll position, its selection and its render count alone", () => {
    render(<QueueHarness ruleIds={["R1", "R2", "R3", "R4"]} />);

    // Put the reviewer somewhere other than the top, and give them a selection.
    const list = screen.getByTestId("candidate-list");
    list.scrollTop = 120;
    const checkbox = within(screen.getByTestId("item-R2")).getByRole("checkbox");
    fireEvent.click(checkbox);
    expect((checkbox as HTMLInputElement).checked).toBe(true);

    const rendersBefore = screen.getByTestId("queue-renders").textContent;
    // Control: the harness has rendered at least once, so an unchanged count
    // below is a real "it did not render again" and not a missing element.
    expect(Number(rendersBefore)).toBeGreaterThan(0);

    fireEvent.click(expanderFor("R3"));
    expect(screen.getByRole("region", { name: "Summary line for R3" })).toBeTruthy();

    expect(list.scrollTop).toBe(120);
    expect((within(screen.getByTestId("item-R2")).getByRole("checkbox") as HTMLInputElement).checked).toBe(
      true,
    );
    expect(screen.getByTestId("queue-renders").textContent).toBe(rendersBefore);

    fireEvent.click(expanderFor("R3"));
    expect(list.scrollTop).toBe(120);
    expect(screen.getByTestId("queue-renders").textContent).toBe(rendersBefore);
  });

  it("shows every attribute as its own row of three parts, with the words unaltered", () => {
    render(<QueueHarness ruleIds={["R1"]} />);
    fireEvent.click(expanderFor("R1"));

    const region = screen.getByRole("region", { name: "Summary line for R1" });
    const rows = within(region).getAllByRole("row");
    // Control: two attribute tables, each with a header row and one body row.
    expect(rows.length).toBeGreaterThanOrEqual(4);

    const appliesRow = rows.find((r) => r.textContent?.includes(ATTRIBUTE_NAME));
    expect(appliesRow).toBeTruthy();
    const cells = Array.from((appliesRow as HTMLElement).querySelectorAll("th, td"));
    expect(cells).toHaveLength(3);
    expect(cells[0].textContent).toBe(ATTRIBUTE_NAME);
    expect(cells[1].textContent).toBe("A party named by R1");
    expect(cells[2].textContent).toContain("party_kind");

    // A run of the document that is not left-to-right is still the document's
    // words, whole. Direction is carried per run, not by the cell: the Arabic
    // sits in its own `bdi` while the cell still reads as one quotation.
    const arabicRun = within(region).getByText(ARABIC_RUN);
    expect(arabicRun.closest("bdi")).toBeTruthy();
    const arabicCell = arabicRun.closest("td");
    expect(arabicCell?.textContent).toBe(`Written notice ${ARABIC_RUN}`);
  });

  it("says a missing attribute table differently from an empty one", () => {
    // Rendered directly, because this is a claim about the display the reviewer
    // agreed to and not about where it is mounted. It is mounted in two places
    // now — the queue's expansion and the full record — and it says the same
    // thing in both because it is one component.
    const withoutTable = candidate("R1");
    delete (withoutTable.rule as { attributes?: unknown }).attributes;
    const { unmount } = render(<RecordedAttributes attributes={withoutTable.rule.attributes} />);
    // One per group: neither "what it applies to" nor "what follows" is known
    // when the record carried no table at all.
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
