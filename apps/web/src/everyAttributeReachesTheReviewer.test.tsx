/**
 * EVERY ATTRIBUTE OF EVERY RULE REACHES THE REVIEWER, WITHOUT SCROLLING SIDEWAYS
 * AND WITHOUT CLICKING ANYTHING.
 *
 * THE FAILURE THIS EXISTS TO PREVENT
 *
 * The Logic tab was a grid, rules down and attributes across. Measured in the
 * running app on the largest policy in the corpus, it laid out at two and a half
 * times the width of the panel it sits in. Everything past the fifth attribute
 * was reachable only by finding a horizontal scrollbar, and no scroll position
 * showed one whole rule. A reviewer answering "did we drop something the
 * document states" was being asked to hold a rule in their head while dragging.
 *
 * The obvious repairs are all worse than the defect: a fixed column width with
 * an ellipsis abbreviates the document's words, and an expander per rule hides
 * what the reviewer is checking for. So the arrangement changed, and these tests
 * hold the new one to what the old one could not do.
 *
 * WHY THESE ARE RENDERS AND NOT READS OF THE SOURCE
 *
 * A source-level check ("no `<table>`") would pass on a view that hid attributes
 * with CSS, with `hidden`, or by slicing the array. So the component is rendered
 * and every value of every rule is looked for in the output, with no interaction
 * of any kind first. The one thing a render in this environment cannot see is
 * layout, so the sideways-scrolling claim is made against the stylesheet the
 * view is drawn with, with a planted violation proving the reader can fail.
 *
 * Every count is paired with a control that fails when nothing renders, because
 * `expect(missing).toHaveLength(0)` is also what a blank page returns.
 */

import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

import type { CanonicalPolicyRule, PolicyAttribute } from "./api";
import { UNKNOWN_COUNT } from "./loadState";
import type {
  PolicyCard,
  PolicyCardPassage,
  PolicyCardRule,
} from "./policyCards";
import { policyLogicShape } from "./policyLogicShape";
import { PolicyLogicTable } from "./components/PolicyLogicTable";

beforeAll(() => {
  // antd reads both on mount and jsdom implements neither.
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }));
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  );
});

afterEach(cleanup);

/** The largest policy on the documents in the database, and a size well past it.
 *
 *  Two sizes rather than one, because a view that is right at seven rules and
 *  wrong at eighty is wrong, and a witness is not a target: nothing below reads
 *  a count, and the larger size exists only to show that nothing does. */
const LARGEST_MEASURED_POLICY = 84;
const LARGER_THAN_ANY_MEASURED = 120;

/** Attributes enough to have run off the side of the old grid. */
const SLOTS = [
  "subject",
  "modality",
  "predicate",
  "object",
  "actor",
  "recipient",
  "condition",
  "constraint",
  "temporal_constraint",
  "frequency",
  "deadline",
  "threshold",
  "exception",
  "consequence",
  "unit",
] as const;

function core(parts: Partial<CanonicalPolicyRule>): CanonicalPolicyRule {
  return parts as CanonicalPolicyRule;
}

function cardRule(
  ruleId: string,
  parts: Partial<CanonicalPolicyRule> | null,
  options: {
    route?: string;
    attributes?: { applies?: PolicyAttribute[]; outcome?: PolicyAttribute[] };
  } = {},
): PolicyCardRule {
  return {
    rule_id: ruleId,
    evaluation_mode: options.route ?? "ai_ready",
    candidate: {
      id: `record-${ruleId}`,
      review_status: "candidate",
      rule: {
        rule_id: ruleId,
        rule_type: "obligation",
        effect: { type: "require_action", action: "" },
        condition: { type: "all", all: [] },
        formulation:
          parts === null ? undefined : { canonical: { rule: core(parts) } },
        attributes: options.attributes
          ? {
              applies: options.attributes.applies ?? [],
              outcome: options.attributes.outcome ?? [],
            }
          : undefined,
      },
    },
  } as unknown as PolicyCardRule;
}

function card(blocks: { key: string; rules: PolicyCardRule[] }[]): PolicyCard {
  const passages: PolicyCardPassage[] = blocks.map((block) => ({
    passage: { key: block.key } as PolicyCardPassage["passage"],
    rules: block.rules,
  }));
  const rules = blocks.flatMap((block) => block.rules);
  return {
    policy: {
      key: "policy-1",
      rule_count: rules.length,
    } as PolicyCard["policy"],
    passages,
    rules,
    hiddenByFilter: 0,
    reviewableIds: rules.map((rule) => rule.candidate.id),
    allIds: rules.map((rule) => rule.candidate.id),
    reviewStatuses: ["candidate"],
  };
}

