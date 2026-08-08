/** What approving one member of a banded family means for the rest of it.
 *
 * A family is a set of rules that are variations of a single decision — the
 * same `group_label`, or the same rule type testing the same fact at different
 * values. That is why they are banded together in the list.
 *
 * The governance consequence is easy to miss on screen. Approving one variant
 * and leaving its siblings pending does not publish "one rule": it publishes a
 * *partially defined decision*. At evaluation time one branch is authoritative
 * and the others are absent, so the rule silently answers for inputs it was
 * never meant to cover, and the gap only shows up as a wrong decision later.
 *
 * The list already draws the relationship. This module is the part that makes a
 * reviewer confront it before it becomes a published version, rather than after.
 */

import type { CandidateRule } from "./api";
import { candidateEditability } from "./candidateEditability";
import { clusterIdentity, clusterLabel, type RuleVariationGroup } from "./ruleDisplay";

/** A family with at least one member the reviewer is about to leave behind. */
export interface FamilyGap {
  /** Stable identity of the cluster, for React keys and de-duplication. */
  key: string;
  /** Human-readable family name, e.g. the curated group label or shared fact. */
  label: string;
  /** Members covered by the action about to be taken. */
  covered: CandidateRule[];
  /** Members that would be left un-acted-on and are still open to review. */
  left: CandidateRule[];
  /** Total reviewable members of this family present in the queue. */
  total: number;
}

type ClusterMap = Map<string, RuleVariationGroup>;

/** Reviewable members of the family `ruleId` belongs to, including itself.
 *
 * Members already approved, published or rejected are excluded: they are not
 * a gap, they are a decision someone already made. */
export function familyMembers(
  ruleId: string,
  clusterMap: ClusterMap,
  candidates: CandidateRule[]
): CandidateRule[] {
  const cluster = clusterMap.get(ruleId);
  if (!cluster) return [];
  const identity = clusterIdentity(cluster);
  return candidates.filter((c) => {
    const other = clusterMap.get(c.rule.rule_id);
    if (!other || clusterIdentity(other) !== identity) return false;
    return candidateEditability(c.review_status).canReview;
  });
}

/** The families that the given selection would split, and by how much.
 *
 * `coveredIds` are candidate ids (not rule ids) the pending action applies to.
 * A family appears in the result only when at least one reviewable member is
 * *not* covered — a fully covered family is not a gap and must not nag.
 */
export function familyGaps(
  coveredIds: Set<string>,
  clusterMap: ClusterMap,
  candidates: CandidateRule[]
): FamilyGap[] {
  const byFamily = new Map<string, { label: string; members: CandidateRule[] }>();

  for (const candidate of candidates) {
    if (!candidateEditability(candidate.review_status).canReview) continue;
    const cluster = clusterMap.get(candidate.rule.rule_id);
    if (!cluster) continue;
    const key = clusterIdentity(cluster);
    const entry = byFamily.get(key) ?? { label: clusterLabel(cluster), members: [] };
    entry.members.push(candidate);
    byFamily.set(key, entry);
  }

  const gaps: FamilyGap[] = [];
  for (const [key, { label, members }] of byFamily) {
    const covered = members.filter((m) => coveredIds.has(m.id));
    // A family nobody touched is not a gap — the reviewer isn't splitting it.
    if (covered.length === 0) continue;
    const left = members.filter((m) => !coveredIds.has(m.id));
    if (left.length === 0) continue;
    gaps.push({ key, label, covered, left, total: members.length });
  }

  // Widest gaps first: the family losing the most members is the one most
  // likely to publish an incomplete decision.
  gaps.sort((a, b) => b.left.length - a.left.length);
  return gaps;
}

/** Every reviewable candidate id across the given families. */
export function idsCoveringFamilies(gaps: FamilyGap[]): string[] {
  const ids = new Set<string>();
  for (const gap of gaps) {
    for (const member of gap.covered) ids.add(member.id);
    for (const member of gap.left) ids.add(member.id);
  }
  return Array.from(ids);
}
