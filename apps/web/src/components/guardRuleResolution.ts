import type { ApprovedPolicyVersion, CanonicalRule } from "../api";

/**
 * What the guard register knows about the rule a guard protects.
 *
 * A guard resolves its rule against the published version its last run
 * evaluated. A guard kept from the case dialog and not yet run has no such
 * version, and the register used to read that absence as "loading" forever — a
 * permanent spinner that a reader cannot tell apart from a failure. These are
 * the distinct, nameable states the register must say instead (constraint 5):
 *
 *  - `resolved`  the rule is in hand and named;
 *  - `loading`   its version's rules are still arriving;
 *  - `missing`   the version's rules are loaded and this rule is not among them,
 *                because a guard can outlive the version it cites;
 *  - `failed`    the version's rules could not be loaded;
 *  - `subset`    the guard names no single rule (it guards a policy subset).
 */
export type GuardRuleResolution =
  | { kind: "subset" }
  | { kind: "resolved"; rule: CanonicalRule; versionNumber: number | null }
  | { kind: "loading" }
  | { kind: "missing"; ruleId: string; versionNumber: number | null }
  | { kind: "failed"; ruleId: string };

export function resolveGuardRule(params: {
  expectedRuleId: string | null | undefined;
  /** The version the guard's latest run evaluated, if it has ever run. */
  runVersionId: string | null | undefined;
  /** The active published version, where a never-run guard's rule still lives. */
  activeVersionId: string | null | undefined;
  rulesByVersionId: Record<string, CanonicalRule[]>;
  versions: ApprovedPolicyVersion[];
  loading: boolean;
  errored: boolean;
}): GuardRuleResolution {
  const ruleId = params.expectedRuleId ?? null;
  if (!ruleId) return { kind: "subset" };

  // Resolve against the run's version when there is one; otherwise the active
  // published version. The original defect was resolving ONLY against the run,
  // so a guard that had never run resolved against nothing.
  const resolveVersionId = params.runVersionId ?? params.activeVersionId ?? null;
  const versionNumber =
    params.versions.find((version) => version.id === resolveVersionId)?.version_number ?? null;

  if (!resolveVersionId) {
    return params.loading || !params.errored ? { kind: "loading" } : { kind: "failed", ruleId };
  }

  // A completed fetch — success OR a stored empty list — puts a key in the map.
  // Its absence means the rules are not in hand yet, which is either still
  // arriving or a failed load. A fetch in flight reads as loading even if an
  // earlier load errored.
  const fetched = Object.prototype.hasOwnProperty.call(params.rulesByVersionId, resolveVersionId);
  if (!fetched) {
    if (params.loading) return { kind: "loading" };
    return params.errored ? { kind: "failed", ruleId } : { kind: "loading" };
  }

  const rule = params.rulesByVersionId[resolveVersionId].find((entry) => entry.rule_id === ruleId);
  if (rule) return { kind: "resolved", rule, versionNumber };
  return { kind: "missing", ruleId, versionNumber };
}

/** The headline a guard row shows for its rule — one line per distinct state. */
export function guardRuleHeadline(view: GuardRuleResolution): string {
  switch (view.kind) {
    case "resolved":
      return view.rule.title;
    case "loading":
      return "Resolving rule…";
    case "missing":
      return "This rule is not in this version";
    case "failed":
      return "Rule could not be loaded";
    case "subset":
      return "Policy subset";
  }
}

/**
 * The sub-line beneath the headline. The run version is shown in its own column,
 * so it is deliberately NOT repeated here — the two version cells on one row were
 * two different unknowns saying the same missing thing.
 */
export function guardRuleDetail(view: GuardRuleResolution, decisionText: string | null): string {
  switch (view.kind) {
    case "resolved":
      return decisionText ?? view.rule.rule_id;
    case "loading":
      return "Resolving from the published version…";
    case "missing":
      return view.versionNumber != null ? `${view.ruleId} · not in v${view.versionNumber}` : view.ruleId;
    case "failed":
      return view.ruleId;
    case "subset":
      return "Multiple policies";
  }
}
