import { describe, expect, it } from "vitest";

/**
 * AN EXCEPTION NAME IS NOT A SENTENCE FOR A POLICY REVIEWER.
 *
 * `loadState.ts` says why this matters, and says it about this exact shape:
 *
 *   > Callers used to write `e instanceof PolicyPlatformApiError ? e.detail :
 *   > String(e)`, and `String(e)` on a failed `fetch` produces "TypeError:
 *   > Failed to fetch" — an internal exception name shown to someone reviewing
 *   > employment policy.
 *
 * `describeApiFailure` exists to convert that. The review queue imported it,
 * used it in one place, and hand-rolled the older form in six others, so a
 * dropped connection reached the reviewer as a TypeError.
 *
 * SCOPE. This guard covers only the files this change owns. The same pattern
 * survives in roughly two dozen other components; a repo-wide assertion would
 * fail work that is in flight elsewhere and is not this change's to break. The
 * count is reported instead, so a cleanup pass can retire the rest deliberately
 * rather than have a test do it by ambush.
 */
describe("no reviewer is shown an exception name by the surfaces this change owns", () => {
  const sources = import.meta.glob("./components/*.tsx", {
    query: "?raw",
    import: "default",
    eager: true,
  }) as Record<string, string>;

  const OWNED = [
    "./components/ReviewQueue.tsx",
    "./components/RuleDetailInline.tsx",
    "./components/CandidateRow.tsx",
    "./components/PolicyDetailPanel.tsx",
    "./components/InlineTabs.tsx",
    "./components/ruleTabPanes.tsx",
    "./components/RecordActionsMenu.tsx",
  ];

  it("is reading real sources rather than an empty glob", () => {
    for (const path of OWNED) {
      expect(sources[path], `${path} was not found`).toBeTypeOf("string");
      expect(sources[path].length).toBeGreaterThan(0);
    }
  });

  it("turns a thrown value into a sentence instead of stringifying it", () => {
    const offenders: string[] = [];
    for (const path of OWNED) {
      const source = sources[path] ?? "";
      source.split("\n").forEach((line, index) => {
        if (line.trim().startsWith("*") || line.trim().startsWith("//")) return;
        if (/String\(\s*(?:e|err|error)\s*\)/.test(line)) {
          offenders.push(`${path}:${index + 1}: ${line.trim()}`);
        }
      });
    }
    expect(offenders, offenders.join("\n")).toEqual([]);
  });

  it("does not re-derive the failure sentence the api seam already decided", () => {
    const offenders: string[] = [];
    for (const path of OWNED) {
      const source = sources[path] ?? "";
      if (/instanceof\s+PolicyPlatformApiError/.test(source)) {
        offenders.push(path);
      }
    }
    expect(offenders, offenders.join("\n")).toEqual([]);
  });
});
