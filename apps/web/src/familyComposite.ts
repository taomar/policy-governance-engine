import type { CanonicalRule, ConditionNode } from "./api";
import { isEmptyCondition } from "./ruleDisplay";

/**
 * The single policy a family of rules collectively states.
 *
 * A severity/SLA matrix arrives as eight rules because eight table rows were
 * formulated separately, but the document states one policy with eight
 * variants. Presenting only the rows makes a reviewer reconstruct that in
 * their head, and nothing on screen says the rows are exhaustive of it.
 *
 * Everything here is derived by *agreement* across members — a part is shared
 * only when every member states it identically. Nothing is summarised,
 * paraphrased or inferred: if the members disagree, the field is empty and the
 * variation is reported instead. That keeps the header a fact about the rules
 * rather than a description of them.
 */
export interface FamilyComposite {
  /** Stated identically by every member, so it describes the family. */
  subject: string;
  predicate: string;
  /** The axis members differ on, in member order. Empty when they agree. */
  variants: string[];
  memberCount: number;
  /** Members that carry no executable condition. */
  needsMappingCount: number;
  /** Distinct review statuses present, so a split family is visible. */
  statuses: string[];
}

function canonicalOf(rule: CanonicalRule) {
  return rule.formulation?.canonical?.rule ?? null;
}

/** The value every member agrees on, or "" when they differ. */
function agreed(values: string[]): string {
  const present = values.map((v) => (v ?? "").trim()).filter(Boolean);
  if (present.length === 0 || present.length !== values.length) return "";
  return present.every((v) => v === present[0]) ? present[0] : "";
}

/** How a single case says when it applies. */
export type EffectiveWhen =
  | { kind: "executable"; node: ConditionNode }
  | { kind: "stated"; lines: string[] }
  | { kind: "none" };

/** One case of an effective policy — a single member rule, in its role. */
export interface EffectiveCase {
  ruleId: string;
  /** What distinguishes this case from its siblings. */
  label: string;
  when: EffectiveWhen;
  /** The action the source requires, in its own words. */
  then: string;
  effectType: string;
  executable: boolean;
  reviewStatus: string;
  /** Clause ids backing this case, for tracing it to the document. */
  clauseIds: string[];
}

/**
 * A family of rules presented as the one policy they collectively state.
 *
 * Strictly a view. Nothing here is persisted, evaluated, or treated as a rule:
 * the platform still decides on the individual members, and this exists so a
 * reviewer can see what those members add up to before deciding them. Every
 * field is either copied from a member or established by agreement across all
 * of them — there is no summarisation step, because a summary of a policy is a
 * new claim about the policy.
 */
export interface EffectivePolicy {
  subject: string;
  predicate: string;
  cases: EffectiveCase[];
  /**
   * Conditions the projection recorded identically on every member.
   *
   * When the source is a table, the agent often projects the whole condition
   * column onto each row, so all members carry all conditions. Shown once at
   * policy level rather than repeated on every case, because repeating them
   * reads as "each case requires all of these" — the opposite of a table.
   *
   * Deliberately not paired with cases by position. The i-th condition does
   * look like the i-th case, but that alignment is an artefact of emission
   * order, and binding a case to a condition on that basis would state a
   * mapping the source never gave.
   */
  sharedConditions: string[];
  /** Case labels stated more than once — a real contradiction to surface. */
  duplicateLabels: string[];
  documentVersionIds: string[];
  executableCount: number;
  reviewStatuses: string[];
}

/** The stated-but-unbound condition phrases a rule's projection recorded. */
function statedConditions(rule: CanonicalRule): string[] {
  const lines: string[] = [];
  for (const decision of rule.formulation?.dmn_decisions ?? []) {
    const projection = decision.semantic_projection;
    if (!projection) continue;
    for (const condition of projection.conditions ?? []) {
      if (condition && !lines.includes(condition)) lines.push(condition);
    }
    const source = projection.condition_source;
    if (source && !lines.includes(source)) lines.push(source);
  }
  return lines;
}

function whenOf(rule: CanonicalRule): EffectiveWhen {
  if (!isEmptyCondition(rule.condition)) {
    return { kind: "executable", node: rule.condition };
  }
  const lines = statedConditions(rule);
  return lines.length > 0 ? { kind: "stated", lines } : { kind: "none" };
}

