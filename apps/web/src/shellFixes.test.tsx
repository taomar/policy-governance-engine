/**
 * Shell-layer fixes: login screen purpose, session-expiry notice, and
 * brand mark -- named as sentences describing the property held.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render } from "@testing-library/react";
import { App as AntApp, ConfigProvider } from "antd";
import { storeSession, getSession, type Session } from "./auth";
import { LoginScreen } from "./components/LoginScreen";

function validSession(overrides: Partial<Session> = {}): Session {
  return {
    accessToken: "tok-test",
    expiresAt: new Date(Date.now() + 3600_000).toISOString(),
    role: "admin",
    name: "Test User",
    ...overrides,
  };
}

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

function renderLogin(props: { onSignedIn?: (s: Session) => void } = {}) {
  return render(
    <ConfigProvider>
      <AntApp>
        <LoginScreen onSignedIn={props.onSignedIn ?? (() => {})} />
      </AntApp>
    </ConfigProvider>,
  );
}

// F3 -- the login screen states what the product is

describe("the login screen states what the product is", () => {
  it("shows the product tagline rather than only Sign in to continue", () => {
    const { container } = renderLogin();
    const text = container.textContent ?? "";
    expect(text).toContain("AI to read. Evidence to prove. Determinism to decide.");
    expect(text).not.toContain("Sign in to continue");
  });

  it("the brand mark reads PV not PP", () => {
    const { container } = renderLogin();
    const mark = container.querySelector(".brand-mark");
    expect(mark).not.toBeNull();
    expect(mark!.textContent).toBe("PV");
  });
});

// F4 -- an expired session is explained rather than silently reset

describe("an expired session is explained rather than silently reset", () => {
  it("an expired token shows a session-expired notice on the login screen", () => {
    storeSession(validSession({
      expiresAt: new Date(Date.now() - 1000).toISOString(),
    }));
    // getSession() detects expiry and records the reason
    getSession();

    const { container } = renderLogin();
    expect(container.textContent).toMatch(/session expired/i);
  });

  it("a first visit with no prior session shows no expiry notice", () => {
    const { container } = renderLogin();
    expect(container.textContent).not.toMatch(/session expired/i);
  });
});
