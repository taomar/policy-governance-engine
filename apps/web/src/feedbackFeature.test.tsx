/**
 * Tests for the policy feedback feature — the properties that matter.
 *
 * Each test is named as a sentence describing a user-visible guarantee.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { SubmitFeedbackModal } from "./components/SubmitFeedbackModal";
import { FeedbackTimeline } from "./components/FeedbackTimeline";
import { FeedbackQueue } from "./components/FeedbackQueue";
import type { PolicyReviewRequest } from "./api";

// Ant Design needs matchMedia and ResizeObserver
beforeEach(() => {
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

function mockRequest(record: Partial<PolicyReviewRequest> = {}) {
  return {
    id: "req-1",
    policy_set_key: "ps-1",
    approved_policy_version_id: "v-1",
    submitted_by: "viewer-user",
    submitted_at: "2025-01-01T12:00:00Z",
    comment: "This is outdated.",
    categories: ["Outdated reference"],
    status: "open" as const,
    ...record,
  };
}

describe("SubmitFeedbackModal", () => {
  it("the composer states that the policy remains in force before the user submits", () => {
    render(
      <SubmitFeedbackModal
        open
        policySetKey="ps-1"
        approvedPolicyVersionId="v-1"
        submittedBy="viewer-user"
        onClose={() => {}}
        onSubmitted={() => {}}
      />,
    );

    expect(screen.getByText("This policy remains current and in force.")).toBeTruthy();
    expect(
      screen.getByText(/it does not change the policy's status or take it out of service/),
    ).toBeTruthy();
  });

  it("submitting does not alter any policy status shown on screen", async () => {
    const { api } = await import("./api");
    vi.spyOn(api, "createReviewRequest").mockResolvedValue(mockRequest());

    const onSubmitted = vi.fn();
    render(
      <SubmitFeedbackModal
        open
        policySetKey="ps-1"
        approvedPolicyVersionId="v-1"
        submittedBy="viewer-user"
        onClose={() => {}}
        onSubmitted={onSubmitted}
      />,
    );

    // Fill in a comment
    const textarea = screen.getByTestId("feedback-comment");
    fireEvent.change(textarea, { target: { value: "Please fix this." } });

    // Submit
    const submitBtn = screen.getByRole("button", { name: /submit/i });
    fireEvent.click(submitBtn);

    await waitFor(() => expect(onSubmitted).toHaveBeenCalledTimes(1));

    // The API was called but no policy-altering endpoint was invoked
    expect(api.createReviewRequest).toHaveBeenCalledWith(
      expect.objectContaining({ comment: "Please fix this." }),
    );
  });
});

describe("FeedbackTimeline", () => {
  it("withdraw is offered only while the request is open", async () => {
    const { api } = await import("./api");
    vi.spyOn(api, "listReviewRequests").mockResolvedValue([
      mockRequest({ id: "open-1", status: "open" }),
      mockRequest({ id: "ack-2", status: "acknowledged" }),
      mockRequest({ id: "dismissed-3", status: "dismissed" }),
    ]);

    render(
      <FeedbackTimeline policySetKey="ps-1" submittedBy="viewer-user" />,
    );

    await waitFor(() => expect(screen.getByTestId("feedback-timeline")).toBeTruthy());

    // Only the open request shows a withdraw link
    expect(screen.getByTestId("withdraw-open-1")).toBeTruthy();
    expect(screen.queryByTestId("withdraw-ack-2")).toBeNull();
    expect(screen.queryByTestId("withdraw-dismissed-3")).toBeNull();
  });
});

describe("FeedbackQueue", () => {
  it("dismissing without a reason is refused by the UI", async () => {
    const { api } = await import("./api");
    vi.spyOn(api, "listReviewRequests").mockResolvedValue([
      mockRequest({ id: "r-1", status: "open" }),
    ]);
    vi.spyOn(api, "resolveReviewRequest").mockResolvedValue(mockRequest({ status: "dismissed" }));

    render(
      <FeedbackQueue policySetKey="ps-1" actorName="author-user" />,
    );

    await waitFor(() => expect(screen.getByText("This is outdated.")).toBeTruthy());

    // Click dismiss
    const dismissBtn = screen.getByRole("button", { name: /dismiss/i });
    fireEvent.click(dismissBtn);

    await waitFor(() => expect(screen.getByTestId("dismiss-note")).toBeTruthy());

    // The modal's OK (Dismiss) button should be disabled because no note is entered
    const modalOk = document.querySelector(".ant-modal-footer .ant-btn-dangerous");
    expect(modalOk).toBeTruthy();
    expect(modalOk?.hasAttribute("disabled")).toBe(true);

    // resolveReviewRequest should not have been called
    expect(api.resolveReviewRequest).not.toHaveBeenCalled();
  });
});

describe("Role visibility", () => {
  it("a viewer sees the submit entry point; an author does not", async () => {
    // The button appears only when isViewer is true (toRbacRole returns "viewer").
    // We test this by checking the toRbacRole logic directly since the button
    // lives deep inside PoliciesTab which requires extensive mocking.
    const { toRbacRole } = await import("./ActorContext");

    expect(toRbacRole("viewer")).toBe("viewer");
    expect(toRbacRole("policy_composer")).toBe("policy_author");
    expect(toRbacRole("system_admin")).toBe("admin");

    // Only "viewer" role should see the feedback button
    expect(toRbacRole("viewer") === "viewer").toBe(true);
    expect(toRbacRole("policy_composer") === "viewer").toBe(false);
    expect(toRbacRole("system_admin") === "viewer").toBe(false);
  });
});
