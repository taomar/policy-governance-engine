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

/* ------------------------------------------------------------------------ */
/* The rewrite: a roster, the document's own words, and no debugging panel.   */
/* ------------------------------------------------------------------------ */

describe("the Overview names the rules the policy holds", () => {
  it("lists every rule, with what it states and the id it is known by", () => {
    const view = record({ rules: [rule("a", "run-1"), rule("b", "run-1")] });
    view.rules[0].route = "deterministic";
    view.rules[1].route = "ai_ready";
    render(<PolicyOverviewPane record={view} />);

    // The thing a reviewer most wants to scan, and the tab named not one of
    // them before this.
    const rows = screen.getAllByTestId("overview-rule");
    expect(rows).toHaveLength(2);
    expect(rows[0].textContent).toContain("Rule a");
    expect(rows[1].textContent).toContain("Rule b");

    const ids = [...document.querySelectorAll("code")].map((c) => c.textContent);
    expect(ids).toContain("a");
    expect(ids).toContain("b");
  });

  it("names each rule's route in the approved words, and neither as a shortfall", () => {
    const view = record({ rules: [rule("a", "run-1"), rule("b", "run-1")] });
    view.rules[0].route = "deterministic";
    view.rules[1].route = "ai_ready";
    render(<PolicyOverviewPane record={view} />);

    const routes = screen.getAllByTestId("overview-rule-route").map((n) => n.textContent);
    expect(routes).toEqual(["Deterministic", "AI Ready"]);

    // A route is how the document states a test, never a grade on it. Copy
    // that framed either one as unfinished, weaker or a fallback has evaded
    // review six times, so it is scanned for here rather than trusted.
    const written = (screen.getByTestId("overview-roster").textContent ?? "").toLowerCase();
    for (const apology of [
      "not yet",
      "incomplete",
      "unfinished",
      "missing",
      "cannot",
      "could not",
      "fallback",
      "needs human",
      "manual",
      "pending",
      "unsupported",
    ]) {
      expect(written).not.toContain(apology);
    }
  });

  it("says nothing about a route the record did not record one for", () => {
    const view = record({ rules: [rule("a", "run-1")] });
    view.rules[0].route = null;
    render(<PolicyOverviewPane record={view} />);
    expect(screen.queryAllByTestId("overview-rule-route")).toHaveLength(0);
    // The rule is still listed. An unrecorded route removes a chip, not a rule.
    expect(screen.getAllByTestId("overview-rule")).toHaveLength(1);
  });
});

