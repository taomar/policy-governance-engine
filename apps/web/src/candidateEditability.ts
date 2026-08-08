/** When a candidate rule may be edited or reviewed, and — when it may not —
 * what the user should do instead.
 *
 * This mirrors `_EDITABLE_STATUSES` in
 * `src/policy_platform/api/routers/candidate_rules.py`, which is the authority:
 * the server rejects an out-of-state edit with 409 regardless of what the UI
 * allows. The client copy exists only so the interface can *explain* the rule
 * before the user runs into it.
 *
 * Previously this policy lived in three places — the Python tuple, a
 * `REVIEWABLE_STATUSES` set rebuilt on every render in ReviewQueue, and the
 * inline JSX conditionals that decided which buttons to draw. The three had
 * already drifted: "can be edited" and "can be reviewed" were gated by the same
 * set even though they are different acts, so an approved-but-unpublished rule
 * simply lost its Edit button with no explanation of the send-back path the
 * server was waiting for.
 */

export type CandidateReviewStatus =
  | "candidate"
  | "approved"
  | "rejected"
  | "changes_requested"
  | "published";

export interface CandidateEditability {
  /** May the rule's content be changed via the edit/revise endpoint? */
  canEdit: boolean;
  /** May an approve/reject decision be recorded right now? */
  canReview: boolean;
  /** Why editing is blocked, phrased as the next action the user can take.
   * `null` when editing is allowed. */
  editBlockedReason: string | null;
}

const EDITABILITY: Record<CandidateReviewStatus, CandidateEditability> = {
  candidate: { canEdit: true, canReview: true, editBlockedReason: null },
  rejected: { canEdit: true, canReview: true, editBlockedReason: null },
  changes_requested: { canEdit: true, canReview: true, editBlockedReason: null },
  approved: {
    canEdit: false,
    canReview: false,
    editBlockedReason:
      "This rule is already approved. A Policy Manager must send it back for changes first, so the reason it was reopened is on the record.",
  },
  published: {
    canEdit: false,
    canReview: false,
    editBlockedReason:
      "This rule is part of a published version. Published versions are immutable snapshots — start a revision instead of editing it in place.",
  },
};

const UNKNOWN_STATUS: CandidateEditability = {
  canEdit: false,
  canReview: false,
  editBlockedReason: "This rule's review status isn't recognised by this build, so editing is blocked as a precaution.",
};

export function candidateEditability(status: string): CandidateEditability {
  return EDITABILITY[status as CandidateReviewStatus] ?? UNKNOWN_STATUS;
}