export function effectivePolicy(members: CanonicalRule[]): EffectivePolicy {
  const composite = familyComposite(members);
  const canonicals = members.map(canonicalOf);

  // Conditions every member carries identically describe the family, not any
  // one case — see `sharedConditions`. Hoisted so they are stated once.
  const perMember = members.map((rule) => statedConditions(rule));
  const firstKey = JSON.stringify(perMember[0] ?? []);
  const allIdentical =
    members.length > 1 &&
    (perMember[0]?.length ?? 0) > 0 &&
    perMember.every((lines) => JSON.stringify(lines) === firstKey);
  const sharedConditions = allIdentical ? perMember[0] : [];

  // The object is usually what varies across a family (the severity band, the
  // SLA value), but not always — and when it does not, labelling by it makes
  // two genuinely different rules look like one.
  //
  // The housing allowance is the case that proved it: three rules, one per
  // staff category, at two limits. Two of them carry the identical object
  // "Fifteen thousand (15,000) SAR", so both rendered with the same label and
  // a reviewer saw what looked like a duplicated row. What distinguishes them
  // is the condition — "for administrative, technical and service staff"
  // versus "for full time lecturers, instructors…" — which the label ignored.
  const rawLabels = members.map((rule, index) => {
    const canonical = canonicals[index];
    return (canonical?.object ?? "").trim() || rule.title;
  });
  const labelCounts = rawLabels.reduce<Record<string, number>>((acc, label) => {
    acc[label] = (acc[label] ?? 0) + 1;
    return acc;
  }, {});

  const cases: EffectiveCase[] = members.map((rule, index) => {
    const canonical = canonicals[index];
    const base = rawLabels[index];
    // Disambiguate only where it is needed. Appending the condition to every
    // case would bury the varying value under repeated qualifying text.
    const qualifier = (canonical?.condition ?? "").trim();
    const label = labelCounts[base] > 1 && qualifier ? `${base} — ${qualifier}` : base;
    return {
      ruleId: rule.rule_id,
      label,
      when: allIdentical ? { kind: "none" } : whenOf(rule),
      then: rule.effect?.action ?? "",
      effectType: rule.effect?.type ?? "",
      executable: rule.machine_executable,
      reviewStatus: rule.review_status,
      clauseIds: Array.from(
        new Set((rule.evidence ?? []).map((e) => e.clause_id).filter((id): id is string => Boolean(id)))
      ),
    };
  });

  const seen = new Set<string>();
  const duplicateLabels: string[] = [];
  for (const item of cases) {
    if (seen.has(item.label) && !duplicateLabels.includes(item.label)) {
      duplicateLabels.push(item.label);
    }
    seen.add(item.label);
  }

  return {
    subject: composite.subject,
    predicate: composite.predicate,
    cases,
    sharedConditions,
    duplicateLabels,
    documentVersionIds: Array.from(
      new Set(members.flatMap((m) => (m.evidence ?? []).map((e) => e.document_version_id)))
    ),
    executableCount: members.filter((m) => m.machine_executable).length,
    reviewStatuses: composite.statuses,
  };
}

export function familyComposite(
  members: CanonicalRule[],
  reviewStatusOf?: (rule: CanonicalRule) => string
): FamilyComposite {
  const canonicals = members.map(canonicalOf);
  const subject = agreed(canonicals.map((c) => c?.subject ?? ""));
  const predicate = agreed(canonicals.map((c) => c?.predicate ?? ""));

  // The varying part. Reported only when it genuinely varies — a list of eight
  // identical strings would suggest a distinction the document never drew.
  const objects = canonicals.map((c) => (c?.object ?? "").trim());
  const distinct = Array.from(new Set(objects.filter(Boolean)));
  const variants = distinct.length > 1 ? objects.filter(Boolean) : [];

  const statuses = Array.from(
    new Set(
      members
        .map((m) => (reviewStatusOf ? reviewStatusOf(m) : m.review_status))
        .filter(Boolean)
    )
  );

  return {
    subject,
    predicate,
    variants,
    memberCount: members.length,
    needsMappingCount: members.filter((m) => !m.machine_executable).length,
    statuses,
  };
}
