import { describe, expect, it } from "vitest";

/**
 * NOTHING A REVIEWER APPROVES MAY BE CLIPPED.
 *
 * A policy card asks for one decision over every rule it holds. That bargain
 * only works if every rule is legible on the card: the reviewer is agreeing to
 * conditions and outcomes they can read, not to a count of them.
 *
 * The violation this file was written for was not in any component. Every word
 * was in the DOM, every test asserting the text was present passed, and the
 * card still rendered
 *
 *     WHEN an employee begins work on a different date · with that date as the st…
 *
 * because `.policy-decision-line` is `white-space: nowrap; overflow: hidden` and
 * `.policy-decision-value` ends in `text-overflow: ellipsis`. The rule was
 * hidden by the stylesheet, and jsdom does no layout, so no rendering test in
 * this suite can see it. A guard that reads the stylesheet can.
 *
 * SCOPE, AND WHY THE SHARED CLASS IS LEFT ALONE. `.policy-decision-line` is also
 * worn by `CandidateRow`, `PolicyRow` and `PolicyInspector`, which are dense
 * scannable lists where one line per row is the point and an ellipsis abbreviates
 * something a click opens. Those are not policed here. The two surfaces a
 * decision is actually made on -- the review card and the detail panel -- are.
 *
 * A `title` tooltip is not a defence. It is the rule behind a control: one hover
 * instead of one click, and invisible to anyone reading rather than pointing.
 *
 * FLOOR PLACEMENT. The verdict is "no clipping declaration reaches these
 * surfaces", and a scan that parses nothing also finds no declaration. So the
 * parse is proved to be seeing -- the stylesheet read, the shared block found
 * with its clipping intact, the scoped overrides found -- and a positive control
 * runs the same evaluator over a stylesheet that does clip.
 */

/** Properties that hide text, with the values that hide it. */
const CLIPPING: readonly (readonly [string, RegExp])[] = [
  ["white-space", /^(nowrap|pre)$/],
  ["overflow", /^(hidden|clip)$/],
  ["overflow-x", /^(hidden|clip)$/],
  ["text-overflow", /^ellipsis$/],
  ["-webkit-line-clamp", /^\d+$/],
];

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
 * The value a property settles on for an element wearing `target`, sitting
 * inside ancestors wearing `scope`.
 *
 * Selectors are matched by the classes they name, which is enough here: this
 * stylesheet addresses these elements by class and nothing else. A selector
 * naming a class the element does not wear, and that no ancestor wears, cannot
 * apply. Later wins at equal weight, heavier wins outright -- the cascade.
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
      // The rightmost class is the element addressed; the rest are ancestry.
      if (classes[classes.length - 1] !== target) continue;
      const ancestry = classes.slice(0, -1);
      if (!ancestry.every((c) => scope.includes(c))) continue;
      const w = weight(selector);
      if (best === undefined || w >= best.weight) best = { value, selector, weight: w };
    }
  });
  return best === undefined ? undefined : { value: best.value, selector: best.selector };
}

/** Every way `target` inside `scope` would hide its own text. */
function clippedBy(css: Block[], target: string, scope: readonly string[]) {
  return CLIPPING.flatMap(([property, hides]) => {
    const settled = settles(css, target, scope, property);
    if (settled === undefined || !hides.test(settled.value)) return [];
    return [{ target, property, ...settled }];
  });
}

const stylesheets = import.meta.glob("./App.css", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

const APP_CSS = blocks(Object.values(stylesheets)[0] ?? "");

/** The elements that carry a rule's condition and its outcome. */
const DECISION_PARTS = ["policy-decision-line", "policy-decision-value", "policy-decision-result"];

/** The two surfaces a reviewer decides from, as the class chain above a rule. */
const CARD = ["policy-card", "policy-card__rules", "policy-card__rule", "policy-card__rule-body"];
const DETAIL = ["policy-detail-panel", "policy-detail-rule", "policy-detail-rule__conditions"];

describe("the stylesheet guard is reading a stylesheet", () => {
  it("parsed App.css into declaration blocks", () => {
    expect(Object.keys(stylesheets)).toHaveLength(1);
    expect(APP_CSS.length).toBeGreaterThan(500);
  });

  it("found the decision line and the two surfaces it is worn on", () => {
    const named = new Set(APP_CSS.flatMap((b) => b.selectors));
    const mentions = (needle: string) => [...named].some((s) => s.includes(needle));
    for (const part of DECISION_PARTS) expect(mentions(part)).toBe(true);
    expect(mentions("policy-card__rule")).toBe(true);
    expect(mentions("policy-detail-rule")).toBe(true);
  });

  it("still sees the shared list styling it exists to exempt", () => {
    // The dense rows keep one line per record. If this ever stops being true the
    // guard below is asserting something nothing was ever at risk of breaking.
    const line = clippedBy(APP_CSS, "policy-decision-line", ["candidate-row"]);
    expect(line.map((c) => c.property)).toContain("white-space");
  });

  it("reports a violation when one is present", () => {
    const planted = blocks(`
      .policy-decision-value { overflow: hidden; text-overflow: ellipsis; }
      .policy-card__rule .policy-decision-value { font-weight: 500; }
    `);
    const found = clippedBy(planted, "policy-decision-value", CARD);
    expect(found.map((c) => c.property).sort()).toEqual(["overflow", "text-overflow"]);
  });
});

describe("nothing a reviewer approves is clipped", () => {
  for (const [surface, scope] of [
    ["the review card", CARD],
    ["the detail panel", DETAIL],
  ] as const) {
    for (const part of DECISION_PARTS) {
      it(`shows ${part} whole on ${surface}`, () => {
        expect(clippedBy(APP_CSS, part, scope)).toEqual([]);
      });
    }
  }

  it("shows the source passage whole on the review card", () => {
    // The passage is what the rules were read out of. Trimming it would leave a
    // reviewer checking a rule against a quotation that had itself been cut.
    expect(clippedBy(APP_CSS, "policy-card__passage-source", CARD)).toEqual([]);
    expect(clippedBy(APP_CSS, "policy-card__passage", CARD)).toEqual([]);
  });

  it("shows a rule's own title whole on the review card", () => {
    expect(clippedBy(APP_CSS, "policy-card__rule-title", CARD)).toEqual([]);
  });
});