/** A policy whose rules fill an uneven, generated share of the slots, so that
 *  every slot is stated by someone and nearly every rule leaves some out. */
function unevenPolicy(size: number): PolicyCard {
  const rules = Array.from({ length: size }, (_, index) => {
    const parts: Record<string, string> = {};
    SLOTS.forEach((slot, position) => {
      // Deliberately arithmetic rather than tabulated: no arrangement below is
      // one an observed document produced.
      if ((index + position) % (position + 2) !== 0) return;
      parts[slot] = `${slot} as rule ${index + 1} states it`;
    });
    // Every rule states at least one thing, or the fixture would be testing the
    // empty case in disguise.
    parts.subject = `subject as rule ${index + 1} states it`;
    return cardRule(`rule-${index}`, parts as Partial<CanonicalPolicyRule>);
  });
  const perPassage = 3;
  const blocks: { key: string; rules: PolicyCardRule[] }[] = [];
  for (let at = 0; at < rules.length; at += perPassage) {
    blocks.push({
      key: `passage-${Math.floor(at / perPassage)}`,
      rules: rules.slice(at, at + perPassage),
    });
  }
  return card(blocks);
}

describe("every attribute of every rule is in the output", () => {
  for (const size of [1, 2, LARGEST_MEASURED_POLICY, LARGER_THAN_ANY_MEASURED]) {
    it(`renders what all ${size} rules state, with nothing to open first`, () => {
      const policy = unevenPolicy(size);
      const shape = policyLogicShape(policy);
      render(<PolicyLogicTable card={policy} />);

      const view = screen.getByTestId("policy-logic");
      const text = view.textContent ?? "";

      // What the rules say differently, once per rule.
      const stated = shape.blocks
        .flatMap((block) => block.rules)
        .flatMap((rule) => rule.stated);
      const missing = stated.filter((row) => !text.includes(row.text));
      expect(missing.map((row) => row.text)).toEqual([]);

      // What they all say the same way, said once above.
      const sharedMissing = shape.shared.filter(
        (fact) => !text.includes(fact.text),
      );
      expect(sharedMissing.map((fact) => fact.text)).toEqual([]);

      // Controls: the assertions above also pass on an empty render.
      expect(stated.length + shape.shared.length).toBeGreaterThan(0);
      // Rules get a block of their own once they differ. Where they do not —
      // one rule, or rules that state the same values — everything they state
      // is said once, above, and repeating it per rule would be the twenty
      // identical cells this view exists to stop printing.
      const blocks = screen.queryAllByTestId("policy-logic-rule");
      expect(blocks).toHaveLength(shape.columns.length > 0 ? size : 0);
      if (shape.columns.length === 0) expect(shape.shared.length).toBeGreaterThan(0);
    });
  }

  it("names every attribute a rule leaves out, on that rule", () => {
    const policy = unevenPolicy(LARGEST_MEASURED_POLICY);
    const shape = policyLogicShape(policy);
    render(<PolicyLogicTable card={policy} />);

    const readings = shape.blocks.flatMap((block) => block.rules);
    const missing: string[] = [];
    for (const reading of readings) {
      const block = document.querySelector(
        `[data-testid="policy-logic-rule"][data-rule="${reading.ruleId}"]`,
      );
      expect(block).not.toBeNull();
      const text = block?.textContent ?? "";
      for (const attribute of reading.absent) {
        if (!text.includes(attribute)) missing.push(`${reading.ruleId}/${attribute}`);
      }
      for (const row of reading.stated) {
        if (!text.includes(row.text)) missing.push(`${reading.ruleId}/${row.attribute}`);
      }
    }
    expect(missing).toEqual([]);
    // Control: a policy where no rule leaves anything out would pass vacuously.
    expect(readings.filter((rule) => rule.absent.length > 0).length).toBeGreaterThan(0);
  });

  it("keeps the coverage count for every attribute the rules differ on", () => {
    const policy = unevenPolicy(LARGEST_MEASURED_POLICY);
    const shape = policyLogicShape(policy);
    render(<PolicyLogicTable card={policy} />);

    const coverage = screen.getByTestId("policy-logic-coverage").textContent ?? "";
    for (const column of shape.columns) {
      expect(coverage).toContain(column.attribute);
      expect(coverage).toContain(`${column.filled} of ${shape.total}`);
    }
    expect(shape.columns.length).toBeGreaterThan(1);
  });
});

