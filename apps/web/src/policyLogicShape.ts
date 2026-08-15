import type { PolicyAttribute, PolicyAttributes } from "./api";
import type { PolicyCard, PolicyCardRule } from "./policyCards";
import { sharedRuleFacets } from "./policyCards";
import { effectMeta } from "./ruleDisplay";

/**
 * Every rule of one policy, arranged so a whole rule fits on one screen.
 *
 * WHERE THE ATTRIBUTES COME FROM, AND WHY ONLY FROM THERE
 *
 * `rule.attributes` — the table the server derives once from the canonical
 * record and serves in the JSON, split into what scopes the rule (`applies`)
 * and what follows from it (`outcome`), each row already carrying the
 * identifier a case supplies a value for. It is read here and nothing is
 * recomputed.
 *
 * An earlier version of this module read the canonical slots instead and then
 * joined the derived rows back on by comparing their text, so it could show the
 * identifier alongside the words. That is two readings of one record, which is
 * the arrangement the rule inspector's own notes say it was built to end: a
 * correction to how attributes pair with facts then has to be made twice, and
 * until it is, one surface disagrees with the other. Measured against the live
 * corpus before this was changed, the two readings agreed on all 3,291 attribute
 * values of both stored documents — no slot the derived table lacked, no derived
 * row no slot held, and no differing text. Agreeing today is not the same as
 * being unable to disagree, and the join is what made disagreement possible.
 *
 * So there is one source, and the aggregate below is a fold over exactly the
 * rows each rule's tree draws. A count cannot claim an attribute a rule's own
 * block does not show.
 *
 * WHAT IT ARRANGES AND WHAT IT REFUSES TO
 *
 * Every string it returns is a run of the document, a canonical field name, an
 * effect the record declares, or a count of rules. Nothing is merged, nothing is
 * shortened, no attribute is dropped, and no summary is composed. Counting how
 * many rules state a slot is a fact about the rules; a policy-level modality or
 * a merged condition would be a claim the document did not make.
 *
 * Rules stay in the order the document states them, under the passage that
 * states them. Ordering by how many attributes a rule filled would be a
 * completeness score with a different name, and a rule whose test the source
 * states in words would sit at the bottom of every policy in the system.
 *
 * ABSENCE IS NOT EMPTINESS
 *
 * A rule whose table names no actor and a rule with no table at all are
 * different facts. The first is `absent` — the decomposition is present and
 * names no such component. The second is `unrecorded`, and only that one wears
 * `loadState.UNKNOWN_COUNT`, which in this app means "we could not ask".
 *
 * THE ORDER THE ATTRIBUTES ARE COUNTED IN
 *
 * Not a fixed list kept here. Each record states its attributes in an order, and
 * the orders agree: across both stored documents no two records disagree about
 * which of any two attributes comes first. So the order is recovered from the
 * records themselves by sorting on the precedences they state, which needs no
 * table to maintain, cannot drift from what the records do, and names no
 * attribute this file has heard of. Where records of one policy do contradict
 * each other the sort falls back to the order they were first seen in, which is
 * still the document's and still stable for that policy.
 *
 * SHAPES
 *
 * Two rules that stated the same set of attributes are the same *shape*. That is
 * the same kind of fact as "five of twenty state a time", and at scale it is the
 * one that makes a policy legible. Grouping is reported, never applied.
 */

/** Which half of the rule an attribute was recorded in. */
export type LogicSide = "applies" | "outcome";

/** One attribute of one rule: its name, its words, and its identifier. */
export interface LogicAttributeReading {
  /** The canonical field name, exactly as the record declares it. Not renamed:
   *  a friendlier label changes what the row asserts. */
  attribute: string;
  side: LogicSide;
  /** The document's words, verbatim. */
  text: string;
  /** The fact a case supplies a value for, or null where the document states
   *  the value itself. */
  fact: string | null;
  /** `money` | `duration` | `number` | `boolean`, when the fact states one. */
  dataType: string | null;
}

/** One half of a rule, as the rule inspector draws it. */
export interface LogicBranch {
  side: LogicSide;
  /** `APPLIES` for the half that scopes the rule; for the other half, the
   *  effect the record declares, which is why it reads `REQUIRES` on one rule
   *  and `PROHIBITS` on the next. Never derived from anything else. */
  heading: string;
  /** The rows this rule states on this side, in the record's own order. */
  rows: LogicAttributeReading[];
  /** Attributes some rule of this policy states on this side and this one does
   *  not. A true statement about the rule, kept whole rather than repeated as
   *  an empty cell per attribute. */
  absent: string[];
}

