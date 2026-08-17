/**
 * The review queue refuses to approve or reject a candidate while no reviewer
 * name is set, and it is right to: an approval with no attributable author is
 * not an audit trail. The refusal was never the defect. The defect was that the
 * requirement was announced *only by failing it* — a ~3s toast fired on the
 * click that did nothing, gone before a reviewer who glanced away could read
 * it. A button that quietly does nothing is how this reached us reported as a
 * broken mutation, more than once.
 *
 * The publish panel had long stated its own copy of this rule up front, in a
 * standing warning; the review action, far more frequent, stated it only after
 * you had already failed. This module holds the review copy so the queue can
 * state the same requirement *before* the click, in the same voice.
 *
 * It is a statement, not a control. The gate reads `identity` — which is
 * `actor.name`, the one home for "who is doing this" — and nothing here sets
 * it. There is deliberately no second name field to drift out of step with the
 * header's.
 *
 * Three states are kept apart — a decision not yet taken, a decision refused
 * for want of an author, and a decision that failed are not one state:
 *   - not yet taken -> this returns null; the queue shows no notice.
 *   - refused       -> this returns the sentence; a standing warning states the
 *                      precondition, and the click still raises the toast.
 *   - failed        -> not ours; the queue's error surface carries it.
 */

/**
 * Aligned in voice with the publish panel's standing hint
 * ("Set your name in the application header before publishing.") so the two
 * actions describe one requirement, not two phrasings of it. It names the
 * actions that need the name and where the name is set, because "in the header"
 * is only useful if the reviewer can act on it — the header carries an
 * "Acting as" control whose button reads "Set name" until one is entered.
 */
export const REVIEW_IDENTITY_NOTICE =
  "Set your name in the application header before approving or rejecting.";

/** A name of whitespace is no name: the same trim the decision gate applies. */
export function identityIsRecorded(identity: string): boolean {
  return identity.trim().length > 0;
}

/**
 * The standing notice to show above the decision controls, or null when none is
 * due.
 *
 * `hasDecisionWork` is what ties the notice to the point of action: with
 * nothing on screen to approve or reject there is no precondition to state, and
 * a notice that stood regardless would be the permanent nag its own reviewer
 * would file next.
 */
export function reviewIdentityNotice(
  identity: string,
  hasDecisionWork: boolean,
): string | null {
  if (identityIsRecorded(identity)) return null;
  if (!hasDecisionWork) return null;
  return REVIEW_IDENTITY_NOTICE;
}
