import { clusterIdentity, type RuleVariationGroup } from "./ruleDisplay";

/** Where one row sits inside its variation family, as currently displayed. */
export interface BandGeometry {
  /** Begins a run of consecutive same-family rows (draws the top cap). */
  isStart: boolean;
  /** Ends a run of consecutive same-family rows (draws the bottom cap). */
  isEnd: boolean;
  /** 1-based position within the family across the whole displayed list. */
  ordinal: number;
  /** How many family members are in the displayed list. */
  total: number;
  /** Family members exist above this run — cap fades instead of closing. */
  continuesAbove: boolean;
  /** Family members exist below this run — cap fades instead of closing. */
  continuesBelow: boolean;
  /** This run holds fewer than all displayed members, so a bare total on the
   * run's head would wrongly imply "these are all of them". */
  fragmented: boolean;
}

/** One entry of the rendered sequence. Dividers (group headers, separators)
 * break runs without belonging to a family themselves. */
export type BandSequenceItem = { kind: "rule"; ruleId: string } | { kind: "divider" };

/**
 * Computes left-edge family band geometry for a displayed list of rules.
 *
 * Two independent facts are produced here:
 *
 *  1. `isStart`/`isEnd` — whether the row begins/ends a run of *consecutive*
 *     same-cluster rows as currently displayed. A divider always breaks a run,
 *     since a band bleeding through a group divider would look broken (a curated
 *     group_label cluster can legitimately span multiple rule_types/categories).
 *     Drives the rounded-cap "bracket" look.
 *
 *  2. `ordinal`/`total`, `continuesAbove`/`continuesBelow` and `fragmented` —
 *     position within the family across the *whole* displayed list, not just this
 *     run. Sorting rarely co-locates a family, so a plain bracket silently implies
 *     "that's all of them". `fragmented` is a property of the *run* (does this run
 *     hold every member?), not of an individual row — computing it per-row from the
 *     end caps would leave a run's middle rows thinking the family was complete.
 *
 * Extracted from PolicyList so the Review queue can band pending candidates by
 * the same criterion the Policies view uses. Duplicating it would have meant two
 * implementations of "which rows are visually one family" that could disagree —
 * and the whole point of the band is that the answer is consistent wherever a
 * reviewer sees the rule.
 */
export function computeBandGeometry(
  sequence: BandSequenceItem[],
  clusterMap: Map<string, RuleVariationGroup> | undefined,
): Map<string, BandGeometry> {
  const map = new Map<string, BandGeometry>();
  if (!clusterMap || clusterMap.size === 0) return map;

  const clusterAt = (i: number): RuleVariationGroup | undefined => {
    const item = sequence[i];
    if (!item || item.kind !== "rule") return undefined;
    return clusterMap.get(item.ruleId);
  };

  const seen = new Map<string, number>();
  const totals = new Map<string, number>();
  for (const item of sequence) {
    if (item.kind !== "rule") continue;
    const cluster = clusterMap.get(item.ruleId);
    if (!cluster) continue;
    const id = clusterIdentity(cluster);
    totals.set(id, (totals.get(id) ?? 0) + 1);
  }

  // Rows of the run currently being walked, so its length can be applied to
  // every member once the run closes.
  let run: string[] = [];
  let runId: string | null = null;
  const closeRun = () => {
    if (runId === null || run.length === 0) return;
    const total = totals.get(runId) ?? run.length;
    const fragmented = run.length < total;
    for (const ruleId of run) {
      const entry = map.get(ruleId);
      if (entry) entry.fragmented = fragmented;
    }
    run = [];
    runId = null;
  };

  for (let i = 0; i < sequence.length; i++) {
    const item = sequence[i];
    if (item.kind !== "rule") {
      closeRun();
      continue;
    }
    const cluster = clusterMap.get(item.ruleId);
    if (!cluster) {
      closeRun();
      continue;
    }
    const id = clusterIdentity(cluster);
    const ordinal = (seen.get(id) ?? 0) + 1;
    seen.set(id, ordinal);
    const total = totals.get(id) ?? 1;
    const prevCluster = clusterAt(i - 1);
    const nextCluster = clusterAt(i + 1);
    const isStart = !prevCluster || clusterIdentity(prevCluster) !== id;
    const isEnd = !nextCluster || clusterIdentity(nextCluster) !== id;
    if (isStart) closeRun();
    runId = id;
    run.push(item.ruleId);
    map.set(item.ruleId, {
      isStart,
      isEnd,
      ordinal,
      total,
      continuesAbove: isStart && ordinal > 1,
      continuesBelow: isEnd && ordinal < total,
      fragmented: false,
    });
    if (isEnd) closeRun();
  }
  closeRun();
  return map;
}
