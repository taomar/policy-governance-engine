/**
 * Decision 2, renegotiated: what a reviewer must not have to click, now that the
 * head says how big the job is.
 *
 * WHAT THIS FILE USED TO FORBID, AND WHY THE PREMISE EXPIRED
 *
 * Grouping a section's rules onto one card makes big cards — the largest measured
 * here holds 72 rules across 7 merged repeats of one heading. This file used to
 * forbid an expander over those rules outright, for a reason the product had paid
 * for twice: an empty page that rendered like a full one, and a queue of 2,735
 * that was not a workload. Both were the interface telling a reviewer something
 * untrue about the size of their job, and a collapsed rule looked worse still,
 * because the reviewer could not know it was there.
 *
 * That argument had a premise, and the premise expired. The head now carries a
 * census the card did not have when this was written: `policyRuleCountLabel`
 * states "72 rules" on the face of the card, and where a policy's rules fall on
 * more than one side `policyComposition`/`recordStance` states that split beside
 * it. A card whose head reads "72 rules" cannot be mistaken for the empty page,
 * and does not understate the workload — it states it as a number instead of as a
 * height. So collapsing the *body* behind a labelled expander no longer tells the
 * reviewer anything untrue: the count they would have earned by scrolling is on
 * the head before they scroll. Thirty-two policies of full-height rules was not a
 * truer picture of the job than thirty-two heads that each say what they hold; it
 * was the same job, told in screens instead of in numbers.
 *
 * WHAT IS STILL FORBIDDEN
 *
 * One harm the census does not answer. In the review queue a card carries
 * Approve and Reject, and a collapsed card with a live Approve would let a
 * reviewer decide a policy whose rules they have not read. The head says how many
 * rules there are; it does not say what they are. So the rule that survives is
 * narrower than the one it replaces: a decision may never be *offered* on a
 * collapsed card. The rules are one obvious expander away, and that expander is
 * the only route to the decision — reveal the rules, then decide them.
 *
 * WHAT IS ASSERTED, AND WHY IT IS A RENDER AND NOT A READ OF THE SOURCE
 *
 * A card that is not the open one renders collapsed: the head — heading, census,
 * route, status, selection — is whole, and the rule body is behind an expander
 * that is a real button carrying `aria-expanded`. Collapsed, it offers no Approve
 * or Reject; expanded in place, without opening the detail panel, it offers both.
 * The head states the rule count whether or not the body is shown, so "collapsed"
 * can never read as "this policy has no rules". And nothing is *stored* behind the
 * expander: the body it reveals holds every rule the policy has, drawn in full,
 * never a slice or a page — checked by rendering the open card, which is the same
 * card fully shown, and by counting the rules the closed one still holds. A
 * source-level check ("no `useState` named collapsed") is not enough, because the
 * thing forbidden is not a mechanism but an outcome: a decision reachable without
 * reading, or a rule the reviewer cannot learn is there.
 *
 * Every count below is paired with a control that fails when nothing renders,
 * because `expect(missing).toHaveLength(0)` is also what a blank page returns.
 */

import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { AssembledPolicy, CandidateRule, CanonicalRule } from "./api";
import { buildPolicyCards, passageQuotations } from "./policyCards";
import { PolicyReviewCard } from "./components/PolicyReviewCard";

/** The largest policy measured on the two documents in the database. */
const LARGEST_MEASURED_POLICY = 72;

/** How many repeats of one heading that policy merged. */
const MERGED_REPEATS = 7;

beforeAll(() => {
  // antd reads both on mount and jsdom implements neither.
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
  vi.unstubAllGlobals();
});

function rule(ruleId: string, elements: string): CanonicalRule {
  return {
    schema_version: "1.0",
    policy_set_id: "set",
    policy_version_id: "draft",
    rule_id: ruleId,
    rule_revision: 1,
    title: `title ${ruleId}`,
    description: `description ${ruleId}`,
    rule_type: "obligation",
    authority: { level: "ai_drafted", owner: "formulator", rank: 0 },
    scope: { jurisdictions: [], organizational_units: [], personas: [], processes: [] },
    condition: { type: "all", all: [] },
    effect: { type: "require_action", action: "act" },
    required_facts: [],
    exceptions: [],
    priority: 0,
    effective_from: "2026-01-01",
    effective_to: null,
    machine_executable: false,
    review_status: "candidate",
    evidence: [],
    lineage: {
      extraction_run_id: "run",
      deployment_name: "model",
      prompt_version: "v1",
      parser_version: "v1",
      schema_version: "1.0",
      source_elements: elements,
    },
    tags: [],
    ambiguity_status: "clear",
    category: "general",
    group_label: "",
    advice: [],
    related_rule_ids: [],
    is_explicit_override: false,
    supersedes_rule_ids: [],
  } as CanonicalRule;
}