describe("nothing is behind a control and nothing is hidden", () => {
  it("offers nothing to expand, and hides no part of the view", () => {
    const policy = unevenPolicy(LARGEST_MEASURED_POLICY);
    render(<PolicyLogicTable card={policy} />);
    const view = screen.getByTestId("policy-logic");

    expect(view.querySelectorAll("details")).toHaveLength(0);
    expect(view.querySelectorAll("[aria-expanded]")).toHaveLength(0);
    expect(view.querySelectorAll("[hidden]")).toHaveLength(0);
    expect(
      view.querySelectorAll('[style*="display: none"], [style*="display:none"]'),
    ).toHaveLength(0);
    // Control.
    expect(view.querySelectorAll("*").length).toBeGreaterThan(0);
  });

  it("draws the shape marks as a second reading, spoken by neither", () => {
    const policy = unevenPolicy(LARGEST_MEASURED_POLICY);
    render(<PolicyLogicTable card={policy} />);
    const strips = screen.getAllByTestId("policy-logic-signature");
    expect(strips).toHaveLength(LARGEST_MEASURED_POLICY);
    for (const strip of strips) {
      // It repeats what the block says in full, so it must not say it again to
      // a reader who cannot see it.
      expect(strip.getAttribute("aria-hidden")).toBe("true");
      expect(strip.textContent).toBe("");
    }
  });
});

describe("the document's words are rendered whole", () => {
  /** Longer than the longest value measured in the corpus, and long enough that
   *  any column-width fix would have to cut it. */
  const LONG = `${"a paragraph of the document that no cell could hold ".repeat(20)}end`;
  const ARABIC = "يجب على الموظف الالتزام بالتعليمات الصادرة";

  it("renders a value of any length, unaltered", () => {
    const policy = card([
      {
        key: "p1",
        rules: [
          cardRule("long", { subject: LONG, predicate: "shall be" }),
          cardRule("short", { subject: "brief", predicate: "shall be" }),
        ],
      },
    ]);
    render(<PolicyLogicTable card={policy} />);

    const block = document.querySelector('[data-rule="long"]');
    expect(block?.textContent).toContain(LONG);
    // Nothing put an ellipsis in it, and nothing shortened it.
    expect(block?.textContent).not.toContain("…");
    expect(LONG.length).toBeGreaterThan(400);
  });

  it("isolates a right-to-left run rather than turning a container round", () => {
    const policy = card([
      {
        key: "p1",
        rules: [
          cardRule("rtl", { subject: ARABIC, predicate: "shall be" }),
          cardRule("ltr", { subject: "an employee", predicate: "shall be" }),
        ],
      },
    ]);
    render(<PolicyLogicTable card={policy} />);

    const block = document.querySelector('[data-rule="rtl"]');
    expect(block?.textContent).toContain(ARABIC);
    const isolated = block?.querySelector("bdi");
    expect(isolated?.getAttribute("dir")).toBe("rtl");
    expect(isolated?.textContent).toBe(ARABIC);

    // Direction belongs to the run and not to the block that holds it, so the
    // rule written in Arabic is laid out no differently from its neighbour.
    const other = document.querySelector('[data-rule="ltr"]');
    expect(block?.className).toBe(other?.className);
    expect(block?.getAttribute("dir")).toBeNull();
  });
});

