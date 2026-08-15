import type { CanonicalPolicyRule } from "./api";
import type { PolicyCard } from "./policyCards";
import { sharedRuleFacets } from "./policyCards";

/**
 * Every rule of a policy, side by side, on the attributes the document filled.
 *
 * WHAT THIS IS FOR
 *
 * A reviewer reading a policy is answering one question — does this faithfully
 * and completely capture what the document says here — and *completeness* is the
 * half the card cannot answer. Read as twenty paragraphs, nobody notices that
 * one rule of the twenty names a time and nineteen do not, or that five name an
 * actor and fifteen do not. Put the same attribute in a column and the eye finds
 * the odd one out without being told to look.
 *
 * So this is built for comparison, not for display. The card already shows each
 * rule in prose; this shows the rules against each other.
 *
 * WHERE THE ATTRIBUTES COME FROM
 *
 * `formulation.canonical.rule` — the decomposition the formulator recorded, in
 * the document's own words. Twenty-five named slots, every value verbatim.
 * Measured over the live corpus, every one of the 692 rules on both documents
 * carries one, and the fill rates are wildly uneven, which is exactly what makes
 * the comparison worth drawing:
 *
 *     subject 99-100%   predicate 100%   object 76-80%   modality 57-68%
 *     condition 24-37%  temporal_constraint 10-15%  actor 3-6%  deadline 3%
 *     exception 1%      sequence 1%      currency 1%
 *
 * `scope` is deliberately *not* read. Personas, organizational units,
 * jurisdictions and processes are empty on all 692 rules of both documents, so a
 * column of them would be four columns of nothing on every policy in the system.
 * That is a gap in extraction and is worth reporting as one; it is not a fact
 * about any policy, and drawing it as one would be four hundred blank cells
 * pretending to be evidence.
 *
 * WHAT IT MAY NOT DO
 *
 * It aggregates nothing that no rule states. Counting how many rules fill a slot
 * is a fact about the rules. A policy-level modality, a merged condition, a
 * single scope covering all of them — each would be a claim the document did not
 * make, arrived at by us, presented in the one view whose whole purpose is to
 * show what the document did make.
 *
 * It computes no conflicts and no gaps. If two rules contradict each other that
 * is a finding, with its own detection and its own severity; a second opinion
 * formed here would be a second definition of the same thing, and this
 * repository has already paid once for having two of something that should have
 * been one.
 *
 * ABSENCE IS NOT EMPTINESS
 *
 * A slot the rule does not state and a slot we failed to record are different
 * facts and must not both be a blank cell. `absent` is a true statement about
 * the rule — the decomposition is present and names no such component.
 * `unrecorded` says the record carries no decomposition at all, so we do not
 * know. `loadState.UNKNOWN_COUNT` is reserved for the second kind and is not
 * used for the first: an em dash in this app means "we could not ask".
 *
 * ROUTE IS NOT A SCORE
 *
 * Route, kind and effect appear as columns only when the rules of the policy
 * disagree about them, on the same terms as the card's badges. Rows are ordered
 * the way the document states them and never by route, by fill count, or by
 * anything else that would rank one rule above another — a table sorted by how
 * many slots a rule filled is a completeness score with a different name, and a
 * rule the source states in words would sink to the bottom of every one of them.
 */

/** The canonical slots, in the order they read as a sentence.
 *
 *  Fixed, and deliberately not sorted by how many rules fill it. A column that
 *  moves between policies cannot be scanned down a queue, and the count in the
 *  header already makes a slot that one rule of twenty fills announce itself. */
const SLOT_ORDER: { attribute: keyof CanonicalPolicyRule; label: string }[] = [
  { attribute: "subject", label: "Subject" },
  { attribute: "modality", label: "Modality" },
  { attribute: "predicate", label: "Predicate" },
  { attribute: "object", label: "Object" },
  { attribute: "actor", label: "Actor" },
  { attribute: "assigner", label: "Assigner" },
  { attribute: "beneficiary", label: "Beneficiary" },
  { attribute: "recipient", label: "Recipient" },
  { attribute: "candidate", label: "Candidate" },
  { attribute: "trigger", label: "Trigger" },
  { attribute: "condition", label: "Condition" },
  { attribute: "prerequisite", label: "Prerequisite" },
  { attribute: "constraint", label: "Constraint" },
  { attribute: "threshold", label: "Threshold" },
  { attribute: "temporal_constraint", label: "Time" },
  { attribute: "frequency", label: "Frequency" },
  { attribute: "deadline", label: "Deadline" },
  { attribute: "location", label: "Place" },
  { attribute: "sequence", label: "Sequence" },
  { attribute: "exception", label: "Exception" },
  { attribute: "consequence", label: "Consequence" },
  { attribute: "remedy", label: "Remedy" },
  { attribute: "calculation", label: "Calculation" },
  { attribute: "unit", label: "Unit" },
  { attribute: "currency", label: "Currency" },
];

