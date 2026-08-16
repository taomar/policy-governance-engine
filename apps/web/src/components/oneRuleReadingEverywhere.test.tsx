/**
 * A RULE READS THE SAME WHEREVER IT IS OPENED FROM.
 *
 * WHAT WENT WRONG
 *
 * There were two components that drew a rule. One — `PolicyInspector` — gives
 * the reading this system is built around: the title and its route, `WHEN …
 * THEN …`, the way back to the source, a strip of eight questions, an identity
 * table where every row says in words what the identifier is, and the source's
 * own words under a heading that says they are the source's own words. The
 * other was a flat stack with none of that, and it was what the published page
 * expanded when a reader clicked `Details` on a rule.
 *
 * So a reader who learned the tabs on one screen found them missing on another,
 * and reported it as a regression. It was not a regression; it was a second
 * renderer. The second renderer is gone.
 *
 * WHAT IS ASSERTED
 *
 * That the reading a row expands to is the same reading the destination panel
 * gives — asserted through the parts a reader would name if they were taken
 * away, and through the identity rows that are the difference between an
 * identifier and a labelled identifier.
 *
 * AND WHAT MUST NOT BE ASSUMED
 *
 * The embedded placement has no surrounding surface to hold "which tab is
 * open", because several rows can be expanded at once and each is its own
 * reading. So it is rendered here exactly as the page renders it — with no tab
 * state passed at all — and the strip is required to work anyway. A version of
 * this component that only navigates when a parent drives it would pass every
 * assertion about the strip's *presence* and still leave the reader unable to
 * reach seven of the eight questions.
 *
 * Nothing here is a phrase from any document, and no number in it is a
 * measurement of one.
 */
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { CanonicalRule } from "../api";
import { PolicyInspector } from "./PolicyInspector";

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

afterEach(() => {
  cleanup();
});

/** The eight questions the strip offers, named as a reader sees them.
 *  Matched loosely, because two of them carry an icon whose own label joins the
 *  accessible name and neither is part of what a reader is looking for. */
const QUESTIONS: readonly (readonly [string, RegExp])[] = [
  ["Overview", /^Overview$/],
  ["Logic", /^Logic$/],
  ["Parties & routes", /Parties & routes/],
  ["Scope", /^Scope$/],
  ["Test scenario", /Test scenario/],
  ["History", /^History$/],
  ["Notes", /^Notes$/],
  ["JSON", /^JSON$/],
];

function rule(overrides: Partial<CanonicalRule> = {}): CanonicalRule {
  return {
    schema_version: "1.0",
    policy_set_id: "a-set",
    policy_version_id: "a-version",
    rule_id: "a-rule",
    rule_revision: 1,
    title: "A rule title",
    description: "A description of the rule",
    rule_type: "obligation",
    authority: { owner: "an-owner", source: "", reference: "" },
    scope: { personas: [], jurisdictions: [], organizational_units: [], processes: [] },
    condition: { type: "all", all: [] },
    evaluation_mode: "ai_ready",
    effect: { type: "require_action" },
    required_facts: [],
    exceptions: [],
    priority: 0,
    effective_from: "2024-01-01",
    effective_to: null,
    machine_executable: false,
    ambiguity_status: "clear",
    review_status: "published",
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
    ...overrides,
  } as unknown as CanonicalRule;
}

/** The reading as a row expands it: embedded, and owning nothing. */
function renderEmbedded(overrides: Partial<CanonicalRule> = {}) {
  return render(
    <PolicyInspector
      rule={rule(overrides)}
      variant="embedded"
      policySetKey="a-set"
      recordLabel="rule"
    />,
  );
}

/** The same reading as the destination column gives it. */
function renderPanel(overrides: Partial<CanonicalRule> = {}) {
  return render(<PolicyInspector rule={rule(overrides)} policySetKey="a-set" />);
}

