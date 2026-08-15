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
 * WHAT ELSE THEY HOLD IT TO
 *
 * Two other surfaces already draw one rule's logic as a tree — what scopes it
 * under `APPLIES`, what follows from it under the effect the record declares —
 * and a reviewer arrives here from both. So the rows here are checked to be
 * those rows, in those halves, wearing the class the shared stylesheet lays out,
 * with the halves taken from the record rather than guessed from the names.
 *
 * WHY THESE ARE RENDERS AND NOT READS OF THE SOURCE
 *
 * A source-level check ("no `<table>`") would pass on a view that hid attributes
 * with CSS, with `hidden`, or by slicing the array. So the component is rendered
 * and every value of every rule is looked for in the output, with no interaction
 * of any kind first. The one thing a render in this environment cannot see is
 * layout, so the sideways-scrolling and no-clipping claims are made against the
 * stylesheet the view is drawn with, each with a planted violation proving the
 * reader can fail.
 *
 * Every count is paired with a control that fails when nothing renders, because
 * `expect(missing).toHaveLength(0)` is also what a blank page returns.
 */

import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

import type { PolicyAttribute } from "./api";
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

/** jsdom builds a tree it will never lay out, and at these sizes that costs
 *  seconds. The browser's own cost is measured in the browser; this only stops
 *  the default five seconds from failing a test that is doing its job. */
const WHOLE_POLICY = 60_000;

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

function row(
  attribute: string,
  text: string,
  fact: string | null = null,
  dataType: string | null = null,
): PolicyAttribute {
  return { attribute, text, fact, data_type: dataType } as PolicyAttribute;
}

function cardRule(
  ruleId: string,
  table: { applies?: PolicyAttribute[]; outcome?: PolicyAttribute[] } | null,
  options: { route?: string; effect?: string } = {},
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
        effect: { type: options.effect ?? "require_action", action: "" },
        condition: { type: "all", all: [] },
        attributes:
          table === null
            ? undefined
            : { applies: table.applies ?? [], outcome: table.outcome ?? [] },
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
 *  every slot is stated by someone and nearly every rule leaves some out.
 *
 *  Which half a slot lands in is decided by its position in the list, not by
 *  anything about its name — the view must read the halves off the record, and a
 *  fixture that agreed with a guess would not show that it does. */
function unevenPolicy(size: number): PolicyCard {
  const rules = Array.from({ length: size }, (_, index) => {
    const applies: PolicyAttribute[] = [];
    const outcome: PolicyAttribute[] = [];
    SLOTS.forEach((slot, position) => {
      // Deliberately arithmetic rather than tabulated: no arrangement below is
      // one an observed document produced.
      if ((index + position) % (position + 2) !== 0) return;
      const entry = row(slot, `${slot} as rule ${index + 1} states it`);
      (position % 2 === 0 ? applies : outcome).push(entry);
    });
    // Every rule states at least one thing, or the fixture would be testing the
    // empty case in disguise.
    if (!applies.some((entry) => entry.attribute === "subject")) {
      applies.unshift(row("subject", `subject as rule ${index + 1} states it`));
    }
    return cardRule(`rule-${index}`, { applies, outcome });
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

      const stated = shape.blocks
        .flatMap((block) => block.rules)
        .flatMap((rule) => rule.stated);
      const missing = stated.filter((entry) => !text.includes(entry.text));
      expect(missing.map((entry) => entry.text)).toEqual([]);

      // Controls: the assertion above also passes on an empty render.
      expect(stated.length).toBeGreaterThan(0);
      // Every rule gets a block of its own, at every size. A rule whose values
      // its neighbours repeat is still a rule, and hoisting its rows out would
      // make a block mean something different depending on what sits beside it.
      expect(screen.queryAllByTestId("policy-logic-rule")).toHaveLength(size);
    }, WHOLE_POLICY);
  }

  it("names every attribute a rule leaves out, on the half that leaves it out", () => {
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
      for (const branch of reading.branches) {
        const half = block?.querySelector(
          `[data-testid="policy-logic-branch"][data-side="${branch.side}"]`,
        );
        const text = half?.textContent ?? "";
        for (const attribute of branch.absent) {
          if (!text.includes(attribute)) {
            missing.push(`${reading.ruleId}/${branch.side}/absent/${attribute}`);
          }
        }
        for (const entry of branch.rows) {
          if (!text.includes(entry.text)) {
            missing.push(`${reading.ruleId}/${branch.side}/${entry.attribute}`);
          }
        }
      }
    }
    expect(missing).toEqual([]);
    // Control: a policy where no rule leaves anything out would pass vacuously.
    expect(
      readings.filter((rule) =>
        rule.branches.some((branch) => branch.absent.length > 0),
      ).length,
    ).toBeGreaterThan(0);
  }, WHOLE_POLICY);

  it("keeps the coverage count for every attribute any rule states", () => {
    const policy = unevenPolicy(LARGEST_MEASURED_POLICY);
    const shape = policyLogicShape(policy);
    render(<PolicyLogicTable card={policy} />);

    const coverage = screen.getByTestId("policy-logic-coverage").textContent ?? "";
    for (const column of shape.columns) {
      expect(coverage).toContain(column.attribute);
      expect(coverage).toContain(`${column.filled} of ${shape.total}`);
    }
    expect(shape.columns.length).toBeGreaterThan(1);
  }, WHOLE_POLICY);
});

