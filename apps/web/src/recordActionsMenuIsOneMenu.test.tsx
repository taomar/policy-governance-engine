import { describe, expect, it, beforeEach, afterEach, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import {
  RecordActionsMenu,
  recordActionsFor,
  recordStateFrom,
  type RecordActionHandlers,
} from "./components/RecordActionsMenu";

/**
 * ONE MENU, IN TWO SCOPES, ON RECORDS IN DIFFERENT STATES.
 *
 * These fail without `RecordActionsMenu`: there is no other overflow control on
 * a review-queue rule or policy, and the assertions below are about the shape of
 * the contract rather than about any one caller.
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

const writeText = vi.fn(() => Promise.resolve());

beforeEach(() => {
  stubEnvironment();
  Object.defineProperty(navigator, "clipboard", {
    configurable: true,
    value: { writeText },
  });
  writeText.mockClear();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

/** Every key a review surface can actually service today. */
const ALL_HANDLERS: RecordActionHandlers = {
  "open-record": vi.fn(),
  "view-history": vi.fn(),
  "ask-ai": vi.fn(),
  edit: vi.fn(),
  "suggest-rewrite": vi.fn(),
  "request-changes": vi.fn(),
  "override-approve": vi.fn(),
  "override-reject": vi.fn(),
};

function renderMenu(
  overrides: Partial<Parameters<typeof RecordActionsMenu>[0]> = {},
) {
  return render(
    <RecordActionsMenu
      scope="rule"
      recordId="rule-7-11-a"
      recordName="Hiring relatives"
      reviewStatuses={["candidate"]}
      on={ALL_HANDLERS}
      {...overrides}
    />,
  );
}

const trigger = () => screen.getByTestId("record-actions-menu");

describe("the menu is not in the document until it is opened", () => {
  it("draws a trigger and no menu", () => {
    renderMenu();
    expect(trigger().getAttribute("aria-haspopup")).toBe("menu");
    expect(trigger().getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByRole("menu")).toBeNull();
    expect(screen.queryAllByRole("menuitem")).toHaveLength(0);
  });

  it("builds its items only once opened, and drops them again on close", () => {
    renderMenu();
    fireEvent.click(trigger());
    expect(screen.getByRole("menu")).toBeTruthy();
    expect(screen.getAllByRole("menuitem").length).toBeGreaterThan(0);
    expect(trigger().getAttribute("aria-expanded")).toBe("true");
    expect(trigger().getAttribute("aria-controls")).toBe(
      screen.getByRole("menu").getAttribute("id"),
    );

    fireEvent.click(trigger());
    expect(screen.queryByRole("menu")).toBeNull();
    expect(screen.queryAllByRole("menuitem")).toHaveLength(0);
  });
});

describe("keyboard and focus", () => {
  it("closes on Escape and returns focus to the trigger", () => {
    renderMenu();
    fireEvent.click(trigger());
    const first = screen.getAllByRole("menuitem")[0];
    expect(document.activeElement).toBe(first);

    fireEvent.keyDown(screen.getByRole("menu"), { key: "Escape" });
    expect(screen.queryByRole("menu")).toBeNull();
    expect(document.activeElement).toBe(trigger());
  });

  it("moves between items with the arrow keys, one tab stop for the menu", () => {
    renderMenu();
    fireEvent.click(trigger());
    const items = screen.getAllByRole("menuitem");
    expect(items.filter((item) => item.tabIndex === 0)).toHaveLength(1);

    fireEvent.keyDown(screen.getByRole("menu"), { key: "ArrowDown" });
    expect(document.activeElement).toBe(screen.getAllByRole("menuitem")[1]);

    fireEvent.keyDown(screen.getByRole("menu"), { key: "End" });
    const afterEnd = screen.getAllByRole("menuitem");
    expect(document.activeElement).toBe(afterEnd[afterEnd.length - 1]);

    fireEvent.keyDown(screen.getByRole("menu"), { key: "Home" });
    expect(document.activeElement).toBe(screen.getAllByRole("menuitem")[0]);
  });

  it("opens from the keyboard on ArrowDown", () => {
    renderMenu();
    fireEvent.keyDown(trigger(), { key: "ArrowDown" });
    expect(screen.getByRole("menu")).toBeTruthy();
  });
});

describe("what a record admits is derived from the record, not passed in", () => {
  it("offers Edit on a candidate and never on a published record", () => {
    const { unmount } = renderMenu({ reviewStatuses: ["candidate"] });
    fireEvent.click(trigger());
    expect(screen.getByRole("menuitem", { name: /Edit/ })).toBeTruthy();
    unmount();

    renderMenu({ reviewStatuses: ["published"] });
    fireEvent.click(trigger());
    const menu = screen.getByRole("menu");
    // Absent, not disabled: a published record is immutable, so "Edit" greyed
    // out would describe a permission problem the reader does not have.
    expect(within(menu).queryByRole("menuitem", { name: /^Edit/ })).toBeNull();
    expect(
      within(menu)
        .getAllByRole("menuitem")
        .every((item) => !item.hasAttribute("disabled") && item.getAttribute("aria-disabled") !== "true"),
    ).toBe(true);
  });

  it("offers Revise only where the record is published", () => {
    const published = recordActionsFor({
      scope: "rule",
      reviewStatuses: ["published"],
      on: { ...ALL_HANDLERS, revise: () => {} },
    }).map((a) => a.key);
    expect(published).toContain("revise");
    expect(published).not.toContain("edit");

    const candidate = recordActionsFor({
      scope: "rule",
      reviewStatuses: ["candidate"],
      on: { ...ALL_HANDLERS, revise: () => {} },
    }).map((a) => a.key);
    expect(candidate).toContain("edit");
    expect(candidate).not.toContain("revise");
  });

  it("offers an override only where there is a decision to override", () => {
    const keysFor = (status: string) =>
      recordActionsFor({ scope: "rule", reviewStatuses: [status], on: ALL_HANDLERS }).map((a) => a.key);
    expect(keysFor("approved")).toContain("override-reject");
    expect(keysFor("approved")).toContain("request-changes");
    expect(keysFor("approved")).not.toContain("override-approve");
    expect(keysFor("rejected")).toContain("override-approve");
    expect(keysFor("candidate")).not.toContain("override-approve");
    expect(keysFor("candidate")).not.toContain("override-reject");
  });

  it("reads a policy as admitting whatever any of its rules admits", () => {
    const state = recordStateFrom(["approved", "candidate"]);
    expect(state.hasApproved).toBe(true);
    expect(state.editability.canEdit).toBe(true);
    expect(state.isPublished).toBe(false);
    expect(recordStateFrom(["published", "published"]).isPublished).toBe(true);
    expect(recordStateFrom(["published", "candidate"]).isPublished).toBe(false);
  });
});

describe("scope changes the entries, one component draws them", () => {
  it("keeps rule-only acts off a policy and policy-only acts off a rule", () => {
    const on: RecordActionHandlers = { ...ALL_HANDLERS, export: () => {}, "compare-versions": () => {} };
    const rule = recordActionsFor({ scope: "rule", reviewStatuses: ["candidate"], on }).map((a) => a.key);
    const policy = recordActionsFor({ scope: "policy", reviewStatuses: ["candidate"], on }).map((a) => a.key);

    // A policy has no wording of its own, so it has nothing to edit or rewrite.
    expect(rule).toContain("edit");
    expect(rule).toContain("suggest-rewrite");
    expect(policy).not.toContain("edit");
    expect(policy).not.toContain("suggest-rewrite");

    // Exporting one rule is not something this app does.
    expect(policy).toContain("export");
    expect(rule).not.toContain("export");
  });

  it("draws nothing for an action the surface cannot service", () => {
    const keys = recordActionsFor({
      scope: "rule",
      reviewStatuses: ["candidate"],
      on: { "open-record": () => {} },
    }).map((a) => a.key);
    expect(keys).toEqual(["open-record", "copy-id"]);
  });

  it("copies the id without needing the surface to supply anything", () => {
    render(
      <RecordActionsMenu
        scope="policy"
        recordId="7.11-hiring-relatives"
        recordName="Hiring relatives"
        reviewStatuses={["candidate"]}
      />,
    );
    fireEvent.click(trigger());
    fireEvent.click(screen.getByRole("menuitem", { name: /Copy ID/ }));
    expect(writeText).toHaveBeenCalledWith("7.11-hiring-relatives");
  });
});

describe("the primary decision and the evidence stay out of the menu", () => {
  it("never offers approve or reject as menu entries", () => {
    for (const scope of ["rule", "policy"] as const) {
      for (const status of ["candidate", "approved", "rejected", "published"]) {
        const labels = recordActionsFor({
          scope,
          reviewStatuses: [status],
          on: {
            ...ALL_HANDLERS,
            revise: () => {},
            export: () => {},
            "compare-versions": () => {},
            "view-source": () => {},
            explain: () => {},
          },
        }).map((a) => a.label.toLowerCase());
        // "Override & approve" names an override, which is a different act from
        // the decision itself; the plain decisions must never appear.
        expect(labels).not.toContain("approve");
        expect(labels).not.toContain("reject");
      }
    }
  });
});

describe("the copy says where a rule goes, never that it fell short", () => {
  const ROUTE_TERMS = [
    "deterministic",
    "machine executable",
    "executable",
    "executability",
    "automatable",
    "automated",
    "ai ready",
    "documentation only",
    "manual",
    "unstructured",
  ];
  const DEFICIENCY = /\b(cannot|can't|unable|fail(?:s|ed|ure)?|not supported|unsupported|missing|incomplete|insufficient|limitation|fallback|degraded|only)\b/i;

  it("names no route and frames nothing as a shortfall", () => {
    const on: RecordActionHandlers = {
      ...ALL_HANDLERS,
      revise: () => {},
      export: () => {},
      "compare-versions": () => {},
      "view-source": () => {},
      explain: () => {},
    };
    const copy = (["rule", "policy"] as const).flatMap((scope) =>
      ["candidate", "approved", "rejected", "published"].flatMap((status) =>
        recordActionsFor({ scope, reviewStatuses: [status], on }).flatMap((a) =>
          [a.label, a.hint].filter((value): value is string => Boolean(value)),
        ),
      ),
    );
    expect(copy.length).toBeGreaterThan(0);
    for (const text of copy) {
      const normalised = text.toLowerCase().replace(/[^a-z ]+/g, " ").replace(/\s+/g, " ").trim();
      for (const term of ROUTE_TERMS) {
        expect(normalised.split(" ").join(" ")).not.toContain(term);
      }
      expect(text).not.toMatch(DEFICIENCY);
    }
  });
});

describe("bidirectional records", () => {
  it("carries the record's own id as directional text rather than as a bare string", () => {
    render(
      <RecordActionsMenu
        scope="rule"
        recordId="قاعدة-٧-١١"
        recordName="توظيف الأقارب"
        reviewStatuses={["candidate"]}
        on={{ "open-record": () => {} }}
      />,
    );
    fireEvent.click(trigger());
    const item = screen.getByRole("menuitem", { name: /Copy ID/ });
    // The id is shown, and shown through the house directional splitter so an
    // Arabic id sits the right way round beside an English label.
    expect(item.querySelector("bdi")).not.toBeNull();
    expect(item.textContent).toContain("قاعدة-٧-١١");
  });
});
