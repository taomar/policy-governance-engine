/**
 * STALENESS HAS TWO AXES, AND A READER IS OWED THE ONE THAT IS ACTUALLY BEHIND.
 *
 * An index can be behind on its **version** — built for a published version
 * that is no longer active — or on its **projection profile**: built for the
 * right version, but under a superseded rendering contract, so a question
 * rendered under the current one is not comparable with the text it would be
 * scored against. Both are repaired by the same rebuild, and that is exactly
 * why they get conflated.
 *
 * They must not be. A panel that says "the recorded index is for v3 while the
 * active version is v3" reads as a contradiction and sends an operator looking
 * for a version problem that is not there; one that says nothing at all leaves
 * them with a rebuild button and no reason to press it. So the axis is derived
 * from what the record can prove, and where it can prove nothing the copy says
 * the version matches and the contract is what is behind — without inventing a
 * profile name it was not given.
 *
 * The rebuild's own result is read the same way. A manifest that never reached
 * `ready` means the build did not finish, and a project in that state is
 * refused by retrieval rather than answered from part of a corpus — so it is
 * reported on the build that produced it, not discovered later as a case that
 * will not run.
 */
import { describe, expect, it } from "vitest";
import type { PolicyIndexBuildResult, PolicyIndexState } from "./api";
import { describePolicyIndexState, policyIndexStaleAxis, rebuildResultMessage } from "./policyIndexHealth";

const EXPECTED_PROFILE = "policy-english-projection-v1";

function indexState(overrides: Partial<PolicyIndexState> = {}): PolicyIndexState {
  return {
    policy_set_key: "a-set",
    index_name: "policy-cases-a-set",
    last_attempt: "built",
    freshness: "stale",
    active_version_number: 3,
    indexed_version_number: 3,
    attempted_version_number: 3,
    document_count: 12,
    built_at: "2026-08-01T00:00:00Z",
    attempted_at: "2026-08-01T00:00:00Z",
    error: null,
    source: "recorded_build_state",
    live_probe: false,
    ...overrides,
  };
}

function buildResult(overrides: Partial<PolicyIndexBuildResult> = {}): PolicyIndexBuildResult {
  return {
    state: "built",
    policy_set_key: "a-set",
    index_name: "policy-cases-a-set",
    version_number: 3,
    document_count: 12,
    indexed_at: "2026-08-30T00:00:00Z",
    error: null,
    ...overrides,
  };
}

describe("which axis a stale index is behind on", () => {
  it("names the projection axis when the version matches and the profile does not", () => {
    const state = indexState({
      projection_profile: "policy-english-projection-v0",
      expected_projection_profile: EXPECTED_PROFILE,
    });
    expect(policyIndexStaleAxis(state)).toBe("projection");
  });

  it("names the version axis when the version is behind and the profile is current", () => {
    const state = indexState({
      indexed_version_number: 2,
      projection_profile: EXPECTED_PROFILE,
      expected_projection_profile: EXPECTED_PROFILE,
    });
    expect(policyIndexStaleAxis(state)).toBe("version");
  });

  it("names both when both are behind", () => {
    const state = indexState({
      indexed_version_number: 2,
      projection_profile: "policy-english-projection-v0",
      expected_projection_profile: EXPECTED_PROFILE,
    });
    expect(policyIndexStaleAxis(state)).toBe("both");
  });

  it("compares a profile only when both sides are named", () => {
    // One name and a blank is not a mismatch; it is a record that cannot say.
    expect(policyIndexStaleAxis(indexState({ expected_projection_profile: EXPECTED_PROFILE }))).toBe("undetermined");
    expect(policyIndexStaleAxis(indexState({ projection_profile: EXPECTED_PROFILE }))).toBe("undetermined");
  });

  it("reads a never-indexed project as behind on its version, not on a contract it never had", () => {
    expect(
      policyIndexStaleAxis(indexState({ last_attempt: "never_attempted", indexed_version_number: null })),
    ).toBe("version");
  });

  it("says nothing about an index that is not stale", () => {
    expect(policyIndexStaleAxis(indexState({ freshness: "current" }))).toBeNull();
    expect(policyIndexStaleAxis(indexState({ freshness: "nothing_to_index" }))).toBeNull();
  });
});

