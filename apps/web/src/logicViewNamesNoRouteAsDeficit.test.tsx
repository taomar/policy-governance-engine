/**
 * THE TWO ROUTES ARE RENDERED THE SAME WAY, AND THIS PROVES IT BY SUBSTITUTION
 * RATHER THAN BY VOCABULARY.
 *
 * A rule is decided either by a comparison or by a reader. Which one it is says
 * something about the sentence the document wrote, and nothing about the quality
 * of the record. Five separate phrasings have nonetheless got past the guards
 * that read this interface for words, because a list of words is a list of the
 * evasions already found and never of the next one.
 *
 * So the first test here does not read words at all. It renders a policy, swaps
 * every rule's route for the other one, renders it again, replaces the two route
 * names with the same placeholder, and demands the two outputs be identical
 * character for character. Anything that treats one route differently — a
 * softer class, an extra caption, a count of how many rules "still" need
 * something, a sort that sinks one kind to the bottom, an ordering of the two in
 * a legend — changes the output and fails, whatever words it is written in.
 *
 * That leaves the case substitution cannot see: copy that disparages both routes
 * equally, or the view as a whole. A short vocabulary covers that, over the text
 * this view wrote and not over the document's words, which are quoted and may
 * say anything at all.
 *
 * Both are checked against planted violations, so neither can pass by reading
 * nothing.
 */

import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { cleanup, render } from "@testing-library/react";

import type { PolicyAttribute } from "./api";
import { POLICY_ROUTE_LABELS } from "./policyGrouping";
import type {
  PolicyCard,
  PolicyCardPassage,
  PolicyCardRule,
} from "./policyCards";
import { PolicyLogicTable } from "./components/PolicyLogicTable";

