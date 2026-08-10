import type { CanonicalRule } from "./api";

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