describe("a rule reads the way the rule inspector reads it", () => {
  it("draws both halves of every rule, with the record's own heading", () => {
    const policy = card([
      {
        key: "p1",
        rules: [
          cardRule("required", {
            applies: [row("subject", "one")],
            outcome: [row("predicate", "be filed")],
          }),
          cardRule(
            "denied",
            {
              applies: [row("subject", "two")],
              outcome: [row("predicate", "be disclosed")],
            },
            { effect: "deny" },
          ),
        ],
      },
    ]);
    render(<PolicyLogicTable card={policy} />);

    const headingsOf = (ruleId: string) =>
      Array.from(
        document
          .querySelector(`[data-rule="${ruleId}"]`)
          ?.querySelectorAll('[data-testid="policy-logic-branch"]') ?? [],
      ).map((half) => half.querySelector(".cond-group-label")?.textContent);

    expect(headingsOf("required")).toEqual(["APPLIES", "REQUIRES"]);
    // The heading follows the effect the record declares, so a rule that
    // forbids something does not read as one that demands it.
    expect(headingsOf("denied")).toEqual(["APPLIES", "PROHIBITS"]);
  });

  it("puts a row only in the half the record recorded it in", () => {
    const policy = card([
      {
        key: "p1",
        rules: [
          cardRule("scoping", { applies: [row("assigner", "the issuing body")] }),
          cardRule("following", { outcome: [row("assigner", "the issuing body")] }),
        ],
      },
    ]);
    render(<PolicyLogicTable card={policy} />);

    const rowsIn = (ruleId: string, side: string) =>
      Array.from(
        document
          .querySelector(`[data-rule="${ruleId}"]`)
          ?.querySelectorAll(
            `[data-testid="policy-logic-branch"][data-side="${side}"] .policy-logic__col-label`,
          ) ?? [],
      ).map((node) => node.textContent);

    expect(rowsIn("scoping", "applies")).toEqual(["assigner"]);
    expect(rowsIn("scoping", "outcome")).toEqual([]);
    expect(rowsIn("following", "applies")).toEqual([]);
    expect(rowsIn("following", "outcome")).toEqual(["assigner"]);
  });

  it("wears the row classes the shared stylesheet lays out", () => {
    const policy = card([
      {
        key: "p1",
        rules: [
          cardRule("a", {
            applies: [row("subject", "an employee", "employee")],
            outcome: [row("threshold", "three days", "elapsed", "duration")],
          }),
          cardRule("b", { applies: [row("subject", "a supplier")] }),
        ],
      },
    ]);
    render(<PolicyLogicTable card={policy} />);

    const first = document.querySelector('[data-rule="a"]');
    const rows = first?.querySelectorAll(".policy-attr") ?? [];
    expect(rows).toHaveLength(2);
    // Name, words, identifier — the three parts, in the classes the inspector's
    // rows wear, so one stylesheet rule lays out both surfaces.
    for (const entry of Array.from(rows)) {
      expect(entry.querySelector(".policy-attr-name")).not.toBeNull();
      expect(entry.querySelector(".policy-attr-value")).not.toBeNull();
      expect(entry.querySelector(".policy-attr-fact")).not.toBeNull();
    }
    const fact = first?.querySelector(".policy-attr-fact-name");
    expect(fact?.textContent).toBe("employee");
    const typed = Array.from(
      first?.querySelectorAll(".policy-attr-fact-name") ?? [],
    ).map((node) => node.textContent);
    expect(typed).toContain("elapsed: duration");
  });

  it("shows the identifier where the record states one and nothing where it does not", () => {
    const policy = card([
      {
        key: "p1",
        rules: [
          cardRule("named", { applies: [row("subject", "an employee", "employee")] }),
          cardRule("unnamed", { applies: [row("subject", "a supplier")] }),
        ],
      },
    ]);
    render(<PolicyLogicTable card={policy} />);

    expect(
      document
        .querySelector('[data-rule="named"]')
        ?.querySelector(".policy-attr-fact-name")?.textContent,
    ).toBe("employee");
    expect(
      document
        .querySelector('[data-rule="unnamed"]')
        ?.querySelector(".policy-attr-fact-name"),
    ).toBeNull();
    // The slot is still there, so the rows line up down the block.
    expect(
      document
        .querySelector('[data-rule="unnamed"]')
        ?.querySelector(".policy-attr-fact"),
    ).not.toBeNull();
  });

  it("offers a wrap point inside a long name without altering the name", () => {
    // A name wider than the space beside a value has three possible fates:
    // shortened, pushed sideways, or wrapped. Only the third is allowed, and a
    // wrap the browser is not told about lands in the middle of a word.
    const long = "a_name_far_longer_than_its_column";
    const policy = card([
      {
        key: "p1",
        rules: [cardRule("a", { applies: [row(long, "some words")] })],
      },
    ]);
    render(<PolicyLogicTable card={policy} />);

    const label = document
      .querySelector('[data-rule="a"]')
      ?.querySelector(".policy-attr-name");
    // Read as text, the name is exactly what the record holds: the marks carry
    // no characters, so a reviewer copying the name copies the record's name.
    expect(label?.textContent).toBe(long);
    // And the browser has somewhere to break other than mid-word.
    expect((label?.querySelectorAll("wbr").length ?? 0) > 0).toBe(true);
  });

  it("leaves a name with no seam whole and unmarked", () => {
    const policy = card([
      {
        key: "p1",
        rules: [cardRule("a", { applies: [row("subject", "some words")] })],
      },
    ]);
    render(<PolicyLogicTable card={policy} />);

    const label = document
      .querySelector('[data-rule="a"]')
      ?.querySelector(".policy-attr-name");
    expect(label?.textContent).toBe("subject");
    expect(label?.querySelectorAll("wbr")).toHaveLength(0);
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
  }, WHOLE_POLICY);

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
  }, WHOLE_POLICY);
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
          cardRule("long", {
            applies: [row("subject", LONG)],
            outcome: [row("predicate", "shall be")],
          }),
          cardRule("short", {
            applies: [row("subject", "brief")],
            outcome: [row("predicate", "shall be")],
          }),
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
          cardRule("rtl", {
            applies: [row("subject", ARABIC)],
            outcome: [row("predicate", "shall be")],
          }),
          cardRule("ltr", {
            applies: [row("subject", "an employee")],
            outcome: [row("predicate", "shall be")],
          }),
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
    // Including the half that holds it, which must not be turned round either.
    const half = block?.querySelector('[data-testid="policy-logic-branch"]');
    expect(half?.getAttribute("dir")).toBeNull();
    expect(half?.className).toBe(
      other?.querySelector('[data-testid="policy-logic-branch"]')?.className,
    );
  });
});

