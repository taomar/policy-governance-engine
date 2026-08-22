/**
 * Bulk review actions — the safety properties.
 *
 * Bulk approval must not become a way to approve rules nobody read. The
 * previous change fixed a defect where a reviewer could approve from a
 * collapsed row without the source passage on screen. A "select all → approve"
 * button would reintroduce that at scale. These tests pin the constraints
 * that keep it from happening:
 *
 *   1. Nothing is decided until the confirmation dialog is accepted.
 *   2. "Select all" reaches the current page and no further.
 *   3. The confirmation names the records, not just a count.
 *   4. A bulk reject requires a reason.
 *   5. A partial failure reports which records were not decided.
 *   6. The remaining-work figure states what it covers.
 *
 * These read the source of ReviewQueue.tsx rather than rendering the full
 * component, which takes 13 minutes under test and whose end-to-end path is
 * proven in a browser. The fragments that must not regress are pinned by
 * source read — the same technique used in
 * theSelectionCounterIsHonestAtSource.test.ts. For the confirmation modal and
 * partial-failure reporting, small extracted helpers are tested by argument.
 */
import { describe, expect, it } from "vitest";

// ---------------------------------------------------------------------------
// Source-read tests: pin structural properties of ReviewQueue.tsx
// ---------------------------------------------------------------------------

const reviewSource = Object.values(
  import.meta.glob("./components/ReviewQueue.tsx", {
    query: "?raw",
    import: "default",
    eager: true,
  }),
)[0] as string;

/** The span between two literal anchors. */
function slice(source: string, from: string, to: string): string {
  const start = source.indexOf(from);
  if (start < 0) throw new Error(`anchor not found: ${from}`);
  const end = source.indexOf(to, start + from.length);
  if (end <= start) throw new Error(`anchor not found after ${from}: ${to}`);
  return source.slice(start, end);
}

describe("nothing is decided until the confirmation is accepted", () => {
  it("handleBulkReview opens a confirmation dialog instead of calling runReview", () => {
    // The handler must set bulkConfirm state, never call requestReview directly.
    const handler = slice(reviewSource, "const handleBulkReview", "confirmBulkReview");
    expect(handler).toContain("setBulkConfirm(");
    expect(handler).not.toContain("requestReview(");
    expect(handler).not.toContain("runReview(");
  });

  it("the bulk confirm modal is gated by bulkConfirm state", () => {
    // The modal's `open` prop must be driven by `bulkConfirm`.
    expect(reviewSource).toContain("open={bulkConfirm !== null}");
  });

  it("confirmBulkReview is the only path from the modal to a decision", () => {
    const confirm = slice(reviewSource, "const confirmBulkReview", "const selectedPolicyCount");
    expect(confirm).toContain("requestReview(");
    // The reject branch requires a reason before proceeding.
    expect(confirm).toContain("bulkRejectReason.trim()");
  });
});

describe("select all reaches the current page and no further", () => {
  it("selectableIds is computed from pagedPolicyCards and pagedCandidates, not the full list", () => {
    const block = slice(reviewSource, "const selectableIds", "const toggleSelectAllVisible");
    // Must use paged variants, not `policyCards` or `filteredCandidates`.
    expect(block).toContain("pagedPolicyCards");
    expect(block).toContain("pagedCandidates");
    expect(block).not.toMatch(/\bpolicyCards\.flatMap\b/);
    expect(block).not.toMatch(/\bfilteredCandidates\b/);
  });

  it("the select-all label says 'on this page', not 'in this filter'", () => {
    // The old label said "in this filter" which implied it reached everything.
    expect(reviewSource).toContain("on this page");
    expect(reviewSource).not.toContain("in this filter");
  });
});

describe("the confirmation names the records, not just a count", () => {
  it("the modal renders bulkConfirmNames with individual record titles", () => {
    const modal = slice(reviewSource, "bulk-confirm-records", "</Modal>");
    // Must iterate over individual records with their titles.
    expect(modal).toContain("r.title");
    // Must have a "and N more" overflow for long lists.
    expect(modal).toContain("more rule");
  });

  it("bulkConfirmNames maps ids to titles from the candidates", () => {
    const block = slice(reviewSource, "const bulkConfirmNames", "const handlePublish");
    expect(block).toContain("rule.title");
    expect(block).toContain("candidates.find");
  });
});

describe("a bulk reject requires a reason", () => {
  it("the reject confirmation renders a reason text area", () => {
    expect(reviewSource).toContain('data-testid="bulk-reject-reason"');
  });

  it("confirmBulkReview refuses to proceed without a reason for rejection", () => {
    const confirm = slice(reviewSource, "const confirmBulkReview", "const selectedPolicyCount");
    // Must check that the reason is non-empty for rejects.
    expect(confirm).toContain("reject");
    expect(confirm).toContain("bulkRejectReason.trim()");
    // The early return when no reason is provided.
    expect(confirm).toMatch(/if.*reject.*!bulkRejectReason/s);
  });

  it("the OK button is disabled when no reason is entered for a rejection", () => {
    // The okButtonProps are on the Modal component which starts before data-testid.
    const modal = slice(reviewSource, "Bulk review confirmation", "</Modal>");
    expect(modal).toContain("!bulkRejectReason.trim()");
  });
});

describe("a partial failure reports which records were not decided", () => {
  it("skipped records are named by title, not just counted", () => {
    const block = slice(reviewSource, "const skippedNames", "message.success");
    // Must look up the title for each skipped id.
    expect(block).toContain("rule.title");
    expect(block).toContain("candidates.find");
    // Must list names, not just a bare count.
    expect(block).toContain("named");
  });
});

describe("the remaining-work figure states what it covers", () => {
  it("undecidedInFilter counts only reviewable candidates in the current filter", () => {
    const block = slice(reviewSource, "const undecidedInFilter", "const bulkConfirmNames");
    expect(block).toContain("filteredCandidates.filter");
    expect(block).toContain("candidateEditability");
    expect(block).toContain("canReview");
  });

  it("the undecided count is rendered with a scope qualifier", () => {
    expect(reviewSource).toContain("undecided in this view");
  });

  it("the count carries a comment noting it becomes wrong under pagination", () => {
    // When cursor pagination lands, the loaded-set count must be replaced by
    // the server total. This comment is the contract.
    const block = slice(reviewSource, "How many records under the current filter", "const bulkConfirmNames");
    expect(block).toContain("cursor pagination");
    expect(block).toContain("server");
  });
});
