/** THE KEY IS THE PUBLIC NAME; EVERYTHING ELSE IS NOT.
 *
 * This drawer exists because two identifiers look interchangeable on a screen
 * and are not. The project **key** is what goes in a URL. The project **UUID**
 * is trace identity, useful in a support conversation and wrong in a path. The
 * **name** is for humans and may be rewritten tomorrow. A drawer whose job is
 * "send this to your integrator" fails the moment a reader copies the wrong one,
 * so the marking of each is asserted here rather than left to the layout.
 *
 * The second thing asserted is an absence. No snippet, and no node the drawer
 * renders, may contain the signed-in session token. A real session is seeded
 * before every render so the assertion has something to find if the feature
 * ever grows a "use my token" convenience.
 *
 * The button is checked where it lives, in the workspace action bar, and beside
 * the control it is a sibling of — `Test a Case`, which this feature does not
 * change. `ProjectCaseRunner.test.tsx` continues to assert that surface's own
 * behaviour and is untouched.
 */

import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { ActorProvider } from "../ActorContext";
import { api, CONFIGURED_API_BASE_URL, type ApprovedPolicyVersion, type PolicySet } from "../api";
import { ConsumeProjectDrawer } from "./ConsumeProjectDrawer";
import { ProjectWorkspace } from "./ProjectWorkspace";

vi.mock("./ProjectOverviewTab", () => ({ ProjectOverviewTab: () => <div>Overview tab</div> }));
vi.mock("./DocumentsPage", () => ({ DocumentsPage: () => <div>Documents tab</div> }));
vi.mock("./PoliciesTab", () => ({ PoliciesTab: () => <div>Policies tab</div> }));
vi.mock("./ReviewQueue", () => ({ ReviewQueue: () => <div>Review tab</div> }));
vi.mock("./ComparePage", () => ({ ComparePage: () => <div>Compare tab</div> }));
vi.mock("./QualityPage", () => ({ QualityPage: () => <div>Quality tab</div> }));
vi.mock("./CorrelationPage", () => ({ CorrelationPage: () => <div>Correlation tab</div> }));
vi.mock("./PolicyValidationLab", () => ({ PolicyValidationLab: () => <div>Validation tab</div> }));
vi.mock("./PolicyExceptionsPage", () => ({ PolicyExceptionsPage: () => <div>Exceptions tab</div> }));
vi.mock("./PolicyAttestationsPage", () => ({ PolicyAttestationsPage: () => <div>Attestations tab</div> }));
vi.mock("./DecisionLogPage", () => ({ DecisionLogPage: () => <div>Decision tab</div> }));

const PROJECT_UUID = "7c9e6679-7425-40de-944b-e07fc1f90ae7";
const VERSION_UUID = "5f2c1a4e-9b31-4d77-8f0a-2c6b1e93ab42";
const SESSION_TOKEN = "eyJhbGciOiJIUzI1NiJ9.a-real-looking-session-token.signature";

beforeAll(() => {
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  );
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  );
});

function policySet(): PolicySet {
  return {
    id: PROJECT_UUID,
    key: "ACME-HR-2024",
    name: "Acme HR policy",
    owner: "owner",
    description: "",
    category: "",
    tags: [],
    review_due_date: null,
    last_reviewed_at: null,
    is_review_overdue: false,
    accountable_owner: "",
    delegate_approver: "",
    escalation_contact: "",
    consulted_parties: [],
    informed_parties: [],
  };
}

function activeVersion(): ApprovedPolicyVersion {
  return {
    id: VERSION_UUID,
    policy_set_id: PROJECT_UUID,
    version_number: 7,
    effective_from: "2026-01-01",
    effective_to: null,
    is_active: true,
    approved_by: "approver",
    approved_at: "2026-01-01T00:00:00Z",
    rule_count: 12,
  };
}

/** Seed a session the way a real sign-in does, so a leak has something to leak. */
function signIn(role: string): void {
  sessionStorage.setItem(
    "policy-platform.session",
    JSON.stringify({
      accessToken: SESSION_TOKEN,
      expiresAt: new Date(Date.now() + 3_600_000).toISOString(),
      role,
      name: role,
    }),
  );
}

