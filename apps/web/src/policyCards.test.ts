/**
 * Tests for the review queue's unit of decision.
 *
 * The population is synthetic on purpose: the shapes that have to hold — a
 * passage of one rule, a passage part-hidden by a filter, a rule the assembly
 * did not place, a passage whose rules take different routes — are properties
 * of the arrangement rather than of any document, and pinning them to a corpus
 * would make the suite depend on a database that has been emptied before.
 *
 * The one exception is `passageStatement`, which is exercised against the
 * actual overlapping sentences of `p9-E000072` as the API returns them. That
 * overlap is the reason the function exists and a synthetic stand-in would not
 * have the shape.
 *
 * Controls sit beside offenders throughout. A suite holding only the cases that
 * were wrong cannot tell you when a fix has begun over-reaching.
 */

import { describe, expect, it } from "vitest";
import type { AssembledPolicy, CandidateRule, CanonicalRule } from "./api";
import {
  buildPolicyCards,
  passageHeading,
  passagePageLabel,
  passageStatement,
  passageTitle,
  policyJsonDocument,
  sharedRuleFacets,
  unplacedCandidates,
} from "./policyCards";

function rule(ruleId: string, overrides: Partial<CanonicalRule> = {}): CanonicalRule {
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
      source_elements: "p1-E000001",
    },
    tags: [],
    related_rule_ids: [],
    is_explicit_override: false,
    supersedes_rule_ids: [],
    ...overrides,
  } as CanonicalRule;
}

function candidate(
  ruleId: string,
  overrides: Partial<CandidateRule> = {},
  ruleOverrides: Partial<CanonicalRule> = {},
): CandidateRule {
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
    rule: rule(ruleId, ruleOverrides),
    ...overrides,
  } as CandidateRule;
}

function policy(
  key: string,
  ruleIds: string[],
  overrides: Partial<AssembledPolicy> = {},
): AssembledPolicy {
  return {
    key,
    source_elements: key,
    page: 9,
    rule_count: ruleIds.length,
    route: "ai_ready",
    rules: ruleIds.map((rule_id) => ({
      rule_id,
      title: `title ${rule_id}`,
      evaluation_mode: "ai_ready",
    })),
    ...overrides,
  };
}