beforeAll(() => {
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

const ROUTES = ["deterministic", "ai_ready"] as const;

function row(attribute: string, text: string): PolicyAttribute {
  return { attribute, text, fact: null, data_type: null } as PolicyAttribute;
}

function cardRule(
  ruleId: string,
  route: string,
  table: { applies: PolicyAttribute[]; outcome: PolicyAttribute[] },
): PolicyCardRule {
  return {
    rule_id: ruleId,
    evaluation_mode: route,
    candidate: {
      id: `record-${ruleId}`,
      review_status: "candidate",
      rule: {
        rule_id: ruleId,
        rule_type: "obligation",
        effect: { type: "require_action", action: "" },
        condition: { type: "all", all: [] },
        attributes: table,
      },
    },
  } as unknown as PolicyCardRule;
}

/** The same rules twice, differing only in which route each one took.
 *
 *  The values are held constant on purpose: a rule decided by reading and a rule
 *  decided by comparison are being asked to look the same, so nothing else may
 *  vary between the two renders. */
function twoWays(size: number): [PolicyCard, PolicyCard] {
  const build = (flip: boolean): PolicyCard => {
    const rules = Array.from({ length: size }, (_, index) => {
      const applies: PolicyAttribute[] = [
        row("subject", `subject as rule ${index + 1} states it`),
      ];
      const outcome: PolicyAttribute[] = [];
      if (index % 3 === 0) {
        applies.push(row("condition", `where rule ${index + 1} applies`));
      }
      if (index % 2 === 0) outcome.push(row("threshold", `${index + 1} days`));
      const route = ROUTES[(index + (flip ? 1 : 0)) % ROUTES.length];
      return cardRule(`rule-${index}`, route, { applies, outcome });
    });
    const passages: PolicyCardPassage[] = [];
    for (let at = 0; at < rules.length; at += 3) {
      passages.push({
        passage: { key: `passage-${Math.floor(at / 3)}` } as PolicyCardPassage["passage"],
        rules: rules.slice(at, at + 3),
      });
    }
    return {
      policy: { key: "policy-1", rule_count: rules.length } as PolicyCard["policy"],
      passages,
      rules,
      hiddenByFilter: 0,
      reviewableIds: rules.map((rule) => rule.candidate.id),
      allIds: rules.map((rule) => rule.candidate.id),
      reviewStatuses: ["candidate"],
    };
  };
  return [build(false), build(true)];
}

/** Both route names replaced by one placeholder, longest first so that a name
 *  containing another is not half-substituted. */
function withoutRouteNames(html: string): string {
  return Object.values(POLICY_ROUTE_LABELS)
    .sort((a, b) => b.length - a.length)
    .reduce((text, label) => text.split(label).join("[route]"), html);
}

function renderedHtml(card: PolicyCard): string {
  const view = render(<PolicyLogicTable card={card} />);
  const html = view.container.innerHTML;
  view.unmount();
  return html;
}

describe("swapping every rule's route changes nothing but the route", () => {
  for (const size of [2, 6, 40]) {
    it(`renders ${size} rules identically either way round`, () => {
      const [one, other] = twoWays(size);
      const first = withoutRouteNames(renderedHtml(one));
      const second = withoutRouteNames(renderedHtml(other));

      expect(first).toBe(second);

      // Controls. Identical strings are also what two failed renders return,
      // and a substitution that matched nothing would compare the originals.
      expect(first.length).toBeGreaterThan(500);
      expect(first).toContain("[route]");
      expect(renderedHtml(one)).not.toBe(renderedHtml(other));
    });
  }

  it("fails when one route is written about differently", () => {
    // A planted defect, standing in for whatever the sixth evasion turns out to
    // be: the substitution notices it without knowing what it says.
    const [one, other] = twoWays(6);
    const disparage = (html: string) =>
      html.replace(
        POLICY_ROUTE_LABELS.ai_ready,
        `${POLICY_ROUTE_LABELS.ai_ready} (for now)`,
      );
    expect(withoutRouteNames(disparage(renderedHtml(one)))).not.toBe(
      withoutRouteNames(disparage(renderedHtml(other))),
    );
  });

  it("shows both routes in the render it is comparing", () => {
    const [one] = twoWays(6);
    const html = renderedHtml(one);
    for (const route of ROUTES) {
      expect(html).toContain(POLICY_ROUTE_LABELS[route]);
    }
  });
});

/** Words that turn a route, or a record, into a shortfall.
 *
 *  Deliberately not the list the repository already enforces: repeating that
 *  one would re-catch the five phrasings that are already caught and none of
 *  the next. These are the ordinary English of an apology — a view that has
 *  started explaining what it could not do is written in them, whichever
 *  particular sentence it reached for. */
const SHORTFALL = [
  "incomplete",
  "unsupported",
  "not supported",
  "fallback",
  "degraded",
  "deficien",
  "shortfall",
  "limitation",
  "limited to",
  "cannot",
  "can't",
  "unable",
  "lacks",
  "lacking",
  "missing",
  "gap",
  "weaker",
  "lesser",
  "merely",
  "unfinished",
  "not yet",
  "still needs",
  "needs work",
  "todo",
  "placeholder",
  "stub",
  "unresolved",
  "partially",
  "fell back",
  "best effort",
];

/** Everything this view wrote, and nothing the document did.
 *
 *  A quotation is marked where it is rendered, so it can be lifted out here. A
 *  policy about incomplete submissions would otherwise fail a scan for the word
 *  "incomplete", and censoring the document is the one thing this view must
 *  never do. */
function copyWrittenHere(root: HTMLElement): string {
  const clone = root.cloneNode(true) as HTMLElement;
  for (const quoted of Array.from(clone.querySelectorAll("[data-verbatim]"))) {
    quoted.remove();
  }
  return clone.textContent ?? "";
}

function shortfallIn(text: string): string[] {
  const lower = text.toLowerCase();
  return SHORTFALL.filter((word) => lower.includes(word));
}

describe("this view apologises for nothing", () => {
  it("writes no copy of shortfall around either route", () => {
    const [one, other] = twoWays(40);
    for (const card of [one, other]) {
      const view = render(<PolicyLogicTable card={card} />);
      const copy = copyWrittenHere(
        view.container.querySelector('[data-testid="policy-logic"]') as HTMLElement,
      );
      expect(shortfallIn(copy)).toEqual([]);
      // Control: a scan of an empty string reports nothing either.
      expect(copy.length).toBeGreaterThan(200);
      view.unmount();
    }
  });

  it("reads the words this view wrote", () => {
    const [one] = twoWays(6);
    const view = render(<PolicyLogicTable card={one} />);
    const root = view.container.querySelector(
      '[data-testid="policy-logic"]',
    ) as HTMLElement;
    const copy = copyWrittenHere(root);
    // It sees this view's own sentences, including the headings and the line
    // that names what a rule leaves out — the copy most likely to acquire an
    // apology later.
    expect(copy).toContain("What each rule states");
    expect(copy).toContain("APPLIES");
    expect(copy).toContain("REQUIRES");
    expect(copy).toContain("states no");
    // And not the document's, which are quoted and may say anything.
    expect(root.textContent).toContain("subject as rule 1 states it");
    expect(copy).not.toContain("subject as rule 1 states it");
    view.unmount();
  });

  it("reports a planted apology", () => {
    expect(shortfallIn("This rule is incomplete")).toEqual(["incomplete"]);
    expect(shortfallIn("not yet decided")).toEqual(["not yet"]);
    expect(shortfallIn("nothing wrong with this sentence")).toEqual([]);
  });
});
