import { Alert } from "antd";
import { reviewIdentityNotice } from "../reviewIdentityNotice";

/**
 * A standing statement, shown above the review queue's decision controls, that
 * a reviewer name must be set before a candidate can be approved or rejected —
 * stated *before* the click, the way the publish panel states its own copy,
 * rather than only by the toast that fires when the refusal is hit.
 *
 * Presentational: it reads `identity` (which the queue passes straight from
 * `actor.name`) and `hasDecisionWork`, and renders or doesn't. It holds no
 * state and sets no name — it is not a second identity control, and cannot
 * drift from the header's. It disappears the moment a name is recorded; a
 * permanent nag would be its own defect.
 *
 * A warning, not an error: a decision refused for want of an author is a
 * different state from a decision that failed, and reads in a different colour
 * from the queue's error surface.
 */
export function ReviewIdentityNotice({
  identity,
  hasDecisionWork,
}: {
  identity: string;
  hasDecisionWork: boolean;
}) {
  const notice = reviewIdentityNotice(identity, hasDecisionWork);
  if (!notice) return null;
  return (
    <Alert
      type="warning"
      showIcon
      message={notice}
      className="review-identity-warning"
    />
  );
}
