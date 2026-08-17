/**
 * The guard-row rule resolver: five distinct, nameable states (constraint 5).
 *
 * The defect this guards against: a guard resolved its rule ONLY against the
 * version its last run evaluated, so a guard that had never run resolved
 * against nothing and its row read "loading" forever. A never-run guard must
 * resolve against the active published version instead — where its rule still
 * lives — and name it. Absent, loading, missing and failed are four different
 * answers and are not collapsed into one spinner.
 *
 * Nothing here names a real policy.
 */
import { describe, expect, it } from "vitest";
import type { ApprovedPolicyVersion, CanonicalRule } from "../api";
import { resolveGuardRule, guardRuleHeadline, guardRuleDetail } from "./guardRuleResolution";

function version(id: string, n: number): ApprovedPolicyVersion {
  return { id, version_number: n } as unknown as ApprovedPolicyVersion;
}

function rule(id: string, title: string): CanonicalRule {
  return { rule_id: id, title } as unknown as CanonicalRule;
}

const versions = [version("v-active", 3), version("v-old", 1)];

describe("resolveGuardRule", () => {
  it("names no single rule as a policy subset when the guard has no expected rule", () => {
    const view = resolveGuardRule({
      expectedRuleId: null,
      runVersionId: null,
      activeVersionId: "v-active",
      rulesByVersionId: { "v-active": [] },
      versions,
      loading: false,
      errored: false,
    });
    expect(view.kind).toBe("subset");
    expect(guardRuleHeadline(view)).toMatch(/subset/i);
  });

  it("resolves a NEVER-RUN guard against the active version — the defect, fixed", () => {
    const view = resolveGuardRule({
      expectedRuleId: "cap",
      runVersionId: null, // never run
      activeVersionId: "v-active",
      rulesByVersionId: { "v-active": [rule("cap", "Capped at 24 hours")] },
      versions,
      loading: false,
      errored: false,
    });
    expect(view.kind).toBe("resolved");
    if (view.kind === "resolved") {
      expect(view.rule.title).toBe("Capped at 24 hours");
      expect(view.versionNumber).toBe(3);
    }
    expect(guardRuleHeadline(view)).toBe("Capped at 24 hours");
  });

  it("resolves a run guard against the version its run evaluated, not the active one", () => {
    const view = resolveGuardRule({
      expectedRuleId: "cap",
      runVersionId: "v-old",
      activeVersionId: "v-active",
      rulesByVersionId: {
        "v-active": [rule("cap", "Active wording")],
        "v-old": [rule("cap", "Wording as run")],
      },
      versions,
      loading: false,
      errored: false,
    });
    expect(view.kind).toBe("resolved");
    if (view.kind === "resolved") {
      expect(view.rule.title).toBe("Wording as run");
      expect(view.versionNumber).toBe(1);
    }
  });

  it("says a rule is MISSING when its version's rules are loaded and it is not among them", () => {
    const view = resolveGuardRule({
      expectedRuleId: "retired",
      runVersionId: null,
      activeVersionId: "v-active",
      rulesByVersionId: { "v-active": [rule("something-else", "Other")] },
      versions,
      loading: false,
      errored: false,
    });
    expect(view.kind).toBe("missing");
    expect(guardRuleHeadline(view)).toMatch(/not in this version/i);
    expect(guardRuleDetail(view, null)).toMatch(/not in v3/i);
  });

  it("is LOADING when the version's rules are not in hand yet and a fetch is in flight", () => {
    const view = resolveGuardRule({
      expectedRuleId: "cap",
      runVersionId: null,
      activeVersionId: "v-active",
      rulesByVersionId: {}, // not fetched yet
      versions,
      loading: true,
      errored: false,
    });
    expect(view.kind).toBe("loading");
    expect(guardRuleHeadline(view)).toMatch(/resolving/i);
  });

  it("prefers loading over a STALE error while a retry is in flight", () => {
    const view = resolveGuardRule({
      expectedRuleId: "cap",
      runVersionId: null,
      activeVersionId: "v-active",
      rulesByVersionId: {},
      versions,
      loading: true,
      errored: true, // an earlier load errored; a retry is running now
    });
    expect(view.kind).toBe("loading");
  });

  it("is FAILED when the rules are not in hand, nothing is loading, and a load errored", () => {
    const view = resolveGuardRule({
      expectedRuleId: "cap",
      runVersionId: null,
      activeVersionId: "v-active",
      rulesByVersionId: {},
      versions,
      loading: false,
      errored: true,
    });
    expect(view.kind).toBe("failed");
    expect(guardRuleHeadline(view)).toMatch(/could not be loaded/i);
  });

  it("treats a stored EMPTY list as fetched — an empty version yields missing, not loading", () => {
    const view = resolveGuardRule({
      expectedRuleId: "cap",
      runVersionId: null,
      activeVersionId: "v-active",
      rulesByVersionId: { "v-active": [] }, // fetched, genuinely empty
      versions,
      loading: false,
      errored: false,
    });
    expect(view.kind).toBe("missing");
  });
});
