/**
 * What a project's policy index state means, and when a rebuild is the fix.
 *
 * Two surfaces ask about the same index from different directions. The project
 * Overview reads the *recorded* build state and says whether it still represents
 * the active published version. The case runner reports what live retrieval
 * *found* when a question was actually asked. Those are deliberately separate
 * mechanisms (see `policy_index.py`), and they are kept separate here.
 *
 * What they must agree on is narrower and is stated once, below: which
 * situations a rebuild repairs. Getting that wrong is not cosmetic — the
 * backend already tells the reader to "republish or rebuild the policy index",
 * so a surface that withholds the control in a state the backend names is a
 * dead-end instruction, which is the defect this module exists to prevent.
 *
 * The logic lives in its own module rather than inside a tab component because
 * it is pure, it is shared by two components, and a decision about what a user
 * is told should be testable without rendering anything.
 */

import type { PolicyIndexState, PolicyIndexBuildResult, PolicyIndexValidationResult } from "./api";

/**
 * Retrieval statuses a rebuild repairs.
 *
 * These are exactly the statuses whose reason tells the reader to republish or
 * rebuild, in `ai_case_project.py`. `index_empty` belongs here for the same
 * reason as the other two: the index exists but holds nothing for this project,
 * which a rebuild fixes. It was missed once, and the Python guard
 * `test_the_index_repair_offer_matches_the_backend` now fails if this set and
 * that instruction ever drift apart again.
 *
 * Statuses NOT here are deliberate. `unavailable` means Search is not
 * configured, which no rebuild fixes; `no_published_version` means there is
 * nothing to index; `no_match` means retrieval worked and nothing bore on the
 * question.
 */
export const INDEX_REPAIRABLE_RETRIEVAL_STATUSES = [
  "index_not_built",
  "index_stale",
  "index_empty",
] as const;

export function retrievalStatusIsIndexRepairable(status: string): boolean {
  return (INDEX_REPAIRABLE_RETRIEVAL_STATUSES as readonly string[]).includes(status);
}

/**
 * Whether the recorded state is one a rebuild would improve.
 *
 * `skipped` is excluded because Search is not configured, so rebuilding would
 * skip again. `nothing_to_index` is excluded because the project has published
 * nothing — there is no work for a rebuild to do, and offering one would imply
 * a fault.
 */
export function policyIndexRepairable(state: PolicyIndexState): boolean {
  return state.freshness === "stale" && state.last_attempt !== "skipped";
}

/**
 * Which axis a stale index is behind on.
 *
 * Staleness has two, and they are repaired by the same rebuild but describe
 * different faults. The **version** axis is the familiar one: the index was
 * built for a published version that is no longer active. The **projection**
 * axis is the second: the index was built for the right version but under a
 * superseded rendering contract, so a question rendered under the current one
 * is not comparable with the text it would be scored against.
 *
 * The server derives freshness across both, and its state response does not
 * have to say which. So this reads what it can prove and never guesses: when
 * the record names its profile and the profile differs, that is the projection
 * axis; when the versions differ, that is the version axis; when a state is
 * stale with versions that match and no profile to compare, the axis is
 * `undetermined` and the interface says the rebuild is the repair without
 * inventing a reason for it.
 */
export type PolicyIndexStaleAxis = "version" | "projection" | "both" | "undetermined";

export function policyIndexStaleAxis(state: PolicyIndexState): PolicyIndexStaleAxis | null {
  if (state.freshness !== "stale") return null;
  const versionsKnown =
    typeof state.active_version_number === "number" && typeof state.indexed_version_number === "number";
  const versionBehind = versionsKnown && state.indexed_version_number !== state.active_version_number;
  const expected = state.expected_projection_profile ?? null;
  const built = state.projection_profile ?? null;
  // A profile is only compared when both sides are named. One name and a blank
  // is not a mismatch, it is a record that cannot say.
  const projectionBehind = Boolean(expected && built && expected !== built);
  if (versionBehind && projectionBehind) return "both";
  if (projectionBehind) return "projection";
  if (versionBehind) return "version";
  // Nothing was never indexed at all, so there is no profile to be behind on:
  // the version is what is missing, and saying so is not a guess.
  if (state.last_attempt === "never_attempted" || state.indexed_version_number === null) return "version";
  return "undetermined";
}

/** The projection axis, in a sentence, when there is something to say. */
function projectionSentence(state: PolicyIndexState, axis: PolicyIndexStaleAxis | null): string {
  if (axis === "projection" || axis === "both") {
    return ` The index was also built under the ${state.projection_profile} rendering contract while this server expects ${state.expected_projection_profile}; a question rendered under one contract is not comparable with text rendered under another, so the same rebuild is the repair.`;
  }
  if (axis === "undetermined") {
    return " The recorded version matches the active one, so what is behind is the rendering contract the index was built under rather than the version — the same rebuild repairs it.";
  }
  return "";
}

