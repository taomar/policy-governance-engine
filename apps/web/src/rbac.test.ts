import { describe, expect, it } from "vitest";
import {
  canAccessPage,
  canAccessTab,
  ROLES,
  ROLE_LABELS,
  ROLE_DESCRIPTIONS,
  surfaceAccess,
} from "./rbac";
import { toRbacRole } from "./ActorContext";

// ---------------------------------------------------------------------------
// The nav ids and tab keys the platform declares. Kept here as plain arrays
// so the tests fail when a surface is added to the product but not to the
// access map — without importing the runtime constants, which would couple
// the test to the component tree.
// ---------------------------------------------------------------------------

const ALL_NAV_IDS = ["dashboard", "projects", "document-inbox", "evaluate", "my-attestations"];
const ALL_TAB_KEYS = [
  "overview", "documents", "review", "policies", "compare",
  "quality", "correlation", "tests", "case-runner", "exceptions",
  "attestations", "decision-log",
];

describe("role-based access control surface map", () => {
  // -----------------------------------------------------------------------
  // Completeness: every role resolves every surface to an explicit decision
  // -----------------------------------------------------------------------

  it("every role resolves every nav id to a definite access decision", () => {
    for (const role of ROLES) {
      for (const id of ALL_NAV_IDS) {
        const access = surfaceAccess(role, id);
        expect(access, `${role} / ${id}`).toHaveProperty("visible");
        expect(access, `${role} / ${id}`).toHaveProperty("readOnly");
        expect(access, `${role} / ${id}`).toHaveProperty("blockedReason");
      }
    }
  });

  it("every role resolves every tab key to a definite access decision", () => {
    for (const role of ROLES) {
      for (const key of ALL_TAB_KEYS) {
        const access = surfaceAccess(role, key);
        expect(access, `${role} / ${key}`).toHaveProperty("visible");
        expect(access, `${role} / ${key}`).toHaveProperty("readOnly");
        expect(access, `${role} / ${key}`).toHaveProperty("blockedReason");
      }
    }
  });

  it("has a label and description for every role", () => {
    for (const role of ROLES) {
      expect(ROLE_LABELS[role]).toBeTruthy();
      expect(ROLE_DESCRIPTIONS[role]).toBeTruthy();
    }
  });

  // -----------------------------------------------------------------------
  // Default-closed: unknown roles get no access (the UNKNOWN_STATUS doctrine)
  // -----------------------------------------------------------------------

  it("an unknown role gets no access to any surface", () => {
    for (const id of [...ALL_NAV_IDS, ...ALL_TAB_KEYS]) {
      const access = surfaceAccess("mysterious_outsider", id);
      expect(access.visible, `unknown role should not see ${id}`).toBe(false);
      expect(access.readOnly, `unknown role should be read-only for ${id}`).toBe(true);
      expect(access.blockedReason, `unknown role should have a reason for ${id}`).toBeTruthy();
    }
  });

  it("an undefined role gets no access to any surface", () => {
    for (const id of [...ALL_NAV_IDS, ...ALL_TAB_KEYS]) {
      const access = surfaceAccess(undefined, id);
      expect(access.visible).toBe(false);
    }
  });

  // -----------------------------------------------------------------------
  // Fix #1: unrecognised role resolves to least privilege, not most
  // -----------------------------------------------------------------------

  it("an unrecognised role resolves to the least privilege, not the most", () => {
    const rbacRole = toRbacRole("corrupted_garbage_value");
    expect(rbacRole).toBe("viewer");
  });

  it("a known old role still maps to its expected RBAC role", () => {
    expect(toRbacRole("system_admin")).toBe("admin");
    expect(toRbacRole("policy_composer")).toBe("policy_author");
    expect(toRbacRole("policy_manager")).toBe("admin");
  });

  it("new RBAC role values pass through toRbacRole unchanged", () => {
    expect(toRbacRole("viewer")).toBe("viewer");
    expect(toRbacRole("policy_author")).toBe("policy_author");
    expect(toRbacRole("admin")).toBe("admin");
  });

  // -----------------------------------------------------------------------
  // Viewer restrictions
  // -----------------------------------------------------------------------

  it("a viewer cannot access document-inbox", () => {
    expect(canAccessPage("viewer", "document-inbox")).toBe(false);
  });

  it("a viewer cannot access the review tab", () => {
    expect(canAccessTab("viewer", "review")).toBe(false);
  });

  // -----------------------------------------------------------------------
  // Fix #2: a viewer can reach documents (read-only) but not quality or tests
  // -----------------------------------------------------------------------

  it("a viewer can reach documents but not quality or tests", () => {
    const docs = surfaceAccess("viewer", "documents");
    expect(docs.visible).toBe(true);
    expect(docs.readOnly).toBe(true);

    expect(canAccessTab("viewer", "quality")).toBe(false);
    expect(canAccessTab("viewer", "tests")).toBe(false);
  });

  // -----------------------------------------------------------------------
  // Viewer grants: evaluate and case-runner are explicitly allowed
  // -----------------------------------------------------------------------

  it("a viewer keeps evaluate — the product owner's explicit grant", () => {
    expect(canAccessPage("viewer", "evaluate")).toBe(true);
    const access = surfaceAccess("viewer", "evaluate");
    expect(access.readOnly).toBe(false);
    expect(access.blockedReason).toBeNull();
  });

  it("a viewer keeps case-runner — the product owner's explicit grant", () => {
    expect(canAccessTab("viewer", "case-runner")).toBe(true);
    const access = surfaceAccess("viewer", "case-runner");
    expect(access.readOnly).toBe(false);
    expect(access.blockedReason).toBeNull();
  });

  // -----------------------------------------------------------------------
  // Fix #4: inherently read-only surfaces carry no blocked reason
  // -----------------------------------------------------------------------

  it("inherently read-only surfaces carry no blocked reason for a viewer", () => {
    for (const id of ["dashboard", "projects", "compare", "decision-log"]) {
      const access = surfaceAccess("viewer", id);
      expect(access.visible, `viewer should see ${id}`).toBe(true);
      expect(access.readOnly, `${id} should not be marked readOnly for viewer`).toBe(false);
      expect(access.blockedReason, `${id} should have no blockedReason for viewer`).toBeNull();
    }
  });

  // -----------------------------------------------------------------------
  // Fix #5: read-only surfaces carry per-surface copy
  // -----------------------------------------------------------------------

  it("read-only surfaces for a viewer carry specific per-surface reasons", () => {
    const overview = surfaceAccess("viewer", "overview");
    expect(overview.readOnly).toBe(true);
    expect(overview.blockedReason).toContain("Policy Author");

    const policies = surfaceAccess("viewer", "policies");
    expect(policies.readOnly).toBe(true);
    expect(policies.blockedReason).toContain("read-only for everyone");

    const documents = surfaceAccess("viewer", "documents");
    expect(documents.readOnly).toBe(true);
    expect(documents.blockedReason).toContain("uploaded by a Policy Author");
  });

  // -----------------------------------------------------------------------
  // Already-hidden surfaces stay hidden for every role, including admin
  // -----------------------------------------------------------------------

  const ALWAYS_HIDDEN_NAV = ["my-attestations"];
  const ALWAYS_HIDDEN_TABS = ["attestations", "correlation", "exceptions"];

  for (const id of ALWAYS_HIDDEN_NAV) {
    it(`${id} stays hidden for every role including admin`, () => {
      for (const role of ROLES) {
        expect(canAccessPage(role, id), `${role} should not see ${id}`).toBe(false);
      }
    });
  }

  for (const key of ALWAYS_HIDDEN_TABS) {
    it(`${key} tab stays hidden for every role including admin`, () => {
      for (const role of ROLES) {
        expect(canAccessTab(role, key), `${role} should not see ${key}`).toBe(false);
      }
    });
  }

  // -----------------------------------------------------------------------
  // Read-only surfaces carry a reason explaining what the user can do
  // -----------------------------------------------------------------------

  it("a full-access surface has no blocked reason", () => {
    const access = surfaceAccess("admin", "dashboard");
    expect(access.readOnly).toBe(false);
    expect(access.blockedReason).toBeNull();
  });
});
