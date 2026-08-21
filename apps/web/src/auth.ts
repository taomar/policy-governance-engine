/**
 * Session storage for the signed-in user's bearer token.
 *
 * **Why `sessionStorage`, not `localStorage`:** the token is a bearer
 * credential — anyone who holds it acts as the user until it expires.
 * A credential that outlives the browser tab on a shared machine is a
 * different risk from a remembered display name.  The existing
 * `localStorage` use for the actor's *name* is fine: a name is not a
 * credential.  `sessionStorage` clears automatically when the tab
 * closes, limiting the exposure window without inventing a sweep.
 */

import type { Role } from "./rbac";

// ---------------------------------------------------------------------------
// Session shape
// ---------------------------------------------------------------------------

export interface Session {
  accessToken: string;
  /** ISO-8601 timestamp from the server's `expires_at`. */
  expiresAt: string;
  role: Role;
  name: string;
}

const STORAGE_KEY = "policy-platform.session";

// ---------------------------------------------------------------------------
// Read / write
// ---------------------------------------------------------------------------

/** Why there is no active session right now. */
export type SessionAbsence = "none" | "expired";

/** Returns the current session, or `null` when there is none or the token
 *  has expired.  An expired token is treated as no session without a server
 *  round trip — the client should not present credentials it already knows
 *  are invalid. */
export function getSession(): Session | null {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed: Session = JSON.parse(raw);
    if (
      typeof parsed.accessToken === "string" &&
      typeof parsed.expiresAt === "string" &&
      typeof parsed.role === "string" &&
      typeof parsed.name === "string"
    ) {
      if (new Date(parsed.expiresAt).getTime() <= Date.now()) {
        // Expired — discard and record why, so the login screen can
        // distinguish "you were signed out" from "you arrived signed out".
        sessionStorage.removeItem(STORAGE_KEY);
        sessionStorage.setItem(ABSENCE_KEY, "expired");
        return null;
      }
      return parsed;
    }
  } catch {
    // Malformed JSON or missing fields — treat as signed out.
  }
  sessionStorage.removeItem(STORAGE_KEY);
  return null;
}

const ABSENCE_KEY = "policy-platform.session-absence";

/** Returns why the session is absent — `"expired"` if the last session
 *  timed out, `"none"` otherwise.  The flag is consumed once: calling this
 *  clears it so the message shows only on the first render after expiry. */
export function consumeSessionAbsence(): SessionAbsence {
  const value = sessionStorage.getItem(ABSENCE_KEY);
  sessionStorage.removeItem(ABSENCE_KEY);
  return value === "expired" ? "expired" : "none";
}

export function storeSession(session: Session): void {
  sessionStorage.setItem(STORAGE_KEY, JSON.stringify(session));
}

export function clearSession(): void {
  sessionStorage.removeItem(STORAGE_KEY);
}
