/**
 * A card shows every rule the passage states, including two it states in the
 * same words.
 *
 * `rule_id` is a digest of a rule's content. Two rules that a document states
 * identically therefore carry the same one, and React drops children that
 * collide on a key — it says so itself: "may be duplicated and/or omitted". In
 * an app whose whole purpose is not losing what a document said, a silently
 * omitted rule is the worst failure available. The row's own identity is unique
 * by construction, so that is what the list is keyed by.
 *
 * Nothing here is a phrase from any document, and no number in it is a
 * measurement of one.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import type { PolicyCard, PolicyCardRule } from "../policyCards";
import type { AssembledPolicy } from "../api";
import { PolicyReviewCard } from "./PolicyReviewCard";

const SHARED_DIGEST = "a-shared-digest";

function rule(candidateId: string, statement: string): PolicyCardRule {
  return {
    // Deliberately shared: this is the case the key has to survive.
    rule_id: SHARED_DIGEST,
    evaluation_mode: "deterministic",
    candidate: {
      id: candidateId,
      review_status: "pending",
      rule: {
        rule_id: SHARED_DIGEST,
        title: statement,
        description: statement,
        evaluation_mode: "deterministic",
        condition: { type: "all", all: [] },
        effect: { type: "obligation", action: "an action" },
      },
    },
  } as unknown as PolicyCardRule;
}

function policy(): AssembledPolicy {
  return {
    key: "a-key",
    heading: "A heading",
    heading_path: ["A heading"],
    topic_label: null,
    persisted: true,
    provision_id: "a-provision-id",
    document_version_id: null,
    source_elements: "p1-E1",
    page: 1,
    rule_count: 2,
    passage_count: 1,
    route: "deterministic",
    passages: [],
    rules: [],
  } as unknown as AssembledPolicy;
}

function card(rules: PolicyCardRule[]): PolicyCard {
  return {
    policy: policy(),
    passages: [
      {
        passage: { key: "a-passage-key" },
        rules,
      },
    ],
    rules,
    reviewableIds: rules.map((one) => one.candidate.id),
    hiddenByFilter: 0,
  } as unknown as PolicyCard;
}

afterEach(() => {
  cleanup();
});

function renderCard(rules: PolicyCardRule[]) {
  return render(
    <PolicyReviewCard
      card={card(rules)}
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
}

describe("a passage that states two rules the same way", () => {
  it("shows both of them, and says nothing about a repeated key", () => {
    // Two records, one digest. React tolerates the collision on first mount but
    // warns, and its own words for what happens next are "may be duplicated
    // and/or omitted". The warning is the signal, so it is what is asserted:
    // waiting for an omission to be observable is waiting for lost content.
    const warnings: unknown[][] = [];
    const spy = vi.spyOn(console, "error").mockImplementation((...args) => {
      warnings.push(args);
    });
    try {
      const view = renderCard([
        rule("11111111-1111-4111-8111-111111111111", "The first statement"),
        rule("22222222-2222-4222-8222-222222222222", "The second statement"),
      ]);

      expect(screen.getAllByTestId("policy-card-rule")).toHaveLength(2);

      // The list rerenders on every queue poll. An update is where React
      // resolves a collision by discarding one of the two.
      view.rerender(
        <PolicyReviewCard
          card={card([
            rule("22222222-2222-4222-8222-222222222222", "The second statement"),
            rule("11111111-1111-4111-8111-111111111111", "The first statement"),
          ])}
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

      expect(screen.getAllByTestId("policy-card-rule")).toHaveLength(2);
    } finally {
      spy.mockRestore();
    }

    const collisions = warnings.filter((args) =>
      args.some((arg) => typeof arg === "string" && arg.includes("same key")),
    );
    expect(collisions).toEqual([]);
  });

  it("keys each rule by something no two rules can share", () => {
    // The rule the reviewer decides on is the candidate record; its id is a row
    // identity, unique by construction. The digest is a property of the words,
    // and words repeat.
    const rules = [
      rule("33333333-3333-4333-8333-333333333333", "The first statement"),
      rule("44444444-4444-4444-8444-444444444444", "The second statement"),
    ];
    const keys = new Set(rules.map((one) => one.candidate.id));
    const digests = new Set(rules.map((one) => one.rule_id));

    expect(keys.size).toBe(rules.length);
    expect(digests.size).toBeLessThan(rules.length);
  });
});

describe("a rule whose record states no effect", () => {
  it("still renders, and takes no other rule down with it", () => {
    // Reading the outcome used to be `rule.effect.action || rule.effect.type`,
    // which throws on a record carrying no effect object at all — and a throw
    // inside the card's render loses the whole card, every rule on it, and the
    // quotations beside them. Nothing in today's corpus is in that state, so
    // this is not a bug report; it is the assumption written down. "Extraction
    // always fills this field" is a claim about a model's output, and the cost
    // of it being wrong once is a reviewer seeing an empty panel with no reason
    // given, which is the one failure this product cannot afford.
    const withEffect = rule("55555555-5555-4555-8555-555555555555", "A rule that states its effect");
    const withoutEffect = rule("66666666-6666-4666-8666-666666666666", "A rule that states none");
    delete (withoutEffect.candidate.rule as { effect?: unknown }).effect;

    expect(() => renderCard([withEffect, withoutEffect])).not.toThrow();
    expect(screen.getByText("A rule that states its effect")).toBeTruthy();
    expect(screen.getByText("A rule that states none")).toBeTruthy();
  });
});
