/**
 * Selecting a policy shows the policy; selecting a rule shows the rule.
 *
 * WHY THESE TESTS
 *
 * Two faults were reported together, and they are the same fault at two
 * depths.
 *
 * Pointing at a policy's heading opened a panel describing one of its rules.
 * The panel offered two identifiers — the rule's, and the policy *set*'s —
 * and neither named the thing that had been clicked, so a reader tracing a
 * policy had nothing to carry. That is not a labelling slip: a policy and a
 * rule are two different records, and one of them was borrowing the other's
 * panel.
 *
 * And a rule's own words were inert text, so the only way into a rule was a
 * control beside it rather than the rule itself.
 *
 * WHAT THESE PIN, AND WHY EACH WOULD OTHERWISE COME BACK
 *
 *  - A card built from published records reports no review progress. `allIds`
 *    is populated on such a card (a record with no draft row is known by its
 *    rule id), so the obvious arithmetic reports every rule of a sealed policy
 *    as freshly decided — a claim about a review that never happened.
 *  - Each panel names which kind of record it is showing. Without it, a reader
 *    tells them apart by counting identifiers, which is what failed.
 *  - The statement is a button, and only the statement. A tidy-up that widened
 *    it to the row would swallow the badges and the menu beside it.
 *
 * Nothing here is a phrase from any document, and no number in it is a
 * measurement of one.
 */
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import type { AssembledPolicy, CandidateRule, CanonicalRule } from "../api";
import { buildPolicyCards } from "../policyCards";
import { policyRecord } from "./policyTabPanes";
import { isOutsideWindow } from "./PoliciesTab";
import { PublishedPolicyCard } from "./PublishedPolicyCard";

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
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  );
});

afterEach(() => cleanup());

function rule(ruleId: string, overrides: Partial<CanonicalRule> = {}): CanonicalRule {
  return {
    schema_version: "1.0",
    policy_set_id: "a-set-id",
    policy_version_id: "a-version-id",
    rule_id: ruleId,
    rule_revision: 1,
    title: `Title for ${ruleId}`,
    description: `Description for ${ruleId}`,
    rule_type: "obligation",
    authority: { owner: "an-owner", source: "", reference: "" },
    scope: { jurisdictions: [], organizational_units: [], processes: [] },
    condition: { type: "all", all: [] },
    evaluation_mode: "ai_ready",
    effect: { type: "require_action" },
    required_facts: [],
    exceptions: [],
    priority: 0,
    effective_from: "2024-01-01",
    effective_to: null,
    machine_executable: false,
    ambiguity_status: "clear",
    review_status: "published",
    evidence: [],
    lineage: {
      extraction_run_id: null,
      deployment_name: null,
      prompt_version: null,
      parser_version: null,
      schema_version: "1.0",
    },
    category: "",
    tags: [],
    group_label: "",
    related_rule_ids: [],
    is_explicit_override: false,
    supersedes_rule_ids: [],
    advice: [],
    ...overrides,
  } as unknown as CanonicalRule;
}

function policy(ruleIds: string[]): AssembledPolicy {
  return {
    key: "a-policy-key",
    heading: "A heading",
    heading_path: ["An outer heading", "A heading"],
    topic_label: null,
    persisted: true,
    provision_id: "a-provision-id",
    document_version_id: null,
    source_elements: "",
    page: 1,
    rule_count: ruleIds.length,
    passage_count: 1,
    route: "ai_ready",
    passages: [
      {
        key: "a-passage-key",
        source_elements: "",
        page: 1,
        rule_count: ruleIds.length,
        rules: ruleIds.map((id) => ({ rule_id: id, evaluation_mode: "ai_ready" })),
      },
    ],
    rules: ruleIds.map((id) => ({ rule_id: id, evaluation_mode: "ai_ready" })),
  } as unknown as AssembledPolicy;
}

/** A draft row, as the queue holds one. */
function draft(ruleId: string, reviewStatus: string): CandidateRule {
  return {
    id: `draft-${ruleId}`,
    rule: rule(ruleId, { review_status: reviewStatus }),
    review_status: reviewStatus,
    policy_set_id: "a-set-id",
  } as unknown as CandidateRule;
}

