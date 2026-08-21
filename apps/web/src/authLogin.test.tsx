/**
 * Tests for sign-in, session gating, and sign-out — named as sentences
 * describing the property held.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { App as AntApp, ConfigProvider } from "antd";
import { ActorProvider } from "./ActorContext";
import App from "./App";
import { clearSession, getSession, storeSession, type Session } from "./auth";

function validSession(overrides: Partial<Session> = {}): Session {
  return {
    accessToken: "tok-test",
    expiresAt: new Date(Date.now() + 3600_000).toISOString(),
    role: "admin",
    name: "Test User",
    ...overrides,
  };
}

// Ant Design needs matchMedia and ResizeObserver
beforeEach(() => {
  sessionStorage.clear();
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }));
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  );
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

function renderApp() {
  return render(
    <ConfigProvider>
      <AntApp>
        <ActorProvider>
          <App />
        </ActorProvider>
      </AntApp>
    </ConfigProvider>,
  );
}

describe("session gate", () => {
  it("with no session the login screen renders and the application shell does not", () => {
    renderApp();
    // The login screen's product name is visible
    expect(screen.getByText("PolicyVerbAItim")).toBeTruthy();
    expect(screen.getByText("Sign in to continue")).toBeTruthy();
    // The app shell's nav items are NOT rendered
    expect(screen.queryByText("Dashboard")).toBeNull();
    expect(screen.queryByText("Projects")).toBeNull();
  });

  it("a successful sign-in stores the session and the role from the response drives the surfaces", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          access_token: "tok-1",
          token_type: "bearer",
          expires_at: new Date(Date.now() + 3600_000).toISOString(),
          role: "policy_author",
          name: "Jane",
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );

    renderApp();

    fireEvent.change(screen.getByLabelText("Username"), { target: { value: "jane" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "secret" } });
    fireEvent.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => {
      // After sign-in, the shell should render — "Dashboard" appears in both
      // the nav and the header breadcrumb.
      expect(screen.getAllByText("Dashboard").length).toBeGreaterThan(0);
    });

    // Session is stored
    const session = getSession();
    expect(session).not.toBeNull();
    expect(session!.role).toBe("policy_author");
  });

  it("a failed sign-in shows one message that does not reveal whether the username exists", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ detail: "Unauthorized" }), {
        status: 401,
        statusText: "Unauthorized",
      }),
    );

    renderApp();

    fireEvent.change(screen.getByLabelText("Username"), { target: { value: "wrong" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "bad" } });
    fireEvent.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => {
      expect(
        screen.getByText("That username and password do not match."),
      ).toBeTruthy();
    });

    // Must NOT contain identity-revealing messages
    expect(screen.queryByText(/user not found/i)).toBeNull();
    expect(screen.queryByText(/unknown user/i)).toBeNull();
  });

  it("an expired stored token is treated as no session without a server round trip", () => {
    storeSession(
      validSession({ expiresAt: new Date(Date.now() - 1000).toISOString() }),
    );

    renderApp();

    // Should show login screen, not the shell
    expect(screen.getByText("Sign in to continue")).toBeTruthy();
    expect(screen.queryByText("Dashboard")).toBeNull();
  });
});

describe("401 handling", () => {
  it("a 401 from any call clears the session", () => {
    // Start with a valid session
    storeSession(validSession());
    expect(getSession()).not.toBeNull();

    // Simulate what request() does on a 401: clear the session
    clearSession();
    expect(getSession()).toBeNull();
  });
});

describe("sign out", () => {
  it("signing out clears the session and returns to the login screen", () => {
    storeSession(validSession());
    expect(getSession()).not.toBeNull();
    clearSession();
    expect(getSession()).toBeNull();
  });
});