/**
 * The recorded state as one sentence a reviewer can act on.
 *
 * `last_attempt` and `freshness` are independent facts and are composed here
 * rather than shown as two raw enums for the reader to reconcile. The order of
 * the branches matters: "nothing to index" and "not configured" are answered
 * before freshness, because neither is a fault and describing either as stale
 * would invent one.
 */
export function describePolicyIndexState(state: PolicyIndexState): {
  title: string;
  detail: string;
  tone: "success" | "warning" | "error" | "info";
  statusLabel: string;
} {
  if (state.freshness === "nothing_to_index") {
    return {
      title: "There is nothing to index yet",
      detail:
        "This project has no active published policy package, so project-wide case search has no published policies to index.",
      tone: "info",
      statusLabel: "Nothing to index",
    };
  }
  if (state.last_attempt === "skipped") {
    // A skipped attempt with a known indexed version is still comparable, so
    // say which it was rather than implying nothing is behind.
    const behind = state.freshness === "stale";
    return {
      title: behind
        ? "Policy search is not configured here, and the recorded index is behind"
        : "Policy search is not configured here",
      detail: behind
        ? `The last build was skipped because Search is not available on this server, and the recorded index is for v${state.indexed_version_number ?? "—"} while the active published version is v${state.active_version_number ?? "—"}.`
        : "The last build was skipped because Search is not available on this server. This is a configuration state, not a broken project index.",
      tone: "info",
      statusLabel: behind ? "Search not configured · behind" : "Search not configured",
    };
  }
  if (state.freshness === "current") {
    // A failed attempt that left the index matching the active version changed
    // nothing. Reporting it as a fault would train the reader to ignore this
    // panel, so it is stated plainly and in success tone.
    if (state.last_attempt === "failed") {
      return {
        title: "The last rebuild failed, and the recorded index still matches",
        detail: `The last rebuild attempt failed, but the recorded index is for the active published version and holds ${state.document_count} policy document${state.document_count === 1 ? "" : "s"}. Whether retrieval finds them is checked when a case is actually run.`,
        tone: "success",
        statusLabel: "Current despite failed attempt",
      };
    }
    return {
      title: "The project-wide case index is up to date",
      detail: `Published v${state.indexed_version_number ?? state.active_version_number ?? "—"} is indexed with ${state.document_count} policy document${state.document_count === 1 ? "" : "s"}.`,
      tone: "success",
      statusLabel: "Current",
    };
  }
  if (state.freshness === "stale") {
    const axis = policyIndexStaleAxis(state);
    if (state.last_attempt === "never_attempted") {
      return {
        title: "No index build has been recorded for this project",
        detail:
          "Nothing has recorded an index build for the active published version. Project-wide case testing needs one, and reports what it finds when a case is run.",
        tone: "warning",
        statusLabel: "Never built",
      };
    }
    if (state.last_attempt === "failed") {
      return {
        title: "The last index rebuild failed and the index is stale",
        detail: `Project-wide case testing will not use this index until a rebuild succeeds.${projectionSentence(state, axis)}`,
        tone: "error",
        statusLabel: "Failed and stale",
      };
    }
    if (axis === "projection") {
      // The version matches, so saying "the recorded index is for v3 while the
      // active version is v3" would read as a contradiction and send a reader
      // looking for a version problem that is not there.
      return {
        title: "The project-wide case index was built under a superseded rendering contract",
        detail: `The index matches the active published version v${state.active_version_number ?? "—"}, but it was built under ${state.projection_profile} while this server expects ${state.expected_projection_profile}. A question rendered under one contract is not comparable with text rendered under another, so a rebuild is needed even though the version is current.`,
        tone: "warning",
        statusLabel: "Stale projection",
      };
    }
    return {
      title: "The project-wide case index is stale",
      detail: `The active published version is v${state.active_version_number ?? "—"}, but the recorded index is for v${state.indexed_version_number ?? "—"}.${projectionSentence(state, axis)}`,
      tone: "warning",
      statusLabel: axis === "both" ? "Stale version and projection" : "Stale",
    };
  }
  return {
    title: "The recorded policy index state is unknown",
    detail:
      "The app could not derive whether the index matches the active published version from the recorded build state.",
    tone: "warning",
    statusLabel: "Unknown",
  };
}

/**
 * What to say about a rebuild that has just run.
 *
 * A rebuild can fail, and a failure keeps its error rather than closing quietly:
 * the alternative is a panel that reports success because it was asked to do
 * something, not because the something worked.
 */