describe("the document's own words lead the Overview", () => {
  it("quotes each passage, above everything the record says about itself", () => {
    const view = record();
    view.source = [
      { key: "p1", page: 4, quotations: ["Staff shall follow the policies of the University."] },
    ];
    const { container } = render(<PolicyOverviewPane record={view} />);

    const quoted = screen.getAllByTestId("overview-quotation");
    expect(quoted).toHaveLength(1);
    expect(quoted[0].textContent).toContain("Staff shall follow the policies of the University.");
    // Marked as the document's, so every scan of this app's own copy skips it.
    expect(quoted[0].getAttribute("data-verbatim")).toBe("true");

    // It is the lead. A reader who came to read the policy reads it first.
    const sections = [...container.querySelectorAll(".policy-pane__section")];
    expect(sections[0].getAttribute("data-testid")).toBe("overview-source");
  });

  it("keeps two quotations of one passage apart rather than joining them", () => {
    const view = record();
    view.source = [{ key: "p1", page: 4, quotations: ["First sentence.", "Second sentence."] }];
    render(<PolicyOverviewPane record={view} />);
    expect(screen.getAllByTestId("overview-quotation")).toHaveLength(2);
  });

  it("says a passage stored no source text rather than rendering it blank", () => {
    const view = record();
    view.source = [{ key: "p1", page: 4, quotations: [] }];
    render(<PolicyOverviewPane record={view} />);
    expect(screen.getByText(/source text for this passage was not stored/)).toBeTruthy();
  });

  it("names the page per passage only where the policy runs across more than one", () => {
    const single = record({ passages: [passage(4)] });
    single.source = [{ key: "p4", page: 4, quotations: ["One page."] }];
    const { unmount } = render(<PolicyOverviewPane record={single} />);
    // The header already said page 4. Saying it again is the repetition this
    // tab was rewritten to stop.
    expect(screen.queryByText("Page 4")).toBeNull();
    unmount();

    const spread = record({ passages: [passage(7), passage(9)] });
    spread.source = [
      { key: "p7", page: 7, quotations: ["Starts here."] },
      { key: "p9", page: 9, quotations: ["Ends here."] },
    ];
    render(<PolicyOverviewPane record={spread} />);
    expect(screen.getByText("Page 7")).toBeTruthy();
    expect(screen.getByText("Page 9")).toBeTruthy();
  });

  it("claims nothing about passages a surface did not supply", () => {
    render(<PolicyOverviewPane record={record()} />);
    expect(screen.queryByTestId("overview-source")).toBeNull();
  });

  /**
   * The lead has to open the policy, not bury it.
   *
   * A policy of eleven passages printed whole put the rule roster and the trace
   * facts below the fold, which is the wall this tab was rewritten to stop —
   * reintroduced by the fix for it. So the passage the policy opens with is
   * printed and the rest is offered, counted exactly.
   *
   * The count is asserted as a number because "a few more" and "others" are the
   * wordings that make a reader guess, and a reviewer deciding whether to open
   * it is deciding against a quantity.
   */
  it("prints the passage the policy opens with, and offers the rest by their count", () => {
    const view = record({ passages: [passage(7), passage(9)] });
    view.source = [
      { key: "p1", page: 7, quotations: ["The passage it opens with."] },
      { key: "p2", page: 8, quotations: ["A later passage."] },
      { key: "p3", page: 9, quotations: ["A later passage still."] },
    ];
    render(<PolicyOverviewPane record={view} />);

    const rest = screen.getByTestId("overview-source-rest");
    // The opening passage is not behind the control.
    expect(rest.textContent).not.toContain("The passage it opens with.");
    expect(screen.getByText("The passage it opens with.")).toBeTruthy();
    // The remainder is, and is counted rather than described.
    expect(rest.querySelector("summary")?.textContent).toContain("other 2 passages");
  });

  /**
   * Deferring is not shortening.
   *
   * The rule that must not be bought back for tidiness: a quotation behind the
   * disclosure is the whole quotation. This asserts the last words of the last
   * passage survive, which an ellipsis or a slice would take first.
   */
  it("defers whole passages and shortens none of them", () => {
    const long =
      "Where a member of staff is absent for a period exceeding three consecutive " +
      "working days, a medical certificate issued by a registered practitioner " +
      "shall be submitted to the Human Resources Department without delay.";
    const view = record({ passages: [passage(7), passage(9)] });
    view.source = [
      { key: "p1", page: 7, quotations: ["Opens here."] },
      { key: "p2", page: 9, quotations: [long] },
    ];
    render(<PolicyOverviewPane record={view} />);

    const quoted = screen.getAllByTestId("overview-quotation").map((n) => n.textContent);
    expect(quoted).toContain(long);
    for (const text of quoted) expect(text).not.toMatch(/[…]|\.\.\./);
  });

  it("offers no control at all when the policy is stated in one passage", () => {
    const view = record();
    view.source = [{ key: "p1", page: 4, quotations: ["The only passage."] }];
    render(<PolicyOverviewPane record={view} />);
    // A disclosure holding nothing is a control a reader opens for no reason.
    expect(screen.queryByTestId("overview-source-rest")).toBeNull();
    expect(screen.getByText("The only passage.")).toBeTruthy();
  });

  it("names one deferred passage as one, not as a plural", () => {
    const view = record({ passages: [passage(7), passage(9)] });
    view.source = [
      { key: "p1", page: 7, quotations: ["Opens here."] },
      { key: "p2", page: 9, quotations: ["Ends here."] },
    ];
    render(<PolicyOverviewPane record={view} />);
    const summary = screen.getByTestId("overview-source-rest").querySelector("summary");
    expect(summary?.textContent).toBe("The other passage this policy is stated in");
  });

  /**
   * The corpus is substantially Arabic, and the quotation is the one place this
   * tab prints the document's characters rather than this app's. Direction is a
   * property of the run, so the run carries it and no box around it does.
   */
  it("marks an Arabic quotation right-to-left on the quoted run itself", () => {
    const arabic = "يجب على الموظف تقديم طلب خطي قبل الإجازة";
    const view = record();
    view.source = [{ key: "p1", page: 4, quotations: [arabic] }];
    const { container } = render(<PolicyOverviewPane record={view} />);

    const quoted = screen.getAllByTestId("overview-quotation")[0];
    const runs = [...quoted.querySelectorAll("bdi")].filter((run) =>
      /[\u0600-\u06FF]/.test(run.textContent ?? ""),
    );
    expect(runs.length).toBeGreaterThan(0);
    for (const run of runs) expect(run.getAttribute("dir")).toBe("rtl");

    // Reversible: a reviewer who copies the quotation gets the document's
    // characters back, in the order they are stored.
    expect(quoted.textContent).toBe(arabic);

    // And the section around it stays as it was, so this app's English labels
    // are not reordered by whichever passage was read first.
    expect(container.querySelector("[data-testid='overview-source']")?.getAttribute("dir") ?? null)
      .toBeNull();
  });

  /**
   * A right-to-left block has to start on the right.
   *
   * Isolating a run fixes its reading order but not where the line begins. An
   * Arabic quotation left in a left-starting block wraps to the wrong side and
   * reads as ragged, which a reviewer sees as damage in the document rather
   * than in this screen. `align` is what puts a block on the side its own base
   * direction starts from, and it belongs on anything owning its full width --
   * which the quotation and each roster title do.
   */
  it("starts a right-to-left quotation and rule title on the side they read from", () => {
    const arabic = "يجب على الموظف تقديم طلب إجازة خطي قبل موعد الإجازة";
    const view = record({ rules: [rule("a", "run-1")] });
    view.rules[0].rule.title = arabic;
    view.source = [{ key: "p1", page: 4, quotations: [arabic] }];
    const { container } = render(<PolicyOverviewPane record={view} />);

    for (const selector of ["[data-testid='overview-quotation']", ".policy-pane__rule-title"]) {
      const host = container.querySelector(selector);
      const block = host?.querySelector(".directional-text--block") ?? host;
      expect(block?.className ?? "").toContain("directional-text--block");
    }
  });
});