/** Clipboard writes resolve unless a test asks otherwise. */
function stubClipboard(behaviour: "resolve" | "reject" = "resolve") {
  const writeText = vi
    .fn()
    .mockImplementation(() => (behaviour === "resolve" ? Promise.resolve() : Promise.reject(new Error("blocked"))));
  vi.stubGlobal("navigator", Object.assign(Object.create(Object.getPrototypeOf(navigator)), navigator, {
    clipboard: { writeText },
  }));
  return writeText;
}

async function openDrawer(version: ApprovedPolicyVersion | null = activeVersion()) {
  vi.spyOn(api, "getActiveVersion").mockResolvedValue(version);
  render(
    <ActorProvider>
      <ConsumeProjectDrawer policySet={policySet()} open onClose={() => {}} />
    </ActorProvider>,
  );
  await screen.findByTestId("consume-key-value");
}

beforeEach(() => {
  sessionStorage.clear();
  localStorage.clear();
  signIn("policy_author");
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  sessionStorage.clear();
  localStorage.clear();
});

// ---------------------------------------------------------------------------

describe("the workspace offers the drawer beside Test a Case", () => {
  function renderWorkspace() {
    vi.spyOn(api, "getWorkspaceCounts").mockResolvedValue({
      documents: 0,
      review_pending: 0,
      policy_rules: 0,
      versions: 0,
      tests: 0,
      regression_tests: 0,
      exceptions_open: 0,
      correlation_findings: 0,
      decisions: 0,
    });
    vi.spyOn(api, "getActiveVersion").mockResolvedValue(activeVersion());
    render(
      <ActorProvider>
        <ProjectWorkspace policySet={policySet()} />
      </ActorProvider>,
    );
  }

  it("places the button immediately after Test a Case in the action bar", () => {
    renderWorkspace();
    const button = screen.getByTestId("consume-open");
    const bar = button.closest(".ws-bar__actions");
    expect(bar).not.toBeNull();
    const previous = button.previousElementSibling;
    expect(previous?.textContent).toBe("Test a Case");
  });

  it("names the action and the actor, on screen and to assistive technology", () => {
    renderWorkspace();
    const button = screen.getByTestId("consume-open");
    expect(button.textContent).toBe("Call from your app");
    expect(button.getAttribute("aria-label")).toBe(
      "Show how to call Acme HR policy published policies from your own application",
    );
  });

  it("keeps the label in a node the bar can drop before it wraps", () => {
    // The header is a fixed single row. At a narrow width the label is hidden
    // and the icon remains, which is only honest because the accessible name
    // lives on the button rather than in the text.
    renderWorkspace();
    const label = screen.getByTestId("consume-open").querySelector(".ws-bar__action-label");
    expect(label?.textContent).toBe("Call from your app");
  });

  it("opens the drawer, and returns focus to the button when it closes", async () => {
    renderWorkspace();
    const button = screen.getByTestId("consume-open");
    fireEvent.click(button);

    const title = await screen.findByTestId("consume-drawer-title");
    await waitFor(() => expect(document.activeElement).toBe(title));

    fireEvent.keyDown(title, { key: "Escape", code: "Escape", keyCode: 27 });
    await waitFor(() => expect(document.activeElement).toBe(button));
  });

  it("withholds the button entirely from a role that may not put a case", async () => {
    // Absence, not a disabled control: an affordance for a capability the actor
    // does not have is noise in a header that may not wrap.
    signIn("mysterious_outsider");
    renderWorkspace();
    await waitFor(() => expect(screen.queryByTestId("consume-open")).toBeNull());
    expect(screen.queryByRole("button", { name: /test a case/i })).toBeNull();
  });
});

// ---------------------------------------------------------------------------

