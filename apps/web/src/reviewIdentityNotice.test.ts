/**
 * The identity requirement is stated before it is failed.
 *
 * Approving or rejecting a candidate with no reviewer name set is refused, and
 * rightly so — an approval with no attributable author is not an audit trail.
 * The defect these tests pin is not the refusal. It is that the requirement
 * used to be announced *only by failing it*: a ~3s toast on the click that did
 * nothing, gone before a reviewer who glanced away could read it. That is how
 * the action reached us reported as a silent no-op.
 *
 * This module holds the standing copy so the queue can state the requirement
 * up front, in the same voice the publish panel already uses. These assertions
 * fix three things: it stands while no name is set and there is work to decide;
 * it clears the moment a name is recorded (a permanent nag is its own defect);
 * and it stays silent when there is nothing to decide, so it lands only at the
 * point of action.
 *
 * Nothing here is a phrase from any document, and no number in it is a
 * measurement of one.
 */
import { describe, it, expect } from "vitest";
import {
  REVIEW_IDENTITY_NOTICE,
  identityIsRecorded,
  reviewIdentityNotice,
} from "./reviewIdentityNotice";

describe("a decision needs a recorded author, and the queue says so before the click", () => {
  it("stands the notice up while no name is recorded and there is work to decide", () => {
    expect(reviewIdentityNotice("", true)).toBe(REVIEW_IDENTITY_NOTICE);
    // A name of whitespace is no name — the same trim the decision gate applies.
    expect(reviewIdentityNotice("   ", true)).toBe(REVIEW_IDENTITY_NOTICE);
  });

  it("clears the moment a name is recorded", () => {
    expect(reviewIdentityNotice("jane.doe", true)).toBeNull();
    expect(identityIsRecorded("jane.doe")).toBe(true);
    expect(identityIsRecorded("   ")).toBe(false);
    expect(identityIsRecorded("")).toBe(false);
  });

  it("says nothing when there is nothing to decide, so it lands only at the point of action", () => {
    expect(reviewIdentityNotice("", false)).toBeNull();
    expect(reviewIdentityNotice("jane.doe", false)).toBeNull();
  });

  it("tells the reviewer which actions and where — actionable, one voice with the publish hint", () => {
    // "In the header" is only useful if the reviewer can act on it: which
    // actions need the name, and where the name is set.
    expect(REVIEW_IDENTITY_NOTICE).toMatch(/approving or rejecting/i);
    expect(REVIEW_IDENTITY_NOTICE).toMatch(/application header/i);
  });
});
