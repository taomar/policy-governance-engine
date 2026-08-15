/**
 * Overview traces the policy, and does not restate the header.
 *
 * WHY THESE TESTS
 *
 * The tab used to render three grey pills — page, passages, rules — under a
 * card header that had just stated the same three facts, and nothing else. A
 * reviewer said they could not trace the policy, which was exactly right: the
 * whole provenance chain was loaded and none of it was on screen.
 *
 * These pin both halves. The repetition must not come back, because it is the
 * kind of thing a later tidy-up restores while thinking it is being helpful.
 * And the chain must stay honest — every link is optional, and a link this app
 * has not loaded has to read differently from a link that is genuinely empty.
 * A policy never published and a policy whose history was never fetched are
 * different facts, and if both render blank the reader cannot tell which they
 * are looking at.
 */
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type {
  AssembledPassage,
  AssembledPolicy,
  CanonicalRule,
  ReviewFacetRun,
} from "../api";
import { PolicyOverviewPane, type PolicyRecordView, type PolicySightingView } from "./policyTabPanes";
import { policyProvenance } from "./policyProvenance";

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

function rule(id: string, runId: string | null): CanonicalRule {
  return {
    rule_id: id,
    title: `Rule ${id}`,
    effect: "allow",
    condition: { type: "all", all: [] },
    obligations: [],
    exceptions: [],
    scope: {},
    source: { document_id: "d", quotes: [] },
    lineage: { extraction_run_id: runId, schema_version: "1" },
  } as unknown as CanonicalRule;
}

function passage(page: number | null): AssembledPassage {
  return { key: `p${page}`, source_elements: `p${page}-E1`, page, rule_count: 1, rules: [] };
}

function record(overrides: {
  rules?: CanonicalRule[];
  passages?: AssembledPassage[];
  policy?: Partial<AssembledPolicy>;
  progress?: PolicyRecordView["progress"];
} = {}): PolicyRecordView {
  const rules = overrides.rules ?? [rule("a", "run-1")];
  return {
    policy: {
      key: "SECTION-KEY-42",
      heading: "The heading",
      heading_path: ["Above", "The heading"],
      passages: overrides.passages ?? [passage(1)],
      page: 1,
      persisted: true,
      provision_id: null,
      document_version_id: "dv-1",
      source_elements: "p1-E1",
      rules: [],
      rule_count: rules.length,
      passage_count: 1,
      route: "computable",
      ...overrides.policy,
    } as unknown as AssembledPolicy,
    passageCount: (overrides.passages ?? [passage(1)]).length,
    rules: rules.map((r) => ({ rule_id: r.rule_id, rule: r })),
    progress: overrides.progress,
  };
}

function facetRun(id: string, overrides: Partial<ReviewFacetRun> = {}): ReviewFacetRun {
  return {
    id,
    reference: `RUN-${id.toUpperCase()}`,
    status: "completed",
    started_at: "2026-01-02T03:04:05Z",
    document_id: "doc-1",
    document_title: "The Source Document",
    document_version_id: "dv-1",
    version_label: "v1",
    content_hash: "abc123",
    total: 1,
    pending: 0,
    delta: { new: 1, changed: 0, unchanged: 0, baseline: 0 },
    ...overrides,
  } as ReviewFacetRun;
}

function sighting(overrides: Partial<PolicySightingView> = {}): PolicySightingView {
  return {
    version_id: "pv-1",
    version_number: 3,
    is_active: true,
    approved_by: "someone",
    approved_at: "2026-02-03T04:05:06Z",
    heading_path: [],
    change: "unchanged",
    rules: [],
    rules_added: [],
    rules_removed: [],
    rules_reworded: [],
    ...overrides,
  };
}

describe("Overview does not say again what the header just said", () => {
  it("renders no page, passage or rule count pill", () => {
    const { container } = render(
      <PolicyOverviewPane record={record({ passages: [passage(4), passage(5)] })} />,
    );
    const tagText = [...container.querySelectorAll(".ant-tag")].map((t) => t.textContent ?? "");
    // The header states these. Restating them here was the whole complaint.
    expect(tagText.some((t) => /^Page \d+$/.test(t))).toBe(false);
    expect(tagText.some((t) => /passages?$/.test(t))).toBe(false);
    expect(tagText.some((t) => /rules?$/.test(t))).toBe(false);
  });
});

