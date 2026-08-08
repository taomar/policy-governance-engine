// Shared business-domain category vocabulary. Kept as suggestions, not a hard
// enum: the AutoComplete/Select inputs that use this list also accept a
// free-typed value so a project or rule is never blocked from an accurate
// label the list doesn't happen to include yet.
export const POLICY_CATEGORIES = [
  "HR",
  "Finance",
  "IT",
  "Legal",
  "Compliance",
  "Security",
  "Procurement",
  "Operations",
];

export const POLICY_CATEGORY_COLORS: Record<string, string> = {
  HR: "magenta",
  Finance: "gold",
  IT: "blue",
  Legal: "purple",
  Compliance: "volcano",
  Security: "red",
  Procurement: "cyan",
  Operations: "green",
};

export function colorForCategory(category: string): string {
  return POLICY_CATEGORY_COLORS[category] ?? "default";
}
