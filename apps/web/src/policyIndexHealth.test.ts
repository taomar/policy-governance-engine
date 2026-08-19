/**
 * The repair is offered exactly where the reader is told to repair.
 *
 * `ai_case_project.py` refuses a project-wide case when the policy index cannot
 * be relied on, and three of those refusals tell the reader to republish or
 * rebuild. The client has to agree about which three, or it prints an
 * instruction beside no control.
 *
 * The Python guard `test_the_index_repair_offer_matches_the_backend` pins this
 * list against those reasons, so the two cannot drift. What is pinned here is
 * the narrower thing that guard cannot see: that the predicate the components
 * actually call reads the list correctly, including for a status the backend
 * never sends.
 */
import { describe, expect, it } from "vitest";
import {
  INDEX_REPAIRABLE_RETRIEVAL_STATUSES,
  retrievalStatusIsIndexRepairable,
} from "./policyIndexHealth";

describe("which retrieval refusals a rebuild repairs", () => {
  it("offers the repair for an index that was never built", () => {
    expect(retrievalStatusIsIndexRepairable("index_not_built")).toBe(true);
  });

  it("offers the repair for an index left on a superseded version", () => {
    expect(retrievalStatusIsIndexRepairable("index_stale")).toBe(true);
  });

  it("offers the repair for an index that exists and holds nothing", () => {
    // The case that was missed. An empty index carries the same instruction as
    // a missing one, and a rebuild is exactly what fixes it.
    expect(retrievalStatusIsIndexRepairable("index_empty")).toBe(true);
  });

  it("does not offer a rebuild when search is not configured", () => {
    // No rebuild repairs a server without Search; offering one would send the
    // reader in a circle.
    expect(retrievalStatusIsIndexRepairable("unavailable")).toBe(false);
  });

  it("does not offer a rebuild when the project has published nothing", () => {
    expect(retrievalStatusIsIndexRepairable("no_published_version")).toBe(false);
  });

  it("does not offer a rebuild when retrieval worked and nothing bore on the question", () => {
    // `no_match` is retrieval succeeding. Offering a repair here would suggest
    // the answer was wrong when it was correct.
    expect(retrievalStatusIsIndexRepairable("no_match")).toBe(false);
    expect(retrievalStatusIsIndexRepairable("narrowed")).toBe(false);
  });

  it("treats a status it has never heard of as not repairable", () => {
    // A newer server can send a status this client predates. Guessing that a
    // rebuild fixes an unknown state would be a claim nothing supports.
    expect(retrievalStatusIsIndexRepairable("some_future_status")).toBe(false);
    expect(retrievalStatusIsIndexRepairable("")).toBe(false);
  });

  it("declares the list it decides from, so the guard can read it", () => {
    expect([...INDEX_REPAIRABLE_RETRIEVAL_STATUSES].sort()).toEqual([
      "index_empty",
      "index_not_built",
      "index_stale",
    ]);
  });
});
