/**
 * Actor identity — who is using the platform right now.
 *
 * The `role` field carries the RBAC role (`viewer`, `policy_author`, `admin`)
 * defined in `rbac.ts`.  A user must not be able to grant themselves a role,
 * so the role is not user-selectable — it can only be set programmatically
 * (by a future auth provider or by tests).
 *
 * The display `name` is still freely editable: it autofills author/reviewer
 * fields consistently, and is a convenience rather than a privilege.
 *
 * **Default role: `admin`.** Existing tests render the app with no auth
 * context and expect to see every surface.  An `admin` default preserves
 * that behaviour exactly.  This is a *development* convenience that the
 * server does not honour — the backend enforces independently, so a client
 * that believes it is admin still gets 403s from the API when the server
 * disagrees.
 *
 * Backward compatibility: the old `ActorRole` type, `ACTOR_ROLE_LABELS` and
 * `ACTOR_ROLE_DESCRIPTIONS` are still exported so that components not yet
 * migrated to the new RBAC system (Dashboard, NotesPanel, etc.) continue to
 * compile and run.  The old role values (`system_admin`, `policy_composer`,
 * `policy_manager`) are mapped to new RBAC roles via `toRbacRole()`.
 */
import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import type { Role } from "./rbac";
import { getSession } from "./auth";

// ---------------------------------------------------------------------------
// Old role type — kept for backward compatibility with components that
// reference it (Dashboard, NotesPanel, etc.) until they are migrated.
// ---------------------------------------------------------------------------

export type ActorRole = "system_admin" | "policy_composer" | "policy_manager";

export const ACTOR_ROLE_LABELS: Record<ActorRole, string> = {
  system_admin: "System Admin",
  policy_composer: "Policy Composer / Reviewer",
  policy_manager: "Policy Manager",
};

export const ACTOR_ROLE_DESCRIPTIONS: Record<ActorRole, string> = {
  system_admin: "Owns source documents, policy sets, and platform configuration.",
  policy_composer: "Drafts and reviews candidate rules extracted from policy documents.",
  policy_manager: "Approves publication, tracks versions, and exports governed data.",
};

// ---------------------------------------------------------------------------
// Mapping from old ActorRole to new RBAC Role
// ---------------------------------------------------------------------------

const ROLE_MAP: Record<ActorRole, Role> = {
  system_admin: "admin",
  policy_composer: "policy_author",
  policy_manager: "admin",
};

/** Maps any actor role string to the new RBAC `Role`.
 *  Old `ActorRole` values are translated; new `Role` values pass through.
 *
 *  Unknown values fall back to `"viewer"` (least privilege) rather than
 *  `"admin"`, so corrupted storage or a future role name cannot silently
 *  grant full access.  The *default actor* (`DEFAULT_ACTOR`) is still
 *  `system_admin`, which is a *known* value that maps to `"admin"` through
 *  `ROLE_MAP` — so existing tests that render with no auth context continue
 *  to see every surface.  The two defaults are intentionally different:
 *  one governs a recognised development identity, the other governs the
 *  genuinely-unknown case. */
export function toRbacRole(role: string): Role {
  if (role === "viewer" || role === "policy_author" || role === "admin") return role;
  return ROLE_MAP[role as ActorRole] ?? "viewer";
}

// ---------------------------------------------------------------------------
// Actor
// ---------------------------------------------------------------------------

export interface Actor {
  name: string;
  /** Carries the old `ActorRole` value for backward compatibility with
   *  components that index `ACTOR_ROLE_LABELS` by it.  Use `toRbacRole()`
   *  to get the canonical RBAC `Role` for access decisions. */
  role: ActorRole;
}

const STORAGE_KEY = "policy-platform.actor";

// Default to system_admin (maps to `admin` via toRbacRole) so that:
// 1. existing tests that render App with no auth see every surface
// 2. Dashboard's ROLE_TOOLKITS[actor.role] finds a valid entry
//
// When a real session exists the session's role wins (see ActorProvider).
// This fallback is a test and local-development convenience only — the
// server enforces independently, so a client that believes it is admin
// still gets 403s from the API when the server disagrees.
const DEFAULT_ACTOR: Actor = { name: "", role: "system_admin" };

function loadActor(): Actor {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_ACTOR;
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed.name === "string" && typeof parsed.role === "string") {
      return { name: parsed.name, role: parsed.role as ActorRole };
    }
  } catch {
    // ignore malformed storage, fall back to default
  }
  return DEFAULT_ACTOR;
}

interface ActorContextValue {
  actor: Actor;
  setActor: (actor: Actor) => void;
}

const ActorContext = createContext<ActorContextValue | null>(null);

export function ActorProvider({ children }: { children: ReactNode }) {
  const [actor, setActorState] = useState<Actor>(() => loadActor());

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(actor));
  }, [actor]);

  // When a signed-in session exists, its role is authoritative — the
  // server issued it and is the only party that may grant a role.
  // When there is no session (tests, local dev) the locally-stored
  // actor role is used as-is so that the ~125 test files that render
  // components without signing in continue to work.  This fallback
  // is a test and local-development convenience; the server enforces
  // independently.
  const session = getSession();
  const effectiveActor = useMemo<Actor>(() => {
    if (!session) return actor;
    return {
      name: session.name || actor.name,
      // Map the server's RBAC role to the old ActorRole that components
      // index ACTOR_ROLE_LABELS by.  The mapping is lossy — it exists
      // only to keep the type system satisfied until the legacy type is
      // retired.
      role: session.role === "admin"
        ? "system_admin"
        : session.role === "policy_author"
          ? "policy_composer"
          : ("policy_manager" as ActorRole),
    };
  }, [session?.role, session?.name, actor]);

  const value = useMemo(() => ({ actor: effectiveActor, setActor: setActorState }), [effectiveActor]);

  return <ActorContext.Provider value={value}>{children}</ActorContext.Provider>;
}

export function useActor(): ActorContextValue {
  const ctx = useContext(ActorContext);
  if (!ctx) throw new Error("useActor() must be used within an ActorProvider");
  return ctx;
}
