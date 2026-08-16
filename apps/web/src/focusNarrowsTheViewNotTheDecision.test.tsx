/**
 * Narrowing the rule list changes what is on screen and nothing else.
 *
 * THE FAILURE THIS EXISTS TO PREVENT
 *
 * Earlier today this app carried a filter that chose rules across policies, so
 * a card could show three of a policy's eighteen rules while its one button
 * still said `Approve policy`. The reviewer read "3 of 18" and asked what it
 * decided. They were right to ask: the card was a fragment presenting itself as
 * a whole, and the answer needed a footnote. We deleted the filter.
 *
 * This control looks like that one and must never behave like it. The
 * difference is real — this narrows one policy the reviewer already has open,
 * and is a reading aid over rules that are all still on the policy — but the
 * difference is only worth anything if it is visible and enforced:
 *
 *   - `Approve` decides the whole policy whichever chip is pressed. The panel
 *     cannot narrow it even by accident, because the handler takes no argument.
 *   - The reviewer is told so, in the panel, whenever anything is narrowed.
 *   - Every rule is one click from being back on screen, and the chip that
 *     brings it back is always drawn and always says how many there are.
 *
 * AND THE NUMBERING IS THE DOCUMENT'S
 *
 * Each rule carries its ordinal — its place in the document. If narrowing
 * renumbered them, rule 7 would become rule 2 with nothing announcing it, and
 * a reviewer citing "rule 2" to a colleague would cite a different rule than
 * the one they meant. Ordinals are spent over every rule of the policy before
 * the narrowing is applied, so they are stable under it.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import type { AssembledPolicy, CandidateRule, CanonicalRule } from "./api";
import { ActorProvider } from "./ActorContext";
import type { PolicyCard } from "./policyCards";
import { PolicyDetailPanel } from "./components/PolicyDetailPanel";

const panelSource = Object.values(
  import.meta.glob("./components/PolicyDetailPanel.tsx", {
    query: "?raw",
    import: "default",
    eager: true,
  }),
)[0] as string;

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
  vi.unstubAllGlobals();
});

/**
 * `effectType` is the only thing these fixtures vary, because it is the only
 * thing the grouping reads. Nothing here says what a rule is *about*.
 */
function canonical(ruleId: string, effectType: string | null): CanonicalRule {
  return {
    schema_version: "1.0",
    policy_set_id: "set",
    policy_version_id: "draft",
    rule_id: ruleId,
    rule_revision: 1,
    title: `Summary line for ${ruleId}`,
    description: `The words the document uses for ${ruleId}`,
    rule_type: "obligation",
    authority: { level: "ai_drafted", owner: "formulator", rank: 0 },
    scope: { jurisdictions: [], organizational_units: [], personas: [], processes: [] },
    condition: { type: "all", all: [] },
    attributes: { applies: [], outcome: [] },
    effect: effectType === null ? { action: "act" } : { type: effectType, action: "act" },
    required_facts: [],
    exceptions: [],
    priority: 0,
    effective_from: "2026-01-01",
    effective_to: null,
    machine_executable: false,
    ambiguity_status: "clear",
    review_status: "candidate",
    evidence: [],
    lineage: {
      extraction_run_id: "run",
      deployment_name: "model",
      prompt_version: "v1",
      parser_version: "v1",
      schema_version: "1.0",
    },
    category: "general",
    tags: [],
    group_label: "",
    related_rule_ids: [],
    is_explicit_override: false,
    supersedes_rule_ids: [],
    advice: [],
  } as unknown as CanonicalRule;
}

function candidate(ruleId: string, effectType: string | null): CandidateRule {
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
    delta_status: null,
    reworded: false,
    baseline_candidate_id: null,
    superseded_by_candidate_id: null,
    superseded_at: null,
    rule: canonical(ruleId, effectType),
  } as unknown as CandidateRule;
}

/** One passage holding the given rules, named by its key. */
interface PassageSpec {
  key: string;
  rules: { id: string; effect: string | null }[];
}

