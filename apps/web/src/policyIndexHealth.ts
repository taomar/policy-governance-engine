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

import type { PolicyIndexState, PolicyIndexBuildResult } from "./api";

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
        detail: "Project-wide case testing will not use this index until a rebuild succeeds.",
        tone: "error",
        statusLabel: "Failed and stale",
      };
    }
    return {
      title: "The project-wide case index is stale",
      detail: `The active published version is v${state.active_version_number ?? "—"}, but the recorded index is for v${state.indexed_version_number ?? "—"}.`,
      tone: "warning",
      statusLabel: "Stale",
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
    return {
      type: "success",
      message: "Policy index rebuilt",
      description: `Indexed ${result.document_count} policy document${result.document_count === 1 ? "" : "s"} for v${result.version_number ?? "—"}. The state below has been refreshed from the server.`,
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