describe("the identity register says what each string is for", () => {
  it("marks the key as the thing that goes in a path", async () => {
    await openDrawer();
    expect(screen.getByTestId("consume-key-value").textContent).toBe("ACME-HR-2024");
    expect(screen.getByTestId("consume-key-marker").textContent).toBe("Use this in API paths");
  });

  it("marks the UUID as trace identity and not a URL segment", async () => {
    await openDrawer();
    expect(screen.getByTestId("consume-uuid-value").textContent).toBe(PROJECT_UUID);
    expect(screen.getByTestId("consume-uuid-marker").textContent).toBe("Trace identity — not a URL segment");
  });

  it("marks the name display-only and offers no way to copy it", async () => {
    await openDrawer();
    const row = screen.getByTestId("consume-row-name");
    expect(screen.getByTestId("consume-name-marker").textContent).toBe("Display only");
    expect(within(row).queryAllByRole("button")).toEqual([]);
  });

  it("shows the active version as a number and an id", async () => {
    await openDrawer();
    await waitFor(() => expect(screen.getByTestId("consume-version-value").textContent).toMatch(/^v\d+ · [0-9a-f-]{36}$/));
  });

  it("says it is still resolving rather than implying there is no version", async () => {
    let resolve: (v: ApprovedPolicyVersion | null) => void = () => {};
    vi.spyOn(api, "getActiveVersion").mockReturnValue(
      new Promise<ApprovedPolicyVersion | null>((r) => {
        resolve = r;
      }),
    );
    render(
      <ActorProvider>
        <ConsumeProjectDrawer policySet={policySet()} open onClose={() => {}} />
      </ActorProvider>,
    );
    expect(await screen.findByTestId("consume-version-loading")).toBeTruthy();
    expect(screen.queryByTestId("consume-no-version")).toBeNull();
    resolve(activeVersion());
    await waitFor(() => expect(screen.queryByTestId("consume-version-loading")).toBeNull());
  });

  it("annotates an unpublished project without withdrawing the examples", async () => {
    await openDrawer(null);
    expect(await screen.findByTestId("consume-no-version")).toBeTruthy();
    for (const id of ["curl", "python", "http"]) {
      expect(screen.getByTestId(`consume-snippet-${id}`).textContent).toContain("policy-decisions");
      expect(screen.getByTestId(`consume-annotation-${id}`).textContent).toBe(
        "This request is correct, but it will return 409 until a version is published.",
      );
    }
  });

  it("says the version could not be read rather than pretending there is none", async () => {
    vi.spyOn(api, "getActiveVersion").mockRejectedValue(new Error("network down"));
    render(
      <ActorProvider>
        <ConsumeProjectDrawer policySet={policySet()} open onClose={() => {}} />
      </ActorProvider>,
    );
    expect(await screen.findByTestId("consume-version-error")).toBeTruthy();
    expect(screen.queryByTestId("consume-no-version")).toBeNull();
  });
});

// ---------------------------------------------------------------------------

