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
 * wiring that joins them is pinned by reading the source. This reads every funnel
 * that commits a change the strip counts and asserts each routes its post-commit
 * reload through the one shared refresh, so none can quietly drop the facet
 * refetch again. The end-to-end proof — approve, and watch the strip agree with
 * the database without a reload — is taken in the browser, where the defect was
 * found.
 *
 * WHICH FUNNELS (and why this grew from two to six)
 *
 * The first cut pinned the two funnels the browser defect was seen through —
 * `runReview` and `handlePublish`. But four more commit a change to what the
 * strip counts, in the same file, through the same rows-only reload, and leaving
 * them was leaving located instances of the very class this guard names:
 *
 *   - `handleDraft` — drafts a new candidate rule, which raises the candidate
 *     tally the strip reads;
 *   - the RewriteModal and EditRuleModal `onApplied` hooks — a rewrite or edit
 *     can move a rule's policy grouping or its decidability, either of which
 *     moves the per-status policy/rule split the strip shows;
 *   - the ManagerActionModal `onApplied` hook — a manager override changes
 *     review_status outright (approve / reject / send-back), moving the tally as
 *     directly as `runReview` does.
 *
 * All six now refresh through the one shared helper. Pure loads — the initial
 * effect and the manual Refresh button — are not commits and already fetch both
 * rows and facets, so they are left alone.
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
const handleDraft = slice("const handleDraft = async", "const addConditionRow");
const loadFacets = slice("const loadFacets = async", "};");

// The three modal hooks that refresh the queue after a mutation. Sliced from
// their opening tag to the self-closing `/>` so the assertion reads exactly the
// `onApplied` each one is wired with.
const rewriteModal = slice("<RewriteModal", "/>");
const editModal = slice("<EditRuleModal", "/>");
const managerModal = slice("<ManagerActionModal", "/>");

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

  it("routes drafting a new candidate through the same shared refresh", () => {
    // Drafting adds a candidate, raising the tally the strip counts from; the
    // rows-only reload left that new rule uncounted on the strip.
    expect(handleDraft).toContain("refreshQueueAndStrip");
  });

  it("routes the rewrite, edit and manager-override modals through the same shared refresh", () => {
    // Each modal commits a change the strip counts — a rewrite or edit can move
    // a rule's policy grouping or decidability, a manager override changes
    // review_status outright — so each onApplied refreshes the strip, not the
    // rows alone.
    expect(rewriteModal).toContain("refreshQueueAndStrip");
    expect(editModal).toContain("refreshQueueAndStrip");
    expect(managerModal).toContain("refreshQueueAndStrip");
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

  it("lets no funnel — decision, publish, draft or modal — reload the rows alone", () => {
    // Anti-drift, file-wide and stronger than the per-funnel checks it replaces:
    // after a commit nothing may reach back to a bare row reload, the shape that
    // left the strip stale. No awaited funnel may `await loadCandidates()`, and
    // no modal may refresh with `void loadCandidates()`. Every post-commit
    // refresh — present and future — goes through the shared helper or this fails.
    expect(source).not.toMatch(/await\s+loadCandidates\(\)\s*;/);
    expect(source).not.toMatch(/onApplied=\{\(\)\s*=>\s*void\s+loadCandidates\(\)\s*\}/);
  });
});
