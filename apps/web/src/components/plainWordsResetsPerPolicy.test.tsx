/**
 * A generated reading belongs to the policy it was asked about, and to no
 * other.
 *
 * WHY THIS FILE EXISTS
 *
 * Both surfaces that read a policy back in plain words — the Overview pane and
 * the Explain dialog — hold the reading in their own `useState`. Neither is
 * remounted when the reader moves to a different policy: the pane keeps its
 * place in the tree and the dialog's button keeps a constant position in a
 * panel that swaps its record underneath it. So React reused the instance, the
 * `provisionId` prop changed, and the previous policy's reading stayed on
 * screen under the new policy's heading.
 *
 * That is not a cosmetic slip. Constraint 8 says a generated word must be
 * unmistakably ours; it must also be unmistakably *about the record it sits
 * beside*. A fluent paragraph about policy A, rendered beneath policy B's
 * quoted words, attributes our account to the wrong record — exactly the
 * failure a compliance reviewer opened this tab to catch.
 *
 * Two things are pinned here, for each surface:
 *
 *  1. RESET ON IDENTITY CHANGE. When the policy changes, the reading is gone.
 *     The new policy offers its own, freshly.
 *
 *  2. NO LATE LANDING. A request that was in flight for the old policy, still
 *     unresolved when the reader moved on, must never resolve into the new
 *     policy's view.
 */
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { AssembledPassage, AssembledPolicy, CanonicalRule } from "../api";
import { aiApi, type PolicyExplanation } from "../api";
import { PolicyOverviewPane, type PolicyRecordView } from "./policyTabPanes";
import { PolicyExplainButton } from "./PolicyExplainButton";

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

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

/** A promise whose settling this test controls, to hold a request in flight. */
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

/**
 * Settle a held request and let the component's awaited continuation run to
 * completion inside `act`, so the assertion that follows reads a settled tree
 * rather than racing the state update it is meant to observe.
 */
async function land<T>(pending: { resolve: (value: T) => void }, value: T) {
  await act(async () => {
    pending.resolve(value);
    await Promise.resolve();
    await Promise.resolve();
  });
}

function rule(id: string): CanonicalRule {
  return {
    rule_id: id,
    title: `Rule ${id}`,
    effect: "allow",
    condition: { type: "all", all: [] },
    obligations: [],
    exceptions: [],
    scope: {},
    source: { document_id: "d", quotes: [] },
    lineage: { extraction_run_id: "run-1", schema_version: "1" },
  } as unknown as CanonicalRule;
}

function passage(page: number): AssembledPassage {
  return { key: `p${page}`, source_elements: `p${page}-E1`, page, rule_count: 1, rules: [] };
}

/** A record for one policy, identified by its own key and provision id. */
function record(provisionId: string, key: string): PolicyRecordView {
  return {
    policy: {
      key,
      heading: `Heading ${key}`,
      heading_path: ["Above", `Heading ${key}`],
      passages: [passage(1)],
      page: 1,
      persisted: true,
      provision_id: provisionId,
      document_version_id: "dv-1",
      source_elements: "p1-E1",
      rules: [],
      rule_count: 1,
      passage_count: 1,
      route: "computable",
    } as unknown as AssembledPolicy,
    passageCount: 1,
    rules: [{ rule_id: "a", rule: rule("a") }],
    progress: undefined,
  };
}

/** A plain-words answer whose text names the policy it was asked about. */
function explanationFor(provisionId: string): PolicyExplanation {
  return {
    provision_id: provisionId,
    heading_path: ["A heading"],
    rule_count: 1,
    rules: [
      {
        rule_id: "a",
        title: "First rule",
        states: { subject: "someone", modality: "must" },
        effect: "a thing follows",
        stated_text: "The document's own sentence.",
      },
    ],
    covers_every_rule: true,
    explanation: `Reading of ${provisionId}.`,
    unavailable_code: null,
    generated_at: "2024-05-01T10:00:00Z",
    model_deployment: "a-deployment",
    prompt_version: "policy-explain-v1",
    source_digest: `digest-${provisionId}`,
  } as PolicyExplanation;
}

const A = "prov-A";
const B = "prov-B";