describe("buildPolicyCards", () => {
  it("makes one card of the three rules one passage states", () => {
    // The owner's case. Three records, one judgement.
    const cards = buildPolicyCards(
      [policy("p9-E000072", ["a", "b", "c"])],
      [candidate("a"), candidate("b"), candidate("c")],
    );

    expect(cards).toHaveLength(1);
    expect(cards[0].rules.map((r) => r.rule_id)).toEqual(["a", "b", "c"]);
    expect(cards[0].reviewableIds).toEqual(["record-a", "record-b", "record-c"]);
    expect(cards[0].hiddenByFilter).toBe(0);
  });

  it("builds a passage of one rule the same way, with nothing extra", () => {
    // CONTROL. Most passages state one rule. If this shape needed its own path
    // the common case would be the exception, which is backwards.
    const cards = buildPolicyCards([policy("p9-E000042", ["only"])], [candidate("only")]);

    expect(cards).toHaveLength(1);
    expect(cards[0].rules).toHaveLength(1);
    expect(cards[0].hiddenByFilter).toBe(0);
    expect(cards[0].reviewStatuses).toEqual(["candidate"]);
  });

  it("keeps the order the passage states its rules in, not the order they arrived", () => {
    const cards = buildPolicyCards(
      [policy("p9-E000072", ["a", "b", "c"])],
      [candidate("c"), candidate("a"), candidate("b")],
    );

    expect(cards[0].rules.map((r) => r.rule_id)).toEqual(["a", "b", "c"]);
  });

  it("keeps the order the server put the passages in", () => {
    const cards = buildPolicyCards(
      [policy("p4-E000007", ["a"]), policy("p9-E000072", ["b"])],
      [candidate("b"), candidate("a")],
    );

    expect(cards.map((card) => card.policy.key)).toEqual(["p4-E000007", "p9-E000072"]);
  });

  it("says how many rules a filter is holding back rather than showing a fragment as the whole", () => {
    const cards = buildPolicyCards(
      [policy("p9-E000072", ["a", "b", "c"])],
      [candidate("a"), candidate("c")],
    );

    expect(cards[0].rules).toHaveLength(2);
    expect(cards[0].hiddenByFilter).toBe(1);
  });

  it("reports a whole passage as whole", () => {
    // CONTROL for the caveat above. A caveat on every card means nothing.
    const cards = buildPolicyCards(
      [policy("p9-E000072", ["a", "b", "c"])],
      [candidate("a"), candidate("b"), candidate("c")],
    );

    expect(cards[0].hiddenByFilter).toBe(0);
  });

  it("makes no card for a passage the filter has emptied", () => {
    const cards = buildPolicyCards([policy("p9-E000072", ["a"])], []);
    expect(cards).toEqual([]);
  });

  it("leaves a decision somebody already made out of the next one", () => {
    // Approving the passage must not re-decide a rule already approved: the
    // server refuses it and the reviewer never asked for it. A rejected rule
    // is deliberately still reviewable — rejection is reversible here — so the
    // status that proves the point is the one that is not.
    const cards = buildPolicyCards(
      [policy("p9-E000072", ["a", "b"])],
      [candidate("a"), candidate("b", { review_status: "approved" })],
    );

    expect(cards[0].rules).toHaveLength(2);
    expect(cards[0].allIds).toEqual(["record-a", "record-b"]);
    expect(cards[0].reviewableIds).toEqual(["record-a"]);
    expect(cards[0].reviewStatuses).toEqual(["candidate", "approved"]);
  });

  it("carries the policy through whole, so nothing downstream rebuilds it", () => {
    const source = [policy("p9-E000072", ["a", "b", "c"], { route: "mixed", page: 12 })];
    const cards = buildPolicyCards(source, [candidate("a"), candidate("b"), candidate("c")]);

    expect(cards[0].policy).toBe(source[0]);
    expect(cards[0].policy.route).toBe("mixed");
  });

  it("keeps each rule's own route when the passage mixes them", () => {
    // Mixed is the ordinary shape of a real document. The rules must arrive
    // carrying their own route and not the passage's summary of it.
    const mixed = policy("p9-E000072", ["a", "b"], { route: "mixed" });
    mixed.rules[0].evaluation_mode = "deterministic";
    const cards = buildPolicyCards([mixed], [candidate("a"), candidate("b")]);

    expect(cards[0].rules.map((r) => r.evaluation_mode)).toEqual(["deterministic", "ai_ready"]);
    expect(cards[0].policy.route).toBe("mixed");
  });

  it("is empty for an empty assembly, without throwing", () => {
    expect(buildPolicyCards([], [candidate("a")])).toEqual([]);
  });
});

describe("unplacedCandidates", () => {
  it("names a rule the assembly did not place instead of dropping it", () => {
    // The flat list asks for superseded rows when a historical run is open and
    // the assembly does not, so this gap is reachable in normal use.
    const left = unplacedCandidates(
      [policy("p9-E000072", ["a"])],
      [candidate("a"), candidate("stray")],
    );

    expect(left.map((c) => c.rule.rule_id)).toEqual(["stray"]);
  });

  it("finds nothing to report when every rule was placed", () => {
    // CONTROL: the ordinary case must produce no note at all.
    expect(unplacedCandidates([policy("p9-E000072", ["a"])], [candidate("a")])).toEqual([]);
  });

  it("treats an unavailable assembly as every rule unplaced, not as no rules", () => {
    const left = unplacedCandidates([], [candidate("a"), candidate("b")]);
    expect(left).toHaveLength(2);
  });
});

