/**
 * A committed decision refreshes the figures the strip is read against.
 *
 * THE FAILURE THIS EXISTS TO PREVENT
 *
 * On a fresh load the status strip counted correctly and matched the database:
 * `7 policies All / 4 policies Needs review / 2 policies Approved / 1 policy
 * Published`. Then one policy was approved in the browser, and the strip became
 * `16 rules All / 10 rules Needs review / 2 rules Approved / 4 rules Published`.
 * Two faults on one action:
 *
 *   1. The tally went stale — wrong by exactly the decision the reviewer had
 *      just taken, at the one moment they were looking at it to confirm the
 *      action landed.
 *   2. The policy figures vanished. Every pill fell back to its rules-only
 *      "cannot vouch for the policy count" state. That fallback is honest when
 *      the server has not served the figure; it is a lie when it fires only
 *      because a refresh was skipped. Absent must mean "not measured", never
 *      "not refreshed".
 *
 * The cause was a missing refetch: `runReview` reloaded the scoped candidate
 * rows (`loadCandidates`) but not the whole-set facet tally the strip counts
 * from (`loadFacets` -> `api.reviewFacets`). The two are one population and must
 * move together on every commit.
 *
 * WHY A SOURCE READ
 *
 * Nothing in this repository renders the whole `<ReviewQueue>` under test — its
 * behaviour is pinned through the pure modules it is assembled from, and the
 * wiring that joins them is pinned by reading the source. This reads the two
 * decision-commit funnels and asserts each routes its post-commit reload through
 * the one shared refresh, so neither can quietly drop the facet refetch again.
 * The end-to-end proof — approve, and watch the strip agree with the database
 * without a reload — is taken in the browser, where the defect was found.
 */
import { describe, expect, it } from "vitest";

const source = Object.values(
  import.meta.glob("./ReviewQueue.tsx", {
    query: "?raw",
    import: "default",
    eager: true,
  }),
)[0] as string;

/** The text of a named block, from its declaration up to the next anchor. */
function slice(from: string, to: string): string {
  const a = source.indexOf(from);
  expect(a, `anchor not found: ${from}`).toBeGreaterThan(-1);
  const b = source.indexOf(to, a + from.length);
  return source.slice(a, b === -1 ? undefined : b);
}

const runReview = slice("const runReview = async", "const requestReview");
const handlePublish = slice("const handlePublish = async", "Copy a composer-generated rule");
const loadFacets = slice("const loadFacets = async", "};");

describe("a committed decision refreshes the figures the strip reads", () => {
  it("routes the decision funnel's reload through the shared refresh", () => {
    // runReview is the single path every approve/reject variant commits through
    // (single row, bulk bar, family confirmation). Fixing it here fixes them all.
    expect(runReview).toContain("refreshQueueAndStrip");
  });

  it("routes publish through the same shared refresh", () => {
    // Publish does not go through runReview; it is its own funnel and moves
    // approved -> published, so it stales the strip the same way.
    expect(handlePublish).toContain("refreshQueueAndStrip");
  });

  it("refreshes the strip's facets and the queue's rows together, not the rows alone", () => {
    // The call passes both loaders; the shared function awaits both. Dropping
    // the facets loader is exactly the bug this guard exists to prevent.
    expect(source).toMatch(
      /refreshQueueAndStrip\(\{[^})]*candidates:\s*loadCandidates[^})]*facets:\s*loadFacets/s,
    );
  });

  it("feeds the strip a server refetch, never a client recompute", () => {
    // The policy figure on the strip is the server's. A client-side recount
    // would be a second opinion that drifts. loadFacets owns that read.
    expect(loadFacets).toContain("api.reviewFacets");
  });

  it("no longer reloads only the rows in either funnel", () => {
    // Anti-drift: neither funnel may reach back to a bare row reload, which is
    // the shape that left the strip stale.
    expect(runReview).not.toMatch(/await\s+loadCandidates\(\)\s*;/);
    expect(handlePublish).not.toMatch(/await\s+loadCandidates\(\)\s*;/);
  });
});
