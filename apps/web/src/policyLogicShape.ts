import type { PolicyAttribute, PolicyAttributes } from "./api";
import type { PolicyCard } from "./policyCards";
import type { LogicColumn } from "./policyLogic";
import { policyLogic } from "./policyLogic";

/**
 * The same comparison `policyLogic` computes, arranged so a whole rule fits on
 * one screen.
 *
 * WHY THIS EXISTS ALONGSIDE `policyLogic` AND NOT INSIDE IT
 *
 * `policyLogic` answers "which attributes did the rules of this policy fill,
 * and what did each rule put in them". That is the comparison, and it is right.
 * What it returns is shaped as a matrix — one cell per rule per attribute — and
 * a matrix is a layout decision that only works while the attributes fit across
 * the page. Measured on the live corpus they do not: the largest policy fills
 * fifteen of them across eighty-four rules, and one of its values is a
 * paragraph of several hundred characters. Drawn as a grid that is a page the
 * reviewer scrolls sideways to read, with the widest value setting the height
 * of an entire row.
 *
 * So this module re-arranges the same facts and adds none. Every string it
 * returns is either the document's own words, a canonical field name, or a
 * count of rules. Nothing is merged, nothing is shortened, and no attribute is
 * dropped: what was a row of cells becomes a block of attribute rows, and what
 * was a column of repeated "not stated" becomes one line per rule naming the
 * attributes that rule does not state.
 *
 * THE THIRD PART OF A ROW
 *
 * An attribute is three things — its own name, the document's words, and the
 * identifier a case supplies a value for. The matrix could only ever show two
 * of them, because the third had nowhere to go inside a cell that already held
 * a quotation. The identifier comes from `rule.attributes`, which the server
 * derives from the same canonical record and serves in the JSON; it is read
 * here and never recomputed, so what a reviewer sees and what they download are
 * the same table rather than two readings that can drift.
 *
 * SHAPES
 *
 * Two rules that filled the same set of attributes are the same *shape*. That
 * is a fact about the records — the same kind of fact as "five of twenty state
 * a time" — and at scale it is the one that makes a policy legible: on the
 * largest policy measured, two shapes account for two thirds of the rules and
 * seven rules are alone in theirs. Grouping is reported, never applied to the
 * rules themselves: they stay in the order the document states them, under the
 * passage that states them, because ordering by anything else would rank rules
 * against each other and a rule the source states in words would sink to the
 * bottom of every policy in the system.
 *
 * Shapes are computed only over rules that carry a decomposition. A rule with
 * none has no known shape, which is a different thing from an empty one.
 */

/** One attribute of one rule: its name, its words, and its identifier. */
export interface LogicAttributeReading {
  /** The canonical field name, exactly as the record declares it. Not renamed:
   *  a friendlier label changes what the row asserts. */
  attribute: string;
  /** The document's words, verbatim. */
  text: string;
  /** The fact a case supplies a value for, or null where the document states
   *  the value itself. */
  fact: string | null;
  /** `money` | `duration` | `number` | `boolean`, when the fact states one. */
  dataType: string | null;
}

export interface LogicRuleReading {
  ruleId: string;
  /** The rule's number on the card, so "rule 9" means the same in both. */
  ordinal: number;
  passageKey: string;
  /** Present only where the policy's rules disagree, as on the card's badges. */
  ruleType: string | null;
  route: string | null;
  /** What this rule states, in canonical slot order. */
  stated: LogicAttributeReading[];
  /** Attributes some rule of this policy states and this one does not. A fact
   *  about the rule, kept whole rather than repeated as a cell per attribute. */
  absent: string[];
  /** The record carries no decomposition, so nothing is known either way. */
  unrecorded: boolean;
  /** Index into `shapes`, or null when the shape is unknown. */
  shape: number | null;
  /** The state of every column, in column order, for the signature strip. */
  marks: LogicMark[];
}

export type LogicMark = "stated" | "absent" | "unrecorded";

/** Rules that filled the same set of attributes. */
export interface LogicShape {
  /** The attributes every rule in this group states, in column order. */
  attributes: string[];
  /** Their numbers on the card, in document order. */
  ruleOrdinals: number[];
}

/** One passage of the policy and the rules stated in it. */
export interface LogicPassageBlock {
  passageKey: string;
  rules: LogicRuleReading[];
}

/** What every rule says the same way, said once. */
export interface LogicSharedReading {
  attribute: string | null;
  label: string;
  text: string;
  fact: string | null;
  dataType: string | null;
}