function cardFor(key: string, passages: PassageSpec[]): PolicyCard {
  const blocks = passages.map((spec) => ({
    passage: {
      key: spec.key,
      source_elements: spec.key,
      page: 11,
      rule_count: spec.rules.length,
      rules: [],
      text: `Verbatim words of ${spec.key}`,
    },
    rules: spec.rules.map((rule) => ({
      rule_id: rule.id,
      // `rule` is the field every consumer reads; `candidate` is the optional
      // draft row a published record would not have. Fixtures carry both so
      // this file tests the shape the app actually receives.
      rule: canonical(rule.id, rule.effect),
      reviewStatus: "candidate",
      recordId: `record-${rule.id}`,
      candidate: candidate(rule.id, rule.effect),
      evaluation_mode: "ai_ready" as const,
    })),
  }));
  const entries = blocks.flatMap((block) => block.rules);
  const policy = {
    key,
    heading: "Hiring relatives",
    heading_path: ["Recruitment", "Hiring relatives"],
    persisted: true,
    provision_id: key,
    document_version_id: "doc-1",
    source_elements: passages.map((p) => p.key).join(","),
    page: 11,
    rule_count: entries.length,
    passage_count: passages.length,
    route: "read",
    passages: [],
    rules: entries.map((entry) => ({ rule_id: entry.rule_id, title: entry.rule.title })),
  } as unknown as AssembledPolicy;
  return {
    policy,
    passages: blocks,
    rules: entries,
    hiddenByFilter: 0,
    reviewableIds: entries.map((entry) => entry.recordId),
    allIds: entries.map((entry) => entry.recordId),
    reviewStatuses: ["candidate"],
  } as unknown as PolicyCard;
}

/** A policy holding both kinds, with a meaning-supplying rule in the middle. */
const MIXED: PassageSpec[] = [
  {
    key: "p1-E1",
    rules: [
      { id: "R1", effect: "require_action" },
      { id: "R2", effect: "informational" },
      { id: "R3", effect: "deny" },
    ],
  },
  { key: "p1-E2", rules: [{ id: "R4", effect: "informational" }] },
];

function renderPanel(
  card: PolicyCard,
  overrides: { onApprove?: () => void } = {},
) {
  return render(
    <ActorProvider>
      <PolicyDetailPanel
        card={card}
        statusColor={() => "default"}
        statusLabel={() => "Pending"}
        onApprove={overrides.onApprove ?? (() => {})}
        onReject={() => {}}
        policySetKey="staff-handbook"
      />
    </ActorProvider>,
  );
}

/**
 * The rule list is not the tab that opens, so every test that reads it asks
 * the panel for it rather than assuming. Written as a helper so a change of
 * default tab breaks one line and not every test in the file.
 */
function revealTheRuleList() {
  const tab = screen
    .getAllByRole("tab")
    .find((element) => /reading/i.test(element.textContent ?? ""));
  if (!tab) throw new Error("the panel no longer offers a tab that lists the rules");
  fireEvent.click(tab);
}

function chips() {
  return screen
    .getAllByRole("button")
    .filter((button) => button.className.includes("composition-focus__chip"));
}

function chipNamed(pattern: RegExp) {
  const found = chips().find((button) => pattern.test(button.textContent ?? ""));
  if (!found) {
    throw new Error(
      `no chip matching ${pattern} among: ${chips()
        .map((button) => button.textContent)
        .join(" | ")}`,
    );
  }
  return found;
}

function shownRuleIds(): string[] {
  return screen
    .getAllByTestId("policy-detail-passage")
    .flatMap((passage) => Array.from(within(passage).queryAllByRole("listitem")))
    .map((item) => item.textContent ?? "")
    .flatMap((text) => {
      const match = /Summary line for (R\d+)/.exec(text);
      return match ? [match[1]] : [];
    });
}

