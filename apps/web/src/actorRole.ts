/**
 * The words for a refusal that turns on who is acting.
 *
 * The server used to send the sentence. Two routers each held a copy of it and
 * this interface held a third, which had already drifted: the servers said
 * "perform this action" and the page said "launch a new campaign". A copy
 * change meant editing three places, two of them behind a deployment.
 *
 * The server now sends a refusal code with the role it wanted and the action it
 * refused. Both are needed. A bare refusal code would leave this file to guess
 * the verb, and the page that already worded it differently is the proof that a
 * guess drifts.
 *
 * TWO CODES ARRIVE HERE, not one. `actor_role_insufficient` is the original,
 * raised for the named guarded actions in `api/actor_role.py`.
 * `rbac_insufficient` is raised by the capability layer in `api/authz.py`, which
 * governs every operation rather than a named few. They are recognised together
 * because a reader does not care which server module refused them, and because
 * recognising only the first would send the second down the generic-error path
 * to be rendered as a raw object — the exact failure the codes were introduced
 * to prevent.
 *
 * Their `action` fields differ in kind, and that is why the sentence below is
 * built from the role first: the original sends a named action with a verb
 * phrase written for it here, while the capability layer sends a route
 * (`POST /api/policy-sets/{key}/publish`), which has no reading for a person.
 * Naming no verb is better than naming a route at a reader.
 *
 * Which roles and actions can arrive is checked from the other side of the
 * boundary by `tests/unit/test_actor_role_wording.py`, which reads the tuples
 * out of `api/actor_role.py` and `api/roles.py` and fails when one of them has
 * no entry here. That direction cannot run from this side: the declaration is
 * Python.
 */

/** How each role is named to a reader.
 *
 *  Both vocabularies live here. `policy_manager` is the original guarded role;
 *  the three below it are the capability layer's, and a reader can be refused
 *  on either.
 */
export const ACTOR_ROLE_LABEL: Record<string, string> = {
  policy_manager: "Policy Manager",
  viewer: "Viewer",
  policy_author: "Policy Author",
  admin: "Admin",
};

/**
 * The verb phrase for each guarded action, written to sit inside "Only a
 * Policy Manager can ___".
 */
export const GUARDED_ACTION_PHRASE: Record<string, string> = {
  launch_attestation_campaign: "launch a new campaign",
};

/** What the server sends when it refuses on the acting role. */
export interface ActorRoleRefusal {
  code: string;
  required_role: string;
  action: string;
}

export const ACTOR_ROLE_REFUSAL = "actor_role_insufficient";

/** The capability layer's refusal. Same shape, different origin. */
export const RBAC_REFUSAL = "rbac_insufficient";

const REFUSAL_CODES: readonly string[] = [ACTOR_ROLE_REFUSAL, RBAC_REFUSAL];

/**
 * True when this is a refusal about who is acting rather than any other 403.
 *
 * Checked on the code, never on the words, so that rewording this file cannot
 * change which errors are recognised.
 */
export function isActorRoleRefusal(detail: unknown): detail is ActorRoleRefusal {
  return (
    typeof detail === "object" &&
    detail !== null &&
    REFUSAL_CODES.includes((detail as { code?: unknown }).code as string)
  );
}

/** What a reader can actually do about it.
 *
 *  This used to read "Switch your acting role in the header", which was true
 *  while a control in the header changed the acting role. Under the capability
 *  layer a role is assigned, not chosen, and that control is gone — so the
 *  sentence named an action the reader could not take, which is worse than
 *  naming none. The advice is now the one thing that does move the situation.
 */
const NEXT_ACTION = "Ask an administrator if you need this access.";

/**
 * The sentence, from the role and the action.
 *
 * Falls back to naming neither rather than inventing either. An unknown role
 * or action means this build is older than the server, and a reader is better
 * served by a true vague sentence than a confident wrong one.
 */
export function actorRoleRefusalText(refusal: {
  required_role: string;
  action: string;
}): string {
  const role = ACTOR_ROLE_LABEL[refusal.required_role];
  const phrase = GUARDED_ACTION_PHRASE[refusal.action];

  if (!role) {
    return `You do not have the role this action needs. ${NEXT_ACTION}`;
  }
  if (!phrase) {
    return `Only a ${role} can do this. ${NEXT_ACTION}`;
  }
  return `Only a ${role} can ${phrase}. ${NEXT_ACTION}`;
}