export function rebuildResultMessage(result: PolicyIndexBuildResult): {
  type: "success" | "info" | "error";
  message: string;
  description: string;
} {
  if (result.state === "built") {
    const split =
      typeof result.policy_document_count === "number" || typeof result.rule_document_count === "number"
        ? ` — ${result.policy_document_count ?? "—"} policy document${result.policy_document_count === 1 ? "" : "s"} and ${result.rule_document_count ?? "—"} rule document${result.rule_document_count === 1 ? "" : "s"}, a large policy being indexed one document per rule as well as its own`
        : "";
    // A manifest that never reached `ready` is the fact retrieval refuses on,
    // so it is reported on the build that produced it rather than left to be
    // discovered later as a case that will not run.
    const incomplete = result.manifest_state !== undefined && result.manifest_state !== "ready";
    const readiness = incomplete
      ? ` The manifest is ${result.manifest_state ?? "not ready"}, so this build did not finish: project-wide case testing will refuse rather than answer from part of the corpus. Run the rebuild again.`
      : result.manifest_state === "ready"
        ? " The manifest reached ready, so every expected document was acknowledged."
        : "";
    const profile = result.projection_profile
      ? ` Built under the ${result.projection_profile} rendering contract.`
      : incomplete
        ? " No rendering contract was recorded, which is the same fact as the unfinished manifest."
        : "";
    return {
      type: incomplete ? "info" : "success",
      message: incomplete ? "Policy index rebuild did not finish" : "Policy index rebuilt",
      description: `Indexed ${result.document_count} policy document${result.document_count === 1 ? "" : "s"} for v${result.version_number ?? "—"}${split}.${profile}${readiness} The state below has been refreshed from the server.`,
    };
  }
  if (result.state === "skipped") {
    return {
      type: "info",
      message: "Policy index rebuild was skipped",
      description: result.error ?? "Search is not configured on this server, so there is no index to rebuild.",
    };
  }
  return {
    type: "error",
    message: "Policy index rebuild failed",
    description: result.error ?? "The server recorded the failed attempt and the state below has been refreshed.",
  };
}

/**
 * What to say about a validation that has just run.
 *
 * Three things have to survive being turned into a sentence, because each one
 * changes what the operator should do next:
 *
 * 1. **`unavailable` is not a pass.** A validation nobody could perform proves
 *    exactly as much as one that failed, and the readiness gate refuses on
 *    both. Reporting it as a qualified success would be the one sentence that
 *    turns this whole mechanism into a lie.
 * 2. **`recorded` is separate from the verdict.** A `passed` that never reached
 *    the manifest has changed nothing about what the project may answer, so it
 *    is reported as unfinished work rather than as a result.
 * 3. **A failure deleted nothing.** The corpus is still there and simply stops
 *    being matchable, which is a reversible finding and must not read like data
 *    loss.
 */
export function validationResultMessage(result: PolicyIndexValidationResult): {
  type: "success" | "info" | "error";
  message: string;
  description: string;
} {
  if (result.state === "skipped") {
    return {
      type: "info",
      message: "Policy index validation was skipped",
      description:
        result.error ?? "Search or embeddings are not configured on this server, so there was nothing to check.",
    };
  }

  const quality = result.quality ?? null;
  const scores =
    quality && quality.checked_documents > 0
      ? ` ${quality.checked_documents} document${quality.checked_documents === 1 ? "" : "s"} scored, lowest ${quality.minimum_similarity ?? "—"}, mean ${quality.mean_similarity ?? "—"}.`
      : "";
  const profile = quality ? ` Checked under ${quality.profile}.` : "";

  if (result.state === "failed" || quality?.state === "failed") {
    const counts = quality
      ? ` ${quality.structural_findings} structural finding${quality.structural_findings === 1 ? "" : "s"} and ${quality.below_floor} pair${quality.below_floor === 1 ? "" : "s"} below the similarity floor.`
      : "";
    return {
      type: "error",
      message: "Policy index validation failed",
      description:
        (result.error ??
          "The corpus is not a faithful rendering of the record it was built from.") +
        `${counts}${scores}${profile} Nothing was deleted: every document is still in the index and the project will refuse to answer from it until a rebuild or a passing validation. `,
    };
  }

  if (quality?.state === "unavailable") {
    return {
      type: "info",
      message: "Policy index could not be validated",
      description: `The check could not be completed, which is not a pass — the project stays unmatchable until one succeeds.${scores}${profile}`,
    };
  }

  if (!result.recorded) {
    return {
      type: "info",
      message: "Policy index validation was not recorded",
      description: `The corpus passed, but the verdict never reached the manifest the readiness gate reads, so it is not in force.${scores}${profile} Run it again.`,
    };
  }

  return {
    type: "success",
    message: "Policy index validated",
    description: `The corpus is a faithful rendering of the record it was built from, and the verdict is recorded on the manifest.${scores}${profile} The state below has been refreshed from the server.`,
  };
}
