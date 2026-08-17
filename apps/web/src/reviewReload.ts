/**
 * What a committed decision must refresh.
 *
 * The review queue lists candidate rows scoped to the current document and run
 * (`loadCandidates`). The status strip above it counts from a whole-set facet
 * tally the server serves (`loadFacets` -> `api.reviewFacets`). They are two
 * reads of one population. When a decision — approve, reject, or a publish —
 * commits, both are a decision out of date, so both have to be refetched or the
 * strip drifts from the list. Worse, a strip left holding a stale tally has no
 * way to know it is stale: it keeps presenting a confident wrong number at the
 * exact moment the reviewer looks to confirm their action landed, and it falls
 * back to its rules-only "cannot vouch for the policy figure" state — turning a
 * skipped refresh into what looks like an unmeasured count.
 *
 * This refetches; it never recomputes. The policy figure on the strip is the
 * server's, and a client-side recount would be a second opinion that drifts —
 * this repository's second-most-logged failure. `loadFacets` owns the fetch and
 * its honest null-fallback ("could not measure"); this only says the two reads
 * happen together, on every commit, through one definition both funnels share
 * so neither can quietly drop the refresh again.
 *
 * It does not clear the last-known-good tally while the refetch is in flight:
 * blanking it would flash the very policy-figure disappearance this fixes. The
 * strip holds the previous truth for the one round-trip the refetch costs, then
 * swaps to the new one.
 */
export interface QueueReload {
  /** Refetch the scoped candidate rows the queue lists. */
  candidates: () => Promise<void>;
  /** Refetch the whole-set facet tally the status strip counts from. */
  facets: () => Promise<void>;
}

export async function refreshQueueAndStrip(reload: QueueReload): Promise<void> {
  // Both, together, not in series: neither read depends on the other, and a
  // reviewer waiting on a decision should wait one round-trip, not two.
  await Promise.all([reload.candidates(), reload.facets()]);
}