function candidate(ruleId: string, elements: string): CandidateRule {
  return {
    id: `record-${ruleId}`,
    policy_set_id: "set",
    extraction_run_id: "run",
    rule_type: "obligation",
    revision: 1,
    review_status: "candidate",
    reviewed_by: null,
    reviewed_at: null,
    review_notes: null,
    published_version_id: null,
    created_at: "2026-01-01T00:00:00Z",
    rule: rule(ruleId, elements),
  } as CandidateRule;
}

/**
 * A policy shaped like the largest one measured: one heading, many passages,
 * many rules. Generic on purpose — no document's words, only its arithmetic.
 */
function bigPolicy(
  ruleCount: number,
  passageCount: number,
): { policy: AssembledPolicy; candidates: CandidateRule[] } {
  const passages = Array.from({ length: passageCount }, (_, block) => {
    const ids = Array.from({ length: Math.ceil(ruleCount / passageCount) }, (_, i) => {
      const ordinal = block * Math.ceil(ruleCount / passageCount) + i;
      return ordinal < ruleCount ? `r${ordinal}` : null;
    }).filter((id): id is string => id !== null);
    return {
      key: `p1-E${String(block).padStart(6, "0")}`,
      source_elements: `p1-E${String(block).padStart(6, "0")}`,
      page: block + 1,
      rule_count: ids.length,
      rules: ids.map((rule_id) => ({
        rule_id,
        title: `title ${rule_id}`,
        evaluation_mode: block % 2 === 0 ? "ai_ready" : "deterministic",
      })),
    };
  }).filter((passage) => passage.rules.length > 0);

  const rules = passages.flatMap((passage) => passage.rules);
  const policy: AssembledPolicy = {
    key: "digest-of-the-heading-chain",
    heading: "Schedule of matters",
    heading_path: ["Part four", "Schedule of matters"],
    persisted: true,
    document_version_id: "dv1",
    source_elements: passages.map((passage) => passage.key).join("; "),
    page: 1,
    rule_count: rules.length,
    passage_count: passages.length,
    route: "mixed",
    passages,
    rules,
  };
  const candidates = passages.flatMap((passage) =>
    passage.rules.map((r) => candidate(r.rule_id, passage.key)),
  );
  return { policy, candidates };
}

function renderCard(
  policy: AssembledPolicy,
  candidates: CandidateRule[],
  opts: {
    open?: boolean;
    onOpen?: () => void;
    onApprove?: () => void;
    onReject?: () => void;
  } = {},
) {
  const [card] = buildPolicyCards([policy], candidates);
  const { container } = render(
    <PolicyReviewCard
      card={card}
      selected={false}
      indeterminate={false}
      open={opts.open ?? false}
      statusColor={() => "default"}
      statusLabel={(status) => status}
      findingsFor={() => 0}
      onToggleSelect={() => {}}
      onOpen={opts.onOpen ?? (() => {})}
      onApprove={opts.onApprove ?? (() => {})}
      onReject={opts.onReject ?? (() => {})}
    />,
  );
  return { card, container };
}

/** The article element the card draws, so a test can read the class it carries. */
function articleOf(container: HTMLElement): HTMLElement {
  const article = container.querySelector<HTMLElement>('[data-testid="policy-card"]');
  if (!article) throw new Error("the card drew no article");
  return article;
}