/** A card of published records: no draft row anywhere on it. */
function publishedCard(ruleIds = ["r1", "r2"]) {
  return buildPolicyCards(
    [policy(ruleIds)],
    ruleIds.map((id) => ({ rule: rule(id) })),
  )[0];
}

/** A card of draft rows, each at the state given. */
function candidateCard(states: Record<string, string>) {
  const ids = Object.keys(states);
  return buildPolicyCards(
    [policy(ids)],
    ids.map((id) => {
      const row = draft(id, states[id]);
      return { rule: row.rule, review_status: row.review_status, id: row.id };
    }),
  )[0];
}

describe("a sealed record reports no review to be in progress", () => {
  it("gives a published card no progress at all", () => {
    expect(policyRecord(publishedCard()).progress).toBeNull();
  });

  it("does not read a published card's record ids as decisions taken", () => {
    // The failure this replaces: `allIds − reviewableIds` on a published card
    // is `2 − 0`, which reported both rules of a sealed policy as just decided.
    const card = publishedCard(["r1", "r2"]);
    expect(card.allIds).toHaveLength(2);
    expect(card.reviewableIds).toHaveLength(0);
    expect(policyRecord(card).progress).toBeNull();
  });

  it("still reports progress where there are draft rows to decide", () => {
    const record = policyRecord(candidateCard({ r1: "candidate", r2: "approved" }));
    expect(record.progress).not.toBeNull();
    expect(record.progress?.decided).toBe(1);
    expect(record.progress?.open).toBe(1);
  });

  it("reports a fully settled candidate as settled, not as sealed", () => {
    // A candidate whose rules have all been decided still holds its rows, and
    // "every rule decided" is true and worth reading there. Only the absence of
    // rows means there was never a review.
    const record = policyRecord(candidateCard({ r1: "approved", r2: "approved" }));
    expect(record.progress).toEqual({ decided: 2, open: 0 });
  });

  it("counts a rejected rule as still open, because it may be reconsidered", () => {
    // "Open" here means a decision may be taken now, not that none ever was.
    // Rejection does not close a draft row — it can be revised and re-decided —
    // so a policy holding one is not finished, and must not read as finished.
    expect(policyRecord(candidateCard({ r1: "rejected", r2: "approved" })).progress).toEqual({
      decided: 1,
      open: 1,
    });
  });

  it("carries the same rules either way, so only the progress question differs", () => {
    expect(policyRecord(publishedCard(["r1", "r2"])).rules.map((r) => r.rule_id)).toEqual(
      policyRecord(candidateCard({ r1: "candidate", r2: "candidate" })).rules.map((r) => r.rule_id),
    );
  });
});

