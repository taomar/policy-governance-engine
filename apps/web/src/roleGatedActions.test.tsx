/** Write actions must be *absent* for a viewer, not merely declared read-only.
 *
 * `rbac.test.ts` already asserts the surface map thoroughly — 23 passing
 * assertions covering `visible`, `readOnly` and `blockedReason` for every role
 * and surface. Every one of them passed while a signed-in viewer was shown
 * working "Edit", "Mark Reviewed", "New project", "Upload" and "Extract with
 * AI" controls, each calling a route the server classifies AUTHOR and answers
 * with 403.
 *
 * The reason is worth stating plainly, because it is the same shape as the
 * login-response bug found in this session: those tests assert what the map
 * *declares*, and nothing asserted what components *do* with it. `readOnly` had
 * two consumers in the entire app and both only rendered explanatory text — so
 * the Documents tab printed "Source documents are uploaded by a Policy Author"
 * directly above a live dropzone. A declaration no component consumes is not a
 * restriction.
 *
 * These tests therefore avoid two tempting shortcuts:
 *
 *  - They do not assert on `surfaceAccess`, because asserting the declaration
 *    is what missed the defect.
 *  - They do not mock `ActorContext`. An existing test in this suite reasons
 *    that "the button lives deep inside PoliciesTab which requires extensive
 *    mocking" and checks `toRbacRole` instead; that is a pure-function test
 *    wearing a role test's name. Here the *real* provider runs, fed by a real
 *    stored session, so the session-role path this session had to repair is
 *    covered end to end.
 */
import { describe, expect, it, beforeEach, afterEach, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { canAuthor, type Role } from "./rbac";

describe("canAuthor mirrors the server's AUTHOR band", () => {
  it("admits exactly the two roles the server admits", () => {
    expect(canAuthor("policy_author")).toBe(true);
    expect(canAuthor("admin")).toBe(true);
  });

  it("refuses a viewer", () => {
    expect(canAuthor("viewer")).toBe(false);
  });

  it("refuses an unknown or absent role, closed by default", () => {
    expect(canAuthor(undefined)).toBe(false);
    expect(canAuthor("")).toBe(false);
    expect(canAuthor("mysterious_outsider")).toBe(false);
  });

  it("refuses the legacy persona vocabulary", () => {
    // `ActorRole` has no viewer member, so a viewer routed through it used to
    // arrive as "policy_composer". Those names are not roles; admitting one
    // here would reinstate exactly that privilege escalation.
    expect(canAuthor("policy_composer")).toBe(false);
    expect(canAuthor("system_admin")).toBe(false);
    expect(canAuthor("policy_manager")).toBe(false);
  });
});

/** Seed a real session, the way a real sign-in does.
 *
 *  Sessions live in `sessionStorage` (per tab, so a token does not outlive the
 *  window), while the legacy actor lives in `localStorage`. Seeding the wrong
 *  one silently yields no session at all and the provider falls back to the
 *  stored actor — which cannot represent a viewer.
 */
function signInAs(role: Role): void {
  const oneHourOut = new Date(Date.now() + 60 * 60 * 1000).toISOString();
  sessionStorage.setItem(
    "policy-platform.session",
    JSON.stringify({
      accessToken: "test-token",
      expiresAt: oneHourOut,
      role,
      name: role,
    }),
  );
}

describe("a signed-in viewer is offered no governed-content action", () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    vi.resetModules();
  });

  afterEach(() => {
    // This project has no global test setup file, so RTL's auto-cleanup is not
    // installed and rendered trees accumulate across tests in a file. Without
    // this the second render sees the first one's DOM and every query finds two
    // matches — which reads exactly like a role gate that did not apply.
    cleanup();
    localStorage.clear();
    sessionStorage.clear();
  });

  async function renderRegisterAs(role: Role) {
    signInAs(role);
    vi.doMock("./api", async () => {
      const actual = await vi.importActual<typeof import("./api")>("./api");
      return {
        ...actual,
        api: {
          ...actual.api,
          listPolicySets: vi.fn().mockResolvedValue([]),
          getProjectPortfolioSummary: vi.fn().mockResolvedValue([]),
          createPolicySet: vi.fn(),
        },
      };
    });
    const { ProjectsPage } = await import("./components/ProjectsPage");
    // Both must come from the *same* module graph. `vi.resetModules()` gives the
    // dynamic import a fresh ActorContext module, and a statically imported
    // provider would therefore be a different React context object — the page
    // would render inside a provider it cannot see.
    const { ActorProvider } = await import("./ActorContext");
    render(
      <ActorProvider>
        <ProjectsPage />
      </ActorProvider>,
    );
    await screen.findAllByText(/No projects yet\./i);
  }

  it("offers a viewer no way to create a project", async () => {
    await renderRegisterAs("viewer");
    const names = screen.queryAllByRole("button").map((b) => b.textContent);
    expect(names.filter((n) => /new project/i.test(n ?? ""))).toEqual([]);
    // 120s, not the 5s default: `vi.resetModules()` means the first render in
    // this block re-imports the whole page module graph. That costs seconds on
    // an idle worker and over a minute when the full suite runs in parallel on
    // a machine also hosting Postgres, the API and the dev server. The budget
    // bounds a hang, not a slow machine — a viewer who *is* offered the button
    // fails the assertion immediately and never reaches the clock.
  }, 120000);

  it("tells a viewer who can create one instead of leaving them stuck", async () => {
    await renderRegisterAs("viewer");
    // `findAll`, not `find`: antd's Empty renders its description into both the
    // visible node and a measurement copy, so the honest assertion is that the
    // sentence is present, not that it appears exactly once.
    const found = await screen.findAllByText(/A Policy Author creates projects/i);
    expect(found.length).toBeGreaterThan(0);
  }, 120000);

  it("still offers creation to a policy author", async () => {
    await renderRegisterAs("policy_author");
    await waitFor(() => {
      expect(screen.queryAllByRole("button", { name: /new project/i }).length).toBeGreaterThan(0);
    });
  }, 120000);
});