describe("absence and not having looked are different things", () => {
  it("says which attributes a rule leaves out, without the em dash", () => {
    const policy = card([
      {
        key: "p1",
        rules: [
          cardRule("states", { subject: "one", exception: "save one" }),
          cardRule("leaves-out", { subject: "two" }),
        ],
      },
    ]);
    render(<PolicyLogicTable card={policy} />);

    const absent = document
      .querySelector('[data-rule="leaves-out"]')
      ?.querySelector('[data-testid="policy-logic-absent"]');
    expect(absent).not.toBeNull();
    expect(absent?.textContent).toContain("exception");
    expect(absent?.textContent).not.toContain(UNKNOWN_COUNT);
    expect(
      document
        .querySelector('[data-rule="leaves-out"]')
        ?.querySelector('[data-testid="policy-logic-unrecorded"]'),
    ).toBeNull();
  });

  it("wears the unknown mark for a rule nothing was recorded for", () => {
    const policy = card([
      {
        key: "p1",
        rules: [
          cardRule("states", { subject: "one", exception: "save one" }),
          cardRule("unrecorded", null),
        ],
      },
    ]);
    render(<PolicyLogicTable card={policy} />);

    const rule = document.querySelector('[data-rule="unrecorded"]');
    const unknown = rule?.querySelector('[data-testid="policy-logic-unrecorded"]');
    expect(unknown).not.toBeNull();
    expect(unknown?.textContent).toContain(UNKNOWN_COUNT);
    // It must not be reported as a rule that states nothing: nobody looked.
    expect(rule?.querySelector('[data-testid="policy-logic-absent"]')).toBeNull();
    expect(screen.getByTestId("policy-logic").textContent).toContain(
      "no recorded decomposition",
    );
  });

  it("marks the two states differently in the signature", () => {
    const policy = card([
      {
        key: "p1",
        rules: [
          cardRule("states", { subject: "one", exception: "save one" }),
          cardRule("leaves-out", { subject: "two" }),
          cardRule("unrecorded", null),
        ],
      },
    ]);
    render(<PolicyLogicTable card={policy} />);

    const marksOf = (ruleId: string) =>
      Array.from(
        document
          .querySelector(`[data-rule="${ruleId}"]`)
          ?.querySelectorAll("[data-mark]") ?? [],
      ).map((node) => node.getAttribute("data-mark"));

    expect(marksOf("states")).toEqual(["stated", "stated"]);
    expect(marksOf("leaves-out")).toEqual(["stated", "absent"]);
    expect(marksOf("unrecorded")).toEqual(["unrecorded", "unrecorded"]);
  });
});

/* The one claim a render in this environment cannot make. jsdom lays nothing
   out, so the stylesheet the view is drawn with is read instead, and a planted
   violation proves the reader can fail. */
const stylesheets = import.meta.glob("./App.css", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

interface Rule {
  selectors: string[];
  declarations: [string, string][];
}

function rules(css: string): Rule[] {
  const stripped = css.replace(/\/\*[\s\S]*?\*\//g, "");
  const found: Rule[] = [];
  for (const match of stripped.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
    const selectors = match[1]
      .split(",")
      .map((one) => one.trim())
      .filter(Boolean);
    if (selectors.some((one) => one.startsWith("@"))) continue;
    const declarations = match[2]
      .split(";")
      .map((one) => one.split(":"))
      .filter((parts) => parts.length >= 2)
      .map(
        (parts) =>
          [parts[0].trim().toLowerCase(), parts.slice(1).join(":").trim()] as [
            string,
            string,
          ],
      );
    found.push({ selectors, declarations });
  }
  return found;
}

/** Every declaration that would make something in this view scroll sideways. */
function scrollsSideways(css: Rule[], surface: string) {
  return css
    .filter((rule) => rule.selectors.some((one) => one.includes(surface)))
    .flatMap((rule) =>
      rule.declarations
        .filter(
          ([property, value]) =>
            (property === "overflow" || property === "overflow-x") &&
            /auto|scroll/.test(value),
        )
        .map(([property, value]) => `${rule.selectors.join(", ")} { ${property}: ${value} }`),
    );
}

describe("no part of this view scrolls sideways", () => {
  const APP_CSS = rules(Object.values(stylesheets)[0] ?? "");

  it("is reading a stylesheet", () => {
    expect(Object.keys(stylesheets)).toHaveLength(1);
    expect(APP_CSS.length).toBeGreaterThan(500);
    expect(
      APP_CSS.filter((rule) =>
        rule.selectors.some((one) => one.includes("policy-logic")),
      ).length,
    ).toBeGreaterThan(10);
  });

  it("reports a violation when one is present", () => {
    const planted = rules(".policy-logic__somewhere { overflow-x: auto; }");
    expect(scrollsSideways(planted, "policy-logic")).toHaveLength(1);
  });

  it("declares no sideways overflow anywhere in the logic view", () => {
    expect(scrollsSideways(APP_CSS, "policy-logic")).toEqual([]);
  });

  it("draws no table that could be wider than the panel", () => {
    const policy = unevenPolicy(LARGEST_MEASURED_POLICY);
    render(<PolicyLogicTable card={policy} />);
    const view = screen.getByTestId("policy-logic");
    expect(view.querySelectorAll("table")).toHaveLength(0);
    // Control: the view rendered something.
    expect(view.querySelectorAll('[data-testid="policy-logic-rule"]').length).toBe(
      LARGEST_MEASURED_POLICY,
    );
  });
});