describe("absence and not having looked are different things", () => {
  it("says which attributes a half of a rule leaves out, without the em dash", () => {
    const policy = card([
      {
        key: "p1",
        rules: [
          cardRule("states", {
            applies: [row("subject", "one")],
            outcome: [row("exception", "save one")],
          }),
          cardRule("leaves-out", { applies: [row("subject", "two")] }),
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
          cardRule("states", {
            applies: [row("subject", "one")],
            outcome: [row("exception", "save one")],
          }),
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
    expect(rule?.querySelector('[data-testid="policy-logic-branch"]')).toBeNull();
    expect(screen.getByTestId("policy-logic").textContent).toContain(
      "no recorded decomposition",
    );
  });

  it("marks the two states differently in the signature", () => {
    const policy = card([
      {
        key: "p1",
        rules: [
          cardRule("states", {
            applies: [row("subject", "one")],
            outcome: [row("exception", "save one")],
          }),
          cardRule("leaves-out", { applies: [row("subject", "two")] }),
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

/* The two claims a render in this environment cannot make. jsdom lays nothing
   out, so the stylesheet the view is drawn with is read instead, and a planted
   violation proves each reader can fail. */
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

/** Every declaration that would cut a value short instead of wrapping it. */
function clips(css: Rule[], className: string) {
  return css
    .filter((rule) =>
      rule.selectors.some((one) => one.trim().endsWith(`.${className}`)),
    )
    .flatMap((rule) =>
      rule.declarations
        .filter(
          ([property, value]) =>
            (property === "text-overflow" && value.includes("ellipsis")) ||
            (property === "white-space" && /nowrap|pre$/.test(value)) ||
            (property === "-webkit-line-clamp" && value !== "none") ||
            (property === "max-height" && value !== "none"),
        )
        .map(([property, value]) => `${rule.selectors.join(", ")} { ${property}: ${value} }`),
    );
}

describe("no part of this view scrolls sideways or cuts a value short", () => {
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
    const clipped = rules(
      ".policy-logic__stated { text-overflow: ellipsis; white-space: nowrap; }",
    );
    expect(clips(clipped, "policy-logic__stated")).toHaveLength(2);
  });

  it("declares no sideways overflow anywhere in the logic view", () => {
    expect(scrollsSideways(APP_CSS, "policy-logic")).toEqual([]);
  });

  it("lets the document's words and the attribute's name wrap", () => {
    // The shared row style cuts a long attribute name short with an ellipsis,
    // which is right where a name is a word and wrong here, where the reviewer
    // is checking that the name is the one the record states. This view undoes
    // it, and that undoing has to keep working.
    expect(clips(APP_CSS, "policy-logic__stated")).toEqual([]);
    expect(clips(APP_CSS, "policy-logic__col-label")).toEqual([]);
    const undone = APP_CSS.filter((rule) =>
      rule.selectors.some((one) => one.trim().endsWith(".policy-logic__col-label")),
    ).flatMap((rule) => rule.declarations);
    expect(undone).toContainEqual(["white-space", "normal"]);
    expect(undone).toContainEqual(["text-overflow", "clip"]);
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
  }, WHOLE_POLICY);
});
