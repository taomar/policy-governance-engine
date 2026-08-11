/**
 * Deterministic, presentation-only helpers derived straight from the
 * structured `CanonicalRule` / `ConditionNode` / `PolicyScope` contracts —
 * no AI, no guessing. Shared by the compact Policies list (`PolicyRow`),
 * the detail inspector (`PolicyInspector`), and the existing `RuleCard`/
 * `ConditionView`, so "what does this rule say" is rendered identically
 * everywhere instead of drifting between a summary and the full view.
 */
import type { CanonicalRule, ConditionNode, Effect, FactOperand, PolicyScope } from "./api";

/** Symbol shown for each condition operator — kept as the single source of
 * truth for both the full condition tree (`ConditionView`) and the short
 * one-line summaries used in list rows. */
export const OPERATOR_SYMBOLS: Record<string, string> = {
  equals: "=",
  notEquals: "≠",
  greaterThan: ">",
  greaterThanOrEqual: "≥",
  lessThan: "<",
  lessThanOrEqual: "≤",
  in: "in",
  notIn: "not in",
  contains: "contains",
  startsWith: "starts with",
  endsWith: "ends with",
  exists: "exists",
  isNull: "is null",
  before: "before",
  after: "after",
  onOrBefore: "on or before",
  onOrAfter: "on or after",
  withinDuration: "within",
  countEquals: "count =",
  countGreaterThan: "count >",
};

/**
 * True when a condition tree imposes no test at all.
 *
 * Mirrors `_is_vacuous` in the evaluator, which refuses to let such a rule
 * match. Shown rather than rendered as a tree because an empty `all` draws a
 * bare "ALL of" with nothing under it, which tells a reviewer nothing about
 * the policy on the one panel meant to explain when it fires.
 */
export function isEmptyCondition(node: ConditionNode): boolean {
  if (node.type === "all") return node.all.length === 0;
  if (node.type === "any") return node.any.length === 0;
  return false;
}

/**
 * The machine annotations `formulation_mapping` appends to every description.
 *
 * They are the audit trail — which agent, which source element, which DMN
 * status, why the condition tree is empty — and they belong on the record. They
 * do not belong in the middle of a sentence a reviewer is reading, where three
 * of them run together into a block like:
 *
 *   "…are subject to the approval of the President. [Formulated by policy agent
 *    — source: p1-E000008] [DMN mapping: not_directly_mappable] [Conditions:
 *    no_scope_derived — No conditions were found in the source. …]"
 *
 * Stripped for display only; nothing is removed from the record. The
 * `[Conditions: …]` note is also carried structurally on
 * `condition_provenance`, which the inspector renders as its own panel — so
 * hiding it here loses nothing and stops the same fact being read twice in two
 * different registers.
 */
const MACHINE_ANNOTATION = /\s*\[(?:Formulated by|DMN mapping:|Conditions:)[^\]]*\]/g;

export function readableDescription(description: string | undefined | null): string {
  return (description ?? "").replace(MACHINE_ANNOTATION, "").trim();
}