describe("Overview traces the chain from document to record", () => {
  it("names the file and the version the policy was read from", () => {
    render(<PolicyOverviewPane record={record()} runs={[facetRun("run-1")]} />);
    expect(screen.getByText("The Source Document")).toBeTruthy();
    expect(screen.getByText(/version v1/)).toBeTruthy();
  });

  it("gives the policy key as a handle, not as prose", () => {
    const { container } = render(<PolicyOverviewPane record={record()} />);
    const codes = [...container.querySelectorAll("code")].map((c) => c.textContent);
    expect(codes).toContain("SECTION-KEY-42");
  });

  it("names every extraction that produced a rule, not just one", () => {
    render(
      <PolicyOverviewPane
        record={record({ rules: [rule("a", "run-1"), rule("b", "run-2")] })}
        runs={[facetRun("run-1"), facetRun("run-2")]}
      />,
    );
    expect(screen.getByTestId("run-reference-run-1")).toBeTruthy();
    expect(screen.getByTestId("run-reference-run-2")).toBeTruthy();
    // And says out loud that there is more than one, which is a finding.
    expect(screen.getByText(/more than one extraction/)).toBeTruthy();
  });

  it("gives the run's own id when the run itself is not loaded, rather than inventing a reference", () => {
    render(<PolicyOverviewPane record={record()} runs={null} />);
    expect(screen.getByTestId("run-reference-run-1").textContent).toBe("run-1");
  });

  it("reports a page range rather than a single page when the policy spans pages", () => {
    render(<PolicyOverviewPane record={record({ passages: [passage(7), passage(9)] })} />);
    expect(screen.getByText(/from page 7 to page 9/)).toBeTruthy();
  });
});

describe("absent is not empty", () => {
  it("says it has not looked, rather than that nothing was found", () => {
    render(<PolicyOverviewPane record={record()} sightings={null} />);
    expect(screen.getByText(/has not looked for published versions/)).toBeTruthy();
    expect(screen.queryByText(/No published version carries this key/)).toBeNull();
  });

  it("says nothing was found, once it has looked", () => {
    render(<PolicyOverviewPane record={record()} sightings={[]} />);
    expect(screen.getByText(/No published version carries this key/)).toBeTruthy();
    expect(screen.queryByText(/has not looked/)).toBeNull();
  });

  it("offers a way to look, rather than leaving the reader at a dead end", () => {
    const ask = vi.fn();
    render(<PolicyOverviewPane record={record()} sightings={null} onRequestSightings={ask} />);
    fireEvent.click(screen.getByTestId("overview-request-sightings"));
    expect(ask).toHaveBeenCalledTimes(1);
  });

  it("lists the versions carrying the key once they are known", () => {
    render(<PolicyOverviewPane record={record()} sightings={[sighting()]} />);
    expect(screen.getByText("Version 3")).toBeTruthy();
    expect(screen.getByText("Active")).toBeTruthy();
  });
});

describe("review progress is a fact about the record, not a permission", () => {
  it("says how many rules are still open when some are", () => {
    render(<PolicyOverviewPane record={record({ progress: { decided: 3, open: 2 } })} />);
    expect(screen.getByText(/3 of its 5 rules have been decided; 2 are still open/)).toBeTruthy();
  });

  it("says nothing about progress on a record that has none to report", () => {
    render(<PolicyOverviewPane record={record({ progress: null })} />);
    expect(screen.queryByText(/How far through review it is/i)).toBeNull();
    // Emphatically not "0 open", which would invite a reader to look for a
    // decision that was never pending.
    expect(screen.queryByText(/still open/)).toBeNull();
  });
});

describe("the chain refuses to guess", () => {
  it("resolves the document from the policy's own version, not from a neighbouring run", () => {
    const chain = policyProvenance(record({ policy: { document_version_id: "dv-OTHER" } }), {
      runs: [facetRun("run-1", { document_version_id: "dv-1", document_title: "Wrong file" })],
    });
    // The run that produced its rules is the fallback, so a title does appear —
    // but the version id it reports is the policy's own, never the run's guess.
    expect(chain.document.versionId).toBe("dv-OTHER");
  });

  it("reports no document at all when nothing can resolve one", () => {
    const chain = policyProvenance(record(), { runs: [] });
    expect(chain.document.title).toBeNull();
    expect(chain.document.contentHash).toBeNull();
  });

  it("counts a run once per rule it produced", () => {
    const chain = policyProvenance(
      record({ rules: [rule("a", "run-1"), rule("b", "run-1"), rule("c", "run-2")] }),
      { runs: [facetRun("run-1"), facetRun("run-2")] },
    );
    expect(chain.runs.map((r) => [r.id, r.rules])).toEqual([
      ["run-1", 2],
      ["run-2", 1],
    ]);
  });

  it("distinguishes never-asked from asked-and-empty", () => {
    expect(policyProvenance(record(), {}).publication).toEqual({ known: false });
    expect(policyProvenance(record(), { sightings: [] }).publication).toEqual({
      known: true,
      versions: [],
    });
  });
});