describe("passageStatement", () => {
  // The three rules of p9-E000072, with the source text each one records,
  // exactly as `GET /policy-sets/ais-employee-handbook/candidate-rules`
  // returns it. The second restates the first before adding its own sentence,
  // which is the overlap this function exists for.
  const first =
    "According to the new organizational structure and policy of AIS for 2022, contracts will normally begin at the beginning of the academic year.";
  const second =
    "According to the new organizational structure and policy of AIS for 2022, contracts will normally begin at the beginning of the academic year. If an employee begins work on a different date, a temporary contract will be issued with that date as the start date and the end date as the end of the Academic Year.";
  const third = "At a later period, the permanent contract will be issued.";

  function withSource(ruleId: string, text: string): CanonicalRule {
    return rule(ruleId, {
      description: text,
      formulation: {
        source_index: 0,
        canonical: {
          source_text: text,
          extraction_status: "complete",
          relationships: [],
          ambiguity: [],
          missing_components: [],
        },
        dmn_decisions: [],
      },
    } as Partial<CanonicalRule>);
  }

  it("quotes the passage once instead of restating its opening three times", () => {
    const statement = passageStatement([
      withSource("a", first),
      withSource("b", second),
      withSource("c", third),
    ]);

    expect(statement).toBe(`${second} ${third}`);
    // The opening sentence appears exactly once, not once per rule.
    expect(statement.split("According to the new organizational structure")).toHaveLength(2);
    expect(statement).toContain("a temporary contract will be issued");
    expect(statement).toContain("the permanent contract will be issued");
  });

  it("adds no word the document does not have", () => {
    const statement = passageStatement([withSource("a", first), withSource("b", second)]);
    expect(second).toContain(statement);
  });

  it("keeps two unrelated sentences whole rather than choosing between them", () => {
    // CONTROL for the containment rule: dropping either would lose a rule's
    // source text, which is worse than repeating a clause.
    const statement = passageStatement([
      withSource("a", "Staff must give notice."),
      withSource("b", "Leave accrues monthly."),
    ]);

    expect(statement).toBe("Staff must give notice. Leave accrues monthly.");
  });

  it("collapses two rules recording the identical sentence to one copy", () => {
    const statement = passageStatement([
      withSource("a", "Staff must read the policies."),
      withSource("b", "Staff must read the policies."),
    ]);

    expect(statement).toBe("Staff must read the policies.");
  });

  it("falls back to the description when no formulator record was stored", () => {
    // Hand-drafted rules carry no formulation. Showing nothing would make the
    // passage look empty when the text is right there on the record.
    expect(passageStatement([rule("a", { description: "Hand written." })])).toBe("Hand written.");
  });

  it("returns nothing rather than something invented when there is no text", () => {
    expect(passageStatement([rule("a", { description: "" })])).toBe("");
    expect(passageStatement([])).toBe("");
  });
});

describe("passageHeading", () => {
  function withSection(ruleId: string, section: string | null): CanonicalRule {
    return rule(ruleId, {
      evidence: [
        {
          document_version_id: "version",
          source_hash: "hash",
          page: 9,
          section,
          clause_id: "clause",
          start_offset: null,
          end_offset: null,
        },
      ],
    } as Partial<CanonicalRule>);
  }

  it("quotes the document's own heading for the passage", () => {
    expect(
      passageHeading([
        withSection("a", "7.1. THE EMPLOYMENT CONTRACT"),
        withSection("b", "7.1. THE EMPLOYMENT CONTRACT"),
      ]),
    ).toBe("7.1. THE EMPLOYMENT CONTRACT");
  });

  it("keeps both headings rather than silently picking one", () => {
    expect(passageHeading([withSection("a", "7.1. CONTRACT"), withSection("b", "7.2. PAY")])).toBe(
      "7.1. CONTRACT · 7.2. PAY",
    );
  });

  it("is empty when no citation recorded one, so the absence can be stated", () => {
    expect(passageHeading([withSection("a", null), withSection("b", "   ")])).toBe("");
    expect(passageHeading([rule("a")])).toBe("");
  });
});

