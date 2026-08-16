/**
 * Which counts the review status tabs and the decision-progress line are given,
 * and whether the policy figures can be shown beside the rule figures honestly.
 *
 * Two populations are in play. `facetTotals` is the server's `review-facets` tally
 * over the whole policy set. The local counts are assembled from the rows the
 * queue holds, which `loadCandidates` scopes to the selected document or run
 * server-side. (Review status and delta status are never sent — they narrow which
 * rows are *shown*, not which are *loaded* — so the local counts are always of
 * whole policies, never split by a delta filter. That is why there is no delta
 * input here.)
 *
 * When a document or run scope is active the whole-set facet tally counts a
 * *different* population than the scoped rows the policy figures come from, and it
 * is not re-fetched when the scope changes. Leading the tabs with it would show a
 * whole-set rule number over a scoped queue, and pairing it with the scoped policy
 * figures — two measurements of one thing, a reader with no way to tell which is
 * which — is the mismatch this refuses. Scoped, the honest counts are the local
 * ones: rule counts and policy counts from the one set of rows, a matched pair, so
 * the tabs can lead with policies under the filter too (constraint 2).
 *
 * Unscoped, the local rows are the whole set, so the server's authoritative tally
 * leads; the policy figures are shown only when they still describe the same
 * population as it. For a moment after an approval the server tally lags the rows
 * the queue holds, and until it catches up the policy figures are withheld and
 * every tab falls back to its rule count, saying so — absent, not a fabricated
 * zero.
 */
export interface ReviewTabCountInputs {
  /** True when a document or run selection scopes the loaded rows. */
  readonly scopeActive: boolean;
  /** The server's `review-facets` tally over the whole set, or null if unloaded. */
  readonly facetTotals: Record<string, number> | null;
  /** Per-status rule counts assembled from the rows the queue holds. */
  readonly localRuleCounts: Record<string, number>;
  /** Per-status policy counts over the same rows as `localRuleCounts`. */
  readonly localPolicyCounts: Record<string, number>;
  /** Total rules over the rows the queue holds. */
  readonly totalRules: number;
  /** Total policies over the rows the queue holds. */
  readonly totalPolicyUnits: number;
}

export interface ReviewTabCounts {
  /** Per-status rule counts to show on the tabs. */
  readonly counts: Record<string, number>;
  /** Grand-total rules, for the `All` tab. */
  readonly total: number;
  /** Per-status policy counts, or null when they cannot be shown honestly. */
  readonly policyCounts: Record<string, number> | null;
  /** Grand-total policies, on the same terms as `policyCounts`. */
  readonly totalPolicies: number | null;
}

function populationsAgree(
  a: Record<string, number>,
  b: Record<string, number>,
): boolean {
  const keys = new Set([...Object.keys(a), ...Object.keys(b)]);
  for (const key of keys) {
    if ((a[key] ?? 0) !== (b[key] ?? 0)) return false;
  }
  return true;
}

export function reviewTabCounts(input: ReviewTabCountInputs): ReviewTabCounts {
  // Scoped, the whole-set facet tally is a different population than the loaded
  // rows, so the counts come from those rows — rules and policies paired. Only
  // when nothing is scoped does the server's whole-set tally lead.
  const counts = input.scopeActive
    ? input.localRuleCounts
    : (input.facetTotals ?? input.localRuleCounts);
  const total =
    input.scopeActive || !input.facetTotals
      ? input.totalRules
      : Object.values(input.facetTotals).reduce((a, b) => a + b, 0);
  const agree = populationsAgree(counts, input.localRuleCounts);
  return {
    counts,
    total,
    policyCounts: agree ? input.localPolicyCounts : null,
    totalPolicies: agree ? input.totalPolicyUnits : null,
  };
}