describe("what a reader is told about a stale index", () => {
  it("does not report a version problem when the version is the thing that matches", () => {
    const copy = describePolicyIndexState(
      indexState({
        projection_profile: "policy-english-projection-v0",
        expected_projection_profile: EXPECTED_PROFILE,
      }),
    );

    expect(copy.title).toContain("superseded rendering contract");
    expect(copy.statusLabel).toBe("Stale projection");
    expect(copy.detail).toContain("matches the active published version v3");
    expect(copy.detail).toContain("policy-english-projection-v0");
    expect(copy.detail).toContain(EXPECTED_PROFILE);
    // The contradiction this avoids: "the recorded index is for v3 while the
    // active published version is v3".
    expect(copy.detail).not.toMatch(/recorded index is for v3/);
  });

  it("still leads with the version when that is what is behind, and adds the contract", () => {
    const copy = describePolicyIndexState(
      indexState({
        indexed_version_number: 2,
        projection_profile: "policy-english-projection-v0",
        expected_projection_profile: EXPECTED_PROFILE,
      }),
    );

    expect(copy.title).toContain("stale");
    expect(copy.statusLabel).toBe("Stale version and projection");
    expect(copy.detail).toContain("the recorded index is for v2");
    expect(copy.detail).toContain("rendering contract");
  });

  it("says which axis it can prove when the record cannot name a profile", () => {
    // Freshness came back stale, the versions match, and there is no profile to
    // compare. The honest reading is that the contract is what is behind — and
    // the copy says so without inventing a profile name.
    const copy = describePolicyIndexState(indexState());
    expect(copy.detail).toContain("the rendering contract the index was built under rather than the version");
    expect(copy.detail).not.toMatch(/undefined|null/);
  });

  it("leaves a current index and a never-built one exactly as they read before", () => {
    const current = describePolicyIndexState(indexState({ freshness: "current", indexed_version_number: 3 }));
    expect(current.statusLabel).toBe("Current");
    const never = describePolicyIndexState(
      indexState({ last_attempt: "never_attempted", indexed_version_number: null }),
    );
    expect(never.statusLabel).toBe("Never built");
  });
});

describe("what a rebuild reports about itself", () => {
  it("says how the documents split, under which contract, and that the manifest is ready", () => {
    const copy = rebuildResultMessage(
      buildResult({
        document_count: 12,
        policy_document_count: 4,
        rule_document_count: 8,
        projection_profile: EXPECTED_PROFILE,
        manifest_state: "ready",
      }),
    );

    expect(copy.type).toBe("success");
    expect(copy.message).toBe("Policy index rebuilt");
    expect(copy.description).toContain("4 policy documents and 8 rule documents");
    expect(copy.description).toContain(EXPECTED_PROFILE);
    expect(copy.description).toContain("every expected document was acknowledged");
  });

  it("reports a manifest that never reached ready as a build that did not finish", () => {
    // The alternative is a green "rebuilt" beside a project that will refuse
    // every case it is asked, for a reason nothing on screen mentioned.
    const copy = rebuildResultMessage(
      buildResult({ projection_profile: null, manifest_state: "incomplete", policy_document_count: 2, rule_document_count: 0 }),
    );

    expect(copy.type).toBe("info");
    expect(copy.message).toBe("Policy index rebuild did not finish");
    expect(copy.description).toContain("manifest is incomplete");
    expect(copy.description).toContain("refuse rather than answer from part of the corpus");
    expect(copy.description).toContain("Run the rebuild again");
  });

  it("reads a server that reports none of it exactly as it did before", () => {
    const copy = rebuildResultMessage(buildResult());
    expect(copy.type).toBe("success");
    expect(copy.message).toBe("Policy index rebuilt");
    expect(copy.description).toContain("Indexed 12 policy documents for v3");
    expect(copy.description).not.toMatch(/manifest|rendering contract|undefined/);
  });

  it("still reports a skipped and a failed rebuild as themselves", () => {
    expect(rebuildResultMessage(buildResult({ state: "skipped", error: null })).type).toBe("info");
    expect(rebuildResultMessage(buildResult({ state: "failed", error: "boom" })).description).toContain("boom");
  });
});
