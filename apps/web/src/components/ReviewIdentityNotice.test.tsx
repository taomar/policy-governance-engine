/**
 * The reviewer is told a name is needed before the click, not by it.
 *
 * The review queue refuses to approve or reject while no reviewer name is set.
 * That refusal is correct and stays. What these tests pin is that the queue now
 * states the requirement *standing* — before any click — and takes the
 * statement down once a name is recorded, so the requirement is no longer
 * invisible until the moment a reviewer trips over it.
 *
 * The standing notice is only half the fix. The other half, asserted against
 * the queue's own source, is that the click still refuses: the gate returns
 * before anything is sent. A change that dropped the notice, or quietly turned
 * the refusal into a success, fails here.
 *
 * A warning, not an error: a decision refused for want of an author is a
 * different state from a decision that failed, and reads in a different colour.
 *
 * Nothing here is a phrase from any document, and no number in it is a
 * measurement of one.
 */
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { ReviewIdentityNotice } from "./ReviewIdentityNotice";
import { REVIEW_IDENTITY_NOTICE } from "../reviewIdentityNotice";

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
});

afterEach(() => cleanup());

describe("the notice states the requirement, and only when it is due", () => {
  it("states it with no name set and work to decide, without any click", () => {
    render(<ReviewIdentityNotice identity="" hasDecisionWork={true} />);
    expect(screen.queryAllByText(REVIEW_IDENTITY_NOTICE).length).toBeGreaterThan(0);
  });

  it("takes the statement down once a name is recorded", () => {
    render(<ReviewIdentityNotice identity="jane.doe" hasDecisionWork={true} />);
    expect(screen.queryByText(REVIEW_IDENTITY_NOTICE)).toBeNull();
  });

  it("shows nothing when there is nothing to decide", () => {
    render(<ReviewIdentityNotice identity="" hasDecisionWork={false} />);
    expect(screen.queryByText(REVIEW_IDENTITY_NOTICE)).toBeNull();
  });
});

/** The queue's own source. The click's refusal lives in a closure over the
 *  actor context and its proof is a POST that is *not* issued, which no render
 *  can show without standing up the whole review stack — so it is read, the way
 *  this repository reads the queue elsewhere, rather than rendered. */
const QUEUE = import.meta.glob("./ReviewQueue.tsx", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

describe("the queue states the requirement up front and still refuses the click", () => {
  const source = (() => {
    const found = Object.values(QUEUE);
    expect(found).toHaveLength(1);
    return found[0];
  })();

  it("mounts the standing notice in the queue", () => {
    expect(source).toContain("<ReviewIdentityNotice");
  });

  it("still refuses a decision with no author, before anything is sent", () => {
    // Everything from the guard's home to the one place a review is dispatched.
    const gate = source.slice(
      source.indexOf("const requestReview"),
      source.indexOf("void runReview"),
    );
    expect(gate.length).toBeGreaterThan(0);
    expect(gate).toMatch(/!identity\.trim\(\)/);
    expect(gate).toMatch(/message\.warning/);
    expect(gate).toContain("return;");
  });
});