describe("the Overview is not a debugging panel", () => {
  it("has deleted the sentence about where the policy sits in the outline", () => {
    const flat = record();
    (flat.policy as unknown as { heading_path: string[] }).heading_path = [];
    const { container } = render(<PolicyOverviewPane record={flat} />);
    const written = container.textContent ?? "";
    // Removed twice at a reviewer's request and restored once. It describes the
    // document's layout, and no reader of this screen has ever needed it.
    expect(written).not.toContain("at its top level");
    expect(written).not.toContain("under no heading above it");
    expect(written).not.toMatch(/begins and ends/);
  });

  it("does not restate the single page the header already carries", () => {
    const { container } = render(<PolicyOverviewPane record={record({ passages: [passage(4)] })} />);
    expect(container.textContent).not.toContain("All of it is on page 4");
  });

  it("promotes one handle and keeps the rest as reference material", () => {
    const view = record({ policy: { provision_id: "prov-9" } });
    const { container } = render(<PolicyOverviewPane record={view} runs={[facetRun("run-1")]} />);

    // The key is what follows a policy across versions of a document, so it is
    // the one a business reader is given without asking.
    expect(container.querySelector(".policy-pane__handle")?.textContent).toContain(
      "SECTION-KEY-42",
    );

    // The rest are kept -- "cannot trace the policy" was the original
    // complaint -- and are out of the reader's way rather than deleted.
    const references = screen.getByTestId("overview-references");
    expect(references.tagName).toBe("DETAILS");
    expect(references.textContent).toContain("prov-9");
    expect(references.textContent).toContain("dv-1");
    expect(references.textContent).toContain("abc123");
  });

  it("says who put a rule here in words rather than in field values", () => {
    const authored = rule("a", "run-1");
    (authored as unknown as { authority: unknown }).authority = {
      owner: "policy-formulator",
      level: "ai_drafted",
    };
    const { container } = render(<PolicyOverviewPane record={record({ rules: [authored] })} />);
    const written = container.textContent ?? "";

    expect(written).toContain("Drafted by this app");
    expect(written).not.toContain("not yet reviewed by a person");
    // The raw values belong on the JSON tab, which is what that tab is for.
    expect(written).not.toContain("ai_drafted");
    expect(written).not.toContain("policy-formulator");
  });

  it("counts rules in a sentence rather than in a bare field value", () => {
    const { container } = render(
      <PolicyOverviewPane record={record()} runs={[facetRun("run-1")]} />,
    );
    const written = container.textContent ?? "";
    // "every rule", standing alone with no verb, read as a field value to a
    // reviewer rather than as an answer.
    expect(written).not.toMatch(/·\s*every rule/);
  });
});