describe("passagePageLabel", () => {
  it("names the page when the assembly recorded one", () => {
    expect(passagePageLabel(9)).toBe("page 9");
  });

  it("invents no page when none was recorded", () => {
    expect(passagePageLabel(null)).toBeNull();
  });
});

describe("policyJsonDocument", () => {
  const cards = buildPolicyCards(
    [policy("p9-E000072", ["a", "b", "c"])],
    [candidate("a"), candidate("b"), candidate("c")],
  );

  it("is one document with the rules nested inside the policy", () => {
    const document = policyJsonDocument(cards[0]) as Record<string, unknown>;

    expect(document.key).toBe("p9-E000072");
    expect(document.source_elements).toBe("p9-E000072");
    expect(document.page).toBe(9);
    expect(document.rule_count).toBe(3);
    expect(document.route).toBe("ai_ready");
    expect(Array.isArray(document.rules)).toBe(true);
    expect((document.rules as CanonicalRule[]).map((r) => r.rule_id)).toEqual(["a", "b", "c"]);
  });

  it("nests the whole rule, not a reference to one", () => {
    const nested = (policyJsonDocument(cards[0]).rules as CanonicalRule[])[0];
    expect(nested.condition).toBeDefined();
    expect(nested.effect).toBeDefined();
    expect(nested.evidence).toBeDefined();
    expect(nested.lineage).toBeDefined();
  });

  it("says nothing about hidden rules when none are hidden", () => {
    // CONTROL: the ordinary download must not carry a caveat it has not earned.
    expect(policyJsonDocument(cards[0])).not.toHaveProperty("rules_hidden_by_filter");
  });

  it("does not pass a partial passage off as a whole one", () => {
    const partial = buildPolicyCards(
      [policy("p9-E000072", ["a", "b", "c"])],
      [candidate("a")],
    )[0];
    const document = policyJsonDocument(partial);

    expect(document.rule_count).toBe(3);
    expect((document.rules as CanonicalRule[])).toHaveLength(1);
    expect(document.rules_hidden_by_filter).toBe(2);
  });

  it("records the absence of a heading rather than omitting the field", () => {
    expect(policyJsonDocument(cards[0]).heading).toBeNull();
  });
});