describe("the Overview pane's plain-words reading", () => {
  it("does not carry policy A's reading onto policy B", async () => {
    vi.spyOn(aiApi, "explainPolicy").mockImplementation(
      async (provisionId: string) => explanationFor(provisionId),
    );

    const { rerender } = render(<PolicyOverviewPane record={record(A, "POLICY-A")} />);
    fireEvent.click(screen.getByTestId("overview-request-plain-words"));
    const reading = await screen.findByTestId("overview-plain-words-text");
    expect(reading.textContent).toContain("Reading of prov-A");

    // The reader moves to another policy. The pane keeps its place in the tree.
    rerender(<PolicyOverviewPane record={record(B, "POLICY-B")} />);

    // Policy A's reading must be gone, not sitting under policy B's heading.
    expect(screen.queryByText(/Reading of prov-A/)).toBeNull();
    // And policy B offers its own, freshly — the section is back to its prompt.
    expect(screen.getByTestId("overview-request-plain-words")).toBeTruthy();
  });

  it("drops a request still in flight for policy A when the reader moves to B", async () => {
    const pending = deferred<PolicyExplanation>();
    vi.spyOn(aiApi, "explainPolicy").mockImplementation(
      (provisionId: string) =>
        provisionId === A ? pending.promise : Promise.resolve(explanationFor(provisionId)),
    );

    const { rerender } = render(<PolicyOverviewPane record={record(A, "POLICY-A")} />);
    fireEvent.click(screen.getByTestId("overview-request-plain-words"));
    // The request for A is in flight — neither answered nor failed.
    await screen.findByText("Reading the record…");

    // The reader moves on before A comes back, then A's request lands, late.
    rerender(<PolicyOverviewPane record={record(B, "POLICY-B")} />);
    await land(pending, explanationFor(A));

    // It must not have populated policy B's view.
    expect(screen.queryByText(/Reading of prov-A/)).toBeNull();
    expect(screen.getByTestId("overview-request-plain-words")).toBeTruthy();
  });
});

describe("the Explain dialog's plain-words reading", () => {
  it("does not carry policy A's reading onto policy B", async () => {
    const asked = vi
      .spyOn(aiApi, "explainPolicy")
      .mockImplementation(async (provisionId: string) => explanationFor(provisionId));

    const { rerender } = render(<PolicyExplainButton provisionId={A} policyKey="POLICY-A" />);
    fireEvent.click(screen.getByTestId("policy-explain-button"));
    const reading = await screen.findByTestId("policy-explain-reading");
    expect(reading.textContent).toContain("Reading of prov-A");

    // The panel swaps the record under a button that keeps its position. On
    // that change the dialog closes and its held reading is cleared, so the
    // reader who reopens it asks about the policy now in hand.
    rerender(<PolicyExplainButton provisionId={B} policyKey="POLICY-B" />);

    // Opening the dialog again asks about policy B, and shows B — not A again.
    asked.mockClear();
    fireEvent.click(screen.getByTestId("policy-explain-button"));
    await waitFor(() => expect(asked).toHaveBeenCalledWith(B, expect.anything()));
    const bReading = await screen.findByTestId("policy-explain-reading");
    expect(bReading.textContent).toContain("Reading of prov-B");
    expect(bReading.textContent).not.toContain("Reading of prov-A");
  });

  it("drops a request still in flight for policy A when the reader moves to B", async () => {
    const pending = deferred<PolicyExplanation>();
    vi.spyOn(aiApi, "explainPolicy").mockImplementation((provisionId: string) =>
      provisionId === A ? pending.promise : Promise.resolve(explanationFor(provisionId)),
    );

    const { rerender } = render(<PolicyExplainButton provisionId={A} policyKey="POLICY-A" />);
    fireEvent.click(screen.getByTestId("policy-explain-button"));
    await screen.findByTestId("policy-explain-pending");

    // Move to policy B while A is still in flight, then let A land late.
    rerender(<PolicyExplainButton provisionId={B} policyKey="POLICY-B" />);
    await land(pending, explanationFor(A));

    // A's late answer must not surface anywhere.
    expect(screen.queryByText(/Reading of prov-A/)).toBeNull();
  });
});
