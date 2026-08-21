/** Role-based access control surface map — the client mirror.
 *
 * This mirrors the server's role enforcement, which is the authority: the
 * backend rejects a forbidden request with 403 regardless of what the UI
 * allows.  The client copy exists only so the interface can *explain* the
 * rule before the user runs into it.
 *
 * Naming: the product owner said "policy reviewer", but `review` already
 * means *approve/reject an extracted candidate rule* in this codebase — there
 * is a `review` workspace tab and a `ReviewQueue` component — so
 * `policy_author` is used to avoid the collision.
 *
 * An unknown or undefined role defaults to **no access**, following the same
 * doctrine as `UNKNOWN_STATUS` in `candidateEditability.ts`: closed by
 * default, with a plain-language reason phrased as the next action the user
 * can take.
 */

// ---------------------------------------------------------------------------
// Roles
// ---------------------------------------------------------------------------

export type Role = "viewer" | "policy_author" | "admin";

export const ROLES: readonly Role[] = ["viewer", "policy_author", "admin"] as const;

export const ROLE_LABELS: Record<Role, string> = {
  viewer: "Viewer",
  policy_author: "Policy Author",
  admin: "Admin",
};

export const ROLE_DESCRIPTIONS: Record<Role, string> = {
  viewer: "Can evaluate policies and view project data. Cannot author, upload documents, or review candidates.",
  policy_author: "Drafts, reviews and publishes policy rules. Full access to authoring surfaces.",
  admin: "Unrestricted access to every surface.",
};

// ---------------------------------------------------------------------------
// Surface access
// ---------------------------------------------------------------------------

/** The three things the UI needs to know about a surface for a given role. */
export interface SurfaceAccess {
  /** Whether the nav item or tab should appear at all. */
  visible: boolean;
  /** Whether the surface is present but interactions are disabled. */
  readOnly: boolean;
  /** Why access is limited, phrased as the next action the user can take.
   *  `null` when full access is granted. */
  blockedReason: string | null;
}

const FULL: SurfaceAccess = { visible: true, readOnly: false, blockedReason: null };

function readOnly(reason: string): SurfaceAccess {
  return { visible: true, readOnly: true, blockedReason: reason };
}

const HIDDEN: SurfaceAccess = { visible: false, readOnly: true, blockedReason: "This surface is not available to your role." };

const UNKNOWN: SurfaceAccess = {
  visible: false,
  readOnly: true,
  blockedReason: "Your role is not recognised by this build. Sign in again or contact an administrator.",
};

// ---------------------------------------------------------------------------
// Per-role surface maps
// ---------------------------------------------------------------------------

// Nav ids from App.tsx NAV_ITEMS.
type NavId = "dashboard" | "projects" | "document-inbox" | "evaluate" | "my-attestations";

// Tab keys from ProjectWorkspace.tsx TAB_META.
type TabKey =
  | "overview" | "documents" | "review" | "policies" | "compare"
  | "quality" | "correlation" | "tests" | "exceptions" | "attestations"
  | "case-runner" | "decision-log";

type SurfaceId = NavId | TabKey;

/** The complete surface map for a role. Every nav id and tab key must appear. */
type SurfaceMap = Record<SurfaceId, SurfaceAccess>;

const VIEWER_MAP: SurfaceMap = {
  // Nav — dashboard and projects are inherently read-only surfaces; no write
  // actions exist in them, so FULL avoids inventing a restriction that isn't real.
  dashboard:        FULL,
  projects:         FULL,
  "document-inbox": HIDDEN,
  evaluate:         FULL,
  "my-attestations": HIDDEN,
  // Tabs
  overview:      readOnly("Project settings are managed by a Policy Author. You can view the project's status and history here."),
  documents:     readOnly("Source documents are uploaded by a Policy Author. You can read them and see how rules were extracted."),
  review:        HIDDEN,
  policies:      readOnly("Published policies are read-only for everyone. To propose a change, ask a Policy Author to start a revision."),
  compare:       FULL,
  quality:       HIDDEN,
  correlation:   HIDDEN,
  tests:         HIDDEN,
  "case-runner":  FULL,
  exceptions:    HIDDEN,
  attestations:  HIDDEN,
  "decision-log": FULL,
};

const AUTHOR_MAP: SurfaceMap = {
  dashboard:        FULL,
  projects:         FULL,
  "document-inbox": FULL,
  evaluate:         FULL,
  "my-attestations": HIDDEN,
  overview:      FULL,
  documents:     FULL,
  review:        FULL,
  policies:      FULL,
  compare:       FULL,
  quality:       FULL,
  // Already hidden for everyone via HIDDEN_TAB_KEYS — mirrored here so
  // the rbac map is a complete surface map and no role can override the
  // phase gate.
  correlation:   HIDDEN,
  tests:         FULL,
  "case-runner":  FULL,
  exceptions:    HIDDEN,
  attestations:  HIDDEN,
  "decision-log": FULL,
};

const ADMIN_MAP: SurfaceMap = {
  dashboard:        FULL,
  projects:         FULL,
  "document-inbox": FULL,
  evaluate:         FULL,
  "my-attestations": HIDDEN,
  overview:      FULL,
  documents:     FULL,
  review:        FULL,
  policies:      FULL,
  compare:       FULL,
  quality:       FULL,
  correlation:   HIDDEN,
  tests:         FULL,
  "case-runner":  FULL,
  exceptions:    HIDDEN,
  attestations:  HIDDEN,
  "decision-log": FULL,
};

const ROLE_SURFACE_MAPS: Record<Role, SurfaceMap> = {
  viewer: VIEWER_MAP,
  policy_author: AUTHOR_MAP,
  admin: ADMIN_MAP,
};

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/** Full access descriptor for a surface under a given role.
 *  Unknown roles get the closed default — no access, with a reason. */
export function surfaceAccess(role: string | undefined, id: string): SurfaceAccess {
  const map = ROLE_SURFACE_MAPS[role as Role];
  if (!map) return UNKNOWN;
  return map[id as SurfaceId] ?? UNKNOWN;
}

/** Whether a top-level nav page should be shown for this role. */
export function canAccessPage(role: string | undefined, pageId: string): boolean {
  return surfaceAccess(role, pageId).visible;
}

/** Whether a workspace tab should be shown for this role. */
export function canAccessTab(role: string | undefined, tabKey: string): boolean {
  return surfaceAccess(role, tabKey).visible;
}