describe("the reviewer may narrow one policy's rule list", () => {
  it("opens showing everything, whatever the policy holds", () => {
    renderPanel(cardFor("prov-1", MIXED));
    revealTheRuleList();
    expect(shownRuleIds()).toEqual(["R1", "R2", "R3", "R4"]);
    expect(chipNamed(/^All /).getAttribute("aria-pressed")).toBe("true");
  });

  it("draws no control at all for a policy whose rules are all of one kind", () => {
    renderPanel(
      cardFor("prov-2", [
        {
          key: "p2-E1",
          rules: [
            { id: "R1", effect: "require_action" },
            { id: "R2", effect: "deny" },
          ],
        },
      ]),
    );
    revealTheRuleList();
    // Both rules decide, so there is nothing to choose between and a chip would
    // only be a button that cannot change anything.
    expect(chips()).toHaveLength(0);
    expect(shownRuleIds()).toEqual(["R1", "R2"]);
  });

  it("never draws a chip for a kind the policy does not hold", () => {
    renderPanel(cardFor("prov-1", MIXED));
    revealTheRuleList();
    const labels = chips().map((button) => button.textContent ?? "");
    expect(labels.some((label) => /do not state which/.test(label))).toBe(false);
    // and nothing reads zero
    for (const label of labels) {
      const count = /(\d+)/.exec(label);
      expect(count).not.toBeNull();
      expect(Number(count?.[1])).toBeGreaterThan(0);
    }
  });

  it("narrows the list to the chosen kind and tracks the choice in aria-pressed", () => {
    renderPanel(cardFor("prov-1", MIXED));
    revealTheRuleList();
    fireEvent.click(chipNamed(/supply meanings/));
    expect(shownRuleIds()).toEqual(["R2", "R4"]);
    expect(chipNamed(/supply meanings/).getAttribute("aria-pressed")).toBe("true");
    expect(chipNamed(/^All /).getAttribute("aria-pressed")).toBe("false");
  });

  it("brings everything back in one click", () => {
    renderPanel(cardFor("prov-1", MIXED));
    revealTheRuleList();
    fireEvent.click(chipNamed(/supply meanings/));
    expect(shownRuleIds()).toEqual(["R2", "R4"]);
    fireEvent.click(chipNamed(/^All /));
    expect(shownRuleIds()).toEqual(["R1", "R2", "R3", "R4"]);
  });

  it("counts a rule whose effect is unstated as its own kind, not as either other", () => {
    renderPanel(
      cardFor("prov-3", [
        {
          key: "p3-E1",
          rules: [
            { id: "R1", effect: "require_action" },
            { id: "R2", effect: null },
          ],
        },
      ]),
    );
    revealTheRuleList();
    fireEvent.click(chipNamed(/does not state which|do not state which/));
    expect(shownRuleIds()).toEqual(["R2"]);
  });
});

describe("narrowing never changes what an action decides", () => {
  it("tells the reviewer the rest are still on the policy, and what Approve does", () => {
    renderPanel(cardFor("prov-1", MIXED));
    revealTheRuleList();
    fireEvent.click(chipNamed(/supply meanings/));
    const status = screen.getByRole("status");
    expect(status.textContent).toMatch(/Showing 2 of 4/);
    expect(status.textContent).toMatch(/still on this policy/);
    expect(status.textContent).toMatch(/Approving this policy decides all 4/);
  });

  it("says nothing when nothing is narrowed", () => {
    renderPanel(cardFor("prov-1", MIXED));
    revealTheRuleList();
    expect(screen.getByRole("status").textContent).toBe("");
  });

  it("still approves while a chip is active", () => {
    const approved: string[] = [];
    renderPanel(cardFor("prov-1", MIXED), { onApprove: () => approved.push("all") });
    revealTheRuleList();
    fireEvent.click(chipNamed(/supply meanings/));
    const approve = screen
      .getAllByRole("button")
      .find((button) => /^approve/i.test(button.textContent?.trim() ?? ""));
    expect(approve).toBeDefined();
    fireEvent.click(approve!);
    expect(approved).toEqual(["all"]);
  });

  it("cannot narrow an action even by accident, because the handler takes no scope", () => {
    // The strongest form of the guarantee available: `onApprove` is a nullary
    // callback and the button passes the reference straight through. There is
    // no argument for a view filter to travel down, so the safety is
    // structural rather than a rule someone must remember.
    expect(panelSource).toMatch(/onApprove\?:\s*\(\)\s*=>\s*void/);
    expect(panelSource).toMatch(/onClick=\{onApprove\}/);
    expect(panelSource).toMatch(/onClick=\{onReject\}/);
  });
});

