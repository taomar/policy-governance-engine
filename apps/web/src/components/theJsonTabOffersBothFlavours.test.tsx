/**
 * The JSON tab offers both flavours, and fetches the lean one rather than
 * rebuilding it.
 *
 * WHAT IS AT STAKE
 *
 * There are two JSONs for a policy now: the full record the tab has always
 * shown, and a lean projection a model reads. The lean one is defined once, on
 * the server, so that the tab and the case tester cannot drift into showing a
 * reader one thing and handing a model another. The trap this guards is the tab
 * quietly growing its own second copy of that projection: the moment it does,
 * the two definitions can disagree and nothing says so.
 *
 * WHAT IS ASSERTED
 *
 *  - The tab opens on the full record, and the full record is what renders.
 *  - Choosing "lean" asks the server for it — at the agreed path, for this
 *    provision — and shows exactly what the server returned, not a local build.
 *  - A grouping with no persisted provision cannot ask: it has no id to project,
 *    so the lean choice is offered disabled rather than failing when pressed.
 *
 * Nothing here is a phrase from any document, and no number in it measures one.
 */
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { AssembledPolicy, CanonicalRule } from "../api";
import { buildPolicyCards } from "../policyCards";
import { PolicyDetailPanel } from "./PolicyDetailPanel";

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
  vi.unstubAllGlobals();
});

function rule(id: string): CanonicalRule {
  return {
    rule_id: id,
    title: `A title for ${id}`,
    description: "A description.",
    rule_type: "obligation",
    evaluation_mode: "ai_ready",
    condition: { type: "all", all: [] },
    effect: { type: "requirement", description: "An effect." },
    required_facts: [],
    decision_readiness: null,
    source_refs: [],
    ambiguity_status: "clear",
    review_status: "published",
    evidence: [],
  } as unknown as CanonicalRule;
}

function policy(key: string, ruleIds: string[], provisionId: string | null): AssembledPolicy {
  return {
    key,
    heading: `A heading for ${key}`,
    heading_path: ["An outer heading", `A heading for ${key}`],
    topic_label: null,
    persisted: provisionId != null,
    provision_id: provisionId,
    document_version_id: null,
    source_elements: "",
    page: 1,
    rule_count: ruleIds.length,
    passage_count: 1,
    route: "ai_ready",
    passages: [
      {
        key: `${key}-passage`,
        source_elements: "",
        page: 1,
        rule_count: ruleIds.length,
        rules: ruleIds.map((id) => ({ rule_id: id, evaluation_mode: "ai_ready" })),
      },
    ],
    rules: ruleIds.map((id) => ({ rule_id: id, evaluation_mode: "ai_ready" })),
  } as unknown as AssembledPolicy;
}

function cardFor(provisionId: string | null, ruleIds: string[] = ["r1", "r2"]) {
  const [card] = buildPolicyCards(
    [policy("a-policy", ruleIds, provisionId)],
    ruleIds.map((id) => ({ rule: rule(id) })),
  );
  return card;
}

function renderPanel(provisionId: string | null, ruleIds?: string[]) {
  return render(
    <PolicyDetailPanel
      card={cardFor(provisionId, ruleIds)}
      statusColor={() => "purple"}
      statusLabel={(status) => status}
      policySetKey="a-set"
    />,
  );
}

/** The text content of the one rendered JSON block. */
function jsonText(): string {
  const block = document.querySelector(".json-view-code");
  return block?.textContent ?? "";
}

describe("the JSON tab offers a full and a lean flavour", () => {
  it("opens on the full record, and renders the full record", () => {
    renderPanel("a-policy-provision");
    fireEvent.click(screen.getByRole("tab", { name: "JSON" }));

    // "passages" is a full-record shape; the lean projection has no such key.
    // Its presence is how we know the full flavour is the one on screen.
    expect(jsonText()).toContain("passages");
    const full = screen.getByRole("radio", { name: "Full record" }) as HTMLInputElement;
    expect(full.checked).toBe(true);
  });

  it("asks the server for the lean flavour, and shows exactly what it returned", async () => {
    const returned = {
      projection: "grounding_projection_v1",
      representation: "canonical",
      envelope: { policy_set_id: "a-policy", provision_id: "a-policy-provision" },
      spans: { sp_abc123: { text: "The document's own words.", clause_id: "E1" } },
      facts: {},
      rules: [{ rule_id: "r1", evidence_refs: ["sp_abc123"] }],
    };
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => returned,
    });
    vi.stubGlobal("fetch", fetchMock);

    renderPanel("a-policy-provision");
    fireEvent.click(screen.getByRole("tab", { name: "JSON" }));
    fireEvent.click(screen.getByRole("radio", { name: "Lean (for a model)" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const url = String(fetchMock.mock.calls[0][0]);
    // The agreed path, for this provision — not the blocked `/policies` prefix.
    expect(url).toContain("/api/policy-payload/a-policy-provision");

    await waitFor(() =>
      expect(jsonText()).toContain('"projection": "grounding_projection_v1"'),
    );
    // What the server returned, verbatim — including the document's own words,
    // which the tab must not have rebuilt for itself.
    expect(jsonText()).toContain("The document's own words.");
    // And not the full-record shape: this is the lean flavour, not the full one
    // relabelled.
    expect(jsonText()).not.toContain("passages");
  });

  it("offers lean disabled, and never asks, when there is no provision to project", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    renderPanel(null);
    fireEvent.click(screen.getByRole("tab", { name: "JSON" }));

    const lean = screen.getByRole("radio", { name: "Lean (for a model)" }) as HTMLInputElement;
    expect(lean.disabled).toBe(true);
    expect(fetchMock).not.toHaveBeenCalled();
    // The full record is still there to read.
    expect(jsonText()).toContain("passages");
  });
});
