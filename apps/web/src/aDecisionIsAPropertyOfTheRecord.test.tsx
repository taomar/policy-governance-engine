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
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import type { CanonicalRule } from "./api";
import { fromDraftRow, type PolicyCard } from "./policyCards";
import { PolicyReviewCard } from "./components/PolicyReviewCard";
import { ActorProvider } from "./ActorContext";

function rule(id: string, markedWhole = false): CanonicalRule {
  const statement = `A statement ${id}`;
  return {
    rule_id: id,
    title: statement,
    // The sentence the document is quoted as stating. When it is longer than
    // the statement the card prints the statement; when it is the statement
    // word for word the card says so instead of printing it twice. Both are
    // ordinary renderings and both are exercised here.
    description: markedWhole ? statement : `The source says ${statement}, among other things.`,
    rule_type: "obligation",
    evaluation_mode: "deterministic",
    condition: { type: "all", all: [] },
    effect: { type: "require_action", action: "an action" },
  } as unknown as CanonicalRule;
}

function cardOf(statuses: readonly string[], markedWhole = false): PolicyCard {
  const rules = statuses.map((review_status, index) => ({
    rule_id: `r${index}`,
    evaluation_mode: "deterministic",
    ...fromDraftRow({
      id: `record-${index}`,
      review_status,
      rule: rule(`r${index}`, markedWhole),
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

describe("reading a rule is not deciding it", () => {
  afterEach(cleanup);

  function drawWithReader(card: PolicyCard, selectedRuleId?: string) {
    const onSelectRule = vi.fn();
    const onToggleSelect = vi.fn();
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
          onToggleSelect={onToggleSelect}
          onOpen={() => {}}
          onSelectRule={onSelectRule}
          selectedRuleId={selectedRuleId}
        />
      </ActorProvider>,
    );
    return { onSelectRule, onToggleSelect };
  }

  it("makes the rule's own words the thing a reader activates", () => {
    // Not a row-wide click handler and not a div wearing `role="button"`. A
    // native button is why Enter and Space work, why it appears in the tab
    // order, and why the shared focus outline applies -- none of which a
    // handler on a list item would give, and all of which are easy to forget
    // when reinventing one.
    drawWithReader(cardOf(["candidate"]));
    const control = screen.getByRole("button", { name: /A statement r0/ });
    expect(control.tagName).toBe("BUTTON");
    expect(control.getAttribute("type")).toBe("button");
    expect(control.hasAttribute("disabled")).toBe(false);
    expect(control.getAttribute("tabindex")).not.toBe("-1");
  });

  it("offers the rule to be opened on a sealed record, where no decision is offered", () => {
    const { onSelectRule } = drawWithReader(cardOf(["published"]));
    expect(screen.getByRole("button", { name: /A statement r0/ })).not.toBeNull();
    expect(screen.queryByRole("button", { name: /approve/i })).toBeNull();
    expect(onSelectRule).not.toHaveBeenCalled();
  });

  it("hands over the identity of the row that was clicked, not the rule it states", () => {
    // `rule_id` is a hash of the rule's content, so a passage stating two rules
    // in identical words gives them one between them. Resolving a click through
    // it opens whichever came first, which is not the one that was pointed at.
    const { onSelectRule } = drawWithReader(cardOf(["candidate", "candidate", "candidate"]));
    fireEvent.click(screen.getByRole("button", { name: /A statement r2/ }));
    expect(onSelectRule).toHaveBeenCalledTimes(1);
    expect(onSelectRule.mock.calls[0][0]).toBe("record-2");
  });

  it("leaves everything else on the row reachable on its own", () => {
    // The row also carries badges, tags and a finding count, each with its own
    // tooltip. Putting them inside the button would be invalid HTML, would take
    // them out of the tab order, and would make one target of several answers.
    const { onSelectRule, onToggleSelect } = drawWithReader(cardOf(["candidate", "published"]));
    const control = screen.getByRole("button", { name: /A statement r0/ });
    expect(within(control).queryByRole("checkbox")).toBeNull();
    expect(within(control).queryByRole("button")).toBeNull();

    const status = screen.getByText("candidate");
    expect(control.contains(status)).toBe(false);

    const checkbox = screen.getAllByRole("checkbox")[0];
    expect(control.contains(checkbox)).toBe(false);
    fireEvent.click(checkbox);
    expect(onToggleSelect).toHaveBeenCalledTimes(1);
    expect(onSelectRule).not.toHaveBeenCalled();
  });

  it("says on the row which rule is the one open beside the card", () => {
    drawWithReader(cardOf(["candidate", "candidate"]), "record-1");
    const rows = screen.getAllByTestId("policy-card-rule");
    expect(rows[0].getAttribute("aria-current")).toBeNull();
    expect(rows[1].getAttribute("aria-current")).toBe("true");
  });

  it("marks no row when nothing is open", () => {
    drawWithReader(cardOf(["candidate", "candidate"]));
    const marked = screen
      .getAllByTestId("policy-card-rule")
      .filter((row) => row.hasAttribute("aria-current"));
    expect(marked).toEqual([]);
  });

  it("does not open the whole policy when a rule inside it is opened", () => {
    // The control sits inside the card, and the card's own click opens the
    // policy. Without stopping the event a reader asking for one rule would get
    // the policy panel instead, which is a different question answered.
    const card = cardOf(["candidate"]);
    const onOpen = vi.fn();
    const onSelectRule = vi.fn();
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
          onOpen={onOpen}
          onSelectRule={onSelectRule}
        />
      </ActorProvider>,
    );
    fireEvent.click(screen.getByRole("button", { name: /A statement r0/ }));
    expect(onSelectRule).toHaveBeenCalledTimes(1);
    expect(onOpen).not.toHaveBeenCalled();
  });

  it("draws no such control on a surface that has nowhere to open a rule", () => {
    // An affordance that leads nowhere is worse than none, so the read-only
    // surfaces render the statement as the plain text it was before this
    // existed -- still on screen, simply not activatable.
    draw(cardOf(["candidate"]));
    expect(screen.queryByRole("button", { name: /A statement r0/ })).toBeNull();
    expect(screen.getAllByText("A statement r0").length).toBeGreaterThan(0);
  });

  it("opens the rule the same way where the card marks the statement instead of printing it", () => {
    // Where the document's own sentence is the statement word for word the card
    // points at the marked words rather than repeating them. That stand-in is
    // the statement on that row, so it is what a reader activates -- the rule is
    // reachable whichever way the card chose to show it.
    const { onSelectRule } = drawWithReader(cardOf(["candidate", "candidate"], true));
    const controls = screen.getAllByTestId("policy-card-rule-open");
    expect(controls.length).toBe(2);
    expect(controls[1].tagName).toBe("BUTTON");
    fireEvent.click(controls[1]);
    expect(onSelectRule.mock.calls[0][0]).toBe("record-1");
  });
});
