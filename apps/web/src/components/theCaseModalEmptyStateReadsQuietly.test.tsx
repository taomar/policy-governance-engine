/**
 * The "Put a case to this policy" modal, before anything has been asked.
 *
 * WHY THESE TESTS
 *
 * The modal used to draw a full three-column table header — Rule | Decided by |
 * Answer — over an empty body while nothing had been asked yet, framing a
 * structure the run had not produced. An empty skeleton like that reads as "the
 * answer came back empty" when the truth is "no case has been put." Constraint 5
 * holds those two apart: absent is not the same as empty.
 *
 * So the table is now drawn only once there are rows to put in it. Until then the
 * modal says, quietly and in words, what will happen — and a policy that states
 * no rules to put a case to says *that*, which is a third thing again. These pin
 * that the three silences read differently and that no header is drawn over a
 * body that does not exist. Nothing here names any real policy; the rules are
 * placeholders, so the modal renders the same for any governance document.
 *
 * (The "asked, and every rule declined to answer" state — answers present but
 * empty — is a defensive branch that a decision run cannot normally reach, since
 * a run over N>0 rules produces one row per rule. It is asserted to be its own
 * copy by inspection of the source, not driven here, because forcing it would
 * require fabricating an unreachable run state.)
 */
import { beforeAll, beforeEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import type { CanonicalRule } from "../api";

const { PolicyCaseRunner } = await import("./PolicyCaseRunner");
const { testTarget } = await import("./policyTesting");

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

beforeEach(() => {
  cleanup();
});

const A_VERSION = testTarget("a-published-version", 1);

function rule(id: string, title: string): CanonicalRule {
  return {
    rule_id: id,
    title,
    effect: "allow",
    evaluation_mode: "ai_ready",
    machine_executable: false,
    condition: { type: "all", all: [] },
    obligations: [],
    exceptions: [],
    scope: {},
    source: { document_id: "d", quotes: [] },
    lineage: { extraction_run_id: "r" },
  } as unknown as CanonicalRule;
}

describe("before a case is put, the modal is quiet and draws no empty table", () => {
  it("shows only the plain-words 'describe a case' state — not the other two silences", () => {
    render(<PolicyCaseRunner policySetKey="a-key" target={A_VERSION} rules={[rule("a", "A rule")]} />);

    // The unasked state is present, and says in words what will happen.
    const unasked = screen.getByTestId("policy-case-empty-unasked");
    expect(unasked.textContent ?? "").toMatch(/Describe a case above, and this policy will answer it\./i);

    // It is not confused with either of the other empty states.
    expect(screen.queryByTestId("policy-case-empty-answered")).toBeNull();
    expect(screen.queryByTestId("policy-case-empty-norules")).toBeNull();
  });

  it("draws no three-column table header over an empty body", () => {
    render(<PolicyCaseRunner policySetKey="a-key" target={A_VERSION} rules={[rule("a", "A rule")]} />);

    // "Decided by" is a column heading that exists only inside the results
    // table. Its absence before a run proves the skeleton header is gone.
    expect(screen.queryByText("Decided by")).toBeNull();
    // There is no antd table drawn at all yet.
    expect(document.querySelector(".ant-table")).toBeNull();
  });
});

describe("the reasoning-effort control is present but demoted and explained", () => {
  it("keeps the control, gives it a reason to exist, and does not sit it on the action", () => {
    render(<PolicyCaseRunner policySetKey="a-key" target={A_VERSION} rules={[rule("a", "A rule")]} />);

    // The capability is not removed: the label and a live <select> are both here.
    const effort = screen.getByTestId("policy-case-effort");
    expect(effort.textContent ?? "").toMatch(/Reasoning effort/i);
    expect(effort.querySelector(".ant-select")).not.toBeNull();

    // It now carries, in a few words, the one reason a reviewer would touch it —
    // so it is no longer a knob with no stated purpose.
    expect(effort.textContent ?? "").toMatch(/how hard the model reasons/i);

    // And it is demoted off the primary action: the submit button is not inside
    // the effort line any more.
    expect(effort.querySelector('[data-testid="policy-case-run"]')).toBeNull();
    // The submit action still exists, elsewhere in the modal.
    expect(screen.getByTestId("policy-case-run")).toBeTruthy();
  });
});

describe("a policy that states no rules says exactly that", () => {
  it("shows the no-rules silence, distinct from the unasked one, and cannot be run", () => {
    render(<PolicyCaseRunner policySetKey="a-key" target={A_VERSION} rules={[]} />);

    const noRules = screen.getByTestId("policy-case-empty-norules");
    expect(noRules.textContent ?? "").toMatch(/This policy states no rules to put a case to\./i);

    // It is not the "describe a case above" state — that would invite an action
    // this policy cannot take.
    expect(screen.queryByTestId("policy-case-empty-unasked")).toBeNull();

    // And the action is closed, not merely quiet.
    expect(screen.getByTestId("policy-case-run").hasAttribute("disabled")).toBe(true);
  });
});
