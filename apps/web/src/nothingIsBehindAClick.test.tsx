/**
 * Decision 2: nothing a reviewer must click to discover.
 *
 * THE FAILURE THIS EXISTS TO PREVENT
 *
 * Grouping a section's rules onto one card makes big cards. The largest
 * measured here holds 72 rules across 7 merged repeats of one heading. The
 * obvious response is an expander — show the passages, reveal the rules on
 * demand — and it is the wrong one, for a reason this product has already paid
 * for twice: an empty page that rendered like a full one, and a queue of 2,735
 * that was not a workload. Both were the interface telling a reviewer something
 * about the size of their job that was not true.
 *
 * A collapsed rule is worse than either, because the reviewer cannot know it is
 * there. The three-level outline — heading, then passage, then rule — is
 * structure, and structure is for reading. It is not a place to put things.
 *
 * WHAT IS ASSERTED, AND WHY IT IS A RENDER AND NOT A READ OF THE SOURCE
 *
 * The card is rendered and every rule the policy holds is looked for in the
 * output, with no interaction of any kind first. A source-level check ("no
 * `useState` named collapsed") would pass on a card that hid rules with CSS,
 * with `hidden`, or by slicing the array — three ways of doing the same thing
 * that share no syntax.
 *
 * Every count below is paired with a control that fails when nothing renders,
 * because `expect(missing).toHaveLength(0)` is also what a blank page returns.
 */

import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
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

function renderCard(policy: AssembledPolicy, candidates: CandidateRule[], open = false) {
  const [card] = buildPolicyCards([policy], candidates);
  render(
    <PolicyReviewCard
      card={card}
      selected={false}
      indeterminate={false}
      open={open}
      statusColor={() => "default"}
      statusLabel={(status) => status}
      findingsFor={() => 0}
      onToggleSelect={() => {}}
      onOpen={() => {}}
      onApprove={() => {}}
      onReject={() => {}}
    />,
  );
  return card;
}

describe("a policy card hides no rule behind an interaction", () => {
  it("draws every one of a large policy's rules with nothing clicked", () => {
    const { policy, candidates } = bigPolicy(LARGEST_MEASURED_POLICY, MERGED_REPEATS);
    const card = renderCard(policy, candidates);

    // CONTROL. If the fixture or the builder collapsed, the loop below would
    // iterate over nothing and the test would pass on an empty page.
    expect(card.rules).toHaveLength(LARGEST_MEASURED_POLICY);

    const missing = card.rules
      .map((r) => r.rule_id)
      .filter((ruleId) => screen.queryAllByText(`title ${ruleId}`).length === 0);

    expect(
      missing,
      `${missing.length} of ${card.rules.length} rules are not on the page until ` +
        "something is clicked. Structure groups rules; it does not store them.",
    ).toEqual([]);
  });

  it("draws every passage of a large policy too", () => {
    const { policy, candidates } = bigPolicy(LARGEST_MEASURED_POLICY, MERGED_REPEATS);
    const card = renderCard(policy, candidates);

    expect(card.passages.length).toBe(MERGED_REPEATS);
    // Each passage draws its own block, so the count of blocks is the count of
    // passages — a card that drew one block and listed 72 rules flat would fail
    // here while passing the test above.
    expect(screen.getAllByTestId("policy-passage")).toHaveLength(card.passages.length);
  });

  it("renders the same rules whether or not the card is the open one", () => {
    // `open` marks the card whose detail panel is showing. If it also gated
    // content, the queue would be a list of titles and the reviewer would have
    // to open each card to find out what was in it.
    const { policy, candidates } = bigPolicy(12, 3);

    renderCard(policy, candidates, false);
    const closed = screen.getAllByTestId("policy-card-rule").length;
    cleanup();

    renderCard(policy, candidates, true);
    const opened = screen.getAllByTestId("policy-card-rule").length;

    expect(closed).toBe(12);
    expect(opened).toBe(closed);
  });

  it("uses no element that conceals its children", () => {
    // Belt and braces with the queries above, which read the accessibility
    // tree and would not notice `<details>` — jsdom renders its children into
    // the DOM whether or not it is open, and Testing Library finds them.
    const { policy, candidates } = bigPolicy(LARGEST_MEASURED_POLICY, MERGED_REPEATS);
    const { container } = (() => {
      const [card] = buildPolicyCards([policy], candidates);
      return render(
        <PolicyReviewCard
          card={card}
          selected={false}
          indeterminate={false}
          open={false}
          statusColor={() => "default"}
          statusLabel={(status) => status}
          findingsFor={() => 0}
          onToggleSelect={() => {}}
          onOpen={() => {}}
        />,
      );
    })();

    expect(container.querySelectorAll("details")).toHaveLength(0);
    expect(container.querySelectorAll("[hidden]")).toHaveLength(0);
    expect(container.querySelectorAll('[aria-expanded="false"]')).toHaveLength(0);
  });

  it("shows a one-rule policy the same way as a large one", () => {
    // CONTROL for all of the above, which a card that special-cased large
    // policies could satisfy while changing the ordinary case.
    const { policy, candidates } = bigPolicy(1, 1);
    renderCard(policy, candidates);

    expect(screen.getAllByTestId("policy-card-rule")).toHaveLength(1);
    expect(screen.getAllByTestId("policy-passage")).toHaveLength(1);
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
