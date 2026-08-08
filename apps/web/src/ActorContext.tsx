/**
 * Actor identity for the 3 human personas this platform is built around:
 *
 *  - system_admin     — owns documents, policy sets, and system configuration.
 *  - policy_composer   — drafts/reviews candidate rules extracted from source
 *                        documents (the "reviewer" role from a governance
 *                        point of view).
 *  - policy_manager    — approves publication, tracks version history,
 *                        exports data, and answers "is this compliant" asks.
 *
 * This is a lightweight, localStorage-persisted "who am I acting as right
 * now" identity — not an authentication system. Its purpose is purely to
 * autofill author/reviewer/approver fields consistently and drive the
 * role-appropriate toolset on the Dashboard. It is NOT purely cosmetic,
 * though: the backend now enforces `policy_manager`-only authority on the
 * manager-override endpoints (request-changes, override). Sending the
 * wrong `actor_role` to those endpoints will be rejected with a 403 — this
 * is a real (if lightweight, local-trust) authorization boundary, not just
 * a UI label.
 */
import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

export type ActorRole = "system_admin" | "policy_composer" | "policy_manager";

export interface Actor {
  name: string;
  role: ActorRole;
}

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

const STORAGE_KEY = "policy-platform.actor";

const DEFAULT_ACTOR: Actor = { name: "", role: "policy_composer" };

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

  const value = useMemo(() => ({ actor, setActor: setActorState }), [actor]);

  return <ActorContext.Provider value={value}>{children}</ActorContext.Provider>;
}

export function useActor(): ActorContextValue {
  const ctx = useContext(ActorContext);
  if (!ctx) throw new Error("useActor() must be used within an ActorProvider");
  return ctx;
}