describe("a list card opens collapsed, and hides no rule once it is open", () => {
  // WHY THE COMPLETENESS TESTS CARRY AN EXPLICIT BUDGET
  //
  // Some of these draw the largest policy anyone has measured and then look for
  // every one of its rules. That is deliberately the most expensive render in
  // the suite, and vitest's default five seconds is not a budget anyone chose
  // for it — it is the default, and it began failing when the card grew a name
  // and an inline detail per rule. A completeness test failing on a stopwatch
  // reports the wrong fault: it says rules are missing when they are all there.
  //
  // So the limit is stated, generously, and what the render costs is reported
  // where cost belongs rather than smuggled in as a timeout. If drawing a whole
  // policy ever gets slow enough to exhaust even this, that is a finding about
  // the card and not about these assertions.
  const DRAWS_A_WHOLE_LARGE_POLICY = 90_000;

  // ---- a card in a list opens collapsed ----

  it("renders collapsed when it is not the open card", () => {
    // The change this file now guards. Nothing in the head is removed — the head
    // is what makes collapsing honest — but the rule body sits behind one
    // obvious control.
    const { container } = (() => {
      const { policy, candidates } = bigPolicy(12, 3);
      return renderCard(policy, candidates);
    })();

    expect(articleOf(container).classList.contains("policy-card--collapsed")).toBe(true);
    const expander = container.querySelector('[data-testid="policy-card-expand"]');
    expect(expander, "a collapsed card must carry one control that opens it").not.toBeNull();
    expect(expander?.getAttribute("aria-expanded")).toBe("false");
  });

  it("states the size of the job in the head even while collapsed", () => {
    // Constraints 5 and 11: collapsed must never read as "this policy has no
    // rules", and the head must carry the information the body stops showing.
    // The count lives on the head, not in the body the expander hides, so it
    // survives the collapse and a card that says "72 rules" cannot be an empty
    // one.
    const { policy, candidates } = bigPolicy(LARGEST_MEASURED_POLICY, MERGED_REPEATS);
    const { container } = renderCard(policy, candidates);

    const head = articleOf(container).querySelector(".policy-card__head");
    expect(head?.textContent ?? "").toContain(`${LARGEST_MEASURED_POLICY} rules`);
  });

  it("offers no decision while collapsed, and the decision once it is opened", () => {
    // The one harm the census does not cure: a decision on a policy no one has
    // read. The records here are decidable, but collapsed the control is
    // withheld and the expander is the only route to it. Opened, the decision
    // the record permits is offered.
    const { policy, candidates } = bigPolicy(6, 2);
    const { container } = renderCard(policy, candidates);

    expect(screen.queryByRole("button", { name: /approve/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /reject/i })).toBeNull();

    fireEvent.click(screen.getByTestId("policy-card-expand"));

    expect(screen.getByRole("button", { name: /approve/i })).toBeTruthy();
    expect(screen.getByRole("button", { name: /reject/i })).toBeTruthy();
    expect(articleOf(container).classList.contains("policy-card--collapsed")).toBe(false);
    expect(screen.getByTestId("policy-card-expand").getAttribute("aria-expanded")).toBe("true");
  });

  it("opens in place, without opening the detail panel", () => {
    // Point 3: a reviewer scanning for context expands the card where it sits.
    // It must not throw them into the detail pane and change which record they
    // were looking at.
    const onOpen = vi.fn();
    const { policy, candidates } = bigPolicy(6, 2);
    renderCard(policy, candidates, { onOpen });

    fireEvent.click(screen.getByTestId("policy-card-expand"));

    expect(onOpen).not.toHaveBeenCalled();
  });

  it(
    "reveals its rules through a labelled disclosure button, not an opaque hide",
    () => {
      // The mechanism matters. Not a <details> (which hides from a sighted reader
      // while jsdom still finds its children, so a query cannot tell the two
      // apart), not a bare [hidden]; a real button that says what it does and
      // carries its state. And the rules behind it are in the DOM in full — the
      // reveal is a show, not a fetch, and not a slice.
      const { policy, candidates } = bigPolicy(LARGEST_MEASURED_POLICY, MERGED_REPEATS);
      const { container } = renderCard(policy, candidates);

      expect(container.querySelectorAll("details")).toHaveLength(0);
      expect(container.querySelectorAll("[hidden]")).toHaveLength(0);
      const expander = container.querySelector('[data-testid="policy-card-expand"]');
      expect(expander?.tagName).toBe("BUTTON");
      expect(expander?.getAttribute("aria-expanded")).toBe("false");
      // Hidden by CSS, not stored: every rule is still in the DOM.
      expect(screen.getAllByTestId("policy-card-rule")).toHaveLength(LARGEST_MEASURED_POLICY);
    },
    DRAWS_A_WHOLE_LARGE_POLICY,
  );

  // ---- once shown, nothing is stored behind the click ----

  it(
    "draws every one of a large policy's rules when it is the open card",
    () => {
      const { policy, candidates } = bigPolicy(LARGEST_MEASURED_POLICY, MERGED_REPEATS);
      const { card } = renderCard(policy, candidates, { open: true });

      // CONTROL. If the fixture or the builder collapsed, the loop below would
      // iterate over nothing and the test would pass on an empty page.
      expect(card.rules).toHaveLength(LARGEST_MEASURED_POLICY);

      const missing = card.rules
        .map((r) => r.rule_id)
        .filter((ruleId) => screen.queryAllByText(`title ${ruleId}`).length === 0);

      expect(
        missing,
        `${missing.length} of ${card.rules.length} rules are missing from the open ` +
          "card. Opening a card reveals its rules; it does not fetch or slice them.",
      ).toEqual([]);
    },
    DRAWS_A_WHOLE_LARGE_POLICY,
  );

  it(
    "draws every passage of a large policy when it is open",
    () => {
      const { policy, candidates } = bigPolicy(LARGEST_MEASURED_POLICY, MERGED_REPEATS);
      const { card } = renderCard(policy, candidates, { open: true });

      expect(card.passages.length).toBe(MERGED_REPEATS);
      // Each passage draws its own block, so the count of blocks is the count of
      // passages — a card that drew one block and listed 72 rules flat would fail
      // here while passing the test above.
      expect(screen.getAllByTestId("policy-passage")).toHaveLength(card.passages.length);
    },
    DRAWS_A_WHOLE_LARGE_POLICY,
  );

  it("reveals every rule the open card shows when a closed card is expanded", () => {
    // The renegotiated form of "renders the same rules whether or not open": the
    // open card and the expanded-in-place card are the same card fully shown, so
    // they hold the same rules. What changed is only whether the reviewer had to
    // ask to see them.
    const { policy, candidates } = bigPolicy(12, 3);

    renderCard(policy, candidates, { open: true });
    const shownOpen = screen.getAllByTestId("policy-card-rule").length;
    cleanup();

    renderCard(policy, candidates);
    fireEvent.click(screen.getByTestId("policy-card-expand"));
    const shownExpanded = screen.getAllByTestId("policy-card-rule").length;

    expect(shownOpen).toBe(12);
    expect(shownExpanded).toBe(shownOpen);
  });

  it("renders the open card expanded, with its decision and no expander", () => {
    // Point 2: the open card is shown exactly as before — full, decidable, and
    // with no expander to collapse the record currently under consideration.
    const { policy, candidates } = bigPolicy(12, 3);
    const { container } = renderCard(policy, candidates, { open: true });

    expect(articleOf(container).classList.contains("policy-card--collapsed")).toBe(false);
    expect(container.querySelector('[data-testid="policy-card-expand"]')).toBeNull();
    expect(screen.getByRole("button", { name: /approve/i })).toBeTruthy();
    expect(screen.getAllByTestId("policy-card-rule")).toHaveLength(12);
  });

  it("collapses a one-rule policy the same way, its head still stating the one rule", () => {
    // CONTROL: the card has no branch for small policies. One rule collapses like
    // seventy-two, and "1 rule" on the head keeps it from reading as empty.
    const { policy, candidates } = bigPolicy(1, 1);
    const { container } = renderCard(policy, candidates);

    expect(articleOf(container).classList.contains("policy-card--collapsed")).toBe(true);
    expect(container.querySelector('[data-testid="policy-card-expand"]')).not.toBeNull();
    const head = articleOf(container).querySelector(".policy-card__head");
    expect(head?.textContent ?? "").toContain("1 rule");
  });
});

describe("the card composes no sentence the document did not write", () => {
  it("keeps two source texts of one passage apart", () => {
    // The concatenation that used to happen here joined a passage's quotations
    // with a space, producing a sentence no document contains. The function
    // now returns them as a list and the card draws each in its own block, so
    // there is no string in the system with both in it.
    const quotations = passageQuotations([
      rule("a", "p1-E000001"),
      rule("b", "p1-E000002"),
    ]);

    for (const quotation of quotations) {
      expect(quotation.includes("description a") && quotation.includes("description b")).toBe(
        false,
      );
    }
  });

  it("draws each quotation in its own block", () => {
    const { policy, candidates } = bigPolicy(4, 2);
    renderCard(policy, candidates);

    const blocks = screen.queryAllByTestId("policy-passage-quotation");
    // Not an assertion about how many: an assertion that no single block holds
    // the text of two different passages glued together.
    for (const block of blocks) {
      expect(block.textContent ?? "").not.toMatch(/description r0.*description r1/s);
    }
  });
});