describe("passageTitle", () => {
  // The passage the owner named, verbatim from
  // `GET /policy-sets/ais-employee-handbook/candidate-rules`.
  const opening =
    "According to the new organizational structure and policy of AIS for 2022, contracts will normally begin at the beginning of the academic year.";
  const rest =
    "If an employee begins work on a different date, a temporary contract will be issued with that date as the start date and the end date as the end of the Academic Year. At a later period, the permanent contract will be issued.";

  function withSource(ruleId: string, text: string, section: string | null = "7.1. THE EMPLOYMENT CONTRACT"): CanonicalRule {
    return rule(ruleId, {
      description: text,
      evidence: section
        ? ([
            {
              document_version_id: "doc",
              source_hash: "hash",
              page: 9,
              section,
              clause_id: "clause",
              start_offset: null,
              end_offset: null,
            },
          ] as CanonicalRule["evidence"])
        : [],
      formulation: {
        source_index: 0,
        canonical: {
          source_text: text,
          extraction_status: "complete",
          relationships: [],
          ambiguity: [],
          missing_components: [],
        },
        dmn_decisions: [],
      },
    } as Partial<CanonicalRule>);
  }

  it("names the policy by its own opening statement, not by why its rules were grouped", () => {
    const title = passageTitle([withSource("a", `${opening} ${rest}`)]);

    expect(title.source).toBe("statement");
    expect(title.text).toBe(opening);
    // The words are the document's, in the document's order, and nothing has
    // been added: title and remainder reassemble the passage exactly.
    expect(`${title.text} ${title.rest}`).toBe(`${opening} ${rest}`);
  });

  it("leaves the rest of the passage to be shown, so the title repeats nothing", () => {
    const title = passageTitle([withSource("a", `${opening} ${rest}`)]);

    expect(title.rest).toBe(rest);
    expect(title.rest).not.toContain("According to the new organizational structure");
  });

  it("does not name a card after a list marker", () => {
    // The first measurement of this idea reported 7 unusable AIS passages
    // because it split after "1." and titled the card "1.".
    const title = passageTitle([
      withSource(
        "a",
        "1. In keeping with the provisions of The Saudi Labor Law, employees are entitled to 30 calendar days paid sick leave. 2. In cases of severe illness, leave can be extended.",
      ),
    ]);

    expect(title.source).toBe("statement");
    expect(title.text).toBe(
      "1. In keeping with the provisions of The Saudi Labor Law, employees are entitled to 30 calendar days paid sick leave.",
    );
  });

  it("names a table row by its own first cell, and says that is what happened", () => {
    // 45 of the AIS passages are rows of the violations table. A row states no
    // sentence; composing one for it would be the one thing forbidden here.
    // Its heading is no better — 50 rows share "Table of Violations and
    // Penalties" — so the row is named by the first cell that says something,
    // which is unique to it and is the document's own text.
    const title = passageTitle([
      withSource(
        "a",
        "1. |  | Late for work, 15 minutes or less without permission | 1 Time Written Warning | 2 Time 5% deduction",
        "Table of Violations and Penalties",
      ),
    ]);

    expect(title.source).toBe("cell");
    expect(title.text).toBe("Late for work, 15 minutes or less without permission");
    // Nothing was taken from the passage, so all of it is still to be shown.
    expect(title.rest).toContain("1 Time Written Warning");
  });

  it("falls back to the heading when a row has no cell that says anything", () => {
    // Honest about the case it cannot name: no cell of this row carries a
    // clause, so nothing is invented and the row is filed under its heading.
    const title = passageTitle([withSource("a", "1. | 5% | 10% | 20%", "Table of Violations and Penalties")]);

    expect(title.source).toBe("section");
    expect(title.text).toBe("Table of Violations and Penalties");
    expect(title.rest).toContain("20%");
  });

  it("does not name a card after an annotation the extraction wrote in", () => {
    // Six AIS passages arrive with "(section: …)" ahead of the row. It reads
    // like a sentence and is not one — it is the pipeline describing itself,
    // and titling a card with it puts a machine's words where the document's
    // should be. The row names itself instead, and the annotation stays in the
    // quoted text rather than being deleted from it.
    const title = passageTitle([
      withSource(
        "a",
        "(section: Table of Violations and Penalties)\n10. | Inappropriate language and gestures. | Two (2) days deduction",
        "Table of Violations and Penalties",
      ),
    ]);

    expect(title.source).toBe("cell");
    expect(title.text).toBe("Inappropriate language and gestures.");
    expect(title.rest).toContain("(section: Table of Violations and Penalties)");
  });

  it("keeps a short whole passage as its own title", () => {
    // CONTROL for the row rule: a short sentence is a name, and diverting it
    // to its heading would put every card of a section under one label.
    const title = passageTitle([withSource("a", "Alcohol and drugs are strictly forbidden.")]);

    expect(title.source).toBe("statement");
    expect(title.text).toBe("Alcohol and drugs are strictly forbidden.");
    expect(title.rest).toBe("");
  });

  it("falls back to the passage key only when the document gave neither", () => {
    const title = passageTitle([withSource("a", "1. | 2. | 3.", null)]);

    expect(title.source).toBe("unnamed");
    expect(title.text).toBe("");
    // Still shown, in full, below whatever the card is called.
    expect(title.rest).toBe("1. | 2. | 3.");
  });

  it("never composes a title out of more than one statement", () => {
    const title = passageTitle([
      withSource("a", "Staff must give notice. Leave accrues monthly. Notice is in writing."),
    ]);

    expect(title.text).toBe("Staff must give notice.");
    expect(title.rest).toBe("Leave accrues monthly. Notice is in writing.");
  });
});