export type LogicMark = "stated" | "absent" | "unrecorded";

export interface LogicRuleReading {
  ruleId: string;
  /** The rule's number on the card, so "rule 9" means the same in both. */
  ordinal: number;
  passageKey: string;
  /** Present only where the policy's rules disagree, as on the card's badges. */
  ruleType: string | null;
  route: string | null;
  /** The two halves, scope first, always both — a half a rule states nothing in
   *  says so, because "this rule attaches no conditions" is a fact a reviewer
   *  checking completeness needs. */
  branches: LogicBranch[];
  /** Everything the rule states, in the counted order. Used for the shape and
   *  the signature; the branches are what a reader reads. */
  stated: LogicAttributeReading[];
  /** The record carries no attribute table, so nothing is known either way. */
  unrecorded: boolean;
  /** Index into `shapes`, or null when the shape is unknown. */
  shape: number | null;
  /** The state of every counted attribute, in that order. */
  marks: LogicMark[];
}

/** One rule of a shape group: its number on the card, and which rule it is. */
export interface LogicShapeMember {
  ordinal: number;
  ruleId: string;
}

/** Rules that stated the same set of attributes. */
export interface LogicShape {
  attributes: string[];
  /** Them, in document order. */
  rules: LogicShapeMember[];
}

/** One passage of the policy and the rules stated in it. */
export interface LogicPassageBlock {
  passageKey: string;
  rules: LogicRuleReading[];
}

/** One attribute of the policy, and how many of its rules state it. */
export interface LogicCoverage {
  attribute: string;
  side: LogicSide;
  /** How many rules state it. Never a proportion and never a bar: "1 of 20" is
   *  a fact, "5%" invites reading it as a shortfall. */
  filled: number;
  /** Every rule states it with the same words. Said here so a reader knows the
   *  repetition down the blocks is the document repeating itself. */
  uniform: boolean;
}

/** What every rule says the same way. */
export interface LogicSharedReading {
  attribute: string;
  side: LogicSide;
  text: string;
  fact: string | null;
  dataType: string | null;
}

export interface PolicyLogicShape {
  total: number;
  /** Every attribute any rule states, in the order the records state them. */
  columns: LogicCoverage[];
  shared: LogicSharedReading[];
  blocks: LogicPassageBlock[];
  /** Distinct attribute sets, in order of first appearance in the document. */
  shapes: LogicShape[];
  /** How many rules carry no attribute table at all. */
  unrecorded: number;
}

/** The heading the scoping half of every rule wears, as the inspector says it. */
const APPLIES_HEADING = "APPLIES";

const SIDES: LogicSide[] = ["applies", "outcome"];

function sideRows(
  attributes: PolicyAttributes | undefined,
  side: LogicSide,
): PolicyAttribute[] {
  if (!attributes) return [];
  return side === "applies" ? (attributes.applies ?? []) : (attributes.outcome ?? []);
}

function hasTable(rule: PolicyCardRule): boolean {
  const attributes = rule.candidate.rule.attributes;
  return attributes !== undefined && attributes !== null;
}

/**
 * The order the records themselves put these attributes in.
 *
 * Every record states its attributes in some order; each states some of the
 * precedences of the whole order and none states all of them. Sorting on the
 * precedences observed recovers it. Ties, and any pair the records contradict
 * each other about, fall back to first appearance in document order — so the
 * result is always a total order and always one the records support.
 */
function statedOrder(sequences: string[][]): string[] {
  const first = new Map<string, number>();
  const after = new Map<string, Set<string>>();
  let seen = 0;

  for (const sequence of sequences) {
    for (let i = 0; i < sequence.length; i += 1) {
      const name = sequence[i];
      if (!first.has(name)) {
        first.set(name, seen);
        seen += 1;
        after.set(name, new Set());
      }
      const later = after.get(name);
      for (let j = i + 1; j < sequence.length; j += 1) later?.add(sequence[j]);
    }
  }

  const remaining = new Set(first.keys());
  const order: string[] = [];
  while (remaining.size > 0) {
    const ready = [...remaining].filter((name) =>
      [...remaining].every((other) => other === name || !after.get(other)?.has(name)),
    );
    // Contradicting records leave nothing ready; take the earliest seen and
    // carry on rather than dropping attributes on the floor.
    const take = (ready.length > 0 ? ready : [...remaining]).sort(
      (a, b) => (first.get(a) ?? 0) - (first.get(b) ?? 0),
    );
    order.push(take[0]);
    remaining.delete(take[0]);
  }
  return order;
}

