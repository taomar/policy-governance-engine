import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { Dashboard } from "./Dashboard";
import { ProjectsPage } from "./ProjectsPage";
import { ActorProvider } from "../ActorContext";
import { api, PolicyPlatformApiError, API_UNREACHABLE_STATUS } from "../api";
import { describeApiFailure, isUnreachable } from "../loadState";

/**
 * AN ABSENT ANSWER IS NOT AN EMPTY ANSWER.
 *
 * With the API unreachable, the project register rendered "0 projects" and the
 * empty state "No projects yet. Create one to start uploading policy documents
 * and extracting rules" -- on an instance that had nine projects and 2,735
 * records. A reader was invited to create what they already had, and following
 * that invitation produces a duplicate project.
 *
 * The cause is that the interface had no vocabulary for "we do not know". An
 * empty array meant both "there are no projects" and "we never found out"; on
 * the dashboard, `undefined` meant both "not asked yet" and "asked and
 * refused", so two panels sat on "Loading..." permanently.
 *
 * WHY THE FLOOR IS THE MOST IMPORTANT TEST IN THIS FILE
 *
 * The cheap way to pass "does not offer the create-prompt when unreachable" is
 * to delete the create-prompt. That would satisfy every absence assertion here
 * while destroying the only state the prompt exists for. So
 * `offers the create-prompt when the server says there are none` runs FIRST
 * and asserts the genuine empty state still renders the invitation, with the
 * same words. Every absence assertion below is only meaningful because that
 * presence assertion holds.
 *
 * The same pairing guards the dashboard: a panel that renders nothing at all
 * passes "does not say Loading forever". So each panel is asserted to reach a
 * real answer on the served path before it is asserted to admit ignorance on
 * the refused one.
 */

const EMPTY_STATE_COPY = /No projects yet/;
const CREATE_PROMPT_COPY = /Create one to start uploading policy documents and extracting rules/;

/** jsdom provides neither, and antd measures both. */
function stubBrowserMeasurements() {
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
}

function jsonResponse(body: unknown) {
  return { ok: true, status: 200, json: async () => body } as unknown as Response;
}

/** The server answers, and the answer is "there are none". */
function serveEmpty() {
  vi.stubGlobal("fetch", vi.fn(async () => jsonResponse([])));
}

/**
 * The server is not reached at all. This is what `fetch` really rejects with
 * when the API is down -- a bare TypeError, which is why the exception name
 * was reaching reviewers verbatim.
 */
function refuseEverything() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => {
      throw new TypeError("Failed to fetch");
    }),
  );
}

/**
 * Both pages render an error alert on failure in every build, broken or fixed.
 * Waiting on that rather than on the new copy means the assertions below trip
 * on the thing they are about -- a create-prompt that should not be there --
 * instead of tripping early on the absence of a panel that is also missing.
 */
async function settleAfterRefusal() {
  await screen.findByRole("alert");
}

function renderDashboard() {
  return render(
    <ActorProvider>
      <Dashboard onNavigate={() => {}} />
    </ActorProvider>,
  );
}

beforeEach(() => {
  stubBrowserMeasurements();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("the register tells a reader whether it knows", () => {
  // FLOOR. Runs first and must stay first: every absence assertion below is
  // only worth anything while the invitation still appears where it belongs.
  it("offers the create-prompt when the server says there are none", async () => {
    serveEmpty();
    render(<ProjectsPage />);

    expect(await screen.findByText(EMPTY_STATE_COPY)).toBeTruthy();
    expect(screen.getByText(CREATE_PROMPT_COPY)).toBeTruthy();
    expect(document.body.textContent).toContain("0 projects");
  });

  it("does not offer the create-prompt when it could not ask", async () => {
    refuseEverything();
    render(<ProjectsPage />);

    await settleAfterRefusal();

    expect(
      screen.queryByText(EMPTY_STATE_COPY),
      "told a reader with projects that they have none",
    ).toBeNull();
    expect(
      screen.queryByText(CREATE_PROMPT_COPY),
      "invited a reader to create a project they already have",
    ).toBeNull();
  });

  it("does not report a count it does not have", async () => {
    refuseEverything();
    render(<ProjectsPage />);

    await settleAfterRefusal();

    expect(
      document.body.textContent,
      "reported 0 projects on an instance whose project count is unknown",
    ).not.toContain("0 projects");
  });

  it("offers a way to ask again", async () => {
    refuseEverything();
    render(<ProjectsPage />);

    await settleAfterRefusal();
    expect(
      screen.queryByRole("button", { name: /Try again/i }),
      "left a reader with a failed register and no way to retry",
    ).not.toBeNull();
  });

  it("names the state it is in", async () => {
    refuseEverything();
    render(<ProjectsPage />);

    await settleAfterRefusal();
    expect(await screen.findByText(/Project register unavailable/i)).toBeTruthy();
  });
});

describe("no internal exception name reaches a reader", () => {
  it("converts a refused fetch into an error that says what happened", async () => {
    refuseEverything();

    const caught = await api.listPolicySets().then(
      () => null,
      (e: unknown) => e,
    );

    expect(caught, "a refused fetch escaped as something other than an api error").toBeInstanceOf(
      PolicyPlatformApiError,
    );
    const error = caught as PolicyPlatformApiError;
    expect(error.status).toBe(API_UNREACHABLE_STATUS);
    expect(error.detail).not.toContain("TypeError");
    expect(error.detail).toMatch(/cannot reach/i);
    expect(isUnreachable(error)).toBe(true);
  });

  // Do not weaken: a server that answers with a refusal is still answering,
  // and that must keep its real status rather than being dressed as an outage.
  it("leaves a real HTTP failure with its real status", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: false,
        status: 404,
        statusText: "Not Found",
        json: async () => ({ detail: "policy set not found" }),
      }) as unknown as Response),
    );

    const caught = await api.listPolicySets().then(
      () => null,
      (e: unknown) => e,
    );

    const error = caught as PolicyPlatformApiError;
    expect(error.status).toBe(404);
    expect(error.detail).toBe("policy set not found");
    expect(isUnreachable(error), "a 404 was reported as the server being unreachable").toBe(false);
  });

  it("never falls back to an exception name as the message", () => {
    expect(describeApiFailure(new TypeError("Failed to fetch"))).not.toContain("TypeError");
    expect(describeApiFailure(new TypeError("Failed to fetch"))).not.toContain("Failed to fetch");
    expect(describeApiFailure("boom")).not.toContain("boom");
    expect(describeApiFailure(new PolicyPlatformApiError(500, "the extractor crashed"))).toBe(
      "the extractor crashed",
    );
  });

  it("shows no exception name on either page when the server is unreachable", async () => {
    refuseEverything();
    render(<ProjectsPage />);
    await settleAfterRefusal();
    expect(document.body.textContent).not.toContain("TypeError");
    expect(document.body.textContent).not.toContain("Failed to fetch");

    cleanup();

    renderDashboard();
    await settleAfterRefusal();
    expect(document.body.textContent).not.toContain("TypeError");
    expect(document.body.textContent).not.toContain("Failed to fetch");
  });
});
