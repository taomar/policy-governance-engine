import { describe, expect, it } from "vitest";

/**
 * A LIST THE READER CHOOSES FROM MUST SCROLL INSIDE ITSELF.
 *
 * WHAT WENT WRONG
 *
 * The two surfaces are a list of policies and, beside it, a panel showing the
 * one the reader picked. The review queue's list scrolls within its own box, so
 * the panel beside it stays where it is. The published list did not: it grew
 * with the page, so picking the fortieth policy left the panel above the fold
 * and the reader looking at an unchanged screen.
 *
 * The compensating fix was to measure the panel after every selection and
 * scroll the window to it. That is a second answer to the question "where is
 * the panel" — one held by the stylesheet, one by a `requestAnimationFrame` and
 * a `getBoundingClientRect` — and the two are free to disagree. It has been
 * deleted. This file holds the remaining one.
 *
 * WHY THE STYLESHEET AND NOT A RENDER
 *
 * jsdom performs no layout, so nothing that renders these components can see
 * whether a list scrolls. Only the stylesheet can be asked, so it is asked
 * here, by the same reading of the cascade `nothingIsClipped.test.ts` uses:
 * selectors are matched by the classes they name, the rightmost class is the
 * element addressed, heavier wins, later wins at equal weight.
 *
 * The floor is proved to be seeing before it is trusted: the stylesheet is
 * parsed, both lists are found by name, and a planted stylesheet that does not
 * scroll is run through the same evaluator.
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

function weight(selector: string): number {
  return (selector.match(/\./g) ?? []).length;
}

/** The value a property settles on for an element wearing `target` inside
 *  ancestors wearing `scope`. */
function settles(
  css: Block[],
  target: string,
  scope: readonly string[],
  property: string,
): string | undefined {
  let best: { value: string; weight: number } | undefined;
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
      if (best === undefined || w >= best.weight) best = { value, weight: w };
    }
  });
  return best?.value;
}

const stylesheets = import.meta.glob("./App.css", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

const APP_CSS = blocks(Object.values(stylesheets)[0] ?? "");

/**
 * The two lists a reader picks a record from, and the container each sits in.
 *
 * Named as a pair on purpose. The defect this file was written for was that one
 * of them scrolled and the other did not, and a guard that policed only the one
 * that was broken would not notice the next surface arriving without it.
 */
const LISTS = [
  { name: "the review queue", target: "candidate-list", scope: ["review-workspace-list"] },
  {
    name: "the published policies",
    target: "published-policy-list",
    scope: ["policies-workspace", "policies-workspace-list"],
  },
] as const;

/** Values that give an element its own scrollbar rather than the page's. */
const SCROLLS = /^(auto|scroll|overlay)$/;

describe("the scroll guard is reading a stylesheet", () => {
  it("parsed App.css into declaration blocks", () => {
    expect(Object.keys(stylesheets)).toHaveLength(1);
    expect(APP_CSS.length).toBeGreaterThan(500);
  });

  it("found both lists by the names the components render", () => {
    const named = new Set(APP_CSS.flatMap((b) => b.selectors));
    for (const list of LISTS) {
      expect([...named].some((s) => s.includes(list.target))).toBe(true);
    }
  });

  it("reports a list that does not scroll", () => {
    const planted = blocks(`.published-policy-list { display: flex; }`);
    expect(settles(planted, "published-policy-list", [], "overflow-y")).toBeUndefined();
  });

  it("reports a list whose scrolling is overridden away", () => {
    // The likeliest regression is not a missing declaration but a later, heavier
    // one that undoes it. The evaluator has to follow the cascade to catch that.
    const planted = blocks(`
      .published-policy-list { overflow-y: auto; }
      .policies-workspace .published-policy-list { overflow-y: visible; }
    `);
    expect(settles(planted, "published-policy-list", ["policies-workspace"], "overflow-y")).toBe(
      "visible",
    );
  });
});

describe("a list the reader picks from keeps the panel beside it on screen", () => {
  for (const list of LISTS) {
    it(`gives ${list.name} its own scrollbar`, () => {
      const settled = settles(APP_CSS, list.target, list.scope, "overflow-y");
      expect(settled).toBeDefined();
      expect(settled).toMatch(SCROLLS);
    });

    it(`lets ${list.name} shrink below its content, so the scrollbar is reachable`, () => {
      // `overflow-y: auto` on a flex child that refuses to shrink is inert: the
      // box grows to its content and the page scrolls instead. `min-height` has
      // to be something other than the flex default of `auto`.
      const settled = settles(APP_CSS, list.target, list.scope, "min-height");
      expect(settled).toBeDefined();
      expect(settled).not.toBe("auto");
    });
  }

  it("leaves the narrow layout scrolling with the page", () => {
    // Not an exemption sneaking in: on a narrow screen the panel is a drawer
    // over the list rather than a column beside it, so there is no panel to
    // scroll off. A boxed list there would be a second scrollbar inside a page
    // that already scrolls.
    expect(
      settles(
        APP_CSS,
        "published-policy-list",
        ["policies-workspace", "policies-workspace-list", "policies-workspace--narrow"],
        "overflow",
      ),
    ).toBe("visible");
  });
});

/**
 * The compensating fix is gone, and stays gone.
 *
 * It read the panel's position out of the live layout and scrolled the window
 * when it judged it off screen. With the list boxed there is nothing for it to
 * correct, and left in place it would be a second, disagreeing answer that
 * moves the page under a reader who did not ask.
 */
describe("nothing measures the panel to decide whether it can be seen", () => {
  const sources = import.meta.glob("./components/PoliciesTab.tsx", {
    query: "?raw",
    import: "default",
    eager: true,
  }) as Record<string, string>;

  it("read the page's source", () => {
    expect(Object.keys(sources)).toHaveLength(1);
    expect(Object.values(sources)[0].length).toBeGreaterThan(1000);
  });

  it("neither measures the viewport nor scrolls it", () => {
    const source = Object.values(sources)[0];
    for (const trace of ["getBoundingClientRect", "scrollIntoView", "isOutsideWindow"]) {
      expect(source).not.toContain(trace);
    }
  });
});
