/**
 * A passage that lists one record twice keeps both rows without colliding keys.
 *
 * WHAT THIS IS, AND WHAT IT IS NOT
 *
 * This is the strict sibling of `aCardNeverDropsARule`, and the two must not be
 * confused. That guard pins two *distinct* records — different row ids — that
 * share one content-hash `rule_id`: keyed by `rule_id` they would collide, so
 * the card keys by the row's own id and both survive. This guard pins the other
 * collision: the *same* record id listed twice in one passage. The draft
 * assembly produces exactly that when a rule has gained a second, unreviewed
 * candidate sharing its content-hash id — the passage then carries the id twice
 * and both entries resolve, through the "first candidate per rule_id" lookup,
 * to the one record. Keyed by that record id alone, the two rows collide and
 * React "may duplicate and/or omit" one of them. So the row's key is
 * disambiguated per occurrence, and neither row is dropped.
 *
 * WHAT THIS DELIBERATELY DOES NOT ASSERT
 *
 * It does not assert the count is right. On this fixture the card shows "2
 * rules", which is the doubled total the (defective) draft assembly supplies —
 * reflected faithfully, not corrected. Correcting the double is the server
 * assembly's job: it must dedupe the passage's rules by `rule_id` the way the
 * published assembly already does. A client that hid the second row instead
 * would trade a wrong count for a missing rule and, because the total is read
 * from the policy's own `rule_count`, would print "1 of 2 rules" and invent a
 * rule "hidden by filter". So this guard keeps both rows and leaves the tally
 * exactly as given. Its passing means the keys do not collide; it means nothing
 * about whether the number beside them is correct.
 *
 * Nothing here is a phrase from any document, and no count in it is a
 * measurement of one.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import type { AssembledPolicy, CandidateRule, CanonicalRule } from "../api";
import { buildPolicyCards } from "../policyCards";
import { PolicyReviewCard } from "./PolicyReviewCard";

/** A sentence long enough to stand as a passage. */
const SOURCE = "The employer sets out obligations for its staff in this section.";

/** One rule, identified by the content-hash id a passage refers to it by. */
function canonicalRule(ruleId: string): CanonicalRule {
  return {
    rule_id: ruleId,
    title: "A staff obligation",
    description: SOURCE,
    evaluation_mode: "deterministic",
    condition: { type: "all", all: [] },
    effect: { type: "require_action", action: "an action" },
  } as unknown as CanonicalRule;
}

/**
 * A policy whose single passage lists the same `rule_id` twice — the shape the
 * draft assembly emits when a rule carries a second candidate record sharing
 * its content-hash id. `rule_count` is the assembly's own doubled total, kept
 * as given so the card is tested on exactly what the server sends.
 */
function passageThatRepeatsARule(ruleId: string): AssembledPolicy {
  return {
    key: "preface",
    heading: "Preface",
    heading_path: ["Preface"],
    topic_label: null,
    persisted: true,
    provision_id: "a-provision-id",
    document_version_id: null,
    source_elements: "p4-E000007",
    page: 4,
    rule_count: 2,
    passage_count: 1,
    route: "deterministic",
    passages: [
      {
        key: "p4-E000007",
        rules: [
          { rule_id: ruleId, evaluation_mode: "deterministic" },
          { rule_id: ruleId, evaluation_mode: "deterministic" },
        ],
      },
    ],
    rules: [],
  } as unknown as AssembledPolicy;
}

/** The one candidate record the two passage entries both resolve to. */
function candidate(ruleId: string, id: string): CandidateRule {
  return {
    id,
    review_status: "published",
    rule: canonicalRule(ruleId),
  } as unknown as CandidateRule;
}

function drawDoubledPassage() {
  const [card] = buildPolicyCards(
    [passageThatRepeatsARule("r-preface")],
    [candidate("r-preface", "candidate-preface")],
    "gmu-staff-handbook-2024",
  );
  if (!card) throw new Error("no card built from the doubled passage");
  return render(
    <PolicyReviewCard
      card={card}
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

afterEach(cleanup);

describe("a passage that lists one record twice", () => {
  it("keys the two rows apart so React drops neither", () => {
    // React tolerates a key collision on mount but warns, and its own words for
    // what follows are "may be duplicated and/or omitted". The warning is the
    // signal; waiting for an omission to become observable is waiting for a lost
    // rule. So the warning is what is asserted.
    const warnings: unknown[][] = [];
    const spy = vi.spyOn(console, "error").mockImplementation((...args) => {
      warnings.push(args);
    });
    try {
      drawDoubledPassage();
      // Both occurrences are still on the card. The repeat is not tidied away.
      expect(screen.getAllByTestId("policy-card-rule")).toHaveLength(2);
    } finally {
      spy.mockRestore();
    }

    const collisions = warnings.filter((args) =>
      args.some((arg) => typeof arg === "string" && arg.includes("same key")),
    );
    expect(collisions).toEqual([]);
  });

  it("leaves the count as given — correcting the double is the server's job", () => {
    // The card shows the total it was handed. Here that is the doubled "2
    // rules". This assertion is the tripwire: a change that made this guard
    // dedupe the rows to tidy the list would drop the count to one, print "1 of
    // 2 rules", and reintroduce exactly the false "hidden by filter" this
    // arrangement exists to avoid. The row-keeping and the count are one
    // decision, and it is the server's.
    const { container } = drawDoubledPassage();
    const meta = container.querySelector(".policy-card__meta");
    expect(meta?.textContent ?? "").toContain("2 rules");
  });
});