describe("the numbering stays the document's", () => {
  it("does not renumber the rules that remain", () => {
    renderPanel(cardFor("prov-1", MIXED));
    revealTheRuleList();
    const ordinalsWhenWhole = screen
      .getAllByTestId("policy-detail-passage")
      .flatMap((passage) =>
        Array.from(passage.querySelectorAll(".policy-card__rule-ordinal")),
      )
      .map((node) => node.textContent);
    expect(ordinalsWhenWhole).toEqual(["1", "2", "3", "4"]);

    fireEvent.click(chipNamed(/supply meanings/));
    const ordinalsWhenNarrowed = screen
      .getAllByTestId("policy-detail-passage")
      .flatMap((passage) =>
        Array.from(passage.querySelectorAll(".policy-card__rule-ordinal")),
      )
      .map((node) => node.textContent);
    // R2 and R4 keep the places they hold in the document. Renumbering them
    // 1 and 2 would be a quiet lie about which rules these are.
    expect(ordinalsWhenNarrowed).toEqual(["2", "4"]);
  });

  it("drops a passage whole rather than leaving a quotation with no rules under it", () => {
    renderPanel(cardFor("prov-1", MIXED));
    revealTheRuleList();
    expect(screen.getAllByTestId("policy-detail-passage")).toHaveLength(2);
    fireEvent.click(chipNamed(/decide what happens/));
    const remaining = screen.getAllByTestId("policy-detail-passage");
    expect(remaining).toHaveLength(1);
    expect(remaining[0].getAttribute("data-passage")).toBe("p1-E1");
  });
});

describe("the choice belongs to the policy the reviewer is looking at", () => {
  it("is dropped when a different policy is opened", () => {
    const { rerender } = renderPanel(cardFor("prov-1", MIXED));
    revealTheRuleList();
    fireEvent.click(chipNamed(/supply meanings/));
    expect(shownRuleIds()).toEqual(["R2", "R4"]);

    rerender(
      <ActorProvider>
        <PolicyDetailPanel
          card={cardFor("prov-9", MIXED)}
          statusColor={() => "default"}
          statusLabel={() => "Pending"}
          onApprove={() => {}}
          onReject={() => {}}
          policySetKey="staff-handbook"
        />
      </ActorProvider>,
    );
    revealTheRuleList();
    // A new policy opens whole. Inheriting the last policy's narrowing would
    // hide rules the reviewer never chose to hide.
    expect(shownRuleIds()).toEqual(["R1", "R2", "R3", "R4"]);
    expect(chipNamed(/^All /).getAttribute("aria-pressed")).toBe("true");
  });

  it("does not persist anywhere, or reach a URL", () => {
    expect(panelSource).not.toMatch(/localStorage|sessionStorage|URLSearchParams|history\.(push|replace)State/);
  });
});

describe("the panel does not hold a second opinion about what a rule is", () => {
  it("reads the stance rather than re-deriving it", () => {
    // One derivation, in `recordStance.ts`. A panel that tested effect values
    // itself would be a second one, and the two would disagree the first time
    // a new effect kind arrived.
    expect(panelSource).toMatch(/composeFocus\(/);
    expect(panelSource).not.toMatch(/"informational"|'informational'/);
    expect(panelSource).not.toMatch(/"require_action"|'require_action'/);
    expect(panelSource).not.toMatch(/rule_type\s*===/);
  });

  it("says nothing about a rule being deficient, or the engine failing at one", () => {
    // The route-not-fault guard has been evaded five times by new phrasings, so
    // this checks the copy this file's feature adds rather than trusting that.
    const forbidden =
      /\b(cannot|can't|unable|fail(s|ed|ure)?|unsupported|not supported|too (hard|complex)|limitation|deficien\w*|only ai|fallback|falls back)\b/i;
    const chipCopy = [
      ...Array.from(panelSource.matchAll(/PolicyCompositionChips[\s\S]{0,200}/g)),
    ].join(" ");
    expect(forbidden.test(chipCopy)).toBe(false);
  });
});
