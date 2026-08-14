import { describe, expect, it } from "vitest";

/**
 * A ROUTE IS NOT A FAULT, INCLUDING WHEN IT IS SPELLED AS A NUMBER.
 *
 * The product rule: a record whose test the source states in words is decided
 * by a judge reading it. That is a ROUTE the source chose, not a FAULT this
 * system committed. Most real policy prose takes it.
 *
 * There is already a guard for this at `tests/unit/test_no_readiness_framing.py`
 * and it matches WORDS -- "machine-executable", "documentation-only", a bare
 * "executability" in a caption. It could not see the violation this file was
 * written for, because that violation contained none of those words in a
 * sentence:
 *
 *     <dt>Deterministic</dt>
 *     <dd>{totals.executable}</dd>
 *
 * A route name, alone, over a numeral, in a row of six counters that otherwise
 * read "Published rules 41" and "High findings 3". In that company
 * "Deterministic 0" is not a route the source took; it is a nought out of six.
 * The accusation is carried entirely by the layout, so a guard reading prose
 * cannot reach it.
 *
 * So this guard reads STRUCTURE: a definition-list cell whose term is a route
 * property and whose value is a bare number. The repair is not to delete the
 * number -- it is to name which routes are present, in counts, in the words
 * `projectRegisterRow.routeCell` owns, the way the dashboard tile already does:
 *
 *     Decision routes / 2735 / all decided by reading
 *
 * SCOPE. Only the counter-cell shape is matched. A per-rule badge reading
 * "Deterministic" beside one rule states that rule's route with the rule in
 * front of the reader; it is not a portfolio scoreline and is left alone.
 *
 * FLOOR PLACEMENT. The verdict is "this list of offenders is empty", and a scan
 * that reads nothing also produces an empty list. So the scan is proved to be
 * seeing -- files read, cells found, and a positive control on the exact shape
 * this guard exists for -- in tests of their own, which fail loudly rather than
 * letting the verdict pass while blind.
 */

/** `<dt>Term</dt>` followed by `<dd>value</dd>`, ignoring whitespace between. */
const COUNTER_CELL = /<dt>\s*([^<{][^<]*?)\s*<\/dt>\s*<dd>\s*([^<]*?)\s*<\/dd>/g;

/**
 * Words naming how a record's test is stated. Bare, over a numeral, each of
 * these reads as a mark out of the row rather than as a property of the source.
 */
const ROUTE_TERMS = [
  "deterministic",
  "machine executable",
  "executable",
  "executability",
  "automatable",
  "automated",
  "ai ready",
  "documentation only",
  "manual",
  "unstructured",
];

function normalise(term: string): string {
  return term
    .toLowerCase()
    .replace(/[^a-z ]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function isRouteTerm(term: string): boolean {
  const value = normalise(term);
  return ROUTE_TERMS.some((route) => value === route || value === `${route} rules`);
}

/**
 * Whether a `<dd>` body is a bare number: a literal, or a JSX expression that
 * produces one without ever naming what it counts. `{n} rules` is not bare --
 * the noun is right there beside it. `{n}` and `{a + b}` are.
 */
function isBareNumeral(value: string): boolean {
  const trimmed = value.trim();
  if (/^\d[\d,. ]*$/.test(trimmed)) return true;
  if (!trimmed.startsWith("{") || !trimmed.endsWith("}")) return false;
  // A quote or backtick means the value carries its own words.
  return !/["'`]/.test(trimmed.slice(1, -1));
}

/**
 * Source with comments removed.
 *
 * A comment renders nothing, so a violation quoted inside one is not a
 * violation -- and the repair comments in this repository deliberately quote
 * the markup they replaced, which is exactly the shape being hunted. Verified
 * against that: before this stripping, the scan reported the sentence
 * describing the fix as the fix's own recurrence.
 */
function withoutComments(text: string): string {
  return text
    .replace(/\/\*[\s\S]*?\*\//g, " ")
    .split("\n")
    .filter((line) => !line.trimStart().startsWith("//"))
    .join("\n");
}

describe("a route is not a fault, including when it is spelled as a number", () => {
  // Sources come through Vite's own graph rather than an `fs` walk: the app
  // project carries no node types, and a path walk can silently resolve to the
  // wrong root and read nothing at all. Same idiom as
  // `projectRegisterRow.test.ts`, for the same reason.
  const sources = import.meta.glob("./**/*.tsx", {
    query: "?raw",
    import: "default",
    eager: true,
  }) as Record<string, string>;

  const files = Object.entries(sources).filter(([path]) => !/\.test\.tsx$/.test(path));
  const cells = files.flatMap(([path, text]) =>
    [...withoutComments(text).matchAll(COUNTER_CELL)].map((match) => ({
      path,
      term: match[1],
      value: match[2],
    })),
  );

  it("is reading the interface source rather than an empty directory", () => {
    expect(files.length).toBeGreaterThan(40);
    expect(files.some(([path]) => path.endsWith("ProjectsPage.tsx"))).toBe(true);
    expect(files.some(([path]) => path.endsWith("ProjectOverviewTab.tsx"))).toBe(true);
  });

  it("is finding counter cells to judge", () => {
    // If this reaches zero the verdict below would pass for the wrong reason.
    expect(cells.length).toBeGreaterThan(5);
  });

  it("still fires on the exact shape it was written for", () => {
    // The violation as it stood in the register, verbatim. If the detector
    // stops seeing this, the guard has been narrowed into uselessness and this
    // test says so rather than the suite going quietly green.
    const known = `
      <div>
        <dt>Deterministic</dt>
        <dd>{totals.executable}</dd>
      </div>`;
    const found = [...known.matchAll(COUNTER_CELL)];
    expect(found).toHaveLength(1);
    expect(isRouteTerm(found[0][1])).toBe(true);
    expect(isBareNumeral(found[0][2])).toBe(true);
  });

  it("leaves a counter that is not a route alone", () => {
    const found = [..."<dt>High findings</dt><dd>{totals.highFindings}</dd>".matchAll(COUNTER_CELL)];
    expect(found).toHaveLength(1);
    expect(isRouteTerm(found[0][1])).toBe(false);
  });

  it("leaves a route stated in words alone", () => {
    const found = [
      ..."<dt>Decision routes</dt><dd>{routeSummary.headline}</dd>".matchAll(COUNTER_CELL),
    ];
    expect(found).toHaveLength(1);
    expect(isRouteTerm(found[0][1])).toBe(false);
  });

  it("renders no route property as a bare numeral", () => {
    const offenders = cells
      .filter((cell) => isRouteTerm(cell.term) && isBareNumeral(cell.value))
      .map((cell) => `${cell.path}: <dt>${cell.term}</dt><dd>${cell.value}</dd>`);
    expect(offenders).toEqual([]);
  });
});
