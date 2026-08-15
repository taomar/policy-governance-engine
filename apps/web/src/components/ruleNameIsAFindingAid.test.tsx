import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";

/**
 * A NAME IS A FINDING AID, AND IT NEVER STANDS IN THE WAY.
 *
 * Four things can be true of a rule's name and only one of them renders. There
 * is a name; nobody has generated one; it was asked for and nothing usable came
 * back; and the request did not complete. The last three are three different
 * facts and the store keeps them apart, but a reader sees the same thing for
 * all three -- the card exactly as it was before this feature existed.
 *
 * WHY THE FIRST TEST IS THE IMPORTANT ONE
 *
 * Every "renders nothing" assertion below is passed trivially by a component
 * that renders nothing ever. So the presence test runs first and pins the whole
 * rendering: the mark, the caption that says the words are ours, and the name
 * itself. The absence assertions only mean something because that one holds.
 *
 * WHY ONE REQUEST
 *
 * A queue draws every rule on the page at once. One request per rule would be
 * seventy requests for one screen, so the store collects a tick's worth of ids
 * and asks once. That is asserted here, because it is invisible in the output
 * and would decay silently.
 */

const ruleNames = vi.fn();

vi.mock("../api", async () => {
  const actual = await vi.importActual<typeof import("../api")>("../api");
  return { ...actual, aiApi: { ...actual.aiApi, ruleNames } };
});

const { RuleName, forgetRuleNames } = await import("./RuleName");

/** The caption a reader sees, so nobody can pass these tests by removing it. */
const OURS = /named by this app/i;

beforeEach(() => {
  forgetRuleNames();
  ruleNames.mockReset();
});

afterEach(() => {
  cleanup();
});

describe("a rule that has a name", () => {
  it("shows it, marked as ours and apart from the document's words", async () => {
    ruleNames.mockResolvedValue({
      names: {
        "rule-1": {
          text: "Warden's tide register upkeep",
          unavailable_code: null,
          generated: true,
        },
      },
    });

    render(<RuleName candidateId="rule-1" />);

    await waitFor(() =>
      expect(screen.getByText("Warden's tide register upkeep")).toBeTruthy(),
    );
    const rendered = screen.getByTestId("rule-name");
    expect(rendered.textContent).toMatch(OURS);
    expect(rendered.textContent).toContain("✦");
    // Said in the markup as well as in the words, for anything reading the page
    // rather than looking at it.
    expect(rendered.getAttribute("data-generated")).toBe("true");
  });

  it("carries the name in a direction-aware run, so Arabic reads correctly", async () => {
    ruleNames.mockResolvedValue({
      names: {
        "rule-1": { text: "مسؤولية القيد في الدفتر", unavailable_code: null, generated: true },
      },
    });

    render(<RuleName candidateId="rule-1" />);

    await waitFor(() => expect(screen.getByTestId("rule-name")).toBeTruthy());
    const run = screen.getByText("مسؤولية القيد في الدفتر");
    expect(run.getAttribute("dir")).toBe("rtl");
  });
});

describe("a rule with no name to show", () => {
  it("renders nothing while the answer is on its way", () => {
    ruleNames.mockReturnValue(new Promise(() => {}));
    const { container } = render(<RuleName candidateId="rule-1" />);
    expect(container.innerHTML).toBe("");
  });

  it("renders nothing when the server holds no name for it", async () => {
    ruleNames.mockResolvedValue({ names: {} });
    const { container } = render(<RuleName candidateId="rule-1" />);
    await waitFor(() => expect(ruleNames).toHaveBeenCalled());
    expect(container.innerHTML).toBe("");
  });

  it("renders nothing when naming was run and produced none", async () => {
    ruleNames.mockResolvedValue({
      names: {
        "rule-1": { text: null, unavailable_code: "reply_declined_to_name", generated: true },
      },
    });
    const { container } = render(<RuleName candidateId="rule-1" />);
    await waitFor(() => expect(ruleNames).toHaveBeenCalled());
    expect(container.innerHTML).toBe("");
  });

  it("renders nothing when the request does not complete", async () => {
    ruleNames.mockRejectedValue(new Error("the call did not land"));
    const { container } = render(<RuleName candidateId="rule-1" />);
    await waitFor(() => expect(ruleNames).toHaveBeenCalled());
    expect(container.innerHTML).toBe("");
  });

  it("does not throw when asked about nothing", () => {
    const { container } = render(<RuleName candidateId="" />);
    expect(container.innerHTML).toBe("");
    expect(ruleNames).not.toHaveBeenCalled();
  });
});

describe("what it costs a page", () => {
  it("asks once for every rule drawn together", async () => {
    ruleNames.mockResolvedValue({ names: {} });

    render(
      <>
        <RuleName candidateId="rule-1" />
        <RuleName candidateId="rule-2" />
        <RuleName candidateId="rule-3" />
      </>,
    );

    await waitFor(() => expect(ruleNames).toHaveBeenCalledTimes(1));
    expect(ruleNames.mock.calls[0][0].sort()).toEqual(["rule-1", "rule-2", "rule-3"]);
  });

  it("does not ask again for a rule it has already asked about", async () => {
    ruleNames.mockResolvedValue({
      names: { "rule-1": { text: "A handle", unavailable_code: null, generated: true } },
    });

    render(<RuleName candidateId="rule-1" />);
    await waitFor(() => expect(screen.getByTestId("rule-name")).toBeTruthy());
    cleanup();
    render(<RuleName candidateId="rule-1" variant="block" />);
    await waitFor(() => expect(screen.getByTestId("rule-name")).toBeTruthy());

    expect(ruleNames).toHaveBeenCalledTimes(1);
  });
});