export function formatConditionValue(value: unknown): string {  if (value === null || value === undefined) return "";
  if (Array.isArray(value)) return `[${value.map(formatConditionValue).join(", ")}]`;
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function leafText(node: Extract<ConditionNode, { type: "factComparison" }>): string {
  const symbol = OPERATOR_SYMBOLS[node.operator] ?? node.operator;
  const showValue = !["exists", "isNull"].includes(node.operator);
  return showValue ? `${node.fact} ${symbol} ${formatConditionValue(node.value)}` : `${node.fact} ${symbol}`;
}

/**
 * The proportion a `FactOperand` applies, as the percentage the policy stated
 * ("10%"), or null when the operand is the plain fact.
 */
export function formatFactor(factor: number): string | null {
  if (factor === 1) return null;
  const percent = factor * 100;
  // Guard against binary-float artefacts (0.07 * 100 = 7.000000000000001).
  return `${Number.isInteger(percent) ? percent : Number(percent.toFixed(6))}%`;
}

/**
 * Renders "10% of employee.compensation.basic_salary" rather than the raw
 * `0.1` factor. A reviewer checking a rule against the policy text is looking
 * for the percentage the document states, so showing the multiplier instead
 * would make them do the arithmetic to confirm the rule says what the
 * document says.
 *
 * A factor of exactly 1 is the plain fact, with no proportion to state.
 */
export function formatFactOperand(operand: FactOperand): string {
  const factor = formatFactor(operand.factor);
  return factor ? `${factor} of ${operand.fact}` : operand.fact;
}

function relativeLeafText(
  node: Extract<ConditionNode, { type: "factRelativeComparison" }>,
): string {
  const symbol = OPERATOR_SYMBOLS[node.operator] ?? node.operator;
  return `${node.fact} ${symbol} ${formatFactOperand(node.reference)}`;
}

function collectLeafTexts(node: ConditionNode): string[] {
  if (node.type === "factComparison") return [leafText(node)];
  if (node.type === "factRelativeComparison") return [relativeLeafText(node)];
  if (node.type === "all") return node.all.flatMap(collectLeafTexts);
  if (node.type === "any") return node.any.flatMap(collectLeafTexts);
  return [`NOT (${collectLeafTexts(node.not).join(" · ")})`];
}

export interface ConditionSummary {
  /** Short, scannable rendering of the condition, e.g. "amount ≤ 100" or
   * "ALL: country = US · amount > 500 · +2 more". */
  text: string;
  /** Total number of leaf comparisons in the condition (for "+N more"). */
  termCount: number;
  truncated: boolean;
}

/**
 * Deterministically renders a `ConditionNode` as a short, human-readable
 * string, gracefully truncating complex conditions to `maxTerms` leaf
 * comparisons. The full expression remains available via `ConditionView`
 * in the inspector's Logic tab — this is only ever a summary.
 */
export function summarizeCondition(node: ConditionNode, maxTerms = 3): ConditionSummary {
  if (node.type === "factComparison") {
    return { text: leafText(node), termCount: 1, truncated: false };
  }
  if (node.type === "factRelativeComparison") {
    return { text: relativeLeafText(node), termCount: 1, truncated: false };
  }
  if (node.type === "not") {
    const inner = summarizeCondition(node.not, maxTerms);
    return { text: `NOT ${inner.text}`, termCount: inner.termCount, truncated: inner.truncated };
  }
  const prefixLabel = node.type === "all" ? "ALL" : "ANY";
  const leaves = collectLeafTexts(node);
  if (leaves.length <= 1) {
    return { text: leaves[0] ?? "", termCount: leaves.length, truncated: false };
  }
  const shown = leaves.slice(0, maxTerms);
  const remaining = leaves.length - shown.length;
  return {
    text: `${prefixLabel}: ${shown.join(" · ")}${remaining > 0 ? ` · +${remaining} more` : ""}`,
    termCount: leaves.length,
    truncated: remaining > 0,
  };
}

/** Generic snake_case/identifier → readable text helper — shared by action
 * names, fact names, and any other machine identifier that needs a human
 * label (kept generic rather than duplicating the same regex per call site). */
export function humanizeIdentifier(id: string): string {
  return id.replace(/_/g, " ").trim();
}

export function humanizeAction(action: string): string {
  return humanizeIdentifier(action);
}

/** What the policy *does*, as a calm descriptive label.
 *
 * These describe the rule's own nature — whether the document permits,
 * forbids, requires or defines something. They are not statuses, and nothing
 * here is addressed to the reader.
 *
 * The labels used to be the internal effect identifiers in capitals, and
 * `require_action` rendered as "REQUIRE ACTION" in amber. That reads as an
 * instruction to the person looking at it, so an ordinary obligation — the
 * single most common kind of policy statement there is — appeared on every
 * other row as though it were demanding attention. It was describing the
 * sentence, not asking for anything.
 *
 * Colour is descriptive too, and deliberately quiet. Red and amber are the
 * palette of things going wrong; a rule that forbids something is not a
 * problem, it is a policy doing its job.
 */
export const EFFECT_META: Record<string, { label: string; color: string }> = {
  allow: { label: "Permits", color: "green" },
  deny: { label: "Prohibits", color: "geekblue" },
  require_action: { label: "Requires", color: "blue" },
  // Definitions and classifications state vocabulary; they authorise nothing.
  informational: { label: "Defines", color: "default" },
};

export function effectMeta(effectType: string): { label: string; color: string } {
  return EFFECT_META[effectType] ?? { label: humanizeIdentifier(effectType), color: "default" };
}

export interface RuleDecisionSummary {
  condition: string;
  action: string;
  text: string;
  truncated: boolean;
  /**
   * True when `condition` is the source's own wording rather than a compiled
   * tree. The caller should mark it, because a stated-but-uncompiled condition
   * is not something the deterministic engine will test.
   */
  conditionIsStatedOnly: boolean;
}

/**
 * The condition the source states, when the compiled tree is empty.
 *
 * An empty tree used to render as "Always", which is a false statement about
 * every rule whose condition could not be compiled. Three housing-allowance
 * rules — one per staff category, at two different limits — all displayed as
 * "WHEN Always", so each claimed to apply to everyone, and the two capped at
 * 15,000 SAR became indistinguishable on screen because the staff category was
 * the only thing separating them and it was exactly what went missing.
 *
 * The wording is read from the canonical decomposition and the semantic
 * projection, both of which already carry it verbatim. Nothing is inferred:
 * if the source states no condition, this returns null and "Always" is then
 * the truth.
 */
function statedCondition(rule: CanonicalRule): string | null {
  const canonical = rule.formulation?.canonical?.rule?.condition;
  if (canonical && canonical.trim()) return canonical.trim();
  for (const decision of rule.formulation?.dmn_decisions ?? []) {
    const projection = decision.semantic_projection;
    if (!projection) continue;
    const phrases = [...(projection.conditions ?? []), projection.condition_source ?? ""].filter(
      (p) => p && p.trim()
    );
    if (phrases.length > 0) return phrases.join(" · ");
  }
  return null;
}

export function ruleDecisionSummary(rule: CanonicalRule, maxTerms = 3): RuleDecisionSummary {
  const cond = summarizeCondition(rule.condition, maxTerms);
  const stated = cond.text ? null : statedCondition(rule);
  // "Always" only when the source genuinely conditions nothing. Saying it for
  // a rule the document did condition is not a simplification — it inverts the
  // rule's scope, from "these staff" to "everyone".
  const condition = cond.text || stated || "Always";
  const action = humanizeAction(rule.effect.action || rule.effect.type);
  return {
    condition,
    action,
    text: `${condition} → ${action}`,
    truncated: cond.truncated,
    conditionIsStatedOnly: !cond.text && stated !== null,
  };
}

/** Backward-compatible string form for search results and callers that do not
 * need the structured WHEN / THEN presentation. */
export function ruleConditionLine(rule: CanonicalRule, maxTerms = 3): { text: string; truncated: boolean } {
  const summary = ruleDecisionSummary(rule, maxTerms);
  return { text: summary.text, truncated: summary.truncated };
}

/** Same "who/where this rule applies to" phrase RuleCard has always shown,
 * moved here so it has one implementation shared with the new Scope tab. */
export function describeScope(scope: PolicyScope): string {
  return (
    [
      scope.personas.length ? `Personas: ${scope.personas.join(", ")}` : null,
      scope.organizational_units.length ? `Units: ${scope.organizational_units.join(", ")}` : null,
      scope.jurisdictions.length ? `Jurisdictions: ${scope.jurisdictions.join(", ")}` : null,
      scope.processes.length ? `Processes: ${scope.processes.join(", ")}` : null,
    ]
      .filter(Boolean)
      .join(" · ") || "Applies globally (no entity restriction)"
  );
}

export interface ScopeEntry {
  label: string;
  value: string;
  isDefault: boolean;
}

/** Structured "Applies to" rows for the inspector's Scope tab — each
 * dimension shown individually rather than one run-on sentence. */
export function scopeEntries(scope: PolicyScope): ScopeEntry[] {
  const entry = (label: string, values: string[]): ScopeEntry =>
    values.length ? { label, value: values.join(", "), isDefault: false } : { label, value: "All", isDefault: true };
  return [
    entry("Persona", scope.personas),
    entry("Business Unit", scope.organizational_units),
    entry("Jurisdiction", scope.jurisdictions),
    entry("Process", scope.processes),
  ];
}

export function effectActionText(effect: Effect): string {
  return humanizeAction(effect.action || effect.type);
}

/** Severity-ranked label + color for a rule's `ambiguity_status`, matching
 * the real backend enum (`contracts/policy.py` `AmbiguityStatus`: none /
 * non_blocking / human_judgment_required / blocking). "none" is the only
 * "nothing to flag" value — "clear" is not a valid value and must never be
 * used as the sentinel (a bug that previously caused the ambiguity flag to
 * render on every rule, since no real rule ever has that literal string). */
export const AMBIGUITY_META: Record<string, { label: string; color: string }> = {
  none: { label: "Clear", color: "green" },
  non_blocking: { label: "Non-blocking note", color: "blue" },
  human_judgment_required: { label: "Human judgment required", color: "gold" },
  blocking: { label: "Blocking", color: "red" },
};

export function ambiguityMeta(status: string): { label: string; color: string } {
  return AMBIGUITY_META[status] ?? { label: status.replace(/_/g, " "), color: "gold" };
}

/** Whether a rule's ambiguity status is worth flagging in a compact view —
 * true for anything other than "none". */
export function hasAmbiguityFlag(status: string): boolean {
  return status !== "none";
}

export interface RuleVariationGroup {
  /** The clustering key: the curated `group_label` text when `kind` is
   * "group", or the shared condition fact name (e.g. "role_profile") when
   * `kind` is "condition". */
  key: string;
  /** "group" — sourced from the curated, authoritative `group_label` field
   * (populated by AI extraction or manual review — see `ai_extraction.py`).
   * "condition" — computed on-the-fly from a shared `factComparison`
   * condition; only used as a fallback when the rule has no `group_label`. */
  kind: "group" | "condition";
  /** Every rule in the cluster (including the rule being inspected). Sorted
   * by title for "group" clusters, by compared value for "condition"
   * clusters, for stable and scannable ordering either way. */
  members: CanonicalRule[];
}

/**
 * Builds the "variations of one decision" cluster for every rule in
 * `allRules` in a single pass, preferring the curated, authoritative
 * `group_label` field when populated and falling back to a display-only
 * heuristic when it isn't. This is the one real implementation — both the
 * per-rule lookup (`findRuleVariations`, used by the inspector) and the
 * whole-list left-side banding (`PolicyList`) read from the same map so the
 * two views can never disagree about which rules are related.
 *
 * **Curated path** (`kind: "group"`): rules sharing the same non-empty
 * `group_label` are grouped together — this is the real, intended
 * clustering key (AI extraction derives `related_rule_ids` from matching
 * `group_label`s, and the Review Queue already surfaces "similar rules by
 * group_label" matches), so it always takes priority over the heuristic
 * below when available.
 *
 * **Heuristic fallback** (`kind: "condition"`, used only when `group_label`
 * is empty — currently true for every rule in all of this platform's
 * sample projects, since they were extracted before `group_label` existed):
 * clusters rules sharing the same `rule_type` and a top-level `condition`
 * that compares the same fact (e.g. five separate "<role> device
 * entitlement" rules that each check `role_profile` against a different
 * value: Contact centre / Data and research / Design and media /
 * Engineering / Executive). Deliberately restricted to simple
 * `factComparison` conditions (no compound `all`/`any` traversal) to keep
 * the match precise, and requires the members to actually *vary* — at
 * least 2 distinct operator+value comparisons — so two unrelated rules
 * that merely share an identical guard (e.g. two different rules both
 * requiring `colleague_in_scope equals true`) are correctly treated as
 * coincidence, not a variation set.
 *
 * Only ever *reads* `CanonicalRule[]` already loaded in the browser — never
 * writes `group_label` / `related_rule_ids` back to the database. Rules
 * that belong to no cluster are simply absent from the returned map (no
 * `null` entries), so `map.has(ruleId)` doubles as the "is this rule part
 * of a visible family" check.
 */
/**
 * Which document a rule was extracted from, as a stable scoping key.
 *
 * Rules with no evidence share the empty scope. That groups all unsourced
 * rules together rather than isolating each one, which is the safer of the two
 * wrong answers: an unsourced rule cannot be shown to belong to any document,
 * so excluding it from every family would silently hide real relationships.
 */
function documentScope(rule: CanonicalRule): string {
  const ids = Array.from(new Set((rule.evidence ?? []).map((e) => e.document_version_id)));
  return ids.sort().join(",");
}

export function buildVariationClusters(allRules: CanonicalRule[]): Map<string, RuleVariationGroup> {
  const result = new Map<string, RuleVariationGroup>();

  // Curated pass: bucket by group_label first so it always wins over the heuristic below.
  //
  // Bucketed per source document, not by label alone. A label is derived from a
  // statement's subject and predicate, so two unrelated documents that happen to
  // phrase something the same way ("This policy applies to") produce the same
  // label — measured on real data as 7 topic keys spanning up to 3 documents.
  // Merging those would assert a relationship neither document stated, and the
  // reviewer would see one family whose members contradict each other for no
  // visible reason. Cross-document relationships need their own evidence.
  const byGroupLabel = new Map<string, CanonicalRule[]>();
  for (const r of allRules) {
    if (!r.group_label) continue;
    const bucket = `${documentScope(r)}\u0000${r.group_label}`;
    if (!byGroupLabel.has(bucket)) byGroupLabel.set(bucket, []);
    byGroupLabel.get(bucket)!.push(r);
  }
  for (const members of byGroupLabel.values()) {
    if (members.length < 2) continue;
    const sorted = [...members].sort((a, b) => a.title.localeCompare(b.title));
    // Keyed on the label the user reads, not the internal bucket — the document
    // is a scoping boundary, never part of the family's name.
    const group: RuleVariationGroup = { key: members[0].group_label, kind: "group", members: sorted };
    for (const r of members) result.set(r.rule_id, group);
  }

  // Heuristic pass: only for rules the curated pass didn't already place.
  // Scoped per document for the same reason as the curated pass — two policies
  // testing the same fact are not variations of one decision just because they
  // share a fact name, and presenting them as one family would invent a
  // relationship across documents that neither one states.
  const byFactAndType = new Map<string, CanonicalRule[]>();
  for (const r of allRules) {
    if (result.has(r.rule_id)) continue;
    if (r.condition.type !== "factComparison") continue;
    const bucketKey = `${documentScope(r)}\u0000${r.rule_type}::${r.condition.fact}`;
    if (!byFactAndType.has(bucketKey)) byFactAndType.set(bucketKey, []);
    byFactAndType.get(bucketKey)!.push(r);
  }
  const valueOf = (r: CanonicalRule) => {
    const cond = r.condition as Extract<ConditionNode, { type: "factComparison" }>;
    return { signature: `${cond.operator}:${formatConditionValue(cond.value)}`, text: formatConditionValue(cond.value) };
  };
  for (const members of byFactAndType.values()) {
    if (members.length < 2) continue;
    if (new Set(members.map((r) => valueOf(r).signature)).size < 2) continue;
    const fact = (members[0].condition as Extract<ConditionNode, { type: "factComparison" }>).fact;
    const sorted = [...members].sort((a, b) => valueOf(a).text.localeCompare(valueOf(b).text));
    const group: RuleVariationGroup = { key: fact, kind: "condition", members: sorted };
    for (const r of members) result.set(r.rule_id, group);
  }

  // Relationship pass: connected components of `related_rule_ids`.
  //
  // That field now carries the confirmed relationship graph — rows of one
  // table, a governing stem and the clauses that complete it, an explicit
  // cross-reference — while `group_label` only ever carried what a shared DMN
  // decision table named. Banding read the second and ignored the first, so on
  // a real document 22 rules had relationships and 4 were banded: the work of
  // establishing the links was invisible exactly where a reviewer needed it.
  //
  // Only confirmed edges reach `related_rule_ids`, so treating them as a family
  // holds them to the same standard as a curated group rather than a weaker one.
  const remaining = allRules.filter((r) => !result.has(r.rule_id));
  const byId = new Map(remaining.map((r) => [r.rule_id, r]));
  const seen = new Set<string>();
  for (const rule of remaining) {
    if (seen.has(rule.rule_id)) continue;

    // Walk the component. Edges are stored on both endpoints, but a one-sided
    // edge would otherwise split one family into two, so neighbours are
    // followed in both directions.
    const component: CanonicalRule[] = [];
    const queue = [rule.rule_id];
    seen.add(rule.rule_id);
    while (queue.length > 0) {
      const id = queue.pop()!;
      const current = byId.get(id);
      if (!current) continue;
      component.push(current);
      const neighbours = new Set(current.related_rule_ids ?? []);
      for (const other of remaining) {
        if ((other.related_rule_ids ?? []).includes(id)) neighbours.add(other.rule_id);
      }
      for (const next of neighbours) {
        if (seen.has(next) || !byId.has(next)) continue;
        seen.add(next);
        queue.push(next);
      }
    }
    if (component.length < 2) continue;

    // Named after the member the others point at most — the governing stem of
    // an enumeration is exactly the rule with the most inbound links, so the
    // family reads as what it is rather than as whichever member sorted first.
    const inbound = new Map<string, number>();
    for (const member of component) {
      for (const target of member.related_rule_ids ?? []) {
        inbound.set(target, (inbound.get(target) ?? 0) + 1);
      }
    }
    const anchor = component.reduce((best, r) =>
      (inbound.get(r.rule_id) ?? 0) > (inbound.get(best.rule_id) ?? 0) ? r : best
    );
    const sorted = [...component].sort((a, b) => a.title.localeCompare(b.title));
    const group: RuleVariationGroup = { key: anchor.title, kind: "group", members: sorted };
    for (const member of component) result.set(member.rule_id, group);
  }

  return result;
}

/**
 * Per-rule convenience wrapper around `buildVariationClusters` for call
 * sites (the inspector) that only ever look at one rule at a time. Prefer
 * `buildVariationClusters` directly (memoized once) when you need the
 * cluster for many/all rules, e.g. the list's left-side banding — calling
 * this in a loop would repeat the full O(n) clustering pass per rule.
 */
export function findRuleVariations(rule: CanonicalRule, allRules: CanonicalRule[]): RuleVariationGroup | null {
  return buildVariationClusters(allRules).get(rule.rule_id) ?? null;
}

/** Stable identity string for a cluster, unique across both `kind`s even in
 * the vanishingly unlikely case a curated `group_label` and a heuristic
 * fact name happen to be the same literal text. Used for adjacency
 * comparisons and color assignment — never shown to the user. */
export function clusterIdentity(cluster: Pick<RuleVariationGroup, "kind" | "key">): string {
  return `${cluster.kind}:${cluster.key}`;
}

/** Human-readable name for a family, phrased differently per `kind`: a
 * curated `group_label` is already a real name and stands on its own, while
 * a heuristic cluster has to explain *why* its members are related. Single
 * source of truth so group headers, family chips, and row tooltips never
 * describe the same family two different ways. */
export function clusterLabel(cluster: Pick<RuleVariationGroup, "kind" | "key">): string {
  return cluster.kind === "group" ? cluster.key : `Varies by ${humanizeIdentifier(cluster.key)}`;
}

/** Small, curated palette for cluster accents — deliberately excludes
 * green/red/gold hues, which are already reserved for effect (ALLOW/DENY)
 * and ambiguity semantics elsewhere in the row, so a cluster color is never
 * mistaken for a status signal. */
const CLUSTER_PALETTE = [
  "#2563eb", // blue
  "#0d9488", // teal
  "#4f46e5", // indigo
  "#c026d3", // fuchsia
  "#0891b2", // cyan
  "#92400e", // brown
  "#475569", // slate
  "#be185d", // deep pink
];

/** Deterministic (non-cryptographic) string hash — same cluster identity
 * always maps to the same palette color, independent of render order. */
function hashString(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) {
    h = (h << 5) - h + s.charCodeAt(i);
    h |= 0;
  }
  return Math.abs(h);
}

/** Deterministic accent color for a cluster, keyed by its full identity
 * (kind + key) so "group" and "condition" clusters never collide. */
export function clusterColor(cluster: Pick<RuleVariationGroup, "kind" | "key">): string {
  return CLUSTER_PALETTE[hashString(clusterIdentity(cluster)) % CLUSTER_PALETTE.length];
}

/** `#rrggbb` → `rgba(r, g, b, alpha)`, for translucent tints (e.g. a hover
 * highlight) derived from a cluster's solid accent color without depending
 * on CSS `color-mix()` browser support. */
export function hexToRgba(hex: string, alpha: number): string {
  const m = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
  if (!m) return hex;
  const [r, g, b] = [m[1], m[2], m[3]].map((h) => parseInt(h, 16));
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}
