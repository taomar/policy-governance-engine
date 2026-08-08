import type { ConditionNode, ConditionOperator } from "./api";

/** One row of the simple condition editor: a single fact comparison.
 *
 * Shared by the draft form and the edit/revise modal. Both previously carried
 * their own copy of this type and its two converters, so a fix to how a value
 * is coerced or how nested logic is detected had to be made twice to be true —
 * the classic way two forms drift into disagreeing about the same rule. */
export interface ConditionRow {
  fact: string;
  operator: string;
  value: string;
}

export const CONDITION_OPERATORS: ConditionOperator[] = [
  "equals",
  "notEquals",
  "greaterThan",
  "greaterThanOrEqual",
  "lessThan",
  "lessThanOrEqual",
  "in",
  "notIn",
  "contains",
  "startsWith",
  "endsWith",
  "exists",
  "isNull",
];

/** Rows -> condition tree. Multiple rows are ANDed, matching what the editor
 * shows the user ("all of these must hold"). */
export function buildCondition(rows: ConditionRow[]): ConditionNode {
  const leaves: ConditionNode[] = rows.map((r) => {
    let value: unknown = r.value;
    if (value !== "" && !isNaN(Number(value))) value = Number(value);
    else if (value === "true") value = true;
    else if (value === "false") value = false;
    return { type: "factComparison", fact: r.fact, operator: r.operator as ConditionOperator, value };
  }) as ConditionNode[];
  if (leaves.length === 1) return leaves[0];
  return { type: "all", all: leaves };
}

/** Condition tree -> rows, or `null` when the tree is richer than the row
 * editor can represent (OR/NOT/nesting, or a vacuous placeholder).
 *
 * Returning `null` rather than a lossy approximation is deliberate: the caller
 * switches to raw-JSON mode instead of silently rewriting the user's logic
 * into something simpler that means something else. */
export function conditionToRows(node: ConditionNode | undefined): ConditionRow[] | null {
  if (!node) return null;
  const flatten = (n: ConditionNode): ConditionRow[] | null => {
    if (n.type === "factComparison") {
      return [
        {
          fact: n.fact,
          operator: n.operator,
          value: n.value === null || n.value === undefined ? "" : String(n.value),
        },
      ];
    }
    if (n.type === "all") {
      const rows: ConditionRow[] = [];
      for (const child of n.all) {
        if (child.type !== "factComparison") return null; // nested logic — fall back to advanced mode
        rows.push({
          fact: child.fact,
          operator: child.operator,
          value: child.value === null || child.value === undefined ? "" : String(child.value),
        });
      }
      return rows;
    }
    return null; // any/not — too complex for the row editor, use advanced mode
  };
  return flatten(node);
}

/** True when a condition constrains nothing, i.e. it matches every scenario.
 *
 * The extraction pipeline emits an empty conjunction (`{type: "all", all: []}`)
 * for a policy it could state in prose but not reduce to fact comparisons.
 * Worth naming rather than testing inline: such a rule is perfectly valid and
 * publishable, so the UI must present it as "no condition yet", not as broken
 * or unsupported logic. */
export function isVacuousCondition(node: ConditionNode | undefined | null): boolean {
  if (!node) return true;
  if (node.type === "all") return node.all.length === 0;
  if (node.type === "any") return node.any.length === 0;
  return false;
}
