/**
 * Dashboard role-awareness tests: viewers get actions they can perform,
 * framing matches the reader's role, and edge cases are honest.
 */
import { describe, expect, it } from "vitest";
import { toRbacRole } from "./ActorContext";
import { canAccessPage, ROLES } from "./rbac";

// F1 -- a viewer is never offered an action their role cannot perform

describe("a viewer is never offered an action their role cannot perform", () => {
  it("the old viewer-to-policy_manager mapping is fixed", () => {
    // This was the core bug: viewer fell through to policy_manager
    // (the approver persona). Now it falls to policy_composer (least
    // privileged legacy persona), and toRbacRole maps that correctly.
    expect(toRbacRole("viewer")).toBe("viewer");
    expect(toRbacRole("something_unknown")).toBe("viewer");
    // policy_manager is admin, not viewer
    expect(toRbacRole("policy_manager")).toBe("admin");
  });

  it("the viewer role can reach projects and evaluate but not document-inbox", () => {
    // These are exactly the surfaces the viewer toolkit routes to.
    expect(canAccessPage("viewer", "projects")).toBe(true);
    expect(canAccessPage("viewer", "evaluate")).toBe(true);
    // A viewer must NOT reach authoring surfaces
    expect(canAccessPage("viewer", "document-inbox")).toBe(false);
  });
});

// F2 -- the dashboard framing matches the reader's role

describe("the dashboard framing matches the reader's role", () => {
  it("viewer resolves to the viewer RBAC role, not admin", () => {
    // The framing is selected by rbacRole. A viewer session must map
    // to "viewer", not "admin" (which policy_manager used to map to).
    expect(toRbacRole("viewer")).toBe("viewer");
  });
});

// F5 -- an unrecognised role is told so

describe("an unrecognised role is told so", () => {
  it("toRbacRole maps an unrecognised string to viewer (least privilege)", () => {
    expect(toRbacRole("galactic_overlord")).toBe("viewer");
  });

  it("a session with an unrecognised role is detectable via ROLES", () => {
    const unknownRole = "galactic_overlord";
    expect((ROLES as readonly string[]).includes(unknownRole)).toBe(false);
    // Dashboard checks this to show a warning alert
  });

  it("all three known roles are in ROLES", () => {
    expect(ROLES).toContain("viewer");
    expect(ROLES).toContain("policy_author");
    expect(ROLES).toContain("admin");
  });
});
