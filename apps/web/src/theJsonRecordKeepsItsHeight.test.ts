import { describe, expect, it } from "vitest";

/**
 * THE JSON RECORD MUST HAVE A HEIGHT TO RENDER INTO ON THE REVIEW PAGE.
 *
 * The defect this file was written for: on the review page a rule's JSON tab
 * drew its three sub-tabs (Evaluator JSON · Canonical formulation · DMN / FEEL)
 * and nothing beneath them. Every element was in the DOM; the record was simply
 * zero pixels tall.
 *
 * WHY. The inspector runs in two height regimes. As the destination *panel* it
 * owns a column of definite height and the record fills it and scrolls inside
 * itself -- `.inspector-pane--json .json-view { flex: 1 1 0 }`. Embedded on the
 * review card it has no height of its own: it is as tall as the rule is long and
 * the list around it scrolls. A `flex: 1 1 0` child is a flex-basis-0 item that
 * gets ALL of its height from the free space its parent hands out. An auto-height
 * column has no free space to hand out, so `.json-view` resolved to 0, its code
 * block overflowed that zero box, and `.ant-tabs-content-active` (overflow:hidden)
 * clipped it away below the switcher. The panel worked only because its definite
 * height flowed down for the flex child to consume.
 *
 * MEASURED (a faithful static reproduction: real App.css, antd 6 DOM). Embedded
 * `.json-view` was 0px and the pane clipped 203px of content to 64px of chrome.
 * The panel `.json-view` was 449px and correct. After parameterising the embedded
 * regime to size to content, embedded `.json-view` measured 2059px, its code
 * block 2028px, and the pane grew to fit with nothing clipped; the panel stayed
 * 449px, untouched. Those pixels are what this guard stands in for.
 *
 * WHAT THIS GUARD CAN AND CANNOT CATCH. jsdom does no layout, so no rendering
 * test in this suite can see a zero-height box. This one reads the stylesheet and
 * asserts the *structural cause* instead: that the embedded variant does not
 * leave the record on a zero flex-basis child, which is the one thing that
 * collapses it in an auto-height column. It CANNOT prove the resulting pixel
 * height, cannot prove the parent is genuinely auto-height at runtime, and would
 * not notice if Ant Design changed its tab DOM out from under the selectors -- the
 * measured reproduction and the on-page screenshot cover those. It CAN catch a
 * regression that puts the record back on `flex: 1 1 0` in the embedded scope, or
 * that "tidies" the panel and embedded regimes back into one rule and so reintro-
 * duces the collapse. The positive control below runs the same detector over the
 * pre-fix stylesheet to prove it is capable of seeing the defect.
 */

type Block = { selectors: string[]; declarations: Map<string, string> };

