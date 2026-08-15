import { describe, expect, it, beforeEach, afterEach, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import {
  RecordActionsMenu,
  recordActionsFor,
  recordStateFrom,
  type RecordActionHandlers,
} from "./components/RecordActionsMenu";
import { candidateEditability } from "./candidateEditability";

/**
 * A SEALED RECORD OFFERS READING, AND ONE ROUTE OUT.
 *
 * The Policies page reads published versions. It once carried its own overflow
 * menu — a second implementation of the same question — and the two drifted:
 * one page offered controls the other refused. These tests exist so the single
 * menu cannot regrow that difference.
 *
 * The guarantee they encode is structural, not conventional. What a record
 * admits is derived from its own review status through `candidateEditability`,
 * so a surface CANNOT wire a decision onto a sealed record by passing the wrong
 * flag — there is no flag. That is why the tests below hand the menu *every*
 * handler the application has and still expect nothing that changes the record:
 * if editability were an argument, this file would fail.
 *
 * `Revise` is the deliberate exception and is not an editing affordance. A
 * published version is an immutable snapshot; the server's own
 * `editBlockedReason` names starting a revision as the route. A revision writes
 * a new record and leaves the published one standing, where an edit would
 * rewrite what a version already promised.
 */

function stubEnvironment() {
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
}

beforeEach(stubEnvironment);
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

/** Every handler this application knows how to supply. Handed in wholesale so
 *  the assertions rest on what the record admits rather than on a caller having
 *  been careful. */
const EVERY_HANDLER: RecordActionHandlers = {
  edit: () => {},
  "suggest-rewrite": () => {},
  "request-changes": () => {},
  "override-approve": () => {},
  "override-reject": () => {},
  revise: () => {},
  "compare-versions": () => {},
  export: () => {},
  explain: () => {},
  "ask-ai": () => {},
  "view-history": () => {},
  "view-source": () => {},
  "open-record": () => {},
};

function keysOffered(statuses: readonly string[], on: RecordActionHandlers = EVERY_HANDLER) {
  return recordActionsFor({ scope: "rule", reviewStatuses: statuses, on }).map((a) => a.key);
}

function openMenu(statuses: readonly string[], on: RecordActionHandlers = EVERY_HANDLER) {
  render(
    <RecordActionsMenu
      scope="rule"
      recordId="R-1"
      recordName="R-1"
      reviewStatuses={statuses}
      on={on}
    />,
  );
  fireEvent.click(screen.getByTestId("record-actions-menu"));
  return screen.getByRole("menu");
}

describe("the record's own status decides what may be done to it", () => {
  it("agrees with the table the server enforces", () => {
    // If this drifts, every assertion below is measuring the wrong thing.
    expect(candidateEditability("published").canEdit).toBe(false);
    expect(recordStateFrom(["published"]).editability.canEdit).toBe(false);
    expect(recordStateFrom(["published"]).isPublished).toBe(true);
  });

  it("draws nothing that would decide or rewrite a sealed record, however it is wired", () => {
    const offered = keysOffered(["published"]);
    for (const forbidden of [
      "edit",
      "suggest-rewrite",
      "request-changes",
      "override-approve",
      "override-reject",
    ]) {
      expect(offered).not.toContain(forbidden);
    }
  });

  it("keeps the one route a sealed version leaves open", () => {
    expect(keysOffered(["published"])).toContain("revise");
  });

  it("never offers both ways of changing a record, in any state", () => {
    for (const status of [
      "candidate",
      "approved",
      "rejected",
      "changes_requested",
      "published",
      "a-status-this-build-has-never-heard-of",
    ]) {
      const offered = keysOffered([status]);
      expect(offered.includes("edit") && offered.includes("revise")).toBe(false);
    }
  });
});

describe("the sealed record's menu, as a reader meets it", () => {
  it("is exactly the read-only arm when the surface offers only that arm", () => {
    // The shape the Policies page asks for: a revisable published rule.
    const menu = openMenu(["published"], {
      revise: () => {},
      "view-history": () => {},
    });
    const labels = within(menu)
      .getAllByRole("menuitem")
      .map((item) => item.getAttribute("data-action"));
    // `Copy ID` sits last by the table's own rule — it is the one act every
    // record admits whatever its state, so it belongs apart from the entries
    // the record's status decides.
    expect(labels).toEqual(["revise", "view-history", "copy-id"]);
  });

  it("says why editing is closed in the words the server chose, on the entry that is the route", () => {
    const reason = candidateEditability("published").editBlockedReason;
    expect(reason).toBeTruthy();

    const menu = openMenu(["published"], { revise: () => {} });
    const revise = within(menu).getAllByRole("menuitem")[0];
    expect(revise.getAttribute("data-action")).toBe("revise");
    expect(revise.textContent).toContain(reason as string);
  });

  it("still opens when this version cannot be revised, rather than vanishing", () => {
    // An older version is not revisable, so the surface passes no handler.
    // Copying an id needs nothing from the surface and must survive alone.
    const menu = openMenu(["published"], {});
    const actions = within(menu)
      .getAllByRole("menuitem")
      .map((item) => item.getAttribute("data-action"));
    expect(actions).toEqual(["copy-id"]);
  });
});

/**
 * The same rule, applied to the two surfaces that show a record in full.
 *
 * `PolicyInspector` and `RuleDetailInline` are reachable from the review queue
 * and from the page that reads published versions. Neither may take a caller's
 * word for whether the record it is showing can be changed — that is the
 * record's own answer, and a prop offering a second one is how the two pages
 * came to disagree in the first place.
 *
 * Read as source rather than rendered, because the claim is about the contract
 * these components publish, not about one arrangement of props. A component
 * that never receives the flag today can still be handed it tomorrow.
 */
const SOURCES = import.meta.glob("./components/{PolicyInspector,RuleDetailInline}.tsx", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

describe("no surface takes a second opinion on whether a record may be changed", () => {
  it("finds the files it is guarding", () => {
    // Without this the suite passes by reading nothing at all.
    expect(Object.keys(SOURCES)).toHaveLength(2);
  });

  for (const flag of ["canEdit", "canReview", "canApprove", "isEditable", "readOnly", "editable"]) {
    it(`declares no \`${flag}\` prop`, () => {
      for (const [path, source] of Object.entries(SOURCES)) {
        // A prop declaration: the name, optional `?`, then `:` — as it appears
        // in an interface or a destructured signature.
        const declared = new RegExp(`(^|[\\s{,])${flag}\\??\\s*:`, "m");
        expect(`${path}: ${declared.test(source)}`).toBe(`${path}: false`);
      }
    });
  }
});
