/**
 * A DECISION IS A PROPERTY OF THE RECORD, NOT OF THE WIRING
 *
 * The card used to draw Approve and Reject when its handlers were supplied, and
 * nothing else. That made "may this be decided?" a question about a call site.
 * A published version is sealed — its decision was made and numbered — and a
 * page that passed the handlers by mistake would have offered to decide it
 * again, drawing a control that writes to a record no longer open to writing.
 *
 * So the card reads each record's own review state through `candidateEditability`,
 * the one place in this app that knows what a state permits, and treats the
 * handlers as how a decision is recorded rather than whether one may be.
 *
 * These tests wire the handlers deliberately, because that is the mistake being
 * guarded against. If the card is ever reverted to asking about its props, every
 * one of them fails.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import type { CanonicalRule } from "./api";
import { fromDraftRow, type PolicyCard } from "./policyCards";
import { PolicyReviewCard } from "./components/PolicyReviewCard";
import { ActorProvider } from "./ActorContext";

function rule(id: string): CanonicalRule {
  return {
    rule_id: id,
    title: `A statement ${id}`,
    description: `A statement ${id}`,
    rule_type: "obligation",
    evaluation_mode: "deterministic",
    condition: { type: "all", all: [] },
    effect: { type: "require_action", action: "an action" },
  } as unknown as CanonicalRule;
}

function cardOf(statuses: readonly string[]): PolicyCard {
  const rules = statuses.map((review_status, index) => ({
    rule_id: `r${index}`,
    evaluation_mode: "deterministic",
    ...fromDraftRow({
      id: `record-${index}`,
      review_status,
      rule: rule(`r${index}`),
    } as never),
  }));
  return {
    policy: {
      key: "a-key",
      heading: "A heading",
      heading_path: ["A heading"],
      topic_label: null,
      persisted: true,
      provision_id: null,
      document_version_id: null,
      source_elements: "p1-E1",
      page: 1,
      rule_count: rules.length,
      passage_count: 1,
      route: "deterministic",
      passages: [{ rules: rules.map(({ rule_id }) => ({ rule_id })) }],
      rules: [],
    },
    passages: [{ passage: { key: "a-passage" }, rules }],
    rules,
    reviewableIds: [],
    allIds: rules.map((one) => one.recordId),
    hiddenByFilter: 0,
  } as unknown as PolicyCard;
}

function draw(card: PolicyCard) {
  const onApprove = vi.fn();
  const onReject = vi.fn();
  render(
    <ActorProvider>
      <PolicyReviewCard
        card={card}
        selected={false}
        indeterminate={false}
        open={false}
        statusColor={() => "blue"}
        statusLabel={(status) => status}
        findingsFor={() => 0}
        onToggleSelect={() => {}}
        onOpen={() => {}}
        onApprove={onApprove}
        onReject={onReject}
      />
    </ActorProvider>,
  );
  return { onApprove, onReject };
}

describe("what may be decided is read from the record", () => {
  afterEach(cleanup);

  it("offers no decision on a policy whose records are all sealed, however it is wired", () => {
    draw(cardOf(["published", "published"]));
    expect(screen.queryByRole("button", { name: /approve/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /reject/i })).toBeNull();
  });

  it("offers no way to gather a sealed policy into a decision either", () => {
    draw(cardOf(["published"]));
    expect(screen.queryByRole("checkbox")).toBeNull();
  });

  it("offers the decision on a policy whose records are still open", () => {
    draw(cardOf(["candidate", "candidate"]));
    expect(screen.getByRole("button", { name: /approve/i })).toBeTruthy();
    expect(screen.getByRole("button", { name: /reject/i })).toBeTruthy();
  });

  it("offers it when one record of the policy is still open and the rest are not", () => {
    draw(cardOf(["published", "candidate", "approved"]));
    expect(screen.getByRole("button", { name: /approve/i })).toBeTruthy();
  });

  it("offers no decision on a state this build does not recognise", () => {
    // Not a default into either answer: an unrecognised state is not known to
    // permit a decision, so the card does not offer one. A new state reaching
    // this build shows up as a control that is missing rather than as a write
    // to a record nobody here understands.
    draw(cardOf(["a_state_from_a_later_build"]));
    expect(screen.queryByRole("button", { name: /approve/i })).toBeNull();
  });

  it("still shows the policy, its heading and its rules when nothing may be decided", () => {
    // Sealed is not hidden. The record is fully readable; only the writing is
    // closed.
    draw(cardOf(["published", "published"]));
    expect(screen.getAllByText(/A heading/).length).toBeGreaterThan(0);
    expect(screen.getAllByTestId("policy-card").length).toBe(1);
  });
});