/** Declaration blocks, innermost-only, so an `@media` wrapper is stepped over. */
function blocks(css: string): Block[] {
  const withoutComments = css.replace(/\/\*[\s\S]*?\*\//g, " ");
  const found: Block[] = [];
  for (const match of withoutComments.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
    const selectors = match[1]
      .split(",")
      .map((s) => s.replace(/\s+/g, " ").trim())
      .filter((s) => s.length > 0 && !s.startsWith("@"));
    if (selectors.length === 0) continue;
    const declarations = new Map<string, string>();
    for (const part of match[2].split(";")) {
      const colon = part.indexOf(":");
      if (colon < 0) continue;
      declarations.set(
        part.slice(0, colon).trim().toLowerCase(),
        part
          .slice(colon + 1)
          .replace(/!important/gi, "")
          .trim()
          .toLowerCase(),
      );
    }
    if (declarations.size > 0) found.push({ selectors, declarations });
  }
  return found;
}

/** How many classes a selector demands, standing in for specificity. */
function weight(selector: string): number {
  return (selector.match(/\./g) ?? []).length;
}

/**
 * The value a property settles on for an element wearing `target`, sitting inside
 * ancestors wearing `scope`. Selectors are matched by the classes they name,
 * which is enough here: this stylesheet addresses these elements by class alone.
 * The rightmost class is the element addressed; the rest are ancestry and must all
 * be present in `scope`. Heavier wins outright, later wins at equal weight -- the
 * cascade for the layout properties in play, none of which is `!important`.
 */
function settles(
  css: Block[],
  target: string,
  scope: readonly string[],
  property: string,
): { value: string; selector: string } | undefined {
  let best: { value: string; selector: string; weight: number } | undefined;
  css.forEach((block) => {
    const value = block.declarations.get(property);
    if (value === undefined) return;
    for (const selector of block.selectors) {
      const classes = [...selector.matchAll(/\.([A-Za-z0-9_-]+)/g)].map((m) => m[1]);
      if (classes.length === 0) continue;
      if (classes[classes.length - 1] !== target) continue;
      const ancestry = classes.slice(0, -1);
      if (!ancestry.every((c) => scope.includes(c))) continue;
      const w = weight(selector);
      if (best === undefined || w >= best.weight) best = { value, selector, weight: w };
    }
  });
  return best === undefined ? undefined : { value: best.value, selector: best.selector };
}

/**
 * Whether a `flex` shorthand leaves its element on a zero basis -- an item that
 * has no size of its own and grows only into space a parent hands out. `1 1 0`
 * and `1 1 0px` do; `0 0 auto` (size to content) and any positive basis do not.
 * `flex: <number>` alone expands to `<number> 1 0`, also a zero basis.
 *
 * This is deliberately narrow: it reads the exact forms this stylesheet uses for
 * the record and does not attempt to be a general flex parser.
 */
function zeroBasis(flex: string): boolean {
  const tokens = flex.trim().split(/\s+/);
  if (tokens.length === 3) return /^0(px)?$/.test(tokens[2]); // grow shrink basis
  if (tokens.length === 1) return /^\d*\.?\d+$/.test(tokens[0]); // <grow> == <grow> 1 0
  return false;
}

const stylesheets = import.meta.glob("./App.css", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

const APP_CSS = blocks(Object.values(stylesheets)[0] ?? "");

/** The record and its code block: the two elements that must own a real height. */
const RECORD = ["json-view", "json-view-code"] as const;

/**
 * The embedded inspector, as the class chain above the record on the review page.
 * `policy-inspector--embedded` is the switch that turns the whole subtree to
 * auto-height, which is exactly the context that collapses a zero-basis child.
 */
const EMBEDDED = [
  "policy-inspector",
  "policy-inspector--embedded",
  "policy-inspector-tabs",
  "inspector-pane",
  "inspector-pane--json",
];

/**
 * The destination panel: the same chain WITHOUT the embedded switch. Here a
 * definite height flows down and the record is meant to fill it and scroll, so
 * the fill regime is correct and must be left in place.
 */
const PANEL = [
  "policy-inspector",
  "policy-inspector-tabs",
  "inspector-pane",
  "inspector-pane--json",
];

describe("the height guard is reading a stylesheet", () => {
  it("parsed App.css into declaration blocks", () => {
    expect(Object.keys(stylesheets)).toHaveLength(1);
    expect(APP_CSS.length).toBeGreaterThan(500);
  });

  it("found the record's flex rule in both regimes", () => {
    // If either lookup returns nothing the assertions below are vacuous: a scope
    // that matched no rule would "pass" for the wrong reason.
    expect(settles(APP_CSS, "json-view", PANEL, "flex")).toBeDefined();
    expect(settles(APP_CSS, "json-view", EMBEDDED, "flex")).toBeDefined();
    expect(settles(APP_CSS, "json-view-code", PANEL, "flex")).toBeDefined();
    expect(settles(APP_CSS, "json-view-code", EMBEDDED, "flex")).toBeDefined();
  });

  it("classes a zero-basis flex apart from a content-sized one", () => {
    // The reading the whole guard turns on, stated on literal values.
    expect(zeroBasis("1 1 0")).toBe(true);
    expect(zeroBasis("1 1 0px")).toBe(true);
    expect(zeroBasis("1")).toBe(true);
    expect(zeroBasis("0 0 auto")).toBe(false);
    expect(zeroBasis("1 1 auto")).toBe(false);
    expect(zeroBasis("0 0 240px")).toBe(false);
  });

  it("reports the collapse when it is present (the pre-fix stylesheet)", () => {
    // The embedded scope with no override of its own: the panel's `flex: 1 1 0`
    // reaches the record and, in an auto-height column, is the zero-height box the
    // reader saw. The detector must flag it, or its silence on the real file below
    // would mean nothing.
    const preFix = blocks(`
      .inspector-pane--json .json-view { flex: 1 1 0; min-height: 0; }
      .inspector-pane--json .json-view-code { flex: 1 1 0; min-height: 120px; }
      .policy-inspector--embedded .inspector-pane--json { height: auto; }
    `);
    for (const part of RECORD) {
      const settled = settles(preFix, part, EMBEDDED, "flex");
      expect(settled).toBeDefined();
      expect(zeroBasis(settled!.value)).toBe(true);
    }
  });
});

describe("the JSON record keeps a height on the review page", () => {
  for (const part of RECORD) {
    it(`does not leave .${part} on a zero flex-basis when embedded`, () => {
      // The regression assertion. On the pre-fix stylesheet this settled on
      // `flex: 1 1 0` and failed; the embedded variant now sizes the record to its
      // content so it renders whole and the list outside scrolls.
      const settled = settles(APP_CSS, part, EMBEDDED, "flex");
      expect(settled).toBeDefined();
      expect(zeroBasis(settled!.value)).toBe(false);
    });
  }

  for (const part of RECORD) {
    it(`still fills and scrolls .${part} in the destination panel`, () => {
      // The other half of the parameterisation: the panel regime is deliberately a
      // zero-basis fill (own the column, scroll inside it). If a future "tidy"
      // flattens the two regimes into one, one of these two halves breaks -- which
      // is the point of asserting both.
      const settled = settles(APP_CSS, part, PANEL, "flex");
      expect(settled).toBeDefined();
      expect(zeroBasis(settled!.value)).toBe(true);
    });
  }

  it("draws the two regimes with different rules, not one shared rule", () => {
    // The embedded record must be addressed by a rule the panel does not match, so
    // the two height regimes stay independent. That rule is heavier (it names the
    // embedded switch) and later, so it wins in the embedded scope only.
    const embedded = settles(APP_CSS, "json-view", EMBEDDED, "flex");
    const panel = settles(APP_CSS, "json-view", PANEL, "flex");
    expect(embedded?.selector).toContain("policy-inspector--embedded");
    expect(panel?.selector).not.toContain("policy-inspector--embedded");
    expect(embedded?.value).not.toBe(panel?.value);
  });
});
