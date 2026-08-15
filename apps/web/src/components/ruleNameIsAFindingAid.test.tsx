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
