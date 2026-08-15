/**
 * What a policy is made of, said on the card the reviewer works from.
 *
 * A reviewer choosing between two lists had to decide which side a policy fell
 * on before they could see it. Showing the mix instead means they never choose:
 * a section that settles three cases and supplies fifteen meanings says so, and
 * both halves stay in view.
 *
 * The axis is not decided here. `policyRecordFacts` already reads the effect the
 * extractor recorded, and the published card already states the same fact from
 * the same function. A second reading of it on this surface would be two answers
 * to one question, which is the drift these surfaces are being pulled out of. So
 * what this file tests is that the card states the shared answer and composes
 * nothing of its own.
 *
 * Nothing here is a phrase from any document, and no count in it is a
 * measurement of one.
 */
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render } from "@testing-library/react";
import { PolicyReviewCard } from "./PolicyReviewCard";
import { policyComposition, policyCompositionLabel } from "../policyRecordFacts";
import type { CanonicalRule } from "../api";
import type { PolicyCard } from "../policyCards";

/** One rule, distinguished only by the effect its record states. */
function rule(ruleId: string, effectType: string | null): CanonicalRule {
  return {
    rule_id: ruleId,
    title: "A statement",
    description: "A statement",
    evaluation_mode: "deterministic",
    condition: { type: "all", all: [] },
    ...(effectType === null ? {} : { effect: { type: effectType, action: "an action" } }),
  } as unknown as CanonicalRule;
}

function card(effects: readonly (string | null)[]): PolicyCard {
  const rules = effects.map((effectType, index) => ({
    rule_id: `r${index}`,
    evaluation_mode: "deterministic",
    candidate: {
      id: `candidate-${index}`,
      review_status: "pending",
      rule_type: "obligation",
      rule: rule(`r${index}`, effectType),
    },
  }));

  return {
    policy: {
      key: "a-key",
      heading: "A heading",
      heading_path: ["A heading"],
      topic_label: null,
      persisted: true,
      provision_id: "a-provision-id",
      document_version_id: null,
      source_elements: "p1-E1",
      page: 1,
      rule_count: rules.length,
      passage_count: 1,
      route: "deterministic",
      passages: [{ rules: rules.map(({ rule_id }) => ({ rule_id })) }],
      rules: [],
    },
    passages: [{ passage: { key: "a-passage-key" }, rules }],
    rules,
    reviewableIds: rules.map((one) => one.candidate.id),
    allIds: rules.map((one) => one.candidate.id),
    hiddenByFilter: 0,
  } as unknown as PolicyCard;
}

function shown(effects: readonly (string | null)[]): {
  said: string | null;
  expected: string | null;
} {
  const model = card(effects);
  const { container } = render(
    <PolicyReviewCard
      card={model}
      selected={false}
      indeterminate={false}
      open={false}
      statusColor={() => "default"}
      statusLabel={(status: string) => status}
      findingsFor={() => 0}
      onToggleSelect={() => {}}
      onOpen={() => {}}
    />,
  );
  return {
    said: container.querySelector('[data-testid="policy-composition"]')?.textContent ?? null,
    expected: policyCompositionLabel(
      policyComposition(model.rules.map((one) => one.candidate.rule)),
    ),
  };
}

afterEach(cleanup);

describe("a card says what it is made of", () => {
  it("shows the mix, so a reviewer sees both halves rather than choosing a side", () => {
    const { said } = shown([
      "require_action",
      "deny",
      "allow",
      ...Array.from({ length: 15 }, () => "informational"),
    ]);

    expect(said).toBeTruthy();
    expect(said).toContain("3");
    expect(said).toContain("15");
  });

  it("states the shared answer word for word, and composes none of its own", () => {
    // The whole point of the shared module. If this card ever builds the phrase
    // itself, the two surfaces start to drift in the same sentence again.
    for (const effects of [
      ["require_action", "informational"],
      ["informational", "informational", "deny"],
      ["allow", "allow", "allow", "informational", "informational"],
    ]) {
      cleanup();
      const { said, expected } = shown(effects);
      expect(said).toBe(expected);
    }
  });

  it("says nothing when every rule falls on one side", () => {
    // A count of zero is the shape a shortfall takes, and there is no shortfall
    // in a policy that defines nothing. The head already carries the total.
    expect(shown(["require_action", "deny", "allow"]).said).toBeNull();
    cleanup();
    expect(shown(["informational", "informational"]).said).toBeNull();
  });

  it("says nothing about a policy of one rule, which has no mix to state", () => {
    expect(shown(["require_action"]).said).toBeNull();
  });

  it("counts an effect kind this app has never met as one that constrains", () => {
    // The axis is `informational is context, anything that constrains is a rule`,
    // and it is stated that way round on purpose. A kind extraction learns
    // tomorrow lands with the rules that bind someone — where a reviewer will
    // read it — rather than in the glossary, where they might not.
    const { said } = shown([
      "an_effect_this_app_has_never_met",
      "informational",
      "informational",
    ]);

    expect(said).toBeTruthy();
    expect(said).toContain("1");
    expect(said).toContain("2");
  });
});

describe("the two surfaces that state this fact", () => {
  // The project carries no node types, and a path walk can silently resolve to
  // the wrong root and read nothing at all. Same idiom as `routeNotFault`, for
  // the same reason.
  const sources = import.meta.glob("./*.tsx", {
    query: "?raw",
    import: "default",
    eager: true,
  }) as Record<string, string>;

  const read = (name: string) => {
    const found = sources[`./${name}`];
    if (typeof found !== "string") throw new Error(`${name} was not read`);
    return found;
  };

  it("read it from the same module rather than each from the records", () => {
    const review = read("PolicyReviewCard.tsx");
    const published = read("PublishedPolicyCard.tsx");

    for (const source of [review, published]) {
      expect(source).toContain("policyCompositionLabel");
      // Neither surface may decide for itself what counts as context. The one
      // literal that names the axis lives in `policyRecordFacts`.
      expect(source).not.toContain('"informational"');
    }
  });

  it("name the fact the same way, so one reader learns it once", () => {
    const review = read("PolicyReviewCard.tsx");
    const published = read("PublishedPolicyCard.tsx");
    const tooltip = /title="(What this policy is made of[^"]*)"/;

    expect(review).toContain('data-testid="policy-composition"');
    expect(published).toContain('data-testid="policy-composition"');
    expect(review.match(tooltip)?.[1]).toBe(published.match(tooltip)?.[1]);
  });
});
