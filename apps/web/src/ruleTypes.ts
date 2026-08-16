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

/**
 * Labels that cannot be produced by title-casing the value.
 *
 * `human_judgment_requirement` is a rule TYPE: the clause hands the decision to
 * a person's discretion. Title-cased, the value read back as a third name for
 * the AI Ready ROUTE -- and a reader meeting it beside a route chip has no way
 * to tell the two axes apart. The value is the API contract and does not move;
 * the words a reader sees do, so that a rule type never again reads as a route.
 */
const LABEL_OVERRIDES: Record<string, string> = {
  human_judgment_requirement: "Discretionary Judgment",
};

/** Turns a snake_case rule_type into a human-readable label, e.g. "approval_requirement" -> "Approval Requirement". */
export function ruleTypeLabel(ruleType: string): string {
  if (!ruleType) return "Uncategorized";
  const override = LABEL_OVERRIDES[ruleType];
  if (override) return override;
  return ruleType
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}
