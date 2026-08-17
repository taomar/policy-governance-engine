import { describe, expect, it } from "vitest";

/**
 * A SHORT LIST MUST NOT RESERVE HEIGHT ITS CONTENT DOES NOT NEED.
 *
 * WHAT WENT WRONG
 *
 * The review queue's list sits in a bordered box beside the inspector. The two
 * are peers held at the workspace's height, and the list box was stretched to
 * that height so it would scroll when the cards were tall and always overflowed.
 *
 * The cards then learned to collapse to their heads — the reader asked for that,
 * and it fixed the scrolling. But a column of collapsed heads is far shorter than
 * the workspace, and a box still stretched to the workspace's height now shows
 * the difference as a wide blank area below the last card, inside its border. A
 * reader reported it, in as many words, as "very bad looking" — a blank that
 * large reads as a rendering that failed.
 *
 * THE FIX, AND WHY IT IS THE COLUMN AND NOT THE CARD
 *
 * The card is right to be short; padding it back to full height would undo the
 * very thing that was asked for. The box is wrong to demand a height its content
 * need not supply. So the list column stops stretching to the workspace height
 * (`align-self: flex-start`) and instead takes the height of what it holds, while
 * a `max-height` equal to the workspace keeps a long list scrolling inside its
 * own box rather than growing the page. Short: hugs its content, no blank.
 * Long: capped and scrolling, the panel beside it stays on screen. Both ends of
 * the same one rule.
 *
 * The peers no longer agree on height when the list is short — the list is as
 * tall as its content and the inspector stays tall. They agree on their top
 * edge instead, which is the alignment worth keeping; stretching the list to
 * match the inspector only ever bought symmetry with a blank.
 *
 * WHY THE STYLESHEET AND NOT A RENDER
 *
 * jsdom performs no layout, so nothing that renders the queue can see whether a
 * box reserves space it does not fill. Only the stylesheet can be asked, so it
 * is asked here, by the same reading of the cascade `theListScrollsSoThePanelIsSeen`
 * uses: selectors are matched by the classes they name, the rightmost class is
 * the element addressed, heavier wins, later wins at equal weight. The floor is
 * proved to be seeing before it is trusted: a planted stylesheet that keeps the
 * old stretch is run through the same evaluator and must be caught.
 *
 * The pixels themselves — container height against content height at one card and
 * at thirty — are measured in the running browser, not here; this guard only
 * pins that the rule which produces them is in the sheet and not overridden away.
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

/** The desktop workspace, where the list and inspector are columns of a row held
 *  at a fixed height. This is the only arrangement that can strand a blank: the
 *  narrow layout has no fixed height and the list flows with the page. */
const DESKTOP = ["review-workspace", "review-workspace--desktop"] as const;

/** Values that stop a flex child stretching to fill its container's cross size. */
const DOES_NOT_STRETCH = /^(flex-start|start|self-start|baseline)$/;

describe("the dead-space guard is reading a stylesheet", () => {
  it("parsed App.css into declaration blocks", () => {
    expect(Object.keys(stylesheets)).toHaveLength(1);
    expect(APP_CSS.length).toBeGreaterThan(500);
  });

  it("found the review list column by the name the component renders", () => {
    const named = new Set(APP_CSS.flatMap((b) => b.selectors));
    expect([...named].some((s) => s.includes("review-workspace-list"))).toBe(true);
  });

  it("reports a column that still stretches to the workspace height", () => {
    // The old sheet named no `align-self`, so the flex default `stretch` stood and
    // the box filled the workspace whatever its content. The evaluator must read
    // that absence as "not fixed" rather than passing it.
    const planted = blocks(`
      .review-workspace-list { flex: 1 1 520px; }
      .review-workspace--desktop { height: 800px; }
    `);
    expect(settles(planted, "review-workspace-list", DESKTOP, "align-self")).toBeUndefined();
  });

  it("reports a column whose hug is overridden back to a stretch", () => {
    // The likeliest regression is not a missing declaration but a later, heavier
    // one that undoes it. The evaluator has to follow the cascade to catch that.
    const planted = blocks(`
      .review-workspace--desktop .review-workspace-list { align-self: flex-start; }
      .review-workspace--desktop.review-workspace--split .review-workspace-list { align-self: stretch; }
    `);
    expect(
      settles(
        planted,
        "review-workspace-list",
        ["review-workspace", "review-workspace--desktop", "review-workspace--split"],
        "align-self",
      ),
    ).toBe("stretch");
  });
});

describe("a short list takes the height of its content, not of the workspace", () => {
  it("does not stretch the list column to the workspace height", () => {
    // `align-self: stretch` is the flex default and is exactly the blank the
    // reader saw: the box grows to the row's height and the short content leaves
    // the rest white. Anything that stops the stretch is what removes it.
    const settled = settles(APP_CSS, "review-workspace-list", DESKTOP, "align-self");
    expect(settled).toBeDefined();
    expect(settled).toMatch(DOES_NOT_STRETCH);
  });

  it("caps the list column at the workspace height, so a long list still scrolls", () => {
    // Without a cap, a column freed to take its content's height would take a long
    // list's full height and grow the page, pushing the inspector off screen — the
    // very failure the boxed, scrolling list was built to avoid. The cap is what
    // keeps `.candidate-list`'s own scrollbar (guarded elsewhere) the one that moves.
    const settled = settles(APP_CSS, "review-workspace-list", DESKTOP, "max-height");
    expect(settled).toBeDefined();
    expect(settled).toBe("100%");
  });

  it("leaves the narrow layout flowing with the page", () => {
    // Not an exemption sneaking in: the narrow workspace has no fixed height, so
    // there is nothing to stretch against and nothing to strand. The hug is a
    // desktop rule and must not reach the column when it is stacked and full width.
    const settled = settles(
      APP_CSS,
      "review-workspace-list",
      ["review-workspace", "review-workspace--narrow"],
      "align-self",
    );
    expect(settled).toBeUndefined();
  });
});