describe("a rule opened in place is the reading, not a summary of it", () => {
  for (const [question, name] of QUESTIONS) {
    it(`can be asked: ${question}`, () => {
      renderEmbedded();
      expect(screen.getByRole("tab", { name })).toBeTruthy();
    });
  }

  it("moves between questions with nothing outside it holding the answer", () => {
    // The defect this guards is subtle: a strip that renders but never changes
    // reads as present and is unusable. Rendered with no tab state supplied,
    // because that is how a row expands it.
    renderEmbedded();
    expect(screen.getByRole("tab", { name: "Overview", selected: true })).toBeTruthy();
    fireEvent.click(screen.getByRole("tab", { name: "Scope" }));
    expect(screen.getByRole("tab", { name: "Scope", selected: true })).toBeTruthy();
    expect(screen.getByRole("tab", { name: "Overview", selected: false })).toBeTruthy();
  });

  it("says in words what each identifier of the record is", () => {
    // An id with no label is a string the reader cannot act on. These rows are
    // the reason this component was named as the one to keep.
    renderEmbedded();
    expect(screen.getByText("The policy set it belongs to")).toBeTruthy();
    expect(screen.getByText("The published version it was read at")).toBeTruthy();
  });

  it("names the source's own words as the source's own words", () => {
    renderEmbedded();
    expect(
      screen.getByText(/ORIGINAL SOURCE TEXT — THE EXACT WORDS FROM THE SOURCE DOCUMENT/i),
    ).toBeTruthy();
  });

  it("states the rule's route without calling it a defect", () => {
    // `ai_ready` is how the document states this test — in words, for a person
    // to settle. It is a route, and a reading that reports it as missing,
    // unsupported, incomplete or not-yet-ready is reporting a fault that is not
    // there.
    const { container } = renderEmbedded({ evaluation_mode: "ai_ready" } as Partial<CanonicalRule>);
    const text = container.textContent ?? "";
    for (const fault of [
      /not (yet )?(ready|supported|implemented)/i,
      /unsupported/i,
      /missing logic/i,
      /incomplete/i,
      /no logic/i,
      /cannot be evaluated/i,
    ]) {
      expect(text).not.toMatch(fault);
    }
  });
});

describe("the two placements are one component", () => {
  it("offers the same questions in the same order", () => {
    renderPanel();
    const panelTabs = screen.getAllByRole("tab").map((tab) => tab.textContent);
    cleanup();
    renderEmbedded();
    const embeddedTabs = screen.getAllByRole("tab").map((tab) => tab.textContent);
    expect(embeddedTabs).toEqual(panelTabs);
  });

  it("labels the record's identity the same way in both", () => {
    renderPanel();
    expect(screen.getByText("The policy set it belongs to")).toBeTruthy();
    cleanup();
    renderEmbedded();
    expect(screen.getByText("The policy set it belongs to")).toBeTruthy();
  });

  it("marks the placement without letting it decide anything", () => {
    // The variant may size a box. It may not gate a control: what a rule offers
    // is read from the rule, and a placement that could withhold a reading
    // would be the fork growing back inside the one file.
    const { container } = renderEmbedded();
    expect(container.querySelector(".policy-inspector--embedded")).toBeTruthy();
    cleanup();
    const panel = renderPanel();
    expect(panel.container.querySelector(".policy-inspector--embedded")).toBeNull();
    expect(panel.container.querySelector(".policy-inspector")).toBeTruthy();
  });
});

/**
 * There is one renderer, and the page uses it.
 *
 * Read from the source rather than by mounting the page, because mounting it
 * needs a policy set, a version, its rules and their clauses — and the thing
 * being asserted is a choice made at one line, which a source read states
 * exactly. If this ever needs relaxing, the reason will be that a second
 * renderer has arrived, which is the thing it exists to stop.
 */
describe("the published page expands a rule into that same reading", () => {
  const sources = import.meta.glob("./PoliciesTab.tsx", {
    query: "?raw",
    import: "default",
    eager: true,
  }) as Record<string, string>;

  const source = () => Object.values(sources)[0] ?? "";

  it("read the page's source", () => {
    expect(Object.keys(sources)).toHaveLength(1);
    expect(source().length).toBeGreaterThan(1000);
  });

  it("draws the inspector under a rule's Details, embedded", () => {
    const detail = source().slice(source().indexOf("ruleDetail={"));
    expect(detail).toContain("<PolicyInspector");
    expect(detail.slice(0, detail.indexOf("/>"))).toContain('variant="embedded"');
  });

  it("no longer draws the component the second renderer expanded", () => {
    // `RuleCard` still has honest callers — comparing versions, the rewrite and
    // edit modals, and the list of rules this page could place under no policy.
    // What it must not be again is the answer to "open this rule of this
    // policy", which is the one place the two readings diverged.
    const detail = source().slice(source().indexOf("ruleDetail={"));
    expect(detail.slice(0, detail.indexOf("ruleActions={"))).not.toContain("<RuleCard");
  });

  it("holds no import of either forked file", () => {
    expect(source()).not.toMatch(/from\s+"\.\/PublishedPolicyCard"/);
    expect(source()).not.toMatch(/from\s+"\.\.\/publishedPolicyCards"/);
  });
});