describe("sharedRuleFacets", () => {
  it("reports what every rule says the same way, so the card can say it once", () => {
    // Three rules that agree on everything: the old card stacked three
    // identical [Requires] [Candidate] rev 1 rows for this.
    const cards = buildPolicyCards(
      [policy("p9-E000072", ["a", "b", "c"])],
      [candidate("a"), candidate("b"), candidate("c")],
    );

    expect(sharedRuleFacets(cards[0])).toEqual({
      ruleType: "obligation",
      effectType: "require_action",
      route: "ai_ready",
      reviewStatus: "candidate",
      revision: 1,
    });
  });

  it("reports null for a facet the rules disagree on, so the difference is shown per rule", () => {
    // p9-E000072 in the live corpus: one human_judgment_requirement and two
    // routing rules. That difference is information and must not be flattened.
    const cards = buildPolicyCards(
      [policy("p9-E000072", ["a", "b", "c"])],
      [
        candidate("a", {}, { rule_type: "human_judgment_requirement" }),
        candidate("b", {}, { rule_type: "routing" }),
        candidate("c", {}, { rule_type: "routing" }),
      ],
    );

    const shared = sharedRuleFacets(cards[0]);
    expect(shared.ruleType).toBeNull();
    // The facets they do agree on are still stated once.
    expect(shared.effectType).toBe("require_action");
    expect(shared.reviewStatus).toBe("candidate");
  });

  it("does not flatten a route onto the policy when its rules take different ones", () => {
    // The binding constraint: mixed is normal, not degraded. A single badge
    // here would have to claim one of the two, and both would be wrong.
    const cards = buildPolicyCards(
      [
        policy("p9-E000072", ["a", "b"], {
          rules: [
            { rule_id: "a", title: "title a", evaluation_mode: "deterministic" },
            { rule_id: "b", title: "title b", evaluation_mode: "ai_ready" },
          ],
        }),
      ],
      [candidate("a"), candidate("b")],
    );

    expect(sharedRuleFacets(cards[0]).route).toBeNull();
  });

  it("states the route once when every rule takes the same one", () => {
    // CONTROL: neither route is a deficiency, so a card whose rules agree
    // says so once rather than repeating it beside each rule.
    const cards = buildPolicyCards(
      [
        policy("p9-E000072", ["a", "b"], {
          rules: [
            { rule_id: "a", title: "title a", evaluation_mode: "deterministic" },
            { rule_id: "b", title: "title b", evaluation_mode: "deterministic" },
          ],
        }),
      ],
      [candidate("a"), candidate("b")],
    );

    expect(sharedRuleFacets(cards[0]).route).toBe("deterministic");
  });

  it("treats a policy of one rule as agreeing with itself", () => {
    // 83 of 155 passages state one rule. Every facet is shared, so the card
    // carries one badge strip and the rule line carries none.
    const cards = buildPolicyCards([policy("p6-E000040", ["a"])], [candidate("a")]);

    expect(sharedRuleFacets(cards[0])).toEqual({
      ruleType: "obligation",
      effectType: "require_action",
      route: "ai_ready",
      reviewStatus: "candidate",
      revision: 1,
    });
  });

  it("shows a part-decided passage rule by rule", () => {
    const cards = buildPolicyCards(
      [policy("p9-E000072", ["a", "b"])],
      [candidate("a"), candidate("b", { review_status: "rejected" })],
    );

    expect(sharedRuleFacets(cards[0]).reviewStatus).toBeNull();
  });
});
