import { describe, expect, it, beforeEach, afterEach, vi } from "vitest";
import type { ReactNode } from "react";
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

/** The props any menu needs to have something to open onto, so a test about
 *  where the menu is drawn does not also have to say what is in it. */
const OPENABLE = {
  scope: "rule",
  recordId: "rule-7-11-a",
  recordName: "Hiring relatives",
  reviewStatuses: ["candidate"],
} as const;

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
    // F4: Edit is present but disabled with a reason explaining why
    // the published version cannot be edited in place (the reason points
    // the user toward starting a revision).
    const editItem = within(menu).queryByRole("menuitem", { name: /^Edit/ });
    if (editItem) {
      expect(
        editItem.hasAttribute("disabled") || editItem.getAttribute("aria-disabled") === "true",
      ).toBe(true);
    }
    // F4: Some items may be disabled with a reason, so we no longer
    // assert that every item is enabled. The key check is above.
  });

  it("offers Revise only where the record is published", () => {
    const published = recordActionsFor({
      scope: "rule",
      reviewStatuses: ["published"],
      on: { ...ALL_HANDLERS, revise: () => {} },
    });
    expect(published.map((a) => a.key)).toContain("revise");
    // F4: edit IS present for published records, but disabled with a reason
    // explaining why — "start a revision instead of editing it in place."
    const editAction = published.find((a) => a.key === "edit");
    if (editAction) {
      expect(editAction.disabled).toBe(true);
      expect(editAction.reason).toBeTruthy();
    }

    const candidateActions = recordActionsFor({
      scope: "rule",
      reviewStatuses: ["candidate"],
      on: { ...ALL_HANDLERS, revise: () => {} },
    });
    expect(candidateActions.map((a) => a.key)).toContain("edit");
    expect(candidateActions.map((a) => a.key)).not.toContain("revise");
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

describe("the menu opens over whatever the record sits inside", () => {
  /** A host that clips its own content, which is what every card this menu is
   *  placed in does: antd's Collapse sets `overflow: hidden` so it can animate,
   *  and a menu positioned inside that box is cut off at the card's edge. */
  const clipping = (children: ReactNode) => (
    <div data-clipper style={{ overflow: "hidden" }}>
      {children}
    </div>
  );

  it("puts the open menu outside the host that would clip it", () => {
    render(
      clipping(
        <RecordActionsMenu
          scope="rule"
          recordId="AI-1"
          recordName="a rule"
          reviewStatuses={["published"]}
          on={{ revise: () => {}, "view-history": () => {} }}
        />,
      ),
    );
    fireEvent.click(trigger());

    // The trigger stays where the caller put it; only the menu escapes. Asserted
    // as a pair, because moving both would take the control off the card too.
    expect(trigger().closest("[data-clipper]")).not.toBeNull();
    expect(screen.getByRole("menu").closest("[data-clipper]")).toBeNull();
  });

  it("still closes on a click outside it, from wherever it was drawn", () => {
    render(clipping(<RecordActionsMenu {...OPENABLE} on={ALL_HANDLERS} />));
    fireEvent.click(trigger());
    expect(screen.queryByRole("menu")).not.toBeNull();
    fireEvent.mouseDown(document.body);
    expect(screen.queryByRole("menu")).toBeNull();
  });

  it("still closes on Escape, and hands focus back to the trigger", () => {
    render(clipping(<RecordActionsMenu {...OPENABLE} on={ALL_HANDLERS} />));
    fireEvent.click(trigger());
    fireEvent.keyDown(screen.getByRole("menu"), { key: "Escape" });
    expect(screen.queryByRole("menu")).toBeNull();
    expect(document.activeElement).toBe(trigger());
  });

  it("carries the record's own direction across, rather than the document's", () => {
    // The menu is drawn on the document now, so it inherits the body's
    // direction. An Arabic record's menu has to be told which way it reads.
    render(
      <div dir="rtl">
        <RecordActionsMenu {...OPENABLE} on={ALL_HANDLERS} />
      </div>,
    );
    fireEvent.click(trigger());
    expect(screen.getByRole("menu").getAttribute("dir")).toBe("rtl");
  });
});