describe("a rule's own words are the way into it", () => {
  function renderCard(props: Partial<React.ComponentProps<typeof PublishedPolicyCard>> = {}) {
    const card = publishedCard(["r1", "r2"]);
    const rendered = render(
      <PublishedPolicyCard
        card={card}
        open={false}
        selectedForExport={false}
        indeterminateForExport={false}
        onToggleExportSelection={() => {}}
        onOpen={() => {}}
        onSelectRule={() => {}}
        onToggleRule={() => {}}
        policySetKey="a-set"
        policyVersionId="a-version"
        {...props}
      />,
    );
    return { card, ...rendered };
  }

  it("renders the statement as a real button, not as text", () => {
    renderCard();
    const rows = screen.getAllByTestId("policy-card-rule");
    for (const row of rows) {
      const opener = within(row).getByTestId("policy-card-rule-open");
      expect(opener.tagName).toBe("BUTTON");
      // A real button is keyboard-reachable without help. A div with a click
      // handler needs a role and a tabindex and still misses half of it.
      expect(opener.getAttribute("role")).toBeNull();
    }
  });

  it("opens the rule the reader clicked, not the first one", () => {
    const onSelectRule = vi.fn();
    renderCard({ onSelectRule });
    const second = screen.getAllByTestId("policy-card-rule")[1];
    fireEvent.click(within(second).getByTestId("policy-card-rule-open"));
    expect(onSelectRule).toHaveBeenCalledTimes(1);
    expect(onSelectRule.mock.calls[0][0].rule_id).toBe("r2");
  });

  it("wraps the statement only, leaving the controls beside it out of the button", () => {
    // Nesting a button inside a button is invalid, and the inner one loses its
    // place in the tab order. The row's menu and its Ask control must stay
    // reachable in their own right.
    renderCard();
    const row = screen.getAllByTestId("policy-card-rule")[0];
    const opener = within(row).getByTestId("policy-card-rule-open");
    expect(opener.querySelector("button")).toBeNull();
    expect(within(row).getAllByRole("button").length).toBeGreaterThan(1);
  });

  it("marks the row the panel is showing, and only that row", () => {
    renderCard({ selectedRuleId: "r2" });
    const rows = screen.getAllByTestId("policy-card-rule");
    expect(rows.filter((row) => row.getAttribute("aria-current") === "true")).toHaveLength(1);
    expect(rows[1].getAttribute("aria-current")).toBe("true");
  });

  it("marks no row when the panel is showing the policy", () => {
    // Absent and "none selected" are the same thing here. A row marked while
    // the panel shows the whole policy would say the reader is somewhere they
    // are not.
    renderCard({ selectedRuleId: null });
    const rows = screen.getAllByTestId("policy-card-rule");
    expect(rows.some((row) => row.getAttribute("aria-current") === "true")).toBe(false);
  });

  it("does not put a click handler on the row itself", () => {
    // A row-wide handler swallows every control inside it, which is how the
    // badges and the menu stopped being independently clickable elsewhere.
    const onSelectRule = vi.fn();
    renderCard({ onSelectRule });
    const row = screen.getAllByTestId("policy-card-rule")[0];
    fireEvent.click(row);
    expect(onSelectRule).not.toHaveBeenCalled();
  });

  it("asks for the policy, not for a rule, when the heading is clicked", () => {
    // The reported fault, at its source: the heading is the policy, so it has
    // to raise the policy. Opening its first rule instead answered a question
    // about one rule of several while the reader was pointing at all of them.
    const onOpen = vi.fn();
    const onSelectRule = vi.fn();
    renderCard({ onOpen, onSelectRule });
    fireEvent.click(screen.getByRole("button", { name: /A heading/ }));
    expect(onOpen).toHaveBeenCalledTimes(1);
    expect(onSelectRule).not.toHaveBeenCalled();
  });
});

describe("the panel is brought back only when it cannot be seen", () => {
  // The card list is taller than the panel beside it, so a reader who scrolled
  // down to reach a rule has scrolled the panel off the top of the window. The
  // click then answers them somewhere they are not looking, which is
  // indistinguishable from the click having done nothing — and "nothing
  // happened" is exactly what was reported.
  const windowHeight = 800;

  it("counts a panel above the window as out of sight", () => {
    expect(isOutsideWindow({ top: -900, bottom: -100 }, windowHeight)).toBe(true);
  });

  it("counts a panel below the window as out of sight", () => {
    expect(isOutsideWindow({ top: 900, bottom: 1700 }, windowHeight)).toBe(true);
  });

  it("leaves a panel that is partly visible alone", () => {
    // Both partial cases. Pulling the page under a reader to gain a few pixels
    // of a panel they are already reading is worse than leaving them still.
    expect(isOutsideWindow({ top: -100, bottom: 700 }, windowHeight)).toBe(false);
    expect(isOutsideWindow({ top: 700, bottom: 1500 }, windowHeight)).toBe(false);
  });

  it("leaves a fully visible panel alone", () => {
    expect(isOutsideWindow({ top: 40, bottom: 760 }, windowHeight)).toBe(false);
  });

  it("treats a panel resting exactly on either edge as out of sight", () => {
    // Zero visible pixels is not visible. This is also what an unmeasured node
    // reports, so the boundary has to fall on the side that brings it back.
    expect(isOutsideWindow({ top: -800, bottom: 0 }, windowHeight)).toBe(true);
    expect(isOutsideWindow({ top: windowHeight, bottom: 1600 }, windowHeight)).toBe(true);
  });
});
