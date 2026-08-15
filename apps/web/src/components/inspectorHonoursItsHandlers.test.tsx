/**
 * A handler supplied is a handler honoured.
 *
 * WHAT IS AT STAKE
 *
 * The inspector had one boolean, `readOnly`, standing in front of four
 * different questions: may a scenario be run against this rule, may a note be
 * written on it, may it be revised, and may the caller's own actions be drawn.
 * Two of those four were already answered by whether the caller passed a
 * handler at all, so the flag was a second opinion on a question the call site
 * had already settled — and a second opinion is where drift starts. Read across
 * every call site, neither of the two callers that raised the flag ever passed
 * either handler, so both gates were unreachable and no reader could tell which
 * of the four the flag was for.
 *
 * The two that remain are not editability. Whether a record may be changed is a
 * property of the record. Whether this inspector is the place the reader came
 * to act, or a citation pulled in beside a finding somewhere else, is a property
 * of the surrounding surface, and the same published rule is both on different
 * pages. That is the only thing the surviving flag is allowed to say, and its
 * name now says it.
 *
 * WHAT IS ASSERTED
 *
 * That the two questions with a handler-shaped answer are decided by the
 * handler, on both surfaces — including the reference view, where the old flag
 * would have swallowed them. Re-adding either gate fails this.
 *
 * And that the surface-level suppression still holds for the two that are
 * genuinely about acting on a rule you arrived at sideways, so this file cannot
 * be read as an argument for deleting the distinction outright.
 *
 * Nothing here is a phrase from any document, and no number in it is a
 * measurement of one.
 */
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
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

function aRule(): CanonicalRule {
  return {
    rule_id: "a-rule",
    title: "A title",
    description: "A description.",
    rule_type: "obligation",
    evaluation_mode: "ai_ready",
    condition: { type: "all", all: [] },
    effect: { type: "requirement", description: "An effect." },
    scope: {
      jurisdictions: [],
      organizational_units: [],
      processes: [],
      personas: [],
      channels: [],
      systems: [],
    },
    authority: { owner: "An owner", level: "A level", reference: "" },
    required_facts: [],
    decision_readiness: null,
    source_refs: [],
    ambiguity_status: "clear",
    review_status: "published",
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
    evidence: [],
    rule_revision: 1,
  } as unknown as CanonicalRule;
}

/** Named so an assertion says which control it went looking for, and so a
 *  control renamed in the component fails here rather than quietly passing on a
 *  substring of something else. */
const AN_ACTION_THE_CALLER_SUPPLIES = "An action this caller supplies";

function renderInspector(props: { shownAsReference?: boolean; withHandlers: boolean }) {
  render(
    <PolicyInspector
      rule={aRule()}
      policySetKey="a-set"
      activeTabKey="overview"
      onTabChange={() => {}}
      shownAsReference={props.shownAsReference}
      onRevise={props.withHandlers ? () => {} : undefined}
      additionalActions={props.withHandlers ? <button type="button">{AN_ACTION_THE_CALLER_SUPPLIES}</button> : undefined}
    />,
  );
}

describe("what the inspector draws, and what decides it", () => {
  it("offers Revise wherever the caller passed a way to revise", () => {
    renderInspector({ withHandlers: true, shownAsReference: true });
    expect(screen.queryByRole("button", { name: /Revise/ })).not.toBeNull();
  });

  it("offers no Revise where the caller passed no way to revise", () => {
    renderInspector({ withHandlers: false });
    expect(screen.queryByRole("button", { name: /Revise/ })).toBeNull();
  });

  it("draws the caller's own actions wherever the caller supplied them", () => {
    renderInspector({ withHandlers: true, shownAsReference: true });
    expect(screen.queryByText(AN_ACTION_THE_CALLER_SUPPLIES)).not.toBeNull();
  });

  it("withholds acting on a rule that was arrived at as a reference", () => {
    renderInspector({ withHandlers: true, shownAsReference: true });
    const tabs = screen.getAllByRole("tab").map((t) => (t.textContent ?? "").trim());
    expect(tabs.some((t) => t.includes("Notes"))).toBe(false);
    expect(tabs.some((t) => t.includes("Test scenario"))).toBe(false);
  });

  it("offers both where the rule is the subject of the surface", () => {
    renderInspector({ withHandlers: true });
    const tabs = screen.getAllByRole("tab").map((t) => (t.textContent ?? "").trim());
    expect(tabs.some((t) => t.includes("Notes"))).toBe(true);
    expect(tabs.some((t) => t.includes("Test scenario"))).toBe(true);
  });
});