/**
 * A published version holds no draft row — there, the rule is the record — so it
 * asks by the rule's own identifier instead. Both doors reach the same stored
 * handle; only the way in differs, and the interface must not be able to tell.
 *
 * The danger the second door carries is that a canonical identifier records
 * where a rule was found in its document, so the same one in two documents is
 * two unrelated rules. Everything below exists to hold that apart.
 */
describe("a rule asked about by its own identifier", () => {
  it("shows the handle stored for it, marked as ours like any other", async () => {
    ruleNames.mockResolvedValue({
      names: {},
      names_by_rule_id: {
        "p4-E000012": { text: "A handle", unavailable_code: null, generated: true },
      },
    });

    render(<RuleName policySetKey="a-set" ruleId="p4-E000012" variant="block" />);

    await waitFor(() => expect(screen.getByTestId("rule-name")).toBeTruthy());
    expect(screen.getByTestId("rule-name").textContent).toMatch(/A handle/);
    expect(screen.getByTestId("rule-name").textContent).toMatch(OURS);
  });

  it("says which set it is asking within, so it cannot be answered by another", async () => {
    ruleNames.mockResolvedValue({ names: {} });

    render(<RuleName policySetKey="a-set" ruleId="p4-E000012" />);

    await waitFor(() => expect(ruleNames).toHaveBeenCalledTimes(1));
    expect(ruleNames.mock.calls[0][1]).toEqual({
      policySetKey: "a-set",
      ruleIds: ["p4-E000012"],
    });
  });

  it("asks each set separately when a page draws rules from more than one", async () => {
    // Rolling several sets into one request would be the unscoped lookup this
    // is arranged to prevent, in the client instead of the query.
    ruleNames.mockResolvedValue({ names: {} });

    render(
      <>
        <RuleName policySetKey="a-set" ruleId="p4-E000012" />
        <RuleName policySetKey="another-set" ruleId="p4-E000012" />
      </>,
    );

    await waitFor(() => expect(ruleNames).toHaveBeenCalledTimes(2));
    const asked = ruleNames.mock.calls.map((call) => call[1].policySetKey).sort();
    expect(asked).toEqual(["a-set", "another-set"]);
  });

  it("keeps one set's answer away from the same identifier in another", async () => {
    // The failure this catches renders as a perfectly ordinary handle above a
    // rule it was never written about, which nothing on screen would reveal.
    ruleNames.mockImplementation((_ids: string[], byRuleId?: { policySetKey: string }) =>
      Promise.resolve({
        names: {},
        names_by_rule_id:
          byRuleId?.policySetKey === "a-set"
            ? { "p4-E000012": { text: "Belongs here", unavailable_code: null, generated: true } }
            : {},
      }),
    );

    render(
      <>
        <RuleName policySetKey="a-set" ruleId="p4-E000012" variant="block" />
        <RuleName policySetKey="another-set" ruleId="p4-E000012" variant="block" />
      </>,
    );

    await waitFor(() => expect(screen.getAllByTestId("rule-name")).toHaveLength(1));
    expect(screen.getByTestId("rule-name").textContent).toMatch(/Belongs here/);
  });

  it("does not let a draft row id and a rule identifier answer each other", async () => {
    // Both are strings, and one map keyed on the bare value would file one
    // under the other's key the moment a document numbered a rule the way a
    // draft row is numbered. Here they collide deliberately: the same string
    // is a draft row id and a canonical rule id, and each must get its own.
    ruleNames.mockResolvedValue({
      names: { "shared-1": { text: "Asked by draft row", unavailable_code: null, generated: true } },
      names_by_rule_id: {
        "shared-1": { text: "Asked by identifier", unavailable_code: null, generated: true },
      },
    });

    render(
      <>
        <RuleName candidateId="shared-1" variant="block" />
        <RuleName policySetKey="a-set" ruleId="shared-1" variant="block" />
      </>,
    );

    await waitFor(() => expect(screen.getAllByTestId("rule-name")).toHaveLength(2));
    expect(screen.getAllByTestId("rule-name").map((node) => node.textContent)).toEqual([
      expect.stringMatching(/Asked by draft row/),
      expect.stringMatching(/Asked by identifier/),
    ]);
  });

  it("renders nothing at all when no handle has been generated for it", async () => {
    // Unchanged from the draft-row door: a card is never blocked by naming.
    ruleNames.mockResolvedValue({ names: {} });

    const { container } = render(<RuleName policySetKey="a-set" ruleId="p4-E000012" />);

    await waitFor(() => expect(ruleNames).toHaveBeenCalled());
    expect(container.textContent).toBe("");
  });
});
