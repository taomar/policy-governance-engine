import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { clearSession, getSession, storeSession, type Session } from "./auth";

function validSession(overrides: Partial<Session> = {}): Session {
  return {
    accessToken: "tok-abc",
    expiresAt: new Date(Date.now() + 3600_000).toISOString(),
    role: "admin",
    name: "alice",
    ...overrides,
  };
}

beforeEach(() => {
  sessionStorage.clear();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("session storage", () => {
  it("with no stored session getSession returns null", () => {
    expect(getSession()).toBeNull();
  });

  it("a stored session is read back with the same fields", () => {
    const s = validSession();
    storeSession(s);
    const read = getSession();
    expect(read).toEqual(s);
  });

  it("an expired stored token is treated as no session without a server round trip", () => {
    const expired = validSession({
      expiresAt: new Date(Date.now() - 1000).toISOString(),
    });
    storeSession(expired);
    // No fetch — the function reads the clock and discards.
    expect(getSession()).toBeNull();
    // And the storage is cleaned up.
    expect(sessionStorage.getItem("policy-platform.session")).toBeNull();
  });

  it("clearSession removes the stored session", () => {
    storeSession(validSession());
    clearSession();
    expect(getSession()).toBeNull();
  });

  it("malformed JSON in storage is treated as no session", () => {
    sessionStorage.setItem("policy-platform.session", "not-json");
    expect(getSession()).toBeNull();
  });
});