describe("the drawer renders every section, and no credential", () => {
  it("keeps all five sections in the document", async () => {
    await openDrawer();
    for (const id of ["identity", "curl", "python", "http", "docs"]) {
      expect(screen.getByTestId(`consume-tab-${id}`)).toBeTruthy();
    }
    expect(screen.getAllByRole("tab").length).toBe(5);
  });

  it("puts no part of the signed-in token anywhere in the drawer", async () => {
    await openDrawer();
    expect(document.body.textContent).not.toContain(SESSION_TOKEN);
    expect(document.body.textContent).not.toContain("a-real-looking-session-token");
    for (const id of ["curl", "python", "http"]) {
      const text = screen.getByTestId(`consume-snippet-${id}`).textContent ?? "";
      expect(text).not.toContain(SESSION_TOKEN);
      expect(text).not.toContain("sessionStorage");
      expect(text).not.toContain("localStorage");
      expect(text).toContain("POLICY_SUBSCRIPTION_KEY");
    }
  });

  it("addresses the project by key in every example, never by UUID", async () => {
    await openDrawer();
    for (const id of ["curl", "python", "http"]) {
      const text = screen.getByTestId(`consume-snippet-${id}`).textContent ?? "";
      expect(text).not.toContain(PROJECT_UUID);
    }
    expect(screen.getByTestId("consume-snippet-curl").textContent).toContain(
      "/api/policy-decisions/ACME-HR-2024/case",
    );
    expect(screen.getByTestId("consume-snippet-http").textContent).toContain(
      "POST /api/policy-decisions/ACME-HR-2024/case",
    );
  });

  it("shows both halves of the round trip in the raw HTTP section", async () => {
    await openDrawer();
    expect(screen.getByTestId("consume-snippet-http").textContent).toContain("POST /api/policy-decisions");
    expect(screen.getByTestId("consume-snippet-http-receipt").textContent).toContain("GET /api/policy-decisions");
  });

  it("says the token never travels with a snippet, permanently", async () => {
    await openDrawer();
    expect(screen.getByTestId("consume-footer-note").textContent).toContain(
      "Snippets never contain your signed-in session token.",
    );
  });

  it("makes each code region reachable and nameable from the keyboard", async () => {
    await openDrawer();
    const block = screen.getByTestId("consume-snippet-python");
    expect(block.getAttribute("tabindex")).toBe("0");
    expect(block.getAttribute("aria-label")).toBe("Python example for project ACME-HR-2024");
  });

  it("exposes the sections as real tabs, each pointing at its own panel", async () => {
    await openDrawer();
    const tabs = screen.getAllByRole("tab");
    expect(tabs[0].getAttribute("aria-selected")).toBe("true");
    for (const tab of tabs) {
      expect(tab.getAttribute("aria-controls")).toBeTruthy();
    }
    // Roving tabindex: one stop in the tab order for the whole strip, which is
    // what makes the arrow keys the way between sections rather than Tab.
    expect(tabs.filter((tab) => tab.getAttribute("tabindex") !== "-1")).toHaveLength(1);

    fireEvent.click(screen.getByTestId("consume-tab-python"));
    await waitFor(() => expect(screen.getAllByRole("tab")[2].getAttribute("aria-selected")).toBe("true"));
    const panel = screen.getAllByRole("tabpanel").find((node) => node.getAttribute("aria-hidden") !== "true");
    expect(panel).toBeTruthy();
  });
});

// ---------------------------------------------------------------------------

/** The narrow-width behaviour is a stylesheet fact, and jsdom does no layout.
 *
 * A rendering test cannot see it, so the guard reads the stylesheet the way
 * `nothingIsClipped.test.ts` does: the header must be able to drop a label
 * rather than wrap, and a code region must wrap rather than scroll sideways —
 * both stated as container queries, because this app's stylesheet is guarded
 * against viewport media queries. */
