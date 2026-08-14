import type { ConditionProvenance } from "./api";
import { DETERMINISTIC_LABEL } from "./ruleExecutability";

/**
 * How a record came to be decided the way it is, in words a reviewer can read.
 *
 * Every record is routed one of two ways. When the source states its test as a
 * comparison between named quantities, the platform compiles that comparison
 * and a case is settled by computing it. When the source states its test in
 * words, the record carries the words and a judge settles a case by reading
 * them. Both are ordinary; neither is a lesser version of the other.
 *
 * `condition_provenance.code` says which of those happened and why, and it is
 * on every extracted record. It was on 273 of 273 records of a document under
 * review and appeared nowhere on screen: a reviewer was asked to approve each
 * one for publication with the single field explaining its route invisible.
 * `ruleDisplay.ts` even strips the same fact out of the description text on the
 * stated grounds that it is "carried structurally on `condition_provenance`,
 * which the inspector renders as its own panel" — a panel that did not exist,
 * so the annotation was removed from the one place it was showing and added to
 * none.
 *
 * The server emits the code and this file owns the words, which is the split
 * `AggregateLimitsPage` already uses for `not_machine_executable`. Wording
 * changes here need no migration and reach records published years ago;
 * wording shipped inside a record would be frozen into every copy of it.
 */
export interface ConditionRoute {
  /** Which of the two routes this record travels. Empty when unknown. */
  route: string;
  /** What the source did, and what follows from it. One or two sentences. */
  reason: string;
  /** antd tag colour for `route`. */
  color: string;
}

/**
 * Wording per code. Keys are `CONDITION_PROVENANCE_CODES` from
 * `contracts/policy.py`, and `tests/unit/test_condition_route_wording.py`
 * fails if that list gains a code this object has not.
 *
 * Each entry says what the source did and what follows from it, in that order.
 * That shape is the whole discipline: a sentence that starts from the source
 * cannot end up describing the record as deficient, because the source is not
 * deficient for stating a rule in words — which is how most policy is written.
 *
 * The two-line formatting is load-bearing for the guard, which reads the keys
 * of this object out of this file. One key per line, opening its brace on the
 * same line.
 */
export const CONDITION_ROUTE: Record<string, ConditionRoute> = {
  derived: {
    route: DETERMINISTIC_LABEL.yes,
    reason:
      "The source states this rule's test as a comparison between named quantities, so the comparison above is the source's own. A case is settled by computing it.",
    color: "green",
  },
  derived_from_stated_bound: {
    route: DETERMINISTIC_LABEL.yes,
    reason:
      "The sentence states its own limit — a named quantity against a fixed value — so the comparison above was read straight out of it. A case is settled by computing it, and the check is against that one sentence.",
    color: "green",
  },
  derived_from_stated_quantity: {
    route: DETERMINISTIC_LABEL.yes,
    reason:
      "The sentence states a quantity and the comparison to make against it — a limit in the source's own words and units. That comparison was read straight out of it, so a case is settled by computing it against this one sentence.",
    color: "green",
  },
  quantity_states_a_range: {
    route: DETERMINISTIC_LABEL.no,
    reason:
      "The source states a range rather than a single limit, leaving the choice within it to whoever applies the rule. There is no one comparison to compute, so a judge settles a case by reading the record against the source's words.",
    color: "blue",
  },
  quantity_states_no_comparison: {
    route: DETERMINISTIC_LABEL.no,
    reason:
      "The source states a quantity but not a test to make of it — what the figure is, rather than what must be true of it. Supplying a comparison would mean inventing a limit the document never set, so this record travels as words and a judge reads them.",
    color: "blue",
  },
  quantity_not_read_as_number: {
    route: DETERMINISTIC_LABEL.no,
    reason:
      "The source states its quantity in a form this platform does not yet read as a number. The figure is in the record and in the source; only the compiler fell short, so a judge settles a case by reading it.",
    color: "blue",
  },
  proportion_has_no_stated_base: {
    route: DETERMINISTIC_LABEL.no,
    reason:
      "The source states a percentage without saying what it is a percentage of. A comparison needs both quantities, and naming the second would mean choosing one the document did not, so a judge settles a case by reading the record.",
    color: "blue",
  },
  conditions_not_projected: {
    route: DETERMINISTIC_LABEL.no,
    reason:
      "The source states this rule's test in words rather than as a comparison between named quantities. The record carries those words, and a judge settles a case by reading them against it.",
    color: "blue",
  },
  conditions_not_representable: {
    route: DETERMINISTIC_LABEL.no,
    reason:
      "The source states this rule's test as one of its own quantities measured against another. A comparison here holds a quantity against a fixed value, so this record travels as words and a judge settles a case by reading them.",
    color: "blue",
  },
  no_scope_derived: {
    route: DETERMINISTIC_LABEL.no,
    reason:
      "The source states no test for this rule — nothing in it narrows when the rule applies. There is no comparison to compute, so a judge settles a case by reading the record against the source's own words.",
    color: "blue",
  },
};

/**
 * What to show for a code this build has never heard of.
 *
 * Two failures are available here and both were worth designing out. Printing
 * the code puts an internal identifier in front of someone who has no way to
 * look it up. Printing nothing is worse: the reviewer cannot tell the record
 * carries a routing reason at all, which is the exact state this whole surface
 * was built to end. So an unknown code says that a reason is recorded, names
 * the field, and points at the tab that shows the record verbatim.
 *
 * The route is left empty rather than guessed. Which of the two routes an
 * unknown code means is not knowable from the code alone, and stating one
 * would be a claim about the record made up by the interface.
 */
export const UNKNOWN_CONDITION_ROUTE: ConditionRoute = {
  route: "",
  reason:
    "This record was routed for a reason this screen has no wording for yet. The reason itself is on the record: the JSON tab shows it under condition_provenance.",
  color: "default",
};

/**
 * The wording for a record's provenance, or null when it carries none.
 *
 * Null is not the unknown-code case. Hand-authored rules never went through the
 * formulator, so there is no derivation to explain and an explanation would be
 * invented. A record that *does* carry a code always gets words back.
 */
export function conditionRoute(
  provenance: ConditionProvenance | null | undefined
): ConditionRoute | null {
  if (!provenance) return null;
  return CONDITION_ROUTE[provenance.code] ?? UNKNOWN_CONDITION_ROUTE;
}
