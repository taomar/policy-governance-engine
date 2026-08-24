/**
 * What the queue summary is allowed to say, and what it must never say.
 *
 * The summary line replaced four stat cards plus a publish bar. Three of the
 * facts it carries are load-bearing in a way a tidy-up could quietly break, so
 * they are pinned here:
 *
 *   - the quality scan has FOUR states, and an *absent* scan must render as "—"
 *     with "No scan of records in review" — never as "0". A scan that ran and found nothing is a
 *     different fact, and it is the one allowed to show "0" (constraint 5);
 *   - decided progress keeps both units — policies and rules — because a policy
 *     is what gets decided and rules are what it is made of (constraint 2); and
 *   - "Ready to publish" leads in POLICIES and keeps the rule count beside it.
 *
 * That last fact was deliberately RE-CUT, not relaxed. This block used to pin a
 * rules-led headline ("Approved rules, not live", a bare rule count) from a time
 * when the summary reasoned in rules. Every other surface — the banner, the
 * bands, the status strip, the project badges — now leads in policies and keeps
 * rules beside, because a policy is what a reviewer decides and publishes
 * (constraint 2), and a KPI still asserting the rules-led wording was the last
 * holdout pinning the behaviour the user rejected. The contract is rewritten to
 * the new intent; the rule figure is kept, never dropped (constraint 11).
 *
 * The component is pure, so each state is rendered directly rather than by
 * driving a live queue into it.
 */
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";

import { ReviewQueueSummary } from "./ReviewQueueSummary";
import { qualityScanSummary } from "../qualityScanSummary";

afterEach(cleanup);

function item(label: string): HTMLElement {
  const dt = screen.getByText(label);
  const box = dt.closest(".review-queue-summary__item");
  if (!box) throw new Error(`no summary item wrapping "${label}"`);
  return box as HTMLElement;
}

describe("decision progress is stated once, in both units", () => {
  it("shows the percentage and the policies-and-rules detail", () => {
    render(
      <ReviewQueueSummary
        decisionPercent={25}
        progressDetail="4 of 32 policies · 40 of 398 rules"
        readyToPublishPolicies={0}
        readyToPublishDetail="0 rules"
        quality={qualityScanSummary({ loading: false, failed: false, count: null })}
      />,
    );
    const progress = item("Decision progress");
    expect(within(progress).getByText("25%")).toBeTruthy();
    // Both units survive: rules never become the unit of counting.
    expect(
      within(progress).getByText("4 of 32 policies · 40 of 398 rules decided"),
    ).toBeTruthy();
  });
});

describe("ready to publish is the next-action count", () => {
  it("shows the count and flags attention when there is something to publish", () => {
    render(
      <ReviewQueueSummary
        decisionPercent={80}
        progressDetail="26 of 32 policies · 320 of 398 rules"
        readyToPublishPolicies={2}
        readyToPublishDetail="2 policies · 7 rules"
        quality={qualityScanSummary({ loading: false, failed: false, count: 0 })}
      />,
    );
    const ready = item("Ready to publish");
    // Leads in policies — the unit a decision is taken in (constraint 2).
    expect(within(ready).getByText("2")).toBeTruthy();
    // Keeps the rule figure beside it and still says it is not live; the unit
    // never silently narrows to a single number (constraint 11 — both units,
    // neither traded for tidiness).
    expect(within(ready).getByText("2 policies · 7 rules, not live")).toBeTruthy();
    expect(ready.classList.contains("review-operation-attention")).toBe(true);
  });

  it("shows zero plainly, without shouting, when nothing is ready", () => {
    render(
      <ReviewQueueSummary
        decisionPercent={0}
        progressDetail="0 of 32 policies · 0 of 398 rules"
        readyToPublishPolicies={0}
        readyToPublishDetail="0 rules"
        quality={qualityScanSummary({ loading: false, failed: false, count: 3 })}
      />,
    );
    const ready = item("Ready to publish");
    expect(within(ready).getByText("0")).toBeTruthy();
    expect(ready.classList.contains("review-operation-attention")).toBe(false);
  });
});

describe("the quality scan keeps its four states apart (constraint 5)", () => {
  it("renders an absent scan as an em-dash, never as zero", () => {
    render(
      <ReviewQueueSummary
        decisionPercent={50}
        progressDetail="16 of 32 policies · 200 of 398 rules"
        readyToPublishPolicies={1}
        readyToPublishDetail="1 policy · 4 rules"
        quality={qualityScanSummary({ loading: false, failed: false, count: null })}
      />,
    );
    const quality = item("Quality findings");
    expect(within(quality).getByText("—")).toBeTruthy();
    expect(within(quality).getByText("No scan of records in review")).toBeTruthy();
    // The crux: absent is not zero. Nothing in this card may read "0".
    expect(within(quality).queryByText("0")).toBeNull();
  });

  it("renders a scan that ran and found nothing as a real zero", () => {
    render(
      <ReviewQueueSummary
        decisionPercent={50}
        progressDetail="16 of 32 policies · 200 of 398 rules"
        readyToPublishPolicies={1}
        readyToPublishDetail="1 policy · 4 rules"
        quality={qualityScanSummary({ loading: false, failed: false, count: 0 })}
      />,
    );
    const quality = item("Quality findings");
    expect(within(quality).getByText("0")).toBeTruthy();
    expect(within(quality).getByText(/None found across loaded rules/i)).toBeTruthy();
    // A true zero is a different fact from an absent scan; it is not "—".
    expect(within(quality).queryByText("—")).toBeNull();
  });

  it("renders a completed scan's real count", () => {
    render(
      <ReviewQueueSummary
        decisionPercent={50}
        progressDetail="16 of 32 policies · 200 of 398 rules"
        readyToPublishPolicies={1}
        readyToPublishDetail="1 policy · 4 rules"
        quality={qualityScanSummary({ loading: false, failed: false, count: 5 })}
      />,
    );
    const quality = item("Quality findings");
    expect(within(quality).getByText("5")).toBeTruthy();
  });

  it("does not claim a scan never ran while one is in flight", () => {
    render(
      <ReviewQueueSummary
        decisionPercent={50}
        progressDetail="16 of 32 policies · 200 of 398 rules"
        readyToPublishPolicies={1}
        readyToPublishDetail="1 policy · 4 rules"
        quality={qualityScanSummary({ loading: true, failed: false, count: null })}
      />,
    );
    const quality = item("Quality findings");
    expect(within(quality).getByText("Scanning now")).toBeTruthy();
    expect(within(quality).queryByText("No scan of records in review")).toBeNull();
  });
});