describe("the narrow-width rules are in the stylesheet, not in a hope", () => {
  const sheets = import.meta.glob("../App.css", { query: "?raw", import: "default", eager: true }) as Record<
    string,
    string
  >;
  const css = Object.values(sheets)[0] ?? "";

  it("read the stylesheet it is judging", () => {
    expect(css.length).toBeGreaterThan(1000);
    expect(css).toContain(".ws-bar__actions");
  });

  it("makes the action bar a query container and lets the label go, not the button", () => {
    expect(css).toMatch(/\.ws-bar\s*\{[^}]*container-type:\s*inline-size/);
    expect(css).toMatch(/@container[^{]*\{\s*\.ws-bar__action-label\s*\{\s*display:\s*none/);
  });

  it("keeps the code region wrapping rather than scrolling sideways", () => {
    expect(css).toMatch(/\.json-line-text\s*\{[^}]*white-space:\s*pre-wrap/);
    expect(css).toMatch(/\.json-line-text\s*\{[^}]*overflow-wrap:\s*anywhere/);
  });
});

// ---------------------------------------------------------------------------

describe("the API base drives the examples and nothing else", () => {
  it("starts at the base this build was configured with", async () => {
    await openDrawer();
    expect((screen.getByTestId("consume-api-base") as HTMLInputElement).value).toBe(CONFIGURED_API_BASE_URL);
  });

  it("regenerates every example and every docs link when it is edited", async () => {
    await openDrawer();
    fireEvent.change(screen.getByTestId("consume-api-base"), { target: { value: "https://x.test" } });

    await waitFor(() =>
      expect(screen.getByTestId("consume-snippet-curl").textContent).toContain(
        "https://x.test/api/policy-decisions/ACME-HR-2024/case",
      ),
    );
    expect(screen.getByTestId("consume-snippet-python").textContent).toContain('BASE = "https://x.test"');
    expect(screen.getByTestId("consume-snippet-http").textContent).toContain("Host: x.test");
    expect(screen.getByTestId("consume-docs-swagger").getAttribute("href")).toBe("https://x.test/docs");
    // The app's own configuration is untouched: this is a preview, not a setting.
    expect(CONFIGURED_API_BASE_URL).not.toBe("https://x.test");
  });

  it("offers a way back to the configured base only once it has been left", async () => {
    await openDrawer();
    expect(screen.queryByTestId("consume-api-base-reset")).toBeNull();
    fireEvent.change(screen.getByTestId("consume-api-base"), { target: { value: "https://x.test" } });
    fireEvent.click(await screen.findByTestId("consume-api-base-reset"));
    await waitFor(() =>
      expect((screen.getByTestId("consume-api-base") as HTMLInputElement).value).toBe(CONFIGURED_API_BASE_URL),
    );
  });

  it("still shows the examples when the base is not a URL, and says so", async () => {
    await openDrawer();
    fireEvent.change(screen.getByTestId("consume-api-base"), { target: { value: "policy.internal" } });
    expect(await screen.findByTestId("consume-api-base-note")).toBeTruthy();
    expect(screen.getByTestId("consume-snippet-curl").textContent).toContain(
      "policy.internal/api/policy-decisions/ACME-HR-2024/case",
    );
    // A documentation link that resolved against this app's origin would point
    // at the wrong server without saying so, so it stops being a link.
    expect(screen.getByTestId("consume-docs-swagger").getAttribute("href")).toBeNull();
    expect(screen.getByTestId("consume-docs-swagger").getAttribute("aria-disabled")).toBe("true");
  });

  it("opens the API's own documentation in a new tab, safely", async () => {
    await openDrawer();
    for (const [id, suffix] of [
      ["swagger", "/docs"],
      ["redoc", "/redoc"],
      ["openapi", "/openapi.json"],
    ] as const) {
      const link = screen.getByTestId(`consume-docs-${id}`);
      expect(link.getAttribute("href")).toBe(`${CONFIGURED_API_BASE_URL}${suffix}`);
      expect(link.getAttribute("target")).toBe("_blank");
      expect(link.getAttribute("rel")).toBe("noopener noreferrer");
    }
  });

  it("claims no SDK or native connector", async () => {
    await openDrawer();
    const text = (document.body.textContent ?? "").toLowerCase();
    expect(text).toContain("no client sdk and no native connector");
  });
});

// ---------------------------------------------------------------------------

describe("copying says what happened", () => {
  it("writes the visible snippet, reports it, and reverts", async () => {
    const writeText = stubClipboard("resolve");
    await openDrawer();
    fireEvent.click(screen.getByTestId("consume-copy-curl"));

    await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
    expect(writeText.mock.calls[0][0]).toContain("/api/policy-decisions/ACME-HR-2024/case");
    const button = screen.getByTestId("consume-copy-curl");
    await waitFor(() => expect(button.textContent).toContain("Copied"));
    await waitFor(() => expect(button.textContent).toContain("Copy"), { timeout: 3000 });
  });

  it("announces the result rather than relying on an icon changing shape", async () => {
    stubClipboard("resolve");
    await openDrawer();
    fireEvent.click(screen.getByTestId("consume-copy-key"));
    await waitFor(() =>
      expect(screen.getByRole("status", { name: "" }).textContent).toContain("Copied project key ACME-HR-2024"),
    );
  });

  it("states a refusal instead of appearing to do nothing", async () => {
    stubClipboard("reject");
    await openDrawer();
    fireEvent.click(screen.getByTestId("consume-copy-python"));
    expect((await screen.findByTestId("consume-copy-error")).textContent).toBe(
      "Copy was blocked by the browser. Select the text and copy manually.",
    );
  });

  it("labels every copy control with what it copies", async () => {
    await openDrawer();
    expect(screen.getByTestId("consume-copy-key").getAttribute("aria-label")).toBe(
      "Copy project key ACME-HR-2024",
    );
    expect(screen.getByTestId("consume-copy-uuid").getAttribute("aria-label")).toBe("Copy project id");
    expect(screen.getByTestId("consume-copy-curl").getAttribute("aria-label")).toBe("Copy the cURL example");
  });
});