export interface LogicColumn {
  /** The canonical field name, exactly as the record declares it. */
  attribute: string;
  /** What the column is called on screen. */
  label: string;
  /** How many rules of this policy state it. Never a proportion and never a
   *  bar: "1 of 20" is a fact, "5%" invites reading it as a shortfall. */
  filled: number;
}

export type LogicCell =
  /** The document's words for this attribute of this rule, verbatim. */
  | { state: "stated"; text: string }
  /** The rule's decomposition is present and names no such component. */
  | { state: "absent" }
  /** The record carries no decomposition, so nothing is known either way. */
  | { state: "unrecorded" };

export interface LogicRow {
  ruleId: string;
  /** The rule's number on the card, so "rule 9" means the same thing in both. */
  ordinal: number;
  /** Which passage of the policy states it. Carried because a reviewer reading
   *  across twenty rules still needs to know which sentence each came from. */
  passageKey: string;
  /** Present only where the policy's rules disagree — the same rule the card's
   *  badges follow, so a value here always means "unlike its neighbours". */
  ruleType: string | null;
  effectType: string | null;
  route: string | null;
  reviewStatus: string | null;
  /** Parallel to `columns`. */
  cells: LogicCell[];
}

export interface SharedLogicFact {
  label: string;
  /** The canonical slot this came from, or null for a facet of the record. */
  attribute: string | null;
  value: string;
}

export interface PolicyLogic {
  /** Rules compared. Equals the card's rule count. */
  total: number;
  columns: LogicColumn[];
  rows: LogicRow[];
  /** What every rule says the same way, said once rather than down a column. */
  shared: SharedLogicFact[];
  /** How many rules carry no canonical decomposition at all. Zero across both
   *  stored documents today; reported rather than assumed, because the cells it
   *  produces mean "unknown" and not "the document states none". */
  unrecorded: number;
}

function slotText(
  core: CanonicalPolicyRule | undefined,
  attribute: string,
): string {
  if (!core) return "";
  const value = (core as unknown as Record<string, unknown>)[attribute];
  return typeof value === "string" ? value.trim() : "";
}

function decomposition(rule: {
  rule: { formulation?: { canonical?: { rule?: CanonicalPolicyRule } } };
}): CanonicalPolicyRule | undefined {
  return rule.rule.formulation?.canonical?.rule;
}

/**
 * The comparison table for one policy.
 *
 * A slot becomes a column when at least one rule states it. A slot every rule
 * states with the same words becomes a shared fact instead: twenty cells
 * carrying one value is the "three identical badge pairs stacked" problem in a
 * wider format, and the value is not lost — it is stated once, above.
 *
 * A policy of one rule falls out of that rule with no special case: every slot
 * it fills is trivially uniform, so it produces no columns and a plain list of
 * what that single rule says. That is the right shape — a comparison needs
 * something on the other side — and most policies in the corpus are small.
 */
export function policyLogic(card: PolicyCard): PolicyLogic {
  const rules = card.rules;
  const cores = rules.map(decomposition);
  const facets = sharedRuleFacets(card);

  const shared: SharedLogicFact[] = [];
  const columns: LogicColumn[] = [];

  for (const slot of SLOT_ORDER) {
    const values = cores.map((core) => slotText(core, slot.attribute));
    const filled = values.filter((value) => value !== "").length;
    if (filled === 0) continue;
    const first = values[0];
    if (filled === values.length && values.every((value) => value === first)) {
      shared.push({
        label: slot.label,
        attribute: slot.attribute,
        value: first,
      });
      continue;
    }
    columns.push({ attribute: slot.attribute, label: slot.label, filled });
  }

  const rows: LogicRow[] = [];
  let ordinal = 0;
  for (const block of card.passages) {
    for (const rule of block.rules) {
      ordinal += 1;
      const core = decomposition(rule);
      rows.push({
        ruleId: rule.rule_id,
        ordinal,
        passageKey: block.passage.key,
        ruleType:
          facets.ruleType === null ? rule.rule.rule_type : null,
        effectType:
          facets.effectType === null
            ? (rule.rule.effect?.type ?? "")
            : null,
        route: facets.route === null ? rule.evaluation_mode : null,
        reviewStatus:
          facets.reviewStatus === null ? rule.reviewStatus : null,
        cells: columns.map((column) => {
          if (!core) return { state: "unrecorded" as const };
          const text = slotText(core, column.attribute);
          return text
            ? { state: "stated" as const, text }
            : { state: "absent" as const };
        }),
      });
    }
  }

  return {
    total: rules.length,
    columns,
    rows,
    shared,
    unrecorded: cores.filter((core) => core === undefined).length,
  };
}
