/**
 * A note on a policy stays attached to that policy.
 *
 * WHAT THIS IS ABOUT
 *
 * Notes are polymorphic: a row carries an `entity_type` and an `entity_id`, and
 * `entity_id` is text because for some kinds it is a row id and for others it is
 * a business key. Which one a new kind picks is not a detail — it decides
 * whether the note is still there next month.
 *
 * A policy is recorded in `document_provisions`, and that table is written per
 * document version. Re-extract the document and every row is replaced with a new
 * one carrying a new id. A note keyed to the row id would therefore stop
 * appearing after the next extraction run, with nothing having deleted it and
 * nothing on screen saying so — a reviewer would simply never learn that a
 * remark had been made. `provision_key` is the policy's identity across
 * versions; it is what History groups by and what the published page relies on
 * to group rules into policies at all.
 *
 * WHY THE ASSERTION IS ON WHAT REACHES THE NETWORK
 *
 * A test that the pane renders would pass whichever id it sent. The only thing
 * that distinguishes the correct implementation from the one that quietly loses
 * every note is the value handed to the notes API, so that is what is asserted.
 * The two ids are given deliberately unlike values, so a swap cannot pass.
 *
 * Nothing here is a phrase from any document, and no number in it is a
 * measurement of one.
 */
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { ActorProvider } from "../ActorContext";
import type { AssembledPolicy, CanonicalRule } from "../api";
import { PolicyNotesPane, type PolicyRecordView } from "./policyTabPanes";

const listNotes = vi.fn();

vi.mock("../api", async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return {
    ...actual,
    api: {
      listNotes: (...args: unknown[]) => listNotes(...args),
      createNote: vi.fn(),
      deleteNote: vi.fn(),
    },
  };
});

/** Two ids that could not be mistaken for one another, so a swap fails loudly
 *  rather than passing because both happened to be strings. */
const THE_POLICYS_KEY_ACROSS_VERSIONS = "the-key-this-policy-keeps";
const THE_ROW_THIS_VERSION_HAPPENS_TO_USE = "a-row-id-replaced-each-run";

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
  window.ResizeObserver =
    window.ResizeObserver ??
    (class {
      observe() {}
      unobserve() {}
      disconnect() {}
    } as unknown as typeof ResizeObserver);
});

beforeEach(() => {
  cleanup();
  listNotes.mockReset();
  listNotes.mockResolvedValue([]);
});

function recordFor(overrides: Partial<AssembledPolicy> = {}): PolicyRecordView {
  const policy = {
    key: THE_POLICYS_KEY_ACROSS_VERSIONS,
    heading: "A heading",
    heading_path: ["A heading"],
    topic_label: null,
    persisted: true,
    provision_id: THE_ROW_THIS_VERSION_HAPPENS_TO_USE,
    document_version_id: null,
    source_elements: "",
    page: 1,
    rule_count: 1,
    passage_count: 1,
    route: "",
    passages: [],
    rules: [],
    ...overrides,
  } as unknown as AssembledPolicy;
  return {
    policy,
    passageCount: 1,
    rules: [{ rule_id: "r1", rule: { rule_id: "r1" } as unknown as CanonicalRule }],
  };
}

/** Rendered inside the actor context the app supplies, because a note records
 *  who wrote it and the composer will not post without a name. */
function renderPane(record: PolicyRecordView) {
  return render(
    <ActorProvider>
      <PolicyNotesPane record={record} />
    </ActorProvider>,
  );
}

describe("a policy's notes", () => {  it("are asked for by the key the policy keeps across versions", async () => {
    renderPane(recordFor());
    await waitFor(() => expect(listNotes).toHaveBeenCalled());
    expect(listNotes).toHaveBeenCalledWith("provision", THE_POLICYS_KEY_ACROSS_VERSIONS);
  });

  it("are never asked for by the row this version happens to use", async () => {
    renderPane(recordFor());
    await waitFor(() => expect(listNotes).toHaveBeenCalled());
    for (const call of listNotes.mock.calls) {
      expect(call).not.toContain(THE_ROW_THIS_VERSION_HAPPENS_TO_USE);
    }
  });

  it("says so, rather than offering a composer, when there is nothing to attach to", async () => {
    // A grouping assembled for display has no recorded identity, so a note
    // written against it would be addressed to nothing. Losing what somebody
    // typed is worse than telling them up front that this is not the place.
    renderPane(recordFor({ persisted: false }));
    expect(await screen.findByTestId("policy-notes-pane")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Add/ })).toBeNull();
    expect(listNotes).not.toHaveBeenCalled();
  });

  it("offers the composer when the policy is one the system has recorded", async () => {
    // The mutation that keeps the previous assertion honest: the same pane, a
    // record that does have an identity, and the composer is there.
    renderPane(recordFor());
    await waitFor(() => expect(listNotes).toHaveBeenCalled());
    expect(screen.getByRole("button", { name: /Add/ })).toBeTruthy();
  });
});
