import { describe, expect, it } from "vitest";
import {
  ACTOR_ROLE_LABEL,
  ACTOR_ROLE_REFUSAL,
  GUARDED_ACTION_PHRASE,
  actorRoleRefusalText,
  isActorRoleRefusal,
} from "./actorRole";

/**
 * The refusal the server sends as a code becomes a sentence here.
 *
 * Which codes can arrive is checked from the Python side by
 * `tests/unit/test_actor_role_wording.py`. What is checked here is everything
 * that stays true whatever the vocabulary is: that the sentence is built from
 * the server's fields rather than assumed, that an unknown field degrades to
 * something true rather than something confident, and that recognition is by
 * code and never by words.
 */
describe("the acting-role refusal", () => {
  it("names the role and the action the server refused", () => {
    expect(
      actorRoleRefusalText({
        required_role: "policy_manager",
        action: "launch_attestation_campaign",
      })
    ).toBe("Only a Policy Manager can launch a new campaign. Ask an administrator if you need this access.");
  });

  it("drops the verb rather than inventing one for an action it does not know", () => {
    const text = actorRoleRefusalText({
      required_role: "policy_manager",
      action: "retire_a_policy_set",
    });

    // Still true, and still names the role the server asked for.
    expect(text).toContain("Policy Manager");
    // And says nothing about what was attempted, because it does not know.
    expect(text).not.toContain("undefined");
    expect(text).not.toContain("retire_a_policy_set");
  });

  it("names no role it does not have a label for", () => {
    const text = actorRoleRefusalText({
      required_role: "policy_auditor",
      action: "launch_attestation_campaign",
    });

    expect(text).not.toContain("policy_auditor");
    expect(text).not.toContain("undefined");
    expect(text).toContain("Ask an administrator if you need this access.");
  });

  it("recognises the capability layer's refusal too, not only the original", () => {
    // Two server modules refuse on who is acting: the named-action guard in
    // `api/actor_role.py` and the capability layer in `api/authz.py`. A reader
    // does not care which one refused them. Recognising only the first would
    // send the second down the generic-error path to be rendered as a raw
    // object, which is what the codes exist to prevent.
    expect(
      isActorRoleRefusal({
        code: "rbac_insufficient",
        required_role: "policy_author",
        action: "POST /api/policy-sets/{key}/publish",
      })
    ).toBe(true);
  });

  it("names a capability-layer role but not the route it refused", () => {
    // The capability layer sends a route as its action. A route has no reading
    // for a person, so the sentence names the role and stops -- the same
    // restraint as an unknown verb above.
    const text = actorRoleRefusalText({
      required_role: "policy_author",
      action: "POST /api/policy-sets/{key}/publish",
    });

    expect(text).toContain("Policy Author");
    expect(text).not.toContain("/api/");
    expect(text).not.toContain("undefined");
  });

  it("recognises the refusal by its code and not by its words", () => {
    expect(
      isActorRoleRefusal({
        code: ACTOR_ROLE_REFUSAL,
        required_role: "policy_manager",
        action: "launch_attestation_campaign",
      })
    ).toBe(true);

    // A plain-string detail is every other error the API sends.
    expect(isActorRoleRefusal("Only a Policy Manager can do this.")).toBe(false);
    expect(isActorRoleRefusal({ code: "something_else" })).toBe(false);
    expect(isActorRoleRefusal(null)).toBe(false);
  });

  it("has wording to look up at all", () => {
    // Positive control. Every assertion above reads these two records; if a
    // refactor emptied them, the fallbacks would answer and the tests that
    // check for absence would still pass.
    expect(Object.keys(ACTOR_ROLE_LABEL).length).toBeGreaterThan(0);
    expect(Object.keys(GUARDED_ACTION_PHRASE).length).toBeGreaterThan(0);
  });
});
