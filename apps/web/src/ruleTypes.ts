/**
 * Canonical `rule_type` taxonomy, shared by the Review Queue's draft form and the
 * Policies tab's categorized browsing view. Order here defines display order when
 * grouping rules by type — kept as a single source of truth so both stay in sync.
 */
export const RULE_TYPES = [
  "eligibility",
  "permission",
  "prohibition",
  "obligation",
  "approval_requirement",
  "evidence_requirement",
  "threshold",
  "deadline",
  "calculation",
  "routing",
  "notification",
  "escalation",
  "exception",
  "definition",
  "scope",
  "delegation_of_authority",
  "retention",
  "access_restriction",
  "human_judgment_requirement",
];

/** Turns a snake_case rule_type into a human-readable label, e.g. "approval_requirement" -> "Approval Requirement". */
export function ruleTypeLabel(ruleType: string): string {
  if (!ruleType) return "Uncategorized";
  return ruleType
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}