export interface PolicyLogicShape {
  total: number;
  /** The attributes the rules do not all state alike, in canonical slot order,
   *  each with how many rules state it. Carried through unchanged. */
  columns: LogicColumn[];
  shared: LogicSharedReading[];
  blocks: LogicPassageBlock[];
  /** Distinct attribute sets, in order of first appearance in the document. */
  shapes: LogicShape[];
  /** How many rules carry no canonical decomposition at all. */
  unrecorded: number;
}

/** Every attribute row the server derived for a rule, both halves in one list.
 *
 *  The applies/outcome split is the server's and is meaningful, but it is not
 *  what this view is arranged by — the columns are, and they run in canonical
 *  slot order. Reading both halves into one lookup keeps that order the only
 *  one in play instead of interleaving two. */
function attributeRows(attributes: PolicyAttributes | undefined): PolicyAttribute[] {
  if (!attributes) return [];
  return [...(attributes.applies ?? []), ...(attributes.outcome ?? [])];
}

export function policyLogicShape(card: PolicyCard): PolicyLogicShape {
  const logic = policyLogic(card);

  /** Attribute name -> the row the server derived, per rule. */
  const derived = new Map<string, Map<string, PolicyAttribute>>();
  for (const rule of card.rules) {
    const rows = new Map<string, PolicyAttribute>();
    for (const row of attributeRows(rule.candidate.rule.attributes)) {
      // First wins. A record may carry the same attribute twice; taking the
      // first keeps this a lookup rather than a merge.
      if (!rows.has(row.attribute)) rows.set(row.attribute, row);
    }
    derived.set(rule.rule_id, rows);
  }

  const shapes: LogicShape[] = [];
  const shapeIndex = new Map<string, number>();

  const readings: LogicRuleReading[] = logic.rows.map((row) => {
    const rows = derived.get(row.ruleId);
    const stated: LogicAttributeReading[] = [];
    const absent: string[] = [];
    const marks: LogicMark[] = [];
    let unrecorded = false;

    row.cells.forEach((cell, index) => {
      const attribute = logic.columns[index].attribute;
      marks.push(cell.state);
      if (cell.state === "stated") {
        const found = rows?.get(attribute);
        // Only where the server's row is for the same words. A record whose
        // derived table disagrees with its canonical slot is a record this view
        // has no business reconciling, so it shows the slot's words and no
        // identifier rather than pairing words with an identifier that was
        // derived from different ones.
        const matches = found !== undefined && found.text.trim() === cell.text;
        stated.push({
          attribute,
          text: cell.text,
          fact: matches ? (found.fact ?? null) : null,
          dataType: matches ? (found.data_type ?? null) : null,
        });
      } else if (cell.state === "absent") {
        absent.push(attribute);
      } else {
        unrecorded = true;
      }
    });

    let shape: number | null = null;
    if (!unrecorded) {
      // The set is already in column order, so two rules filling the same
      // attributes produce the same key without sorting.
      const key = stated.map((row) => row.attribute).join("\u0000");
      const existing = shapeIndex.get(key);
      if (existing === undefined) {
        shape = shapes.length;
        shapeIndex.set(key, shape);
        shapes.push({
          attributes: stated.map((row) => row.attribute),
          ruleOrdinals: [row.ordinal],
        });
      } else {
        shape = existing;
        shapes[existing].ruleOrdinals.push(row.ordinal);
      }
    }

    return {
      ruleId: row.ruleId,
      ordinal: row.ordinal,
      passageKey: row.passageKey,
      ruleType: row.ruleType,
      route: row.route,
      stated,
      absent,
      unrecorded,
      shape,
      marks,
    };
  });

  const blocks: LogicPassageBlock[] = [];
  for (const reading of readings) {
    const last = blocks[blocks.length - 1];
    // Consecutive rather than keyed: the rows arrive in document order, and a
    // passage that states rules in two runs stated them in two runs.
    if (last && last.passageKey === reading.passageKey) last.rules.push(reading);
    else blocks.push({ passageKey: reading.passageKey, rules: [reading] });
  }

  const shared: LogicSharedReading[] = logic.shared.map((fact) => {
    const attribute = fact.attribute;
    const found = attribute
      ? card.rules
          .map((rule) => derived.get(rule.rule_id)?.get(attribute))
          .find((row) => row !== undefined && row.text.trim() === fact.value)
      : undefined;
    return {
      attribute: fact.attribute,
      label: fact.label,
      text: fact.value,
      fact: found?.fact ?? null,
      dataType: found?.data_type ?? null,
    };
  });

  return {
    total: logic.total,
    columns: logic.columns,
    shared,
    blocks,
    shapes,
    unrecorded: logic.unrecorded,
  };
}