export function policyLogicShape(card: PolicyCard): PolicyLogicShape {
  const facets = sharedRuleFacets(card);
  const total = card.rules.length;

  /** Every attribute any rule states, per side, in the records' own order. */
  const counted: LogicCoverage[] = [];
  const countedBySide = new Map<LogicSide, string[]>();

  for (const side of SIDES) {
    const order = statedOrder(
      card.rules.map((rule) =>
        sideRows(rule.candidate.rule.attributes, side).map((row) => row.attribute),
      ),
    );
    countedBySide.set(side, order);
    for (const attribute of order) {
      const values = card.rules
        .map(
          (rule) =>
            sideRows(rule.candidate.rule.attributes, side).find(
              (row) => row.attribute === attribute,
            )?.text,
        )
        .filter((value): value is string => value !== undefined);
      counted.push({
        attribute,
        side,
        filled: values.length,
        uniform:
          total > 0 &&
          values.length === total &&
          values.every((value) => value === values[0]),
      });
    }
  }

  const shapes: LogicShape[] = [];
  const shapeIndex = new Map<string, number>();
  const blocks: LogicPassageBlock[] = [];

  let ordinal = 0;
  for (const passage of card.passages) {
    for (const rule of passage.rules) {
      ordinal += 1;
      const attributes = rule.candidate.rule.attributes;
      const unrecorded = !hasTable(rule);

      const branches: LogicBranch[] = SIDES.map((side) => {
        const rows: LogicAttributeReading[] = sideRows(attributes, side).map((row) => ({
          attribute: row.attribute,
          side,
          text: row.text,
          fact: row.fact ?? null,
          dataType: row.data_type ?? null,
        }));
        const present = new Set(rows.map((row) => row.attribute));
        return {
          side,
          heading:
            side === "applies"
              ? APPLIES_HEADING
              : effectMeta(rule.candidate.rule.effect?.type ?? "").label.toUpperCase(),
          rows,
          absent: unrecorded
            ? []
            : (countedBySide.get(side) ?? []).filter((name) => !present.has(name)),
        };
      });

      const stated: LogicAttributeReading[] = [];
      const marks: LogicMark[] = [];
      for (const column of counted) {
        const found = branches
          .find((branch) => branch.side === column.side)
          ?.rows.find((row) => row.attribute === column.attribute);
        if (unrecorded) marks.push("unrecorded");
        else if (found) {
          marks.push("stated");
          stated.push(found);
        } else marks.push("absent");
      }

      let shape: number | null = null;
      if (!unrecorded) {
        // The set is already in the counted order, so two rules stating the
        // same attributes produce the same key without sorting.
        const key = stated.map((row) => `${row.side}\u0001${row.attribute}`).join("\u0000");
        const existing = shapeIndex.get(key);
        if (existing === undefined) {
          shape = shapes.length;
          shapeIndex.set(key, shape);
          shapes.push({
            attributes: stated.map((row) => row.attribute),
            rules: [{ ordinal, ruleId: rule.rule_id }],
          });
        } else {
          shape = existing;
          shapes[existing].rules.push({ ordinal, ruleId: rule.rule_id });
        }
      }

      const reading: LogicRuleReading = {
        ruleId: rule.rule_id,
        ordinal,
        passageKey: passage.passage.key,
        ruleType: facets.ruleType === null ? rule.candidate.rule.rule_type : null,
        route: facets.route === null ? rule.evaluation_mode : null,
        branches,
        stated,
        unrecorded,
        shape,
        marks,
      };

      const last = blocks[blocks.length - 1];
      // Consecutive rather than keyed: the rules arrive in document order, and
      // a passage that states rules in two runs stated them in two runs.
      if (last && last.passageKey === reading.passageKey) last.rules.push(reading);
      else blocks.push({ passageKey: reading.passageKey, rules: [reading] });
    }
  }

  /* What every rule states the same way. Reported, not removed from the rules:
     each block draws the rule's whole table, the same table the rule inspector
     draws, and a block missing the rows this policy happens to agree on would
     be a different reading of one record depending on its neighbours. */
  const shared: LogicSharedReading[] = counted
    .filter((column) => column.uniform)
    .map((column) => {
      const row = sideRows(card.rules[0]?.candidate.rule.attributes, column.side).find(
        (candidate) => candidate.attribute === column.attribute,
      );
      return {
        attribute: column.attribute,
        side: column.side,
        text: row?.text ?? "",
        fact: row?.fact ?? null,
        dataType: row?.data_type ?? null,
      };
    });

  return {
    total,
    columns: counted,
    shared,
    blocks,
    shapes,
    unrecorded: card.rules.filter((rule) => !hasTable(rule)).length,
  };
}
