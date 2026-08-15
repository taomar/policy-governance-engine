/**
 * The condition on which this control was allowed to exist.
 *
 * A filter across the review queue was deleted today because it made a policy
 * card a fragment: it showed three of eighteen rules while `Approve policy`
 * still presented itself as a policy-level act. A reviewer read "3 of 18" and
 * had to ask what it meant, which is the message failing.
 *
 * These chips narrow one policy the reviewer already has open, and they must
 * never repeat that fault. Narrowing the view may not change what an action
 * decides, and — because that is invisible unless said — the interface has to
 * say so while a focus is in force. Every test below is that one requirement
 * looked at from a different side.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";

import { composeFocus, recordStance, type RecordStance } from "../recordStance";
import { PolicyCompositionChips } from "./PolicyCompositionChips";

afterEach(cleanup);

type Record_ = { effect?: { type?: string | null } | null };

const withEffect = (type: unknown): Record_ => ({ effect: { type } }) as Record_;

const MIXED: Record_[] = [
  withEffect("require_action"),
  withEffect("deny"),
  withEffect("allow"),
  withEffect("informational"),
  withEffect("informational"),
];

function show(records: Record_[], focus: RecordStance | null = null) {
  const onFocus = vi.fn();
  const composition = composeFocus(records, recordStance, focus);
  const { container } = render(
    <PolicyCompositionChips composition={composition} onFocus={onFocus} />,
  );
  return { onFocus, composition, container };
}

const chips = () => screen.queryAllByRole("button");
const pressed = () => chips().filter((chip) => chip.getAttribute("aria-pressed") === "true");
const consequence = () => screen.queryByRole("status")?.textContent?.trim() ?? "";

describe("narrowing the view never narrows the decision", () => {
  it("says what approving decides, whenever anything is narrowed", () => {
    // The load-bearing sentence. Without it this control reintroduces exactly
    // the ambiguity that got its predecessor deleted.
    show(MIXED, "supplies-meaning");

    expect(consequence()).toMatch(/Approving this policy decides all 5/);
  });

  it("names the whole policy in that sentence, not the part on screen", () => {
    // "Approving decides all 2" under a focus showing 2 of 5 would be the old
    // fault in new words.
    show(MIXED, "supplies-meaning");
    const said = consequence();

    expect(said).toContain("2 of 5");
    expect(said).toMatch(/decides all 5\b/);
    expect(said).not.toMatch(/decides all 2\b/);
  });

  it("says the rest are still here, so nothing reads as removed", () => {
    show(MIXED, "decides");

    expect(consequence()).toMatch(/still on this policy/i);
  });

  it("says nothing extra when everything is shown, because there is nothing to warn of", () => {
    show(MIXED, null);

    expect(consequence()).toBe("");
  });

  it("keeps that sentence in the tree so a change to it is announced", () => {
    // A caller that renders the sentence only while narrowed replaces a node
    // rather than changing one, and a polite live region announces nothing for
    // a node that has just arrived.
    show(MIXED, null);
    expect(screen.getByRole("status")).toBeTruthy();
  });
});

describe("a reviewer can always tell which state they are in", () => {
  it("shows every record and marks All until they choose otherwise", () => {
    show(MIXED, null);

    expect(pressed()).toHaveLength(1);
    expect(pressed()[0].textContent).toMatch(/^All 5 rules$/);
  });

  it("marks exactly one choice, whichever it is", () => {
    for (const focus of [null, "decides", "supplies-meaning"] as const) {
      cleanup();
      show(MIXED, focus);
      expect(pressed()).toHaveLength(1);
    }
  });

  it("marks All when asked for a kind this policy does not hold", () => {
    // Otherwise the reviewer sees every rule with no chip pressed, which is a
    // state they cannot name and cannot leave on purpose.
    cleanup();
    show([withEffect("deny"), withEffect("allow"), {}], "supplies-meaning");

    expect(pressed()).toHaveLength(1);
    expect(pressed()[0].textContent).toMatch(/^All 3 rules$/);
  });

  it("is one click back to everything, from any focus", () => {
    const { onFocus } = show(MIXED, "decides");
    fireEvent.click(screen.getByText(/^All 5 rules$/));

    expect(onFocus).toHaveBeenCalledWith(null);
  });

  it("lets the pressed chip itself clear the focus, so a mis-click costs nothing", () => {
    const { onFocus, composition } = show(MIXED, "decides");
    const chip = chips().find((one) => one.getAttribute("aria-pressed") === "true");
    // The pressed chip here is `All` only when focus is null; under a focus the
    // pressed one is that stance's own chip.
    expect(composition.focus).toBe("decides");
    fireEvent.click(chip as HTMLElement);

    expect(onFocus).toHaveBeenCalledWith(null);
  });
});

describe("the choices offered are whatever the policy holds", () => {
  it("offers no control at all for a policy of one kind", () => {
    // Not a disabled control and not a single chip: a choice with one option is
    // a click that teaches nothing.
    show([withEffect("deny"), withEffect("require_action")]);

    expect(chips()).toHaveLength(0);
  });

  it("never offers a choice reading zero", () => {
    show([withEffect("deny"), withEffect("informational")]);

    for (const chip of chips()) expect(chip.textContent).not.toMatch(/\b0\b/);
  });

  it("offers no chip for a kind the policy does not hold", () => {
    show([withEffect("deny"), withEffect("informational")]);
    const labels = chips().map((chip) => chip.textContent ?? "");

    expect(labels.some((label) => /does not state/i.test(label))).toBe(false);
  });

  it("offers one for a record stating no effect, rather than folding it into another", () => {
    show([withEffect("deny"), withEffect("informational"), {}]);
    const labels = chips().map((chip) => chip.textContent ?? "");

    expect(labels.some((label) => /does not state/i.test(label))).toBe(true);
  });

  it("counts the same records the chips are drawn from", () => {
    // The chips' counts must sum to the total the All chip states, or a reviewer
    // reading them against each other is misled by arithmetic that looks
    // checkable.
    const records = [
      ...Array.from({ length: 4 }, () => withEffect("require_action")),
      ...Array.from({ length: 7 }, () => withEffect("informational")),
      {},
    ];
    show(records);
    const [all, ...rest] = chips().map((chip) => chip.textContent ?? "");
    const parts = rest.flatMap((label) =>
      [...label.matchAll(/(\d+)/g)].map((match) => Number(match[1])),
    );

    expect(all).toBe(`All ${records.length} rules`);
    expect(parts.reduce((sum, one) => sum + one, 0)).toBe(records.length);
  });

  it("uses the same words as the summary line above it", () => {
    // So a reviewer who read "4 decide cases · 8 supply meanings" recognises the
    // chips as the same fact rather than a second opinion about it.
    const { composition } = show(MIXED);
    const labels = chips().map((chip) => chip.textContent ?? "");

    for (const entry of composition.tally) {
      const phrase =
        entry.stance === "decides"
          ? `${entry.count} decide cases`
          : `${entry.count} supply meanings`;
      expect(labels).toContain(phrase);
    }
  });
});

describe("the control is reachable without a mouse", () => {
  it("draws real buttons rather than clickable text", () => {
    show(MIXED);

    for (const chip of chips()) expect(chip.tagName).toBe("BUTTON");
  });

  it("states which choice is in force, for a reader who cannot see the fill", () => {
    show(MIXED, "decides");

    for (const chip of chips()) expect(chip.hasAttribute("aria-pressed")).toBe(true);
  });

  it("announces the narrowed list politely rather than interrupting", () => {
    show(MIXED, "decides");
    const region = screen.getByRole("status");

    expect(region.getAttribute("aria-live")).toBe("polite");
  });

  it("names the group of choices, so it is not an unlabelled row of buttons", () => {
    const { container } = show(MIXED);
    const group = container.querySelector('[role="group"]') as HTMLElement;
    const labelledBy = group.getAttribute("aria-labelledby") as string;

    expect(within(group).getByText("Show").id).toBe(labelledBy);
  });
});

describe("no choice offered here is a lesser one", () => {
  /** Words that grade a record, its route, or the reviewer's attention. */
  const RANKING =
    /\b(only|just|merely|simply|mere|minor|lesser|trivial|incidental|unimportant|boilerplate|noise|filler|ignorab\w*|safely ignor\w*|skip|skippable|low.?value|less important|not important|real rules?|actual rules?|proper rules?|deficien\w*|gap|limitation|shortcoming|gaps?|cannot|can't|unable|fail\w*|weak\w*|missing)\b/i;

  const everySentence = (records: Record_[], focus: RecordStance | null) => {
    cleanup();
    const { container } = render(
      <PolicyCompositionChips
        composition={composeFocus(records, recordStance, focus)}
        onFocus={() => {}}
      />,
    );
    return (container.textContent ?? "").trim();
  };

  const shapes: Record_[][] = [
    MIXED,
    [withEffect("deny"), withEffect("informational")],
    [withEffect("deny"), {}],
    [withEffect("informational"), {}],
    [withEffect("deny"), withEffect("informational"), {}],
    [withEffect("an_effect_this_app_has_never_met"), withEffect("informational")],
  ];

  it("grades no record and no route, in any state it can be in", () => {
    const offences: string[] = [];
    for (const shape of shapes) {
      for (const focus of [null, "decides", "supplies-meaning", "unstated"] as const) {
        const said = everySentence(shape, focus);
        if (RANKING.test(said)) offences.push(said);
        if (/\b(ai|deterministic|ai.?ready|automat\w*|manual)\b/i.test(said)) offences.push(said);
      }
    }
    expect(offences).toEqual([]);
  });

  it("names no filter, tab or lane, because none of those is what this is", () => {
    // The predecessor pointed at a control by name and outlived it. This one
    // describes what is on screen and what an action decides, and names no
    // navigation at all.
    const offences: string[] = [];
    for (const shape of shapes) {
      for (const focus of [null, "decides", "supplies-meaning", "unstated"] as const) {
        const said = everySentence(shape, focus);
        if (/\b(filter|filtered|tab|lane|glossary|elsewhere|another (view|page|screen))\b/i.test(said)) {
          offences.push(said);
        }
      }
    }
    expect(offences).toEqual([]);
  });

  it("supplies no vocabulary of its own about what documents contain", () => {
    // The categories are what a record does, never what it is about. A word
    // here naming a topic would be the start of a domain list.
    const said = everySentence(MIXED, "supplies-meaning");

    expect(said).not.toMatch(
      /\b(employee|staff|leave|salary|policy area|hr|department|category|topic|subject)\b/i,
    );
  });
});
