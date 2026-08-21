/**
 * THE LOGIC TAB NAMES THINGS, AND NAMES THEM AS THE DOCUMENT DOES.
 *
 * WHAT THIS EXISTS TO PREVENT
 *
 * Above the logic trees sat a panel that counted attributes across the policy
 * and grouped rules by which attributes they filled. A reviewer's verdict was
 * that it looked poor and showed no value, and that the logic below it should
 * stay. It was deleted, and the first half of this file holds the deletion:
 * nothing it named may have stopped reaching the reviewer, and no later tidy-up
 * may restore an aggregate that counts what happens to be on screen.
 *
 * Below it, each passage was headed by the run of source element identifiers it
 * was addressed by -- `p9-E000071`. That is the pipeline's name for a passage,
 * printed on a screen written for a compliance officer, who cites the heading
 * the document itself gives. So the heading leads and the run of elements is
 * kept, demoted, as the reference it is.
 *
 * WHY THE SOURCE TEXT IS THE ONE THING BEHIND A DISCLOSURE
 *
 * This view's promise is that every attribute a rule states, and every one it
 * does not, is on screen without clicking anything. The sentence the rule was
 * read out of is not one of those: it is what a reviewer checks them against,
 * it is printed in full on the Reading tab, and it is long. So it is offered
 * per rule and closed, and the tests here pin that nothing else ever joins it.
 */

import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import type { CandidateRule, PolicyAttribute } from "./api";
import { fromDraftRow } from "./policyCards";
import type { PolicyCard, PolicyCardPassage, PolicyCardRule } from "./policyCards";
import { policyLogicShape } from "./policyLogicShape";
import { PolicyLogicTable } from "./components/PolicyLogicTable";

beforeAll(() => {
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

afterEach(cleanup);

function row(attribute: string, text: string): PolicyAttribute {
  return { attribute, text, fact: null, data_type: null } as PolicyAttribute;
}

function cardRule(
  ruleId: string,
  options: {
    title?: string;
    statedText?: string | null;
    section?: string | null;
    route?: string;
  } = {},
): PolicyCardRule {
  return {
    rule_id: ruleId,
    evaluation_mode: options.route ?? "deterministic",
    ...fromDraftRow({
      id: `record-${ruleId}`,
      review_status: "candidate",
      rule: {
        rule_id: ruleId,
        title: options.title ?? `What ${ruleId} requires`,
        rule_type: "obligation",
        effect: { type: "require_action", action: "" },
        condition: { type: "all", all: [] },
        attributes: { applies: [row("subject", `subject of ${ruleId}`)], outcome: [] },
        description: options.statedText ?? undefined,
        evidence:
          options.section === null
            ? []
            : [{ section: options.section ?? "Chapter 3 — Leave", quote: "" }],
      },
    } as unknown as CandidateRule),
  } as unknown as PolicyCardRule;
}

function card(
  blocks: { key: string; page?: number | null; rules: PolicyCardRule[] }[],
): PolicyCard {
  const passages: PolicyCardPassage[] = blocks.map((block) => ({
    passage: {
      key: block.key,
      page: block.page ?? null,
    } as PolicyCardPassage["passage"],
    rules: block.rules,
  }));
  const rules = blocks.flatMap((block) => block.rules);
  return {
    policy: { key: "policy-1", rule_count: rules.length } as PolicyCard["policy"],
    passages,
    rules,
    hiddenByFilter: 0,
    reviewableIds: rules.map((rule) => rule.recordId),
    allIds: rules.map((rule) => rule.recordId),
    reviewStatuses: ["candidate"],
    // No set: this fixture exercises what a card says, not where it was
    // published from. Absent, so nothing is looked up by it.
    policy_set_key: null,
  };
}

describe("the panel that counted attributes across the policy is gone", () => {
  it("writes no aggregate count, and no group of rules by their shape", () => {
    const view = render(
      <PolicyLogicTable
        card={card([{ key: "p9-E000071", page: 9, rules: [cardRule("a"), cardRule("b")] }])}
      />,
    ).container;

    expect(screen.queryByTestId("policy-logic-coverage")).toBeNull();
    expect(view.querySelectorAll(".policy-logic__shapes")).toHaveLength(0);
    expect(view.querySelectorAll(".policy-logic__shape-rule")).toHaveLength(0);
    expect(view.textContent).not.toContain("What each rule states");
    expect(view.textContent).not.toMatch(/attributes across them/i);
  });

  it("keeps computing what the panel showed, so nothing downstream lost a fact", () => {
    // The deletion is a rendering decision. The shape of the policy is still
    // derived, still carries each rule's absent list, and is still what the
    // trees are drawn from -- a later surface that wants the aggregate can have
    // it without recovering deleted arithmetic.
    const shape = policyLogicShape(
      card([{ key: "p9-E000071", page: 9, rules: [cardRule("a"), cardRule("b")] }]),
    );
    expect(shape.columns.length).toBeGreaterThan(0);
    expect(shape.total).toBe(2);
  });
});

describe("a passage is headed by what the document calls it", () => {
  it("leads with the cited heading and keeps the element run as a reference", () => {
    render(
      <PolicyLogicTable
        card={card([
          {
            key: "p9-E000071",
            page: 9,
            rules: [cardRule("a", { section: "Chapter 3 — Leave" })],
          },
        ])}
      />,
    );

    // What a compliance officer cites.
    expect(screen.getByText("Chapter 3 — Leave")).toBeTruthy();
    // The pipeline's address for the same passage. Kept, because somebody
    // tracing a record pastes it into a query -- and demoted, because it was
    // standing where the heading belongs.
    const reference = screen.getByText(/p9-E000071/);
    expect(reference.className).toContain("policy-logic__passage-key");
    expect(screen.getByText(/Page 9/)).toBeTruthy();
  });

  it("keeps both headings when a passage's rules cite two", () => {
    render(
      <PolicyLogicTable
        card={card([
          {
            key: "p9-E000071",
            page: 9,
            rules: [
              cardRule("a", { section: "Chapter 3 — Leave" }),
              cardRule("b", { section: "Chapter 4 — Absence" }),
            ],
          },
        ])}
      />,
    );
    // Choosing one silently would file the passage under a heading the document
    // may not put it under.
    const head = document.querySelector(".policy-logic__passage-heading");
    expect(head?.textContent).toContain("Chapter 3 — Leave");
    expect(head?.textContent).toContain("Chapter 4 — Absence");
  });

  it("says nothing rather than falling back to the element run as a heading", () => {
    render(
      <PolicyLogicTable
        card={card([{ key: "p9-E000071", page: 9, rules: [cardRule("a", { section: null })] }])}
      />,
    );
    // No rule of the passage recorded a heading. That is a fact about how the
    // document was read; filling it in with the key would state something the
    // document did not.
    expect(document.querySelector(".policy-logic__passage-heading")).toBeNull();
    expect(screen.getByText(/p9-E000071/)).toBeTruthy();
  });

  it("omits the page where the passage recorded none", () => {
    render(
      <PolicyLogicTable
        card={card([{ key: "p9-E000071", page: null, rules: [cardRule("a")] }])}
      />,
    );
    expect(screen.queryByText(/^Page /)).toBeNull();
  });
});

describe("a rule is headed by what it states, not by its id", () => {
  it("prints the rule's own words, marked as the record's rather than ours", () => {
    render(
      <PolicyLogicTable
        card={card([
          {
            key: "p9-E000071",
            page: 9,
            rules: [cardRule("a", { title: "Staff shall request leave in writing" })],
          },
        ])}
      />,
    );
    const title = document.querySelector(".policy-logic__rule-title");
    expect(title?.textContent).toBe("Staff shall request leave in writing");
    // So every scan of this app's own copy skips it: it may say anything.
    expect(title?.getAttribute("data-verbatim")).toBe("true");
  });

  it("offers the source sentence per rule, closed, and never anything else", () => {
    const view = render(
      <PolicyLogicTable
        card={card([
          {
            key: "p9-E000071",
            page: 9,
            rules: [
              cardRule("a", {
                statedText: "An employee shall submit a written request before taking leave.",
              }),
            ],
          },
        ])}
      />,
    ).container;

    // The source quotation is always visible (not behind a disclosure — F1).
    const quotes = [...view.querySelectorAll("blockquote[data-testid='policy-logic-source']")];
    expect(quotes).toHaveLength(1);
    expect(quotes[0].textContent).toContain(
      "An employee shall submit a written request before taking leave.",
    );

    // The reviewer's own checks stay in the open. This is the invariant the
    // whole view is built on, and the one thing a disclosure must never take.
    expect(quotes[0].querySelectorAll(".policy-attr-name")).toHaveLength(0);
    expect(quotes[0].querySelectorAll("[data-absent]")).toHaveLength(0);
    expect(view.querySelectorAll(".policy-attr-name").length).toBeGreaterThan(0);
  });

  it("offers no disclosure for a rule whose source text was not stored", () => {
    const view = render(
      <PolicyLogicTable
        card={card([
          { key: "p9-E000071", page: 9, rules: [cardRule("a", { statedText: null })] },
        ])}
      />,
    ).container;
    // A summary opening onto nothing is worse than no summary: it reads as text
    // this app is withholding.
    expect(view.querySelectorAll("details")).toHaveLength(0);
  });
});

describe("the three new runs of document words carry their own direction", () => {
  // The corpus this app is pointed at is substantially Arabic, and the rule this
  // enforces is that direction belongs to each run of text and never to a box
  // drawn around it. The heading, the rule's stated title and the source
  // sentence are the three places this view began printing the document's own
  // words, so each is checked here rather than trusted to a convention.
  const ARABIC = "يجب على الموظف تقديم طلب خطي";

  function arabicCard() {
    return card([
      {
        key: "p9-E000071",
        page: 9,
        rules: [cardRule("a", { title: ARABIC, statedText: ARABIC, section: ARABIC })],
      },
    ]);
  }

  it.each([
    [".policy-logic__passage-heading", "the heading the document gives the passage"],
    [".policy-logic__rule-title", "the sentence the rule states"],
    [".policy-logic__source-text", "the source text behind the disclosure"],
  ])("marks %s right-to-left on the run itself", (selector) => {
    const view = render(<PolicyLogicTable card={arabicCard()} />).container;
    const host = view.querySelector(selector);
    expect(host).not.toBeNull();

    // `<bdi>` is what isolates a run from its neighbours. Finding the Arabic
    // inside one, carrying its own `dir`, is the whole claim: a container that
    // flipped its children instead would have no such element.
    const runs = [...host!.querySelectorAll("bdi")];
    const arabic = runs.filter((run) => /[\u0600-\u06FF]/.test(run.textContent ?? ""));
    expect(arabic.length).toBeGreaterThan(0);
    for (const run of arabic) {
      expect(run.getAttribute("dir")).toBe("rtl");
    }
  });

  it("reproduces the stored text exactly, character for character", () => {
    const view = render(<PolicyLogicTable card={arabicCard()} />).container;
    const title = view.querySelector(".policy-logic__rule-title");
    // Splitting into runs must be reversible. A reviewer who copies a rule is
    // owed the document's characters, not what the screen happened to show.
    expect(title?.textContent).toBe(ARABIC);
  });

  it("does not push direction onto the block that holds several rules", () => {
    const view = render(<PolicyLogicTable card={arabicCard()} />).container;
    // The wall a container-level `dir` builds: it reorders every sibling,
    // including this app's own English labels, and it does so on the strength of
    // whichever rule happened to be read first.
    for (const selector of [".policy-logic__passage-head", "[data-testid='policy-logic']"]) {
      const box = view.querySelector(selector);
      expect(box?.getAttribute("dir") ?? null).toBeNull();
    }
  });
});
